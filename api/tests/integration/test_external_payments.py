"""H2 externally attested confirmations: exact R to P, one journal, one external identity."""

import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.business import ledger, modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_invoice_issue as invoice_shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import seed_user
from tests.integration.test_invoice_issue import (
    InvoiceWorld,
    approved_check,
    packaged_function,
)
from tests.integration.test_ledger import LedgerWorld
from tests.integration.test_settlements import SettlementWorld, _wait_for_blocked
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = invoice_shared.client
idp = invoice_shared.idp
manager_a = invoice_shared.manager_a
manager_b = invoice_shared.manager_b
enabled = invoice_shared.enabled
invoices = invoice_shared.invoices


@dataclass(frozen=True)
class PaymentWorld:
    settlements: SettlementWorld
    cash: UUID

    @property
    def ledger(self) -> LedgerWorld:
        return self.settlements.ledger

    @property
    def root(self) -> str:
        return self.settlements.root

    def body(
        self,
        sequence: int,
        allocations: list[tuple[UUID, str]],
        amount: str,
        reference: str,
        **changes: object,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "expected_sequence": sequence,
            "amount": amount,
            "actual_external_date": "2026-10-02",
            "entry_date": "2026-10-02",
            "cash_account_id": str(self.cash),
            "source_account_alias": "FAKE main bank account",
            "external_reference": reference,
            "attestation": "manual_attestation",
            "allocations": [
                {"obligation_id": str(obligation), "amount": value}
                for obligation, value in allocations
            ],
            **changes,
        }

    async def confirm(
        self,
        settlement: UUID,
        sequence: int,
        allocations: list[tuple[UUID, str]],
        amount: str,
        reference: str,
        *,
        payment: UUID | None = None,
        key: str | None = None,
        headers: dict[str, str] | None = None,
        changes: dict[str, object] | None = None,
    ) -> httpx.Response:
        return await self.ledger.client.post(
            f"{self.root}/settlements/{settlement}/confirmations/{payment or uuid7()}",
            json=self.body(sequence, allocations, amount, reference, **(changes or {})),
            headers=headers or self.ledger.headers(key),
        )

    async def payment_journals(self, app_pool: RuntimePool) -> int:
        async with tenant_transaction(app_pool, self.ledger.business) as conn:
            row = await (
                await conn.execute(
                    "select count(*) from gba.journal_entries "
                    "where book_id=%s and source_kind='payment'",
                    (self.ledger.book,),
                )
            ).fetchone()
        assert row is not None
        return int(row[0])

    async def write_directly(
        self,
        app_pool: RuntimePool,
        settlement: UUID,
        sequence: int,
        obligation: UUID,
        minor: int,
        reference: str,
        *,
        allocated: int | None = None,
    ) -> None:
        """One receivable confirmation written by SQL alone, in the order the service uses."""
        business, book = self.ledger.business, self.ledger.book
        user = self.ledger.user.user_id
        payment, entry = uuid7(), uuid7()
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.settlement_events "
                "(tenant_id,book_id,settlement_id,sequence,kind,created_by) "
                "values (%s,%s,%s,%s,'confirmed',%s)",
                (business, book, settlement, sequence, user),
            )
            await conn.execute(
                "insert into gba.external_payments (tenant_id,book_id,id,settlement_id,sequence,"
                "direction,currency,amount_minor,actual_external_date,entry_date,cash_account_id,"
                "source_account_alias,external_reference,attestation,entry_id,created_by) "
                "values (%s,%s,%s,%s,%s,'receivable','USD',%s,'2026-10-02','2026-10-02',%s,"
                "'FAKE main bank account',%s,'manual_attestation',%s,%s)",
                (
                    business,
                    book,
                    payment,
                    settlement,
                    sequence,
                    minor,
                    self.cash,
                    reference,
                    entry,
                    user,
                ),
            )
            await conn.execute(
                "insert into gba.external_payment_allocations "
                "(tenant_id,book_id,payment_id,line_no,obligation_id,amount_minor) "
                "values (%s,%s,%s,1,%s,%s)",
                (business, book, payment, obligation, minor if allocated is None else allocated),
            )
            await conn.execute(
                "insert into gba.journal_entries "
                "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
                "values (%s,%s,%s,'2026-10-02','USD','payment',%s,%s)",
                (business, entry, book, str(payment), user),
            )
            control = self.settlements.invoices.control
            await conn.execute(
                "insert into gba.journal_lines "
                "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) values "
                "(%s,%s,1,%s,%s,'debit',%s),(%s,%s,2,%s,%s,'credit',%s)",
                (business, entry, book, self.cash, minor, business, entry, book, control, minor),
            )


@pytest.fixture
async def payments(invoices: InvoiceWorld, app_pool: RuntimePool) -> PaymentWorld:
    async with tenant_transaction(app_pool, invoices.ledger.business) as conn:
        chart = await ledger.list_accounts(
            conn, invoices.ledger.business, invoices.ledger.book, after=None, limit=100
        )
    return PaymentWorld(
        SettlementWorld(invoices), next(a.account_id for a in chart.items if a.code == "1100")
    )


async def test_confirmation_routes_require_authentication(client: httpx.AsyncClient) -> None:
    base = f"/v1/businesses/{uuid7()}/financial-documents/books/{uuid7()}"
    assert (await client.get(f"{base}/payments/{uuid7()}")).status_code == 401
    refused = await client.post(f"{base}/settlements/{uuid7()}/confirmations/{uuid7()}", json={})
    assert refused.status_code == 401


async def test_partial_confirmations_move_exactly_reserve_to_paid_with_one_journal_each(
    payments: PaymentWorld,
    app_pool: RuntimePool,
) -> None:
    world = payments.settlements
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    first_payment = uuid7()
    first = await payments.confirm(
        settlement, 3, [(obligation, "40.00")], "40.00", "FAKE-TXN-1", payment=first_payment
    )
    assert first.status_code == 200, first.text
    view = first.json()
    assert (view["status"], view["sequence"]) == ("partially_confirmed", 4)
    assert (view["confirmed"], view["reserved"], view["total"]) == ("40.00", "30.00", "70.00")
    assert view["events"][-1]["kind"] == "confirmed"
    assert view["events"][-1]["payment_id"] == str(first_payment)
    balance = await world.balance(obligation)
    assert (balance["paid"], balance["reserved"], balance["available"]) == (
        "40.00",
        "30.00",
        "30.00",
    )
    http, auth = payments.ledger.client, payments.ledger.auth
    recorded = await http.get(f"{payments.root}/payments/{first_payment}", headers=auth)
    assert recorded.status_code == 200, recorded.text
    payment = recorded.json()
    assert (payment["amount"], payment["attestation"], payment["settlement_id"]) == (
        "40.00",
        "manual_attestation",
        str(settlement),
    )
    assert payment["external_reference"] == "FAKE-TXN-1"
    assert payment["actual_external_date"] == "2026-10-02"
    entry_path = f"{payments.ledger.base}/entries/{payment['entry_id']}"
    legacy = await http.get(entry_path, headers=auth)
    assert legacy.json()["error"]["code"] == "JOURNAL_VERSION_REQUIRED"
    entry = await http.get(entry_path, params={"schema_version": 2}, headers=auth)
    assert entry.status_code == 200, entry.text
    assert (entry.json()["source_kind"], entry.json()["source_id"]) == (
        "payment",
        str(first_payment),
    )
    assert [(r["account_id"], r["side"], r["amount"]) for r in entry.json()["lines"]] == [
        (str(payments.cash), "debit", "40.00"),
        (str(world.invoices.control), "credit", "40.00"),
    ]
    second = await payments.confirm(settlement, 4, [(obligation, "30.00")], "30.00", "FAKE-TXN-2")
    assert second.status_code == 200, second.text
    assert (second.json()["status"], second.json()["confirmed"], second.json()["reserved"]) == (
        "confirmed",
        "70.00",
        "0.00",
    )
    balance = await world.balance(obligation)
    assert (balance["paid"], balance["reserved"], balance["available"]) == (
        "70.00",
        "0.00",
        "30.00",
    )
    assert await payments.payment_journals(app_pool) == 2
    report = await http.get(
        payments.ledger.base + "/trial-balance",
        params={"period_from": "2026-10", "period_to": "2026-10", "currency": "USD"},
        headers=auth,
    )
    assert report.json()["totals"]["debit"] == "170.00"
    assert report.json()["totals"]["credit"] == "170.00"
    # A fully confirmed settlement is final.
    for response in (
        await world.act(settlement, "release", 5),
        await world.act(settlement, "sent", 5),
        await payments.confirm(settlement, 5, [(obligation, "1.00")], "1.00", "FAKE-TXN-3"),
    ):
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    assert (await world.balance(obligation))["paid"] == "70.00"


async def test_confirmation_must_fit_its_lines_and_equal_its_allocations(
    payments: PaymentWorld,
    app_pool: RuntimePool,
) -> None:
    world = payments.settlements
    obligation = await world.obligation()
    other = await world.obligation("50.00")
    settlement = await world.reserved(obligation, "70.00")
    too_much = await payments.confirm(settlement, 3, [(obligation, "70.01")], "70.01", "FAKE-A")
    assert too_much.status_code == 409
    assert too_much.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    unequal = await payments.confirm(settlement, 3, [(obligation, "40.00")], "50.00", "FAKE-B")
    assert unequal.status_code == 422
    assert unequal.json()["error"]["code"] == "FINANCIAL_AMOUNT_INVALID"
    foreign_line = await payments.confirm(settlement, 3, [(other, "10.00")], "10.00", "FAKE-C")
    assert foreign_line.status_code == 409
    assert foreign_line.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    scale = await payments.confirm(settlement, 3, [(obligation, "1.001")], "1.001", "FAKE-D")
    assert scale.status_code == 422
    control_as_cash = await payments.confirm(
        settlement,
        3,
        [(obligation, "10.00")],
        "10.00",
        "FAKE-E",
        changes={"cash_account_id": str(world.invoices.control)},
    )
    assert control_as_cash.status_code == 409
    not_an_asset = await payments.confirm(
        settlement,
        3,
        [(obligation, "10.00")],
        "10.00",
        "FAKE-F",
        changes={"cash_account_id": str(world.invoices.counter)},
    )
    assert not_an_asset.status_code == 409
    provider = await payments.confirm(
        settlement,
        3,
        [(obligation, "10.00")],
        "10.00",
        "FAKE-G",
        changes={"attestation": "provider_verified"},
    )
    assert provider.status_code == 422
    stale = await payments.confirm(settlement, 2, [(obligation, "10.00")], "10.00", "FAKE-H")
    assert stale.status_code == 409
    approved = await world.approved(other, "10.00")
    early = await payments.confirm(approved, 2, [(other, "10.00")], "10.00", "FAKE-I")
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    assert await payments.payment_journals(app_pool) == 0
    balance = await world.balance(obligation)
    assert (balance["paid"], balance["reserved"]) == ("0.00", "70.00")
    assert (await world.view(settlement))["sequence"] == 3


async def test_closed_period_refuses_the_confirmation_and_keeps_the_reserve(
    payments: PaymentWorld,
    app_pool: RuntimePool,
) -> None:
    world = payments.settlements
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    closed = await payments.ledger.client.post(
        f"{payments.ledger.base}/periods/2026-10/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=payments.ledger.headers(),
    )
    assert closed.status_code == 200, closed.text
    denied = await payments.confirm(settlement, 3, [(obligation, "40.00")], "40.00", "FAKE-CLOSED")
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "LEDGER_PERIOD_CLOSED"
    view = await world.view(settlement)
    assert (view["sequence"], view["status"], view["confirmed"]) == (3, "reserved", "0.00")
    assert (await world.balance(obligation))["reserved"] == "70.00"
    assert await payments.payment_journals(app_pool) == 0
    async with tenant_transaction(app_pool, payments.ledger.business) as conn:
        row = await (
            await conn.execute(
                "select count(*) from gba.external_payments where book_id=%s",
                (payments.ledger.book,),
            )
        ).fetchone()
        assert row == (0,)
    # A plain release moves no money and needs no open period.
    assert (await world.act(settlement, "release", 3)).status_code == 200


async def test_replay_and_the_same_external_identity_post_money_once(
    payments: PaymentWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    world = payments.settlements
    business = payments.ledger.business
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    payment, key = uuid7(), str(uuid7())
    allocations = [(obligation, "40.00")]
    first = await payments.confirm(
        settlement, 3, allocations, "40.00", "FAKE-SAME", payment=payment, key=key
    )
    assert first.status_code == 200, first.text
    replay = await payments.confirm(
        settlement, 3, allocations, "40.00", "FAKE-SAME", payment=payment, key=key
    )
    assert replay.status_code == 200
    assert replay.json() == first.json()
    changed = await payments.confirm(
        settlement, 3, allocations, "40.00", "FAKE-OTHER", payment=payment, key=key
    )
    assert changed.status_code == 422
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    # Another browser tab: new key and new payment id, the same real external fact.
    again = await payments.confirm(settlement, 4, [(obligation, "30.00")], "30.00", "FAKE-SAME")
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "FINANCIAL_SOURCE_ALREADY_RECORDED"
    assert again.json()["error"]["details"]["payment_id"] == str(payment)
    assert "FAKE-SAME" not in again.text
    # Another settlement form cannot repeat it either.
    other = await world.obligation("50.00")
    elsewhere = await world.reserved(other, "50.00")
    repeated = await payments.confirm(elsewhere, 3, [(other, "40.00")], "40.00", "FAKE-SAME")
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "FINANCIAL_SOURCE_ALREADY_RECORDED"
    reused_id = await payments.confirm(
        elsewhere, 3, [(other, "40.00")], "40.00", "FAKE-NEW", payment=payment
    )
    assert reused_id.status_code == 409
    assert await payments.payment_journals(app_pool) == 1
    balance = await world.balance(obligation)
    assert (balance["paid"], balance["reserved"]) == ("40.00", "30.00")
    with owner_tenant_transaction(owner_conn, business):
        deleted = owner_conn.execute(
            "delete from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.settlement_confirm' and idempotency_key=%s",
            (business, key),
        )
        assert deleted.rowcount == 1
    commands = f"/v1/businesses/{business}/financial-documents/commands"
    reference = {
        "schema_version": 1,
        "operation": "settlement_confirm",
        "book_id": str(payments.ledger.book),
        "subject_id": str(settlement),
        "revision": 4,
    }
    resolved = await payments.ledger.client.post(
        f"{commands}/{key}/resolve", json=reference, headers=payments.ledger.auth
    )
    assert resolved.json()["state"] == "committed"
    late = await payments.confirm(
        settlement, 3, allocations, "40.00", "FAKE-SAME", payment=payment, key=key
    )
    assert late.status_code == 200
    assert late.json() == first.json()
    with owner_tenant_transaction(owner_conn, business):
        stored = owner_conn.execute(
            "select response_body from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.settlement_confirm' and idempotency_key=%s",
            (business, key),
        ).fetchone()
        audit = owner_conn.execute(
            "select details from gba.audit_events where tenant_id=%s "
            "and action='finance.settlement_confirm'",
            (business,),
        ).fetchall()
    assert stored is not None
    assert set(stored[0]) == {"book_id", "settlement_id", "sequence"}
    assert audit
    # Audit keeps identifiers only: no amount, alias or external reference.
    assert all(set(row[0]) == {"book_id", "sequence"} for row in audit)
    assert await payments.payment_journals(app_pool) == 1
    # A cancelled unresolved key seals a late original confirmation.
    sealed_key = str(uuid7())
    cancelled = await payments.ledger.client.post(
        f"{commands}/{sealed_key}/cancel",
        json={**reference, "revision": 5},
        headers=payments.ledger.headers(),
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    blocked = await payments.confirm(
        settlement, 4, [(obligation, "30.00")], "30.00", "FAKE-LATE", key=sealed_key
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "FINANCIAL_COMMAND_CANCELLED"
    assert await payments.payment_journals(app_pool) == 1


async def test_two_partial_confirmations_wait_on_real_lock_and_one_wins(
    payments: PaymentWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    world = payments.settlements
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    async with tenant_transaction(app_pool, payments.ledger.business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (payments.ledger.business,))
        pending = [
            asyncio.create_task(
                payments.confirm(settlement, 3, [(obligation, "50.00")], "50.00", f"FAKE-RACE-{n}")
            )
            for n in range(2)
        ]
        try:
            await _wait_for_blocked(owner_conn, 2)
        except BaseException:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
    results = await asyncio.gather(*pending)
    assert sorted(r.status_code for r in results) == [200, 409]
    balance = await world.balance(obligation)
    assert (balance["paid"], balance["reserved"], balance["available"]) == (
        "50.00",
        "20.00",
        "30.00",
    )
    assert await payments.payment_journals(app_pool) == 1


async def test_release_and_confirmation_race_keep_the_cap(
    payments: PaymentWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    world = payments.settlements
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    competitor = await world.approved(obligation, "60.00")
    async with tenant_transaction(app_pool, payments.ledger.business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (payments.ledger.business,))
        pending = [
            asyncio.create_task(
                payments.confirm(settlement, 3, [(obligation, "50.00")], "50.00", "FAKE-RACE")
            ),
            asyncio.create_task(world.act(settlement, "release", 3)),
            asyncio.create_task(world.act(competitor, "reserve", 2)),
        ]
        try:
            await _wait_for_blocked(owner_conn, 3)
        except BaseException:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
    confirmed, released, reserved = await asyncio.gather(*pending)
    # Confirmation and release named the same sequence: exactly one of them is recorded.
    assert sorted((confirmed.status_code, released.status_code)) == [200, 409]
    balance = await world.balance(obligation)
    paid = "50.00" if confirmed.status_code == 200 else "0.00"
    assert balance["paid"] == paid
    held = {
        ("50.00", 200): None,
        ("50.00", 409): "20.00",
        ("0.00", 200): "60.00",
        ("0.00", 409): "0.00",
    }[(paid, reserved.status_code)]
    # 50 paid + 20 still held leaves 30: a 60 reserve can never also succeed.
    assert held is not None
    assert balance["reserved"] == held
    assert await payments.payment_journals(app_pool) == (1 if paid == "50.00" else 0)


async def test_sent_outcome_stays_unresolved_after_a_partial_confirmation(
    payments: PaymentWorld,
) -> None:
    world = payments.settlements
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    assert (await world.act(settlement, "sent", 3)).status_code == 200
    partial = await payments.confirm(settlement, 4, [(obligation, "40.00")], "40.00", "FAKE-SENT")
    assert partial.status_code == 200, partial.text
    assert (partial.json()["status"], partial.json()["outcome_unresolved"]) == (
        "partially_confirmed",
        True,
    )
    plain = await world.act(settlement, "release", 5)
    assert plain.status_code == 409
    assert plain.json()["error"]["code"] == "FINANCIAL_OUTCOME_UNRESOLVED"
    resolved = await world.act(
        settlement,
        "release",
        5,
        resolution="attested_no_payment",
        reason="FAKE remainder was never sent",
        evidence_source="FAKE bank statement",
    )
    assert resolved.status_code == 200, resolved.text
    assert (
        resolved.json()["status"],
        resolved.json()["confirmed"],
        resolved.json()["reserved"],
    ) == (
        "released",
        "40.00",
        "0.00",
    )
    assert resolved.json()["outcome_unresolved"] is False
    balance = await world.balance(obligation)
    assert (balance["paid"], balance["reserved"], balance["available"]) == (
        "40.00",
        "0.00",
        "60.00",
    )


async def test_outgoing_payment_and_several_obligations_post_exact_control_lines(
    payments: PaymentWorld,
    app_pool: RuntimePool,
) -> None:
    world = payments.settlements
    http, auth = payments.ledger.client, payments.ledger.auth
    async with tenant_transaction(app_pool, payments.ledger.business) as conn:
        chart = await ledger.list_accounts(
            conn, payments.ledger.business, payments.ledger.book, after=None, limit=100
        )
    liability = next(a.account_id for a in chart.items if a.code == "2000")
    expense = next(a.account_id for a in chart.items if a.type == "expense")
    owed = []
    for amount in ("60.00", "40.00"):
        owed.append(
            await world.obligation(
                amount,
                direction="payable",
                control_account_id=str(liability),
                lines=[
                    {
                        "line_id": str(uuid7()),
                        "counter_account_id": str(expense),
                        "description": "FAKE supplier expense",
                        "amount": amount,
                    }
                ],
            )
        )
    settlement = uuid7()
    prepared = await world.prepare(
        settlement, [(owed[0], "60.00"), (owed[1], "40.00")], direction="payable"
    )
    assert prepared.status_code == 200, prepared.text
    assert (await world.act(settlement, "approve", 1)).status_code == 200
    assert (await world.act(settlement, "reserve", 2)).status_code == 200
    payment = uuid7()
    paid = await payments.confirm(
        settlement,
        3,
        [(owed[0], "30.00"), (owed[1], "20.00")],
        "50.00",
        "FAKE-OUT",
        payment=payment,
    )
    assert paid.status_code == 200, paid.text
    assert [(a["confirmed"], a["reserved"]) for a in paid.json()["allocations"]] == [
        ("30.00", "30.00"),
        ("20.00", "20.00"),
    ]
    recorded = (await http.get(f"{payments.root}/payments/{payment}", headers=auth)).json()
    assert recorded["direction"] == "payable"
    entry = await http.get(
        f"{payments.ledger.base}/entries/{recorded['entry_id']}",
        params={"schema_version": 2},
        headers=auth,
    )
    assert [(r["account_id"], r["side"], r["amount"]) for r in entry.json()["lines"]] == [
        (str(payments.cash), "credit", "50.00"),
        (str(liability), "debit", "30.00"),
        (str(liability), "debit", "20.00"),
    ]
    assert (await world.balance(owed[0]))["paid"] == "30.00"
    assert (await world.balance(owed[1]))["available"] == "0.00"


async def test_generic_reversal_and_sql_cannot_touch_or_forge_a_payment(
    payments: PaymentWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    world = payments.settlements
    business, book = payments.ledger.business, payments.ledger.book
    user = payments.ledger.user.user_id
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    payment = uuid7()
    confirmed = await payments.confirm(
        settlement, 3, [(obligation, "40.00")], "40.00", "FAKE-SQL", payment=payment
    )
    assert confirmed.status_code == 200, confirmed.text
    recorded = await payments.ledger.client.get(
        f"{payments.root}/payments/{payment}", headers=payments.ledger.auth
    )
    entry = UUID(recorded.json()["entry_id"])
    denied = await payments.ledger.client.post(
        f"{payments.ledger.base}/entries/{entry}/reverse",
        json={"schema_version": 1, "reversal_entry_id": str(uuid7()), "entry_date": "2026-10-03"},
        headers=payments.ledger.headers(),
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "LEDGER_STATE_INVALID"
    with pytest.raises(psycopg.errors.CheckViolation, match="H-owned journal correction"):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,"
                "source_kind,source_id,reverses_entry_id,created_by) "
                "values (%s,%s,%s,'2026-10-03','USD','reversal',%s,%s,%s)",
                (business, uuid7(), book, str(entry), entry, user),
            )
    with pytest.raises(psycopg.errors.CheckViolation, match="needs its external payment"):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.journal_entries "
                "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
                "values (%s,%s,%s,'2026-10-02','USD','payment',%s,%s)",
                (business, uuid7(), book, str(uuid7()), user),
            )
    # A confirmed fact without its payment never commits.
    with pytest.raises(psycopg.errors.CheckViolation, match="needs its external payment"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.settlement_events "
                "(tenant_id,book_id,settlement_id,sequence,kind,created_by) "
                "values (%s,%s,%s,5,'confirmed',%s)",
                (business, book, settlement, user),
            )
            await conn.execute("set constraints all immediate")
    with pytest.raises(psycopg.errors.CheckViolation, match="written with their payment"):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.external_payment_allocations "
                "(tenant_id,book_id,payment_id,line_no,obligation_id,amount_minor) "
                "values (%s,%s,%s,2,%s,3000)",
                (business, book, payment, obligation),
            )
    with pytest.raises(psycopg.errors.CheckViolation, match="confirmed settlement event"):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.external_payments (tenant_id,book_id,id,settlement_id,sequence,"
                "direction,currency,amount_minor,actual_external_date,entry_date,cash_account_id,"
                "source_account_alias,external_reference,attestation,entry_id,created_by) "
                "values (%s,%s,%s,%s,3,'receivable','USD',1000,'2026-10-02','2026-10-02',%s,"
                "'FAKE alias','FAKE-FORGED','manual_attestation',%s,%s)",
                (business, book, uuid7(), settlement, payments.cash, uuid7(), user),
            )
    for table in ("external_payments", "external_payment_allocations"):
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="kept unchanged"),
            owner_tenant_transaction(owner_conn, business),
        ):
            owner_conn.execute(
                sql.SQL("update gba.{} set book_id=book_id where book_id=%s").format(
                    sql.Identifier(table)
                ),
                (book,),
            )
    balance = await world.balance(obligation)
    assert (balance["paid"], balance["reserved"]) == ("40.00", "30.00")
    assert await payments.payment_journals(app_pool) == 1


async def test_late_journal_pair_cannot_change_a_confirmed_payment(
    payments: PaymentWorld,
    app_pool: RuntimePool,
) -> None:
    from datetime import date

    from gorgona_booking.business import settlements as service
    from gorgona_booking.business.settlement_contracts import PaymentConfirmInput

    world = payments.settlements
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    payment = uuid7()
    body = PaymentConfirmInput.model_validate(
        payments.body(3, [(obligation, "40.00")], "40.00", "FAKE-LATE-PAIR")
    )
    assert body.entry_date == date(2026, 10, 2)
    with pytest.raises(psycopg.errors.CheckViolation, match="cash line and every allocation"):  # noqa: PT012
        async with tenant_transaction(app_pool, payments.ledger.business) as conn:
            await service.confirm(
                conn,
                business_id=payments.ledger.business,
                book_id=payments.ledger.book,
                settlement_id=settlement,
                payment_id=payment,
                user_id=payments.ledger.user.user_id,
                actor=f"user:{payments.ledger.user.user_id}",
                key=str(uuid7()),
                body=body,
            )
            entry = await (
                await conn.execute(
                    "select entry_id from gba.external_payments where id=%s", (payment,)
                )
            ).fetchone()
            assert entry is not None
            await conn.execute(
                "insert into gba.journal_lines "
                "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) values "
                "(%s,%s,3,%s,%s,'debit',1),(%s,%s,4,%s,%s,'credit',1)",
                (
                    payments.ledger.business,
                    entry[0],
                    payments.ledger.book,
                    payments.cash,
                    payments.ledger.business,
                    entry[0],
                    payments.ledger.book,
                    world.invoices.control,
                ),
            )
            await conn.execute("set constraints all immediate")
    assert (await world.view(settlement))["sequence"] == 3
    assert await payments.payment_journals(app_pool) == 0


async def test_sql_alone_cannot_exceed_the_reserve_repeat_an_identity_or_delete(
    payments: PaymentWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    world = payments.settlements
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    # Control: the same rows are accepted without the service when they are exact.
    await payments.write_directly(app_pool, settlement, 4, obligation, 4000, "FAKE-RAW-1")
    view = await world.view(settlement)
    assert (view["sequence"], view["status"]) == (4, "partially_confirmed")
    assert (view["confirmed"], view["reserved"]) == ("40.00", "30.00")
    with pytest.raises(psycopg.errors.CheckViolation, match="exceeds the reserved settlement line"):
        await payments.write_directly(app_pool, settlement, 5, obligation, 3001, "FAKE-RAW-2")
    with pytest.raises(psycopg.errors.CheckViolation, match="must equal the confirmed amount"):
        await payments.write_directly(
            app_pool, settlement, 5, obligation, 1000, "FAKE-RAW-3", allocated=900
        )
    with pytest.raises(psycopg.errors.UniqueViolation, match=_IDENTITY):
        await payments.write_directly(app_pool, settlement, 5, obligation, 1000, "FAKE-RAW-1")
    for table in ("external_payments", "external_payment_allocations"):
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="kept unchanged"),
            owner_tenant_transaction(owner_conn, payments.ledger.business),
        ):
            owner_conn.execute(
                sql.SQL("delete from gba.{} where book_id=%s").format(sql.Identifier(table)),
                (payments.ledger.book,),
            )
    balance = await world.balance(obligation)
    assert (balance["paid"], balance["reserved"], balance["available"]) == (
        "40.00",
        "30.00",
        "30.00",
    )
    assert (await world.view(settlement))["sequence"] == 4
    assert await payments.payment_journals(app_pool) == 1


async def test_off_and_withdrawn_readiness_block_confirmation_but_keep_history(
    payments: PaymentWorld,
    idp: FakeIdp,
    monkeypatch: pytest.MonkeyPatch,
    app_pool: RuntimePool,
) -> None:
    world = payments.settlements
    obligation = await world.obligation()
    settlement = await world.reserved(obligation, "70.00")
    payment = uuid7()
    first = await payments.confirm(
        settlement, 3, [(obligation, "10.00")], "10.00", "FAKE-ON", payment=payment
    )
    assert first.status_code == 200, first.text
    feature = modules.MODULES_BY_ID["finance_documents"]
    with monkeypatch.context() as patch:
        patch.setitem(
            modules.MODULES_BY_ID,
            "finance_documents",
            feature.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
        )
        unready = await payments.confirm(settlement, 4, [(obligation, "10.00")], "10.00", "FAKE-NR")
        assert unready.status_code == 409
        assert unready.json()["error"]["code"] == "MODULE_NOT_READY"
    config = Config(payments.ledger.client, idp)
    await config.publish(payments.ledger.user, payments.ledger.business, 2, ["booking_resources"])
    off = await payments.confirm(settlement, 4, [(obligation, "10.00")], "10.00", "FAKE-OFF")
    assert off.status_code == 409
    assert off.json()["error"]["code"] == "MODULE_DISABLED"
    http, auth = payments.ledger.client, payments.ledger.auth
    assert (await http.get(f"{payments.root}/payments/{payment}", headers=auth)).status_code == 200
    view = await world.view(settlement)
    assert (view["status"], view["confirmed"], view["reserved"]) == (
        "partially_confirmed",
        "10.00",
        "60.00",
    )
    assert await payments.payment_journals(app_pool) == 1
    # The unconfirmed remainder was never sent: its plain release stays possible.
    released = await world.act(settlement, "release", 4)
    assert released.status_code == 200, released.text
    balance = await world.balance(obligation)
    assert (balance["paid"], balance["reserved"]) == ("10.00", "0.00")


@pytest.mark.parametrize(
    ("role", "branch", "expected"),
    [
        ("owner", False, 200),
        ("front_desk", False, 403),
        ("artist", False, 403),
        ("manager", True, 403),
    ],
)
async def test_payment_routes_keep_company_finance_permissions(
    payments: PaymentWorld,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
    branch: bool,
    expected: int,
) -> None:
    obligation = await payments.settlements.obligation()
    settlement = await payments.settlements.reserved(obligation, "70.00")
    payment = uuid7()
    recorded = await payments.confirm(
        settlement, 3, [(obligation, "10.00")], "10.00", "FAKE-ROLE", payment=payment
    )
    assert recorded.status_code == 200, recorded.text
    member = seed_user(owner_conn, f"FAKE-H2-pay-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=payments.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    auth = idp.bearer(member.subject, email=member.email)
    read = await payments.ledger.client.get(f"{payments.root}/payments/{payment}", headers=auth)
    assert read.status_code == expected, read.text
    if expected != 200:
        keyed = {**auth, "Idempotency-Key": str(uuid7())}
        denied = await payments.confirm(
            settlement, 4, [(obligation, "10.00")], "10.00", "FAKE-DENIED", headers=keyed
        )
        assert denied.status_code == 403
        assert (await payments.settlements.balance(obligation))["paid"] == "10.00"


_IDENTITY = "external_payments_identity"


@pytest.mark.parametrize(
    ("change", "restore"),
    [
        (
            "alter table gba.external_payments disable trigger external_payments_check",
            "alter table gba.external_payments enable trigger external_payments_check",
        ),
        (
            "alter table gba.journal_lines disable trigger journal_lines_payment_consistent",
            "alter table gba.journal_lines enable trigger journal_lines_payment_consistent",
        ),
        (
            f"alter table gba.external_payments drop constraint {_IDENTITY}",
            f"alter table gba.external_payments add constraint {_IDENTITY} unique "
            "(tenant_id, book_id, direction, source_account_alias, external_reference)",
        ),
        (
            "alter table gba.external_payments drop constraint external_payments_attestation_check",
            approved_check("external_payments", "external_payments_attestation_check"),
        ),
        (
            "alter policy external_payments_unrestricted_scope on gba.external_payments "
            "using (true) with check (true)",
            "alter policy external_payments_unrestricted_scope on gba.external_payments "
            "using (gba.current_location_id() is null) "
            "with check (gba.current_location_id() is null)",
        ),
        (
            "grant update on gba.external_payment_allocations to gba_runtime",
            "revoke update on gba.external_payment_allocations from gba_runtime",
        ),
        (
            "create or replace function gba.assert_payment_consistent(tenant uuid, book uuid, "
            "payment uuid) returns void language plpgsql as $$ begin return; end; $$",
            packaged_function("assert_payment_consistent"),
        ),
        (
            "create or replace function gba.obligation_balance(tenant uuid, book uuid, "
            "obligation uuid) returns table (principal_minor bigint, paid_minor bigint, "
            "credited_minor bigint, reserved_minor bigint) language plpgsql as $$ begin "
            "return query select 1::bigint, 0::bigint, 0::bigint, 0::bigint; end; $$",
            packaged_function("obligation_balance"),
        ),
    ],
)
async def test_damaged_payment_controls_fail_readiness_with_503(
    payments: PaymentWorld,
    owner_conn: psycopg.Connection,
    change: str,
    restore: str,
) -> None:
    http, auth, base = payments.ledger.client, payments.ledger.auth, payments.ledger.base
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
