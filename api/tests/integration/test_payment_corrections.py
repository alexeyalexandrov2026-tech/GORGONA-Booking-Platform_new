"""H3 payment corrections: a void or a replacement is a new revision of the same payment."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.business import modules, settlements
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.business.settlement_contracts import PaymentVoidInput
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_credit_notes as credit_shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import seed_user
from tests.integration.test_credit_notes import CreditWorld, _race
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_invoice_issue import approved_check, packaged_function
from tests.integration.test_ledger import LedgerWorld
from tests.integration.test_settlements import SettlementWorld
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = credit_shared.client
idp = credit_shared.idp
manager_a = credit_shared.manager_a
manager_b = credit_shared.manager_b
enabled = credit_shared.enabled
invoices = credit_shared.invoices
payments = credit_shared.payments
credits = credit_shared.credits

_ATTESTED = {
    "attestation": "attested_erroneous_confirmation",
    "entry_date": "2026-10-04",
    "reason": "FAKE the bank never received this transfer",
    "evidence_source": "FAKE bank statement October",
}


@dataclass(frozen=True)
class CorrectionWorld:
    credits: CreditWorld

    @property
    def settlements(self) -> SettlementWorld:
        return self.credits.settlements

    @property
    def payments(self) -> PaymentWorld:
        return self.credits.payments

    @property
    def ledger(self) -> LedgerWorld:
        return self.credits.ledger

    def path(self, settlement: UUID, payment: UUID, action: str) -> str:
        return f"{self.payments.root}/settlements/{settlement}/confirmations/{payment}/{action}"

    async def held(
        self, allocations: list[tuple[UUID, str]], *, direction: str = "receivable"
    ) -> UUID:
        """A FAKE settlement prepared, approved and reserved: its next sequence is 4."""
        settlement, world = uuid7(), self.settlements
        prepared = await world.prepare(settlement, allocations, direction=direction)
        assert prepared.status_code == 200, prepared.text
        for action, sequence in (("approve", 1), ("reserve", 2)):
            assert (await world.act(settlement, action, sequence)).status_code == 200
        return settlement

    async def confirm(
        self,
        settlement: UUID,
        sequence: int,
        allocations: list[tuple[UUID, str]],
        amount: str,
        reference: str,
        **changes: object,
    ) -> UUID:
        payment = uuid7()
        confirmed = await self.payments.confirm(
            settlement, sequence, allocations, amount, reference, payment=payment, changes=changes
        )
        assert confirmed.status_code == 200, confirmed.text
        return payment

    async def confirmed(
        self, allocations: list[tuple[UUID, str]], amount: str, reference: str
    ) -> tuple[UUID, UUID]:
        """Reserve exactly the allocations and confirm `amount` of them at sequence 4."""
        settlement = await self.held(allocations)
        return settlement, await self.confirm(settlement, 3, allocations, amount, reference)

    async def void(
        self,
        settlement: UUID,
        payment: UUID,
        sequence: int,
        *,
        key: str | None = None,
        headers: dict[str, str] | None = None,
        **changes: object,
    ) -> httpx.Response:
        return await self.ledger.client.post(
            self.path(settlement, payment, "void"),
            json={"schema_version": 1, "expected_sequence": sequence, **_ATTESTED, **changes},
            headers=headers or self.ledger.headers(key),
        )

    async def correct(
        self,
        settlement: UUID,
        payment: UUID,
        sequence: int,
        allocations: list[tuple[UUID, str]],
        amount: str,
        *,
        key: str | None = None,
        headers: dict[str, str] | None = None,
        **changes: object,
    ) -> httpx.Response:
        body = {
            "schema_version": 1,
            "expected_sequence": sequence,
            **_ATTESTED,
            "amount": amount,
            "actual_external_date": "2026-10-03",
            "cash_account_id": str(self.payments.cash),
            "allocations": [
                {"obligation_id": str(obligation), "amount": value}
                for obligation, value in allocations
            ],
            **changes,
        }
        return await self.ledger.client.post(
            self.path(settlement, payment, "correct"),
            json=body,
            headers=headers or self.ledger.headers(key),
        )

    async def payment(self, payment: UUID) -> dict[str, Any]:
        response = await self.ledger.client.get(
            f"{self.payments.root}/payments/{payment}", headers=self.ledger.auth
        )
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result

    async def entry(self, entry: object) -> dict[str, Any]:
        response = await self.ledger.client.get(
            f"{self.ledger.base}/entries/{entry}",
            params={"schema_version": 2},
            headers=self.ledger.auth,
        )
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result

    async def balances(self, obligation: UUID) -> tuple[object, ...]:
        balance = await self.settlements.balance(obligation)
        return balance["paid"], balance["credited"], balance["reserved"], balance["available"]

    async def corrections_posted(self, app_pool: RuntimePool) -> int:
        return await self.credits.count(
            app_pool,
            "select count(*) from gba.journal_entries "
            "where book_id=%s and source_kind='payment_correction'",
            self.ledger.book,
        )


@pytest.fixture
def corrections(credits: CreditWorld) -> CorrectionWorld:
    return CorrectionWorld(credits)


def _lines(entry: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(r["account_id"], r["side"], r["amount"]) for r in entry["lines"]]


async def test_correction_routes_require_authentication(client: httpx.AsyncClient) -> None:
    base = f"/v1/businesses/{uuid7()}/financial-documents/books/{uuid7()}/settlements"
    for action in ("void", "correct"):
        path = f"{base}/{uuid7()}/confirmations/{uuid7()}/{action}"
        assert (await client.post(path, json={})).status_code == 401


async def test_void_reverses_the_journal_and_returns_the_allocation_to_the_reserve(
    corrections: CorrectionWorld,
    app_pool: RuntimePool,
) -> None:
    obligation = await corrections.settlements.obligation()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-VOID-1"
    )
    key = str(uuid7())
    voided = await corrections.void(settlement, payment, 4, key=key)
    assert voided.status_code == 200, voided.text
    view = voided.json()
    assert (view["status"], view["sequence"], view["confirmed"], view["reserved"]) == (
        "reserved",
        5,
        "0.00",
        "70.00",
    )
    assert (view["events"][-1]["kind"], view["events"][-1]["payment_id"]) == (
        "payment_voided",
        str(payment),
    )
    assert view["allocations"][0]["confirmed"] == "0.00"
    assert (await corrections.void(settlement, payment, 4, key=key)).json() == view
    assert await corrections.balances(obligation) == ("0.00", "0.00", "70.00", "30.00")
    recorded = await corrections.payment(payment)
    assert (recorded["state"], recorded["revision"], recorded["effective_amount"]) == (
        "voided",
        2,
        "0.00",
    )
    assert recorded["effective_allocations"] == []
    # The original attestation and its identity are kept exactly as recorded.
    assert (recorded["amount"], recorded["external_reference"]) == ("70.00", "FAKE-VOID-1")
    (revision,) = recorded["revisions"]
    assert (revision["kind"], revision["sequence"], revision["amount"]) == ("voided", 5, None)
    assert (revision["entry_id"], revision["cash_account_id"]) == (None, None)
    assert revision["attestation"] == "attested_erroneous_confirmation"
    assert revision["reason"] == _ATTESTED["reason"]
    entry = await corrections.entry(revision["reversal_entry_id"])
    assert (entry["source_kind"], entry["source_id"], entry["entry_date"]) == (
        "payment_correction",
        f"{payment}:2:reversal",
        "2026-10-04",
    )
    control = str(corrections.settlements.invoices.control)
    assert _lines(entry) == [
        (str(corrections.payments.cash), "credit", "70.00"),
        (control, "debit", "70.00"),
    ]
    closing = await corrections.credits.closing()
    assert closing["1100"] == ("0.00", "0.00")
    assert closing["1200"] == ("100.00", "0.00")
    # A void is final, and the identity it carried is never free again.
    final = await corrections.void(settlement, payment, 5)
    assert final.status_code == 409, final.text
    assert final.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    again = await corrections.payments.confirm(
        settlement, 5, [(obligation, "70.00")], "70.00", "fake-void-1"
    )
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "FINANCIAL_SOURCE_ALREADY_RECORDED"
    assert again.json()["error"]["details"]["payment_id"] == str(payment)
    # The restored reserve takes the real payment under its own identity.
    await corrections.confirm(settlement, 5, [(obligation, "70.00")], "70.00", "FAKE-VOID-2")
    assert (await corrections.settlements.view(settlement))["status"] == "confirmed"
    assert await corrections.balances(obligation) == ("70.00", "0.00", "0.00", "30.00")
    # A replay still answers with the settlement as the void left it.
    assert (await corrections.void(settlement, payment, 4, key=key)).json() == view
    # G never reverses an H correction journal.
    refused = await corrections.ledger.client.post(
        f"{corrections.ledger.base}/entries/{revision['reversal_entry_id']}/reverse",
        json={"schema_version": 1, "reversal_entry_id": str(uuid7()), "entry_date": "2026-10-05"},
        headers=corrections.ledger.headers(),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "LEDGER_STATE_INVALID"
    legacy = await corrections.ledger.client.get(
        f"{corrections.ledger.base}/entries/{revision['reversal_entry_id']}",
        headers=corrections.ledger.auth,
    )
    assert legacy.json()["error"]["code"] == "JOURNAL_VERSION_REQUIRED"
    assert await corrections.corrections_posted(app_pool) == 1


async def test_correction_replaces_the_attestation_within_the_restored_reserve(
    corrections: CorrectionWorld,
) -> None:
    world = corrections.settlements
    first, second = await world.obligation(), await world.obligation("50.00")
    settlement = await corrections.held([(first, "60.00"), (second, "40.00")])
    payment = await corrections.confirm(settlement, 3, [(first, "60.00")], "60.00", "FAKE-FIX-1")
    # The replaced allocation returns to its line, and no line gives more than it holds.
    for allocations, amount in (
        ([(first, "61.00")], "61.00"),
        ([(first, "20.00"), (second, "41.00")], "61.00"),
    ):
        over = await corrections.correct(settlement, payment, 4, allocations, amount)
        assert over.status_code == 409, over.text
        assert over.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    cash = corrections.credits.chart["1000"]
    corrected = await corrections.correct(
        settlement,
        payment,
        4,
        [(first, "45.00"), (second, "30.00")],
        "75.00",
        cash_account_id=str(cash),
    )
    assert corrected.status_code == 200, corrected.text
    view = corrected.json()
    assert (view["status"], view["sequence"], view["confirmed"], view["reserved"]) == (
        "partially_confirmed",
        5,
        "75.00",
        "25.00",
    )
    assert (view["events"][-1]["kind"], view["events"][-1]["payment_id"]) == (
        "payment_corrected",
        str(payment),
    )
    assert await corrections.balances(first) == ("45.00", "0.00", "15.00", "40.00")
    assert await corrections.balances(second) == ("30.00", "0.00", "10.00", "10.00")
    recorded = await corrections.payment(payment)
    assert (recorded["state"], recorded["revision"], recorded["effective_amount"]) == (
        "corrected",
        2,
        "75.00",
    )
    assert recorded["effective_allocations"] == [
        {"obligation_id": str(first), "amount": "45.00"},
        {"obligation_id": str(second), "amount": "30.00"},
    ]
    # The external identity never changes with a correction.
    assert (recorded["source_account_alias"], recorded["external_reference"]) == (
        "FAKE main bank account",
        "FAKE-FIX-1",
    )
    (revision,) = recorded["revisions"]
    assert (revision["amount"], revision["actual_external_date"]) == ("75.00", "2026-10-03")
    assert revision["cash_account_id"] == str(cash)
    control, bank = str(world.invoices.control), str(corrections.payments.cash)
    reversal = await corrections.entry(revision["reversal_entry_id"])
    assert _lines(reversal) == [(bank, "credit", "60.00"), (control, "debit", "60.00")]
    replacement = await corrections.entry(revision["entry_id"])
    assert (replacement["source_kind"], replacement["source_id"]) == (
        "payment_correction",
        f"{payment}:2:replacement",
    )
    assert _lines(replacement) == [
        (str(cash), "debit", "75.00"),
        (control, "credit", "45.00"),
        (control, "credit", "30.00"),
    ]
    closing = await corrections.credits.closing()
    assert closing["1000"] == ("75.00", "0.00")
    assert closing["1100"] == ("0.00", "0.00")
    assert closing["1200"] == ("75.00", "0.00")
    # A second correction reverses the replacement, not the original.
    again = await corrections.correct(settlement, payment, 5, [(first, "60.00")], "60.00")
    assert again.status_code == 200, again.text
    latest = (await corrections.payment(payment))["revisions"][-1]
    assert latest["revision"] == 3
    undone = await corrections.entry(latest["reversal_entry_id"])
    assert _lines(undone) == [
        (str(cash), "credit", "75.00"),
        (control, "debit", "45.00"),
        (control, "debit", "30.00"),
    ]
    assert await corrections.balances(first) == ("60.00", "0.00", "0.00", "40.00")
    assert await corrections.balances(second) == ("0.00", "0.00", "40.00", "10.00")
    closing = await corrections.credits.closing()
    assert closing["1000"] == ("0.00", "0.00")
    assert closing["1100"] == ("60.00", "0.00")


async def test_a_later_credit_splits_against_the_corrected_payment(
    corrections: CorrectionWorld,
) -> None:
    credits = corrections.credits
    obligation, (line,) = await credits.invoice()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-LATER-1"
    )
    corrected = await corrections.correct(settlement, payment, 4, [(obligation, "50.00")], "50.00")
    assert corrected.status_code == 200, corrected.text
    released = await corrections.settlements.act(settlement, "release", 5)
    assert released.status_code == 200, released.text
    # 100 accrued, 50 effectively paid: a credit of 50 is unpaid credit, no refund.
    view = await credits.credit(obligation, [(line, "50.00")])
    assert (view["applied"], view["refund"], view["refund_obligation_id"]) == (
        "50.00",
        "0.00",
        None,
    )
    assert await corrections.balances(obligation) == ("50.00", "50.00", "0.00", "0.00")


async def test_void_of_a_released_settlement_lowers_paid_only(
    corrections: CorrectionWorld,
) -> None:
    obligation = await corrections.settlements.obligation()
    settlement = await corrections.held([(obligation, "70.00")])
    voided_payment = await corrections.confirm(
        settlement, 3, [(obligation, "20.00")], "20.00", "FAKE-REL-1"
    )
    kept = await corrections.confirm(settlement, 4, [(obligation, "20.00")], "20.00", "FAKE-REL-2")
    released = await corrections.settlements.act(settlement, "release", 5)
    assert released.status_code == 200, released.text
    assert await corrections.balances(obligation) == ("40.00", "0.00", "0.00", "60.00")
    voided = await corrections.void(settlement, voided_payment, 6)
    assert voided.status_code == 200, voided.text
    assert (voided.json()["status"], voided.json()["reserved"]) == ("released", "0.00")
    # A released reserve is gone: the void restores no reserve, only lowers P.
    assert await corrections.balances(obligation) == ("20.00", "0.00", "0.00", "80.00")
    refused = await corrections.correct(settlement, kept, 7, [(obligation, "20.00")], "20.00")
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"


async def test_credit_or_refund_dependency_requires_reconciliation_without_effects(
    corrections: CorrectionWorld,
    app_pool: RuntimePool,
) -> None:
    credits = corrections.credits
    obligation, (line,) = await credits.invoice()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-DEP-1"
    )
    view = await credits.credit(obligation, [(line, "50.00")], refund=credits.chart["2100"])
    for attempt in (
        corrections.void(settlement, payment, 4),
        corrections.correct(settlement, payment, 4, [(obligation, "60.00")], "60.00"),
    ):
        refused = await attempt
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "FINANCIAL_RECONCILIATION_REQUIRED"
        assert refused.json()["error"]["details"]["obligation_id"] == str(obligation)
    assert await corrections.balances(obligation) == ("70.00", "30.00", "0.00", "0.00")
    # A real refund is never undone to make a correction possible.
    refund = UUID(str(view["refund_obligation_id"]))
    refund_settlement = await corrections.held([(refund, "20.00")], direction="payable")
    refund_payment = await corrections.confirm(
        refund_settlement,
        3,
        [(refund, "20.00")],
        "20.00",
        "FAKE-DEP-REFUND",
        entry_date="2026-10-04",
        actual_external_date="2026-10-04",
    )
    refused = await corrections.void(refund_settlement, refund_payment, 4)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "FINANCIAL_RECONCILIATION_REQUIRED"
    assert (await corrections.settlements.balance(refund))["paid"] == "20.00"
    assert await corrections.corrections_posted(app_pool) == 0


async def test_unknown_sent_outcomes_block_corrections_until_resolved(
    corrections: CorrectionWorld,
) -> None:
    world = corrections.settlements
    # Its own sent remainder is still unknown.
    obligation = await world.obligation()
    settlement = await corrections.held([(obligation, "70.00")])
    assert (await world.act(settlement, "sent", 3)).status_code == 200
    partial = await corrections.confirm(settlement, 4, [(obligation, "30.00")], "30.00", "FAKE-S-1")
    pending = await corrections.void(settlement, partial, 5)
    assert pending.status_code == 409, pending.text
    assert pending.json()["error"]["code"] == "FINANCIAL_OUTCOME_UNRESOLVED"
    await corrections.confirm(settlement, 5, [(obligation, "40.00")], "40.00", "FAKE-S-2")
    # Fully confirmed, the outcome is known; the void reopens it until attested.
    voided = await corrections.void(settlement, partial, 6)
    assert voided.status_code == 200, voided.text
    assert (voided.json()["status"], voided.json()["outcome_unresolved"]) == (
        "partially_confirmed",
        True,
    )
    plain = await world.act(settlement, "release", 7)
    assert plain.status_code == 409, plain.text
    attested = await world.act(
        settlement,
        "release",
        7,
        resolution="attested_no_payment",
        reason="FAKE only 40 arrived",
        evidence_source="FAKE bank statement",
    )
    assert attested.status_code == 200, attested.text
    assert await corrections.balances(obligation) == ("40.00", "0.00", "0.00", "60.00")
    # Another settlement of the same obligation with an unknown outcome.
    other = await world.obligation()
    paid, payment = await corrections.confirmed([(other, "50.00")], "50.00", "FAKE-S-3")
    sent = await corrections.held([(other, "50.00")])
    assert (await world.act(sent, "sent", 3)).status_code == 200
    blocked = await corrections.void(paid, payment, 4)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "FINANCIAL_RECONCILIATION_REQUIRED"
    assert blocked.json()["error"]["details"]["settlement_id"] == str(sent)
    resolved = await world.act(
        sent,
        "release",
        4,
        resolution="attested_no_payment",
        reason="FAKE the transfer was rejected",
        evidence_source="FAKE bank notice",
    )
    assert resolved.status_code == 200, resolved.text
    assert (await corrections.void(paid, payment, 4)).status_code == 200


async def test_correction_dates_amounts_accounts_and_closed_month(
    corrections: CorrectionWorld,
    app_pool: RuntimePool,
) -> None:
    world = corrections.settlements
    obligation, outsider = await world.obligation(), await world.obligation()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-DATE-1"
    )
    early = await corrections.void(settlement, payment, 4, entry_date="2026-10-01")
    assert early.status_code == 422, early.text
    assert early.json()["error"]["code"] == "LEDGER_DATE_INVALID"
    allocations = [(obligation, "70.00")]
    future = await corrections.correct(
        settlement, payment, 4, allocations, "70.00", actual_external_date="2099-01-01"
    )
    assert future.status_code == 422, future.text
    assert future.json()["error"]["code"] == "LEDGER_DATE_INVALID"
    control = await corrections.correct(
        settlement, payment, 4, allocations, "70.00", cash_account_id=str(world.invoices.control)
    )
    assert control.status_code == 409, control.text
    assert control.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    stranger = await corrections.correct(settlement, payment, 4, [(outsider, "70.00")], "70.00")
    assert stranger.status_code == 409, stranger.text
    assert stranger.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    mismatch = await corrections.correct(settlement, payment, 4, allocations, "69.00")
    assert mismatch.status_code == 422, mismatch.text
    assert mismatch.json()["error"]["code"] == "FINANCIAL_AMOUNT_INVALID"
    stale = await corrections.void(settlement, payment, 3)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["details"]["sequence"] == 4
    missing = await corrections.void(settlement, uuid7(), 4)
    assert missing.status_code == 404, missing.text
    closed = await corrections.ledger.client.post(
        f"{corrections.ledger.base}/periods/2026-10/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=corrections.ledger.headers(),
    )
    assert closed.status_code == 200, closed.text
    denied = await corrections.void(settlement, payment, 4)
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "LEDGER_PERIOD_CLOSED"
    assert (await corrections.payment(payment))["state"] == "confirmed"
    assert await corrections.balances(obligation) == ("70.00", "0.00", "0.00", "30.00")
    assert await corrections.corrections_posted(app_pool) == 0


@pytest.mark.parametrize("void_first", [True, False])
async def test_void_and_credit_wait_on_one_lock(
    corrections: CorrectionWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    void_first: bool,
) -> None:
    credits = corrections.credits
    obligation, (line,) = await credits.invoice()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-RACE-1"
    )
    document = await credits.drafted(obligation, [(line, "20.00")])
    calls: list[Callable[[], Coroutine[Any, Any, httpx.Response]]] = [
        lambda: corrections.void(settlement, payment, 4),
        lambda: credits.issue(document),
    ]
    first, second = await _race(credits, app_pool, owner_conn, calls if void_first else calls[::-1])
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    if void_first:
        # The void restored an active reserve, which a credit must not ignore.
        assert second.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
        assert await corrections.balances(obligation) == ("0.00", "0.00", "70.00", "30.00")
    else:
        assert second.json()["error"]["code"] == "FINANCIAL_RECONCILIATION_REQUIRED"
        assert await corrections.balances(obligation) == ("70.00", "20.00", "0.00", "10.00")


async def test_competing_corrections_of_one_payment_commit_once(
    corrections: CorrectionWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    obligation = await corrections.settlements.obligation()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-RACE-2"
    )
    results = await _race(
        corrections.credits,
        app_pool,
        owner_conn,
        [
            lambda: corrections.correct(settlement, payment, 4, [(obligation, "65.00")], "65.00"),
            lambda: corrections.void(settlement, payment, 4),
        ],
    )
    assert [r.status_code for r in results] == [200, 409]
    recorded = await corrections.payment(payment)
    assert (recorded["state"], recorded["revision"]) == ("corrected", 2)
    assert await corrections.balances(obligation) == ("65.00", "0.00", "5.00", "30.00")
    assert await corrections.corrections_posted(app_pool) == 2


async def _void_in_transaction(
    corrections: CorrectionWorld, conn: RuntimeConnection, settlement: UUID, payment: UUID
) -> UUID:
    await settlements.void_payment(
        conn,
        business_id=corrections.ledger.business,
        book_id=corrections.ledger.book,
        settlement_id=settlement,
        payment_id=payment,
        user_id=corrections.ledger.user.user_id,
        actor=f"user:{corrections.ledger.user.user_id}",
        key=str(uuid7()),
        body=PaymentVoidInput(
            expected_sequence=4,
            attestation="attested_erroneous_confirmation",
            entry_date=date(2026, 10, 4),
            reason="FAKE service void",
            evidence_source="FAKE statement",
        ),
    )
    row = await (
        await conn.execute(
            "select reversal_entry_id from gba.external_payment_revisions where payment_id=%s",
            (payment,),
        )
    ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


async def _void_directly(
    corrections: CorrectionWorld,
    conn: RuntimeConnection,
    settlement: UUID,
    sequence: int,
    payment: UUID,
    revision: int,
    *,
    replaced: UUID,
    shrink: int = 0,
) -> None:
    """A complete void written by SQL alone, in the order the service uses."""
    business, book = corrections.ledger.business, corrections.ledger.book
    user, reversal = corrections.ledger.user.user_id, uuid7()
    await conn.execute(
        "insert into gba.settlement_events "
        "(tenant_id,book_id,settlement_id,sequence,kind,created_by) "
        "values (%s,%s,%s,%s,'payment_voided',%s)",
        (business, book, settlement, sequence, user),
    )
    await conn.execute(
        "insert into gba.external_payment_revisions (tenant_id,book_id,payment_id,revision,"
        "settlement_id,sequence,kind,entry_date,attestation,reason,evidence_source,"
        "reversal_entry_id,created_by) values (%s,%s,%s,%s,%s,%s,'voided','2026-10-04',"
        "'attested_erroneous_confirmation','FAKE SQL void','FAKE SQL evidence',%s,%s)",
        (business, book, payment, revision, settlement, sequence, reversal, user),
    )
    await conn.execute(
        "insert into gba.journal_entries "
        "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
        "values (%s,%s,%s,'2026-10-04','USD','payment_correction',%s,%s)",
        (business, reversal, book, f"{payment}:{revision}:reversal", user),
    )
    await conn.execute(
        "insert into gba.journal_lines "
        "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
        "select tenant_id,%s,line_no,book_id,account_id,"
        "case side when 'debit' then 'credit' else 'debit' end,amount_minor-%s "
        "from gba.journal_lines where tenant_id=%s and entry_id=%s",
        (reversal, shrink, business, replaced),
    )
    await conn.execute("set constraints all immediate")


async def _payment_entry(app_pool: RuntimePool, business: UUID, payment: UUID) -> UUID:
    async with tenant_transaction(app_pool, business) as conn:
        row = await (
            await conn.execute("select entry_id from gba.external_payments where id=%s", (payment,))
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


async def test_sql_rechecks_a_void_and_its_mirrored_journal(
    corrections: CorrectionWorld,
    app_pool: RuntimePool,
) -> None:
    business, book = corrections.ledger.business, corrections.ledger.book
    obligation = await corrections.settlements.obligation()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-SQL-1"
    )
    cash = corrections.payments.cash
    # A complete service void, then a balanced extra pair on its reversal.
    with pytest.raises(psycopg.errors.CheckViolation, match="mirror"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            reversal = await _void_in_transaction(corrections, conn, settlement, payment)
            await conn.execute(
                "insert into gba.journal_lines "
                "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) values "
                "(%s,%s,3,%s,%s,'debit',1),(%s,%s,4,%s,%s,'credit',1)",
                (business, reversal, book, cash, business, reversal, book, cash),
            )
            await conn.execute("set constraints all immediate")
    replaced = await _payment_entry(app_pool, business, payment)
    # A reversal of 69 of a journal of 70 mirrors nothing.
    with pytest.raises(psycopg.errors.CheckViolation, match="mirror"):
        async with tenant_transaction(app_pool, business) as conn:
            await _void_directly(
                corrections, conn, settlement, 5, payment, 2, replaced=replaced, shrink=100
            )
    # A voided or corrected fact needs its revision.
    with pytest.raises(psycopg.errors.CheckViolation, match="needs its payment revision"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.settlement_events "
                "(tenant_id,book_id,settlement_id,sequence,kind,created_by) "
                "values (%s,%s,%s,5,'payment_voided',%s)",
                (business, book, settlement, corrections.ledger.user.user_id),
            )
            await conn.execute("set constraints all immediate")
    # SQL alone records a complete void, and nothing may follow it.
    async with tenant_transaction(app_pool, business) as conn:
        await _void_directly(corrections, conn, settlement, 5, payment, 2, replaced=replaced)
    assert await corrections.balances(obligation) == ("0.00", "0.00", "70.00", "30.00")
    with pytest.raises(psycopg.errors.CheckViolation, match="voided payment is final"):
        async with tenant_transaction(app_pool, business) as conn:
            await _void_directly(corrections, conn, settlement, 6, payment, 3, replaced=replaced)


async def test_sql_alone_cannot_void_a_payment_an_issued_credit_depends_on(
    corrections: CorrectionWorld,
    app_pool: RuntimePool,
) -> None:
    business = corrections.ledger.business
    credits = corrections.credits
    obligation, (line,) = await credits.invoice()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-SQL-2"
    )
    await credits.credit(obligation, [(line, "10.00")])
    replaced = await _payment_entry(app_pool, business, payment)
    with pytest.raises(psycopg.errors.CheckViolation, match="issued credit depends"):
        async with tenant_transaction(app_pool, business) as conn:
            await _void_directly(corrections, conn, settlement, 5, payment, 2, replaced=replaced)
    # A sent settlement whose outcome is unknown waits, whoever writes.
    other = await corrections.settlements.obligation()
    sent = await corrections.held([(other, "70.00")])
    assert (await corrections.settlements.act(sent, "sent", 3)).status_code == 200
    partial = await corrections.confirm(sent, 4, [(other, "30.00")], "30.00", "FAKE-SQL-3")
    partial_entry = await _payment_entry(app_pool, business, partial)
    with pytest.raises(psycopg.errors.CheckViolation, match="resolve the sent outcome"):
        async with tenant_transaction(app_pool, business) as conn:
            await _void_directly(corrections, conn, sent, 6, partial, 2, replaced=partial_entry)
    assert await corrections.balances(obligation) == ("70.00", "10.00", "0.00", "20.00")
    assert (await corrections.payment(partial))["state"] == "confirmed"


async def _correct_directly(
    corrections: CorrectionWorld,
    conn: RuntimeConnection,
    settlement: UUID,
    payment: UUID,
    obligation: UUID,
    *,
    replaced: UUID,
    amount: int,
    allocated: int,
    posted: int,
    entry_date: str = "2026-10-04",
) -> None:
    """A complete correction at sequence 5, revision 2, written by SQL alone."""
    business, book = corrections.ledger.business, corrections.ledger.book
    user, reversal, entry = corrections.ledger.user.user_id, uuid7(), uuid7()
    cash, control = corrections.payments.cash, corrections.settlements.invoices.control
    await conn.execute(
        "insert into gba.settlement_events "
        "(tenant_id,book_id,settlement_id,sequence,kind,created_by) "
        "values (%s,%s,%s,5,'payment_corrected',%s)",
        (business, book, settlement, user),
    )
    await conn.execute(
        "insert into gba.external_payment_revisions (tenant_id,book_id,payment_id,revision,"
        "settlement_id,sequence,kind,amount_minor,actual_external_date,cash_account_id,"
        "entry_date,attestation,reason,evidence_source,reversal_entry_id,entry_id,created_by) "
        "values (%s,%s,%s,2,%s,5,'corrected',%s,'2026-10-03',%s,%s,"
        "'attested_erroneous_confirmation','FAKE SQL fix','FAKE SQL evidence',%s,%s,%s)",
        (business, book, payment, settlement, amount, cash, entry_date, reversal, entry, user),
    )
    await conn.execute(
        "insert into gba.external_payment_revision_allocations "
        "(tenant_id,book_id,payment_id,revision,line_no,obligation_id,amount_minor) "
        "values (%s,%s,%s,2,1,%s,%s)",
        (business, book, payment, obligation, allocated),
    )
    for journal, component in ((reversal, "reversal"), (entry, "replacement")):
        await conn.execute(
            "insert into gba.journal_entries "
            "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
            "values (%s,%s,%s,%s,'USD','payment_correction',%s,%s)",
            (business, journal, book, entry_date, f"{payment}:2:{component}", user),
        )
    await conn.execute(
        "insert into gba.journal_lines "
        "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
        "select tenant_id,%s,line_no,book_id,account_id,"
        "case side when 'debit' then 'credit' else 'debit' end,amount_minor "
        "from gba.journal_lines where tenant_id=%s and entry_id=%s",
        (reversal, business, replaced),
    )
    await conn.execute(
        "insert into gba.journal_lines "
        "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) values "
        "(%s,%s,1,%s,%s,'debit',%s),(%s,%s,2,%s,%s,'credit',%s)",
        (business, entry, book, cash, posted, business, entry, book, control, posted),
    )
    await conn.execute("set constraints all immediate")


async def test_sql_rechecks_a_correction_and_its_replacement_journal(
    corrections: CorrectionWorld,
    app_pool: RuntimePool,
) -> None:
    business = corrections.ledger.business
    obligation = await corrections.settlements.obligation()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-SQL-FIX"
    )
    replaced = await _payment_entry(app_pool, business, payment)
    cases = (
        ("must equal the corrected amount", {"amount": 7000, "allocated": 6000, "posted": 7000}),
        ("journal must match", {"amount": 6000, "allocated": 6000, "posted": 5000}),
        (
            "before the version it replaces",
            {"amount": 6000, "allocated": 6000, "posted": 6000, "entry_date": "2026-10-01"},
        ),
        (
            "exceeds the reserved settlement line",
            {"amount": 7100, "allocated": 7100, "posted": 7100},
        ),
    )
    for message, values in cases:
        with pytest.raises(psycopg.errors.CheckViolation, match=message):
            async with tenant_transaction(app_pool, business) as conn:
                await _correct_directly(
                    corrections,
                    conn,
                    settlement,
                    payment,
                    obligation,
                    replaced=replaced,
                    **values,
                )
    assert await corrections.balances(obligation) == ("70.00", "0.00", "0.00", "30.00")
    async with tenant_transaction(app_pool, business) as conn:
        await _correct_directly(
            corrections,
            conn,
            settlement,
            payment,
            obligation,
            replaced=replaced,
            amount=6000,
            allocated=6000,
            posted=6000,
        )
    assert await corrections.balances(obligation) == ("60.00", "0.00", "10.00", "30.00")


async def test_sql_alone_cannot_void_a_refund_payment_or_one_a_sent_outcome_holds(
    corrections: CorrectionWorld,
    app_pool: RuntimePool,
) -> None:
    business, credits = corrections.ledger.business, corrections.credits
    obligation, (line,) = await credits.invoice()
    await corrections.confirmed([(obligation, "70.00")], "70.00", "FAKE-SQL-R1")
    view = await credits.credit(obligation, [(line, "50.00")], refund=credits.chart["2100"])
    refund = UUID(str(view["refund_obligation_id"]))
    refunded = await corrections.held([(refund, "20.00")], direction="payable")
    refund_payment = await corrections.confirm(
        refunded,
        3,
        [(refund, "20.00")],
        "20.00",
        "FAKE-SQL-R2",
        entry_date="2026-10-04",
        actual_external_date="2026-10-04",
    )
    replaced = await _payment_entry(app_pool, business, refund_payment)
    with pytest.raises(psycopg.errors.CheckViolation, match="refund payment"):
        async with tenant_transaction(app_pool, business) as conn:
            await _void_directly(
                corrections, conn, refunded, 5, refund_payment, 2, replaced=replaced
            )
    other = await corrections.settlements.obligation()
    paid, payment = await corrections.confirmed([(other, "50.00")], "50.00", "FAKE-SQL-R3")
    sent = await corrections.held([(other, "50.00")])
    assert (await corrections.settlements.act(sent, "sent", 3)).status_code == 200
    replaced = await _payment_entry(app_pool, business, payment)
    with pytest.raises(psycopg.errors.CheckViolation, match="sent outcome depends"):
        async with tenant_transaction(app_pool, business) as conn:
            await _void_directly(corrections, conn, paid, 5, payment, 2, replaced=replaced)
    assert (await corrections.settlements.balance(refund))["paid"] == "20.00"
    assert (await corrections.settlements.balance(other))["paid"] == "50.00"


async def test_correction_history_stays_unchanged(
    corrections: CorrectionWorld,
    owner_conn: psycopg.Connection,
) -> None:
    obligation = await corrections.settlements.obligation()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-HIST-1"
    )
    corrected = await corrections.correct(settlement, payment, 4, [(obligation, "60.00")], "60.00")
    assert corrected.status_code == 200, corrected.text
    business = corrections.ledger.business
    changes = {
        "external_payment_revisions": "reason='FAKE rewritten'",
        "external_payment_revision_allocations": "amount_minor=7000",
    }
    for table, change in changes.items():
        for statement in (
            "update gba.{} set " + change + " where payment_id=%s",
            "delete from gba.{} where payment_id=%s",
        ):
            with (
                pytest.raises(psycopg.errors.CheckViolation, match="kept unchanged"),
                owner_tenant_transaction(owner_conn, business),
            ):
                owner_conn.execute(
                    sql.SQL(statement).format(sql.Identifier(table)),
                    (payment,),
                )
    assert await corrections.balances(obligation) == ("60.00", "0.00", "10.00", "30.00")


async def test_off_and_withdrawn_readiness_block_corrections_but_keep_history(
    corrections: CorrectionWorld,
    idp: FakeIdp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    obligation = await corrections.settlements.obligation()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-OFF-1"
    )
    feature = modules.MODULES_BY_ID["finance_documents"]
    with monkeypatch.context() as patch:
        patch.setitem(
            modules.MODULES_BY_ID,
            "finance_documents",
            feature.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
        )
        unready = await corrections.void(settlement, payment, 4)
        assert unready.status_code == 409
        assert unready.json()["error"]["code"] == "MODULE_NOT_READY"
    config = Config(corrections.ledger.client, idp)
    await config.publish(
        corrections.ledger.user, corrections.ledger.business, 2, ["booking_resources"]
    )
    for attempt in (
        corrections.void(settlement, payment, 4),
        corrections.correct(settlement, payment, 4, [(obligation, "60.00")], "60.00"),
    ):
        off = await attempt
        assert off.status_code == 409, off.text
        assert off.json()["error"]["code"] == "MODULE_DISABLED"
    assert (await corrections.payment(payment))["state"] == "confirmed"
    assert await corrections.balances(obligation) == ("70.00", "0.00", "0.00", "30.00")


async def test_correction_replay_recovery_and_cancel_before_late_original(
    corrections: CorrectionWorld,
    owner_conn: psycopg.Connection,
) -> None:
    obligation = await corrections.settlements.obligation()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-REC-1"
    )
    key = str(uuid7())
    corrected = await corrections.correct(
        settlement, payment, 4, [(obligation, "60.00")], "60.00", key=key
    )
    assert corrected.status_code == 200, corrected.text
    business = corrections.ledger.business
    with owner_tenant_transaction(owner_conn, business):
        deleted = owner_conn.execute(
            "delete from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.settlement_payment_correct' and idempotency_key=%s",
            (business, key),
        )
        assert deleted.rowcount == 1
    command = f"/v1/businesses/{business}/financial-documents/commands"
    reference = {
        "schema_version": 1,
        "operation": "settlement_payment_correct",
        "book_id": str(corrections.ledger.book),
        "subject_id": str(settlement),
        "revision": 5,
    }
    http, auth = corrections.ledger.client, corrections.ledger.auth
    resolved = await http.post(f"{command}/{key}/resolve", json=reference, headers=auth)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "committed"
    replayed = await corrections.correct(
        settlement, payment, 4, [(obligation, "60.00")], "60.00", key=key
    )
    assert replayed.json() == corrected.json()
    late_key = str(uuid7())
    cancelled = await http.post(
        f"{command}/{late_key}/cancel",
        json={**reference, "operation": "settlement_payment_void", "revision": 6},
        headers=auth,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    sealed = await corrections.void(settlement, payment, 5, key=late_key)
    assert sealed.status_code == 409
    assert sealed.json()["error"]["code"] == "FINANCIAL_COMMAND_CANCELLED"
    assert (await corrections.payment(payment))["state"] == "corrected"


@pytest.mark.parametrize(
    ("role", "branch"),
    [("front_desk", False), ("artist", False), ("manager", True)],
)
async def test_correction_routes_keep_company_finance_permissions(
    corrections: CorrectionWorld,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    manager_b: object,
    role: str,
    branch: bool,
) -> None:
    obligation = await corrections.settlements.obligation()
    settlement, payment = await corrections.confirmed(
        [(obligation, "70.00")], "70.00", "FAKE-PERM-1"
    )
    member = seed_user(owner_conn, f"FAKE-H3-correction-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=corrections.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    foreign = Config(corrections.ledger.client, idp).auth(manager_b)  # type: ignore[arg-type]
    for auth in (idp.bearer(member.subject, email=member.email), foreign):
        keyed = {**auth, "Idempotency-Key": str(uuid7())}
        assert (await corrections.void(settlement, payment, 4, headers=keyed)).status_code == 403
        corrected = await corrections.correct(
            settlement, payment, 4, [(obligation, "60.00")], "60.00", headers=keyed
        )
        assert corrected.status_code == 403
    assert (await corrections.payment(payment))["state"] == "confirmed"


_KIND_REFS = ("external_payment_revisions", "external_payment_revisions_kind_refs")


@pytest.mark.parametrize(
    ("change", "restore"),
    [
        (
            "alter table gba.external_payment_revisions "
            "drop constraint external_payment_revisions_kind_refs",
            approved_check(*_KIND_REFS),
        ),
        (
            "create or replace function gba.effective_payment_allocations(tenant uuid, book uuid, "
            "obligation uuid, settlement uuid) returns table (payment_id uuid, settlement_id uuid, "
            "obligation_id uuid, amount_minor bigint) language plpgsql as $$ begin "
            "return query select null::uuid, null::uuid, null::uuid, 0::bigint where false; "
            "end; $$",
            packaged_function("effective_payment_allocations"),
        ),
        (
            "drop trigger external_payment_revisions_check on gba.external_payment_revisions",
            "create trigger external_payment_revisions_check before insert on "
            "gba.external_payment_revisions for each row execute function "
            "gba.enforce_external_payment_revision()",
        ),
        (
            "grant update on gba.external_payment_revisions to gba_runtime",
            "revoke update on gba.external_payment_revisions from gba_runtime",
        ),
        (
            "create or replace function gba.cash_account_used(tenant uuid, book uuid, "
            "account uuid) returns boolean language plpgsql as $$ begin return false; end; $$",
            packaged_function("cash_account_used"),
        ),
    ],
)
async def test_damaged_correction_controls_fail_readiness_with_503(
    corrections: CorrectionWorld,
    owner_conn: psycopg.Connection,
    change: str,
    restore: str,
) -> None:
    http, auth, base = corrections.ledger.client, corrections.ledger.auth, corrections.ledger.base
    owner_conn.execute(change)
    try:
        result = await http.get(base, headers=auth)
        assert result.status_code == 503, result.text
        assert result.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert (await http.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(restore)
    assert (await http.get(base, headers=auth)).status_code == 200
    assert (await http.get("/health/ready")).status_code == 200
