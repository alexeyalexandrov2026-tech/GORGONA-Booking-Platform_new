"""H3 credit notes: unpaid credit C, a separate refund obligation and one exact journal."""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql

from gorgona_booking.business import credit_notes, ledger, modules
from gorgona_booking.business.financial_contracts import CreditIssueInput
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_external_payments as payment_shared
from tests.integration import test_invoice_issue as invoice_shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import seed_user
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_invoice_issue import approved_check, packaged_function, widened_check
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
payments = payment_shared.payments

_ZERO = ("0.00", "0.00")


@dataclass(frozen=True)
class CreditWorld:
    payments: PaymentWorld
    chart: dict[str, UUID]

    @property
    def settlements(self) -> SettlementWorld:
        return self.payments.settlements

    @property
    def ledger(self) -> LedgerWorld:
        return self.payments.ledger

    @property
    def base(self) -> str:
        return f"{self.payments.root}/credits"

    async def invoice(
        self, *amounts: str, counter: UUID | None = None, **changes: object
    ) -> tuple[UUID, list[UUID]]:
        """Issue a FAKE invoice with one line per amount; its obligation and line ids."""
        invoices = self.settlements.invoices
        document = uuid7()
        body = invoices.draft_body(**changes)
        lines = [
            {
                "line_id": str(uuid7()),
                "counter_account_id": str(counter or invoices.counter),
                "description": "FAKE invoiced service",
                "amount": amount,
            }
            for amount in amounts or ("100.00",)
        ]
        body["lines"] = lines
        saved = await invoices.save(document=document, body=body)
        assert saved.status_code == 200, saved.text
        issued = await invoices.issue(document)
        assert issued.status_code == 200, issued.text
        return UUID(issued.json()["obligation_id"]), [UUID(line["line_id"]) for line in lines]

    def draft(
        self,
        obligation: UUID,
        lines: list[tuple[UUID, str]],
        *,
        counter: UUID | None = None,
        **changes: object,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "expected_revision": 0,
            "credited_obligation_id": str(obligation),
            "counterparty_revision": 1,
            "credit_date": "2026-10-03",
            "title": "FAKE credit note",
            "number": "FAKE-CN-001",
            "lines": [
                {
                    "line_id": str(uuid7()),
                    "credited_line_id": str(line),
                    "counter_account_id": str(counter or self.settlements.invoices.counter),
                    "description": "FAKE goodwill reduction",
                    "amount": amount,
                }
                for line, amount in lines
            ],
            **changes,
        }

    async def save(
        self,
        document: UUID,
        body: dict[str, object],
        *,
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self.ledger.client.put(
            f"{self.base}/{document}", json=body, headers=headers or self.ledger.headers(key)
        )

    async def issue(
        self,
        document: UUID,
        *,
        refund: UUID | None = None,
        key: str | None = None,
        headers: dict[str, str] | None = None,
        **changes: object,
    ) -> httpx.Response:
        return await self.ledger.client.post(
            f"{self.base}/{document}/issue",
            json={
                "schema_version": 1,
                "expected_revision": 1,
                "entry_date": "2026-10-03",
                "attestation": "confirmed_account_treatment",
                "refund_control_account_id": None if refund is None else str(refund),
                **changes,
            },
            headers=headers or self.ledger.headers(key),
        )

    async def drafted(
        self,
        obligation: UUID,
        lines: list[tuple[UUID, str]],
        *,
        counter: UUID | None = None,
    ) -> UUID:
        document = uuid7()
        saved = await self.save(document, self.draft(obligation, lines, counter=counter))
        assert saved.status_code == 200, saved.text
        return document

    async def credit(
        self,
        obligation: UUID,
        lines: list[tuple[UUID, str]],
        *,
        refund: UUID | None = None,
        counter: UUID | None = None,
    ) -> dict[str, object]:
        document = await self.drafted(obligation, lines, counter=counter)
        issued = await self.issue(document, refund=refund)
        assert issued.status_code == 200, issued.text
        result: dict[str, object] = issued.json()
        return result

    async def paid(
        self, obligation: UUID, amount: str, reference: str, *, direction: str = "receivable"
    ) -> UUID:
        """Reserve and confirm `amount` in full through one settlement."""
        settlement = uuid7()
        world = self.settlements
        prepared = await world.prepare(settlement, [(obligation, amount)], direction=direction)
        assert prepared.status_code == 200, prepared.text
        for action, sequence in (("approve", 1), ("reserve", 2)):
            assert (await world.act(settlement, action, sequence)).status_code == 200
        confirmed = await self.payments.confirm(
            settlement, 3, [(obligation, amount)], amount, reference
        )
        assert confirmed.status_code == 200, confirmed.text
        return settlement

    async def journal(self, entry: object) -> list[tuple[str, str, str]]:
        response = await self.ledger.client.get(
            f"{self.ledger.base}/entries/{entry}",
            params={"schema_version": 2},
            headers=self.ledger.auth,
        )
        assert response.status_code == 200, response.text
        return [(r["account_id"], r["side"], r["amount"]) for r in response.json()["lines"]]

    async def closing(self) -> dict[str, tuple[str, str]]:
        """Closing debit and credit of every USD account that moved in October."""
        report = await self.ledger.client.get(
            self.ledger.base + "/trial-balance",
            params={"period_from": "2026-10", "period_to": "2026-10", "currency": "USD"},
            headers=self.ledger.auth,
        )
        assert report.status_code == 200, report.text
        codes = {account: code for code, account in self.chart.items()}
        return {
            codes[UUID(row["account_id"])]: (row["closing_debit"], row["closing_credit"])
            for row in report.json()["rows"]
        }

    async def count(self, app_pool: RuntimePool, query: str, *args: object) -> int:
        async with tenant_transaction(app_pool, self.ledger.business) as conn:
            row = await (await conn.execute(query, args)).fetchone()
        assert row is not None
        return int(row[0] or 0)


@pytest.fixture
async def credits(payments: PaymentWorld, app_pool: RuntimePool) -> CreditWorld:
    async with tenant_transaction(app_pool, payments.ledger.business) as conn:
        chart = await ledger.list_accounts(
            conn, payments.ledger.business, payments.ledger.book, after=None, limit=100
        )
    return CreditWorld(payments, {a.code: a.account_id for a in chart.items})


async def test_credit_routes_require_authentication(client: httpx.AsyncClient) -> None:
    base = f"/v1/businesses/{uuid7()}/financial-documents/books/{uuid7()}/credits"
    assert (await client.get(base)).status_code == 401
    assert (await client.get(f"{base}/{uuid7()}")).status_code == 401
    assert (await client.put(f"{base}/{uuid7()}", json={})).status_code == 401
    assert (await client.post(f"{base}/{uuid7()}/issue", json={})).status_code == 401


async def test_paid_70_credit_50_is_credit_30_and_a_separate_refund_obligation_of_20(
    credits: CreditWorld,
    app_pool: RuntimePool,
) -> None:
    obligation, (line,) = await credits.invoice()
    await credits.paid(obligation, "70.00", "FAKE-CN-PAY-1")
    refund_account = credits.chart["2100"]
    document = await credits.drafted(obligation, [(line, "50.00")])
    http, auth = credits.ledger.client, credits.ledger.auth
    draft = (await http.get(f"{credits.base}/{document}", headers=auth)).json()
    assert (draft["state"], draft["revision"], draft["total"]) == ("draft", 1, "50.00")
    assert (draft["direction"], draft["control_account_id"]) == (
        "receivable",
        str(credits.settlements.invoices.control),
    )
    assert (draft["applied"], draft["refund"], draft["entry_id"]) == (None, None, None)
    # The paid part becomes a refund, so its account must be chosen explicitly.
    missing = await credits.issue(document)
    assert missing.status_code == 409, missing.text
    assert missing.json()["error"]["code"] == "FINANCIAL_REFUND_ACCOUNT_INVALID"
    assert missing.json()["error"]["details"]["refund"] == "20.00"
    key = str(uuid7())
    issued = await credits.issue(document, refund=refund_account, key=key)
    assert issued.status_code == 200, issued.text
    view = issued.json()
    assert (view["state"], view["revision"], view["total"]) == ("issued", 2, "50.00")
    assert (view["applied"], view["refund"]) == ("30.00", "20.00")
    assert view["refund_control_account_id"] == str(refund_account)
    assert view["attestation"] == "confirmed_account_treatment"
    assert (await credits.issue(document, refund=refund_account, key=key)).json() == view
    original = await credits.settlements.balance(obligation)
    assert (
        original["principal"],
        original["paid"],
        original["credited"],
        original["reserved"],
        original["available"],
    ) == ("100.00", "70.00", "30.00", "0.00", "0.00")
    refund = await credits.settlements.balance(UUID(view["refund_obligation_id"]))
    assert (refund["source_kind"], refund["source_id"], refund["direction"]) == (
        "credit_refund",
        str(document),
        "payable",
    )
    assert (refund["principal"], refund["paid"], refund["available"]) == ("20.00", "0.00", "20.00")
    assert refund["control_account_id"] == str(refund_account)
    assert await credits.journal(view["entry_id"]) == [
        (str(credits.settlements.invoices.counter), "debit", "50.00"),
        (str(credits.settlements.invoices.control), "credit", "30.00"),
        (str(refund_account), "credit", "20.00"),
    ]
    legacy = await http.get(f"{credits.ledger.base}/entries/{view['entry_id']}", headers=auth)
    assert legacy.json()["error"]["code"] == "JOURNAL_VERSION_REQUIRED"
    # Historical cash and the original principal stay as they were.
    closing = await credits.closing()
    assert closing["1200"] == _ZERO
    assert closing["1100"] == ("70.00", "0.00")
    assert closing["4000"] == ("0.00", "50.00")
    assert closing["2100"] == ("0.00", "20.00")
    payments_posted = await credits.count(
        app_pool,
        "select count(*) from gba.journal_entries where book_id=%s and source_kind='payment'",
        credits.ledger.book,
    )
    assert payments_posted == 1
    # Issued history stays unchanged.
    changed = await credits.save(
        document, credits.draft(obligation, [(line, "1.00")], expected_revision=2)
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    listed = await http.get(credits.base, headers=auth)
    assert [item["document_id"] for item in listed.json()["items"]] == [str(document)]


async def test_refund_obligation_settles_through_its_own_reserve_and_payment(
    credits: CreditWorld,
) -> None:
    obligation, (line,) = await credits.invoice()
    await credits.paid(obligation, "70.00", "FAKE-CN-PAY-2")
    view = await credits.credit(obligation, [(line, "50.00")], refund=credits.chart["2100"])
    refund = UUID(str(view["refund_obligation_id"]))
    world = credits.settlements
    # A refund owed to the customer is payable: a receivable settlement cannot take it.
    wrong = await world.prepare(uuid7(), [(refund, "20.00")])
    assert wrong.status_code == 409
    settlement = uuid7()
    prepared = await world.prepare(settlement, [(refund, "20.00")], direction="payable")
    assert prepared.status_code == 200, prepared.text
    for action, sequence in (("approve", 1), ("reserve", 2)):
        assert (await world.act(settlement, action, sequence)).status_code == 200
    # The refund cannot be paid before the credit that created it was posted.
    early = await credits.payments.confirm(
        settlement, 3, [(refund, "15.00")], "15.00", "FAKE-REFUND-EARLY"
    )
    assert early.status_code == 422, early.text
    assert early.json()["error"]["code"] == "LEDGER_DATE_INVALID"
    payment = uuid7()
    confirmed = await credits.payments.confirm(
        settlement,
        3,
        [(refund, "15.00")],
        "15.00",
        "FAKE-REFUND-1",
        payment=payment,
        changes={"entry_date": "2026-10-04", "actual_external_date": "2026-10-04"},
    )
    assert confirmed.status_code == 200, confirmed.text
    balance = await world.balance(refund)
    assert (balance["paid"], balance["reserved"], balance["available"]) == (
        "15.00",
        "5.00",
        "0.00",
    )
    recorded = await credits.ledger.client.get(
        f"{credits.payments.root}/payments/{payment}", headers=credits.ledger.auth
    )
    assert await credits.journal(recorded.json()["entry_id"]) == [
        (str(credits.payments.cash), "credit", "15.00"),
        (str(credits.chart["2100"]), "debit", "15.00"),
    ]
    closing = await credits.closing()
    assert closing["2100"] == ("0.00", "5.00")
    assert closing["1100"] == ("55.00", "0.00")
    # A refund obligation is never credited itself.
    lines: list[dict[str, str]] = view["lines"]  # type: ignore[assignment]
    nested = await credits.save(
        uuid7(), credits.draft(refund, [(UUID(lines[0]["line_id"]), "1.00")])
    )
    assert nested.status_code == 409
    assert nested.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"


async def test_unpaid_credit_reduces_available_and_takes_no_refund_account(
    credits: CreditWorld,
    app_pool: RuntimePool,
) -> None:
    obligation, (line,) = await credits.invoice()
    document = await credits.drafted(obligation, [(line, "40.00")])
    unneeded = await credits.issue(document, refund=credits.chart["2100"])
    assert unneeded.status_code == 409
    assert unneeded.json()["error"]["code"] == "FINANCIAL_REFUND_ACCOUNT_INVALID"
    issued = await credits.issue(document)
    assert issued.status_code == 200, issued.text
    view = issued.json()
    assert (view["applied"], view["refund"], view["refund_obligation_id"]) == (
        "40.00",
        "0.00",
        None,
    )
    assert await credits.journal(view["entry_id"]) == [
        (str(credits.settlements.invoices.counter), "debit", "40.00"),
        (str(credits.settlements.invoices.control), "credit", "40.00"),
    ]
    balance = await credits.settlements.balance(obligation)
    assert (balance["credited"], balance["available"]) == ("40.00", "60.00")
    # The credited part can never be reserved again.
    too_much = await credits.settlements.approved(obligation, "60.01")
    over = await credits.settlements.act(too_much, "reserve", 2)
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    exact = await credits.settlements.approved(obligation, "60.00")
    assert (await credits.settlements.act(exact, "reserve", 2)).status_code == 200
    obligations = await credits.count(
        app_pool,
        "select count(*) from gba.financial_obligations where book_id=%s",
        credits.ledger.book,
    )
    assert obligations == 1


async def test_active_or_sent_reserve_must_be_resolved_before_a_credit(
    credits: CreditWorld,
) -> None:
    obligation, (line,) = await credits.invoice()
    world = credits.settlements
    settlement = await world.reserved(obligation, "30.00")
    document = await credits.drafted(obligation, [(line, "10.00")])
    held = await credits.issue(document)
    assert held.status_code == 409
    assert held.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    assert (await world.act(settlement, "sent", 3)).status_code == 200
    unknown = await credits.issue(document)
    assert unknown.status_code == 409
    assert unknown.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
    resolved = await world.act(
        settlement,
        "release",
        4,
        resolution="attested_no_payment",
        reason="FAKE bank confirmed nothing was sent",
        evidence_source="FAKE bank statement",
    )
    assert resolved.status_code == 200, resolved.text
    issued = await credits.issue(document)
    assert issued.status_code == 200, issued.text
    assert (await world.balance(obligation))["credited"] == "10.00"


async def test_credit_is_limited_by_each_uncredited_original_line(
    credits: CreditWorld,
) -> None:
    obligation, (first, second) = await credits.invoice("60.00", "40.00")
    await credits.credit(obligation, [(first, "60.00"), (second, "15.00")])
    beyond = await credits.drafted(obligation, [(second, "25.01")])
    over = await credits.issue(beyond)
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    spent = await credits.drafted(obligation, [(first, "0.01")])
    assert (await credits.issue(spent)).json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    # A single draft line can never exceed its original line.
    larger = await credits.save(uuid7(), credits.draft(obligation, [(second, "40.01")]))
    assert larger.status_code == 409
    assert larger.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    zero = await credits.save(uuid7(), credits.draft(obligation, [(second, "0.00")]))
    assert zero.status_code == 422
    assert zero.json()["error"]["code"] == "FINANCIAL_AMOUNT_INVALID"
    other, (foreign,) = await credits.invoice()
    stranger = await credits.save(uuid7(), credits.draft(obligation, [(foreign, "1.00")]))
    assert stranger.status_code == 422
    assert stranger.json()["error"]["code"] == "INVALID_REFERENCE"
    rest = await credits.credit(obligation, [(second, "25.00")])
    assert rest["applied"] == "25.00"
    balance = await credits.settlements.balance(obligation)
    assert (balance["credited"], balance["available"]) == ("100.00", "0.00")
    assert (await credits.settlements.balance(other))["credited"] == "0.00"


async def test_another_account_needs_a_reason_and_may_cite_the_recognition_entry(
    credits: CreditWorld,
) -> None:
    deferred, revenue = credits.chart["2100"], credits.chart["4100"]
    obligation, (line,) = await credits.invoice(counter=deferred)
    recognition = uuid7()
    posted = await credits.ledger.post(
        credits.ledger.entry(
            entry_date="2026-10-02",
            lines=[
                {"account_id": str(deferred), "side": "debit", "amount": "100.00"},
                {"account_id": str(revenue), "side": "credit", "amount": "100.00"},
            ],
        ),
        entry=recognition,
    )
    assert posted.status_code == 200, posted.text
    silent = await credits.save(
        uuid7(), credits.draft(obligation, [(line, "50.00")], counter=revenue)
    )
    assert silent.status_code == 422
    assert silent.json()["error"]["code"] == "FINANCIAL_TREATMENT_INVALID"
    pointless = credits.draft(obligation, [(line, "50.00")], counter=deferred)
    pointless["lines"][0]["reason"] = "FAKE same account"  # type: ignore[index]
    refused = await credits.save(uuid7(), pointless)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "FINANCIAL_TREATMENT_INVALID"
    foreign_currency = uuid7()
    euro = await credits.ledger.post(
        credits.ledger.entry(currency="EUR", entry_date="2026-10-02"), entry=foreign_currency
    )
    assert euro.status_code == 200, euro.text
    for cited in (foreign_currency, uuid7()):
        body = credits.draft(obligation, [(line, "50.00")], counter=revenue)
        body["lines"][0] |= {  # type: ignore[index]
            "reason": "FAKE recognized by manual entry",
            "reference_entry_id": str(cited),
        }
        wrong = await credits.save(uuid7(), body)
        assert wrong.status_code == 422, wrong.text
        assert wrong.json()["error"]["code"] == "INVALID_REFERENCE"
    explained = credits.draft(obligation, [(line, "50.00")], counter=revenue)
    explained["lines"][0] |= {  # type: ignore[index]
        "reason": "FAKE revenue was recognized by a manual entry",
        "reference_entry_id": str(recognition),
    }
    document = uuid7()
    saved = await credits.save(document, explained)
    assert saved.status_code == 200, saved.text
    assert saved.json()["lines"][0]["reference_entry_id"] == str(recognition)
    issued = await credits.issue(document)
    assert issued.status_code == 200, issued.text
    assert await credits.journal(issued.json()["entry_id"]) == [
        (str(revenue), "debit", "50.00"),
        (str(credits.settlements.invoices.control), "credit", "50.00"),
    ]
    closing = await credits.closing()
    assert closing["4100"] == ("0.00", "50.00")
    assert closing["2100"] == _ZERO
    assert closing["1200"] == ("50.00", "0.00")


async def test_payable_credit_after_full_payment_is_a_receivable_refund(
    credits: CreditWorld,
) -> None:
    payable, expense = credits.chart["2000"], credits.chart["6900"]
    obligation, (line,) = await credits.invoice(
        counter=expense, direction="payable", control_account_id=str(payable)
    )
    await credits.paid(obligation, "100.00", "FAKE-SUPPLIER-PAY", direction="payable")
    document = await credits.drafted(obligation, [(line, "40.00")], counter=expense)
    # The bank account paid the supplier: it is an asset, but cash is never a control.
    cash = await credits.issue(document, refund=credits.payments.cash)
    assert cash.status_code == 409, cash.text
    assert cash.json()["error"]["code"] == "FINANCIAL_REFUND_ACCOUNT_INVALID"
    issued = await credits.issue(document, refund=credits.chart["1200"])
    assert issued.status_code == 200, issued.text
    view = issued.json()
    assert (view["direction"], view["applied"], view["refund"]) == ("payable", "0.00", "40.00")
    assert await credits.journal(view["entry_id"]) == [
        (str(expense), "credit", "40.00"),
        (str(credits.chart["1200"]), "debit", "40.00"),
    ]
    refund = await credits.settlements.balance(UUID(str(view["refund_obligation_id"])))
    assert (refund["direction"], refund["principal"]) == ("receivable", "40.00")
    original = await credits.settlements.balance(obligation)
    assert (original["paid"], original["credited"], original["available"]) == (
        "100.00",
        "0.00",
        "0.00",
    )


@pytest.mark.parametrize("account", ["1100", "1200", "4000"])
async def test_refund_account_is_an_open_opposite_control_never_cash(
    credits: CreditWorld,
    account: str,
) -> None:
    obligation, (line,) = await credits.invoice()
    await credits.paid(obligation, "100.00", "FAKE-CN-ACCOUNT")
    document = await credits.drafted(obligation, [(line, "10.00")])
    # Bank cash, the receivable control itself and revenue are never a refund liability.
    refused = await credits.issue(document, refund=credits.chart[account])
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "FINANCIAL_REFUND_ACCOUNT_INVALID"
    assert (await credits.settlements.balance(obligation))["credited"] == "0.00"


async def test_credit_cannot_post_before_the_accrual_or_in_a_closed_month(
    credits: CreditWorld,
    app_pool: RuntimePool,
) -> None:
    obligation, (line,) = await credits.invoice()
    document = await credits.drafted(obligation, [(line, "10.00")])
    early = await credits.issue(document, entry_date="2026-09-30")
    assert early.status_code == 422
    assert early.json()["error"]["code"] == "LEDGER_DATE_INVALID"
    closed = await credits.ledger.client.post(
        f"{credits.ledger.base}/periods/2026-10/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=credits.ledger.headers(),
    )
    assert closed.status_code == 200, closed.text
    denied = await credits.issue(document)
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "LEDGER_PERIOD_CLOSED"
    journals = await credits.count(
        app_pool,
        "select count(*) from gba.journal_entries where book_id=%s and source_kind='credit'",
        credits.ledger.book,
    )
    assert journals == 0
    latest = await credits.count(
        app_pool,
        "select max(revision) from gba.financial_document_versions where document_id=%s",
        document,
    )
    assert latest == 1
    assert (await credits.settlements.balance(obligation))["credited"] == "0.00"


async def test_manual_accrual_obligation_takes_a_credit_too(credits: CreditWorld) -> None:
    root = credits.payments.root
    document, line = uuid7(), uuid7()
    body = credits.settlements.invoices.draft_body()
    body["lines"] = [
        {
            "line_id": str(line),
            "counter_account_id": str(credits.settlements.invoices.counter),
            "description": "FAKE manual fee",
            "amount": "80.00",
        }
    ]
    http, headers = credits.ledger.client, credits.ledger.headers
    saved = await http.put(f"{root}/accruals/{document}", json=body, headers=headers())
    assert saved.status_code == 200, saved.text
    issued = await http.post(
        f"{root}/accruals/{document}/issue",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "entry_date": "2026-10-01",
            "attestation": "confirmed_account_treatment",
        },
        headers=headers(),
    )
    assert issued.status_code == 200, issued.text
    obligation = UUID(issued.json()["obligation_id"])
    view = await credits.credit(obligation, [(line, "80.00")])
    assert view["applied"] == "80.00"
    assert (await credits.settlements.balance(obligation))["available"] == "0.00"


async def _race(
    credits: CreditWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    calls: list[Callable[[], Coroutine[Any, Any, httpx.Response]]],
) -> list[httpx.Response]:
    """Queue the calls in order behind one held ledger lock, then let them run."""
    pending: list[asyncio.Task[httpx.Response]] = []
    async with tenant_transaction(app_pool, credits.ledger.business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (credits.ledger.business,))
        try:
            for waiting, call in enumerate(calls, 1):
                pending.append(asyncio.create_task(call()))
                await _wait_for_blocked(owner_conn, waiting)
        except BaseException:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
    return list(await asyncio.gather(*pending))


@pytest.mark.parametrize("credit_first", [True, False])
async def test_credit_and_reserve_wait_on_one_lock_and_keep_the_cap(
    credits: CreditWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    credit_first: bool,
) -> None:
    obligation, (line,) = await credits.invoice()
    world = credits.settlements
    settlement = await world.approved(obligation, "70.00")
    document = await credits.drafted(obligation, [(line, "50.00")])
    calls: list[Callable[[], Coroutine[Any, Any, httpx.Response]]] = [
        lambda: credits.issue(document),
        lambda: world.act(settlement, "reserve", 2),
    ]
    first, second = await _race(
        credits, app_pool, owner_conn, calls if credit_first else calls[::-1]
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    balance = await world.balance(obligation)
    if credit_first:
        assert second.json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
        assert (balance["credited"], balance["reserved"]) == ("50.00", "0.00")
    else:
        assert second.json()["error"]["code"] == "FINANCIAL_STATE_INVALID"
        assert (balance["credited"], balance["reserved"]) == ("0.00", "70.00")


async def test_two_credits_compete_for_one_line_and_only_one_commits(
    credits: CreditWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    obligation, (line,) = await credits.invoice()
    first, second = [await credits.drafted(obligation, [(line, "60.00")]) for _ in range(2)]
    results = await _race(
        credits,
        app_pool,
        owner_conn,
        [lambda: credits.issue(first), lambda: credits.issue(second)],
    )
    assert [r.status_code for r in results] == [200, 409]
    assert results[1].json()["error"]["code"] == "FINANCIAL_CAP_EXCEEDED"
    assert (await credits.settlements.balance(obligation))["credited"] == "60.00"


async def _issue_in_transaction(
    credits: CreditWorld, conn: RuntimeConnection, document: UUID, refund: UUID | None
) -> UUID:
    view = await credit_notes.issue_credit(
        conn,
        business_id=credits.ledger.business,
        book_id=credits.ledger.book,
        document_id=document,
        user_id=credits.ledger.user.user_id,
        actor=f"user:{credits.ledger.user.user_id}",
        key=str(uuid7()),
        body=CreditIssueInput(
            expected_revision=1,
            entry_date=date(2026, 10, 3),
            attestation="confirmed_account_treatment",
            refund_control_account_id=refund,
        ),
    )
    assert view.entry_id is not None
    return view.entry_id


async def test_sql_rechecks_a_credit_journal_and_refund_lineage(
    credits: CreditWorld,
    app_pool: RuntimePool,
) -> None:
    business, book = credits.ledger.business, credits.ledger.book
    obligation, (line,) = await credits.invoice()
    await credits.paid(obligation, "70.00", "FAKE-CN-SQL")
    refund_account = credits.chart["2100"]
    document = await credits.drafted(obligation, [(line, "50.00")])
    # A complete service issue, then a balanced extra pair on its journal.
    with pytest.raises(psycopg.errors.CheckViolation, match="credit journal"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            entry = await _issue_in_transaction(credits, conn, document, refund_account)
            await conn.execute(
                "insert into gba.journal_lines "
                "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) values "
                "(%s,%s,4,%s,%s,'debit',1),(%s,%s,5,%s,%s,'credit',1)",
                (business, entry, book, refund_account, business, entry, book, refund_account),
            )
            await conn.execute("set constraints all immediate")
    # A refund obligation without its issued credit note.
    with pytest.raises(psycopg.errors.CheckViolation, match="issued invoice"):  # noqa: PT012
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.financial_obligations "
                "(tenant_id,book_id,id,source_kind,source_id,source_revision,component,"
                "counterparty_id,counterparty_revision,direction,currency,control_account_id,"
                "principal_minor,created_by) values (%s,%s,%s,'credit_refund',%s,1,'principal',"
                "%s,1,'payable','USD',%s,2000,%s)",
                (
                    business,
                    book,
                    uuid7(),
                    document,
                    credits.settlements.invoices.party,
                    refund_account,
                    credits.ledger.user.user_id,
                ),
            )
            await conn.execute("set constraints all immediate")
    assert (await credits.settlements.balance(obligation))["credited"] == "0.00"
    journals = await credits.count(
        app_pool, "select count(*) from gba.journal_entries where source_kind='credit'"
    )
    assert journals == 0


async def _write_credit_directly(
    credits: CreditWorld,
    conn: RuntimeConnection,
    obligation: UUID,
    line: UUID,
    *,
    total: int,
    applied: int,
    refund_account: UUID | None,
) -> None:
    """A complete credit issue written by SQL alone, in the order the service uses."""
    business, book = credits.ledger.business, credits.ledger.book
    user, party = credits.ledger.user.user_id, credits.settlements.invoices.party
    control, counter = credits.settlements.invoices.control, credits.settlements.invoices.counter
    document, entry, line_id = uuid7(), uuid7(), uuid7()
    refund_obligation = uuid7() if applied < total else None
    await conn.execute(
        "insert into gba.financial_documents (tenant_id,book_id,id,created_by,kind) "
        "values (%s,%s,%s,%s,'credit_note')",
        (business, book, document, user),
    )
    for revision in (1, 2):
        issued = revision == 2
        await conn.execute(
            "insert into gba.financial_document_versions (tenant_id,book_id,document_id,"
            "revision,state,direction,counterparty_id,counterparty_revision,currency,"
            "invoice_date,control_account_id,title,number,principal_minor,line_count,"
            "credited_obligation_id,entry_id,obligation_id,issued_on,attestation,"
            "applied_minor,refund_control_account_id,created_by) values (%s,%s,%s,%s,%s,"
            "'receivable',%s,1,'USD','2026-10-03',%s,'FAKE SQL credit','FAKE-SQL',%s,1,%s,"
            "%s,%s,%s,%s,%s,%s,%s)",
            (
                business,
                book,
                document,
                revision,
                "issued" if issued else "draft",
                party,
                control,
                total,
                obligation,
                entry if issued else None,
                refund_obligation if issued else None,
                "2026-10-03" if issued else None,
                "confirmed_account_treatment" if issued else None,
                applied if issued else None,
                refund_account if issued and refund_obligation else None,
                user,
            ),
        )
        await conn.execute(
            "insert into gba.financial_document_lines (tenant_id,book_id,document_id,revision,"
            "line_no,line_id,credited_line_id,counter_account_id,description,amount_minor) "
            "values (%s,%s,%s,%s,1,%s,%s,%s,'FAKE SQL credit line',%s)",
            (business, book, document, revision, line_id, line, counter, total),
        )
    if refund_obligation is not None:
        await conn.execute(
            "insert into gba.financial_obligations "
            "(tenant_id,book_id,id,source_kind,source_id,source_revision,component,"
            "counterparty_id,counterparty_revision,direction,currency,control_account_id,"
            "principal_minor,created_by) values (%s,%s,%s,'credit_refund',%s,2,'principal',"
            "%s,1,'payable','USD',%s,%s,%s)",
            (
                business,
                book,
                refund_obligation,
                document,
                party,
                refund_account,
                total - applied,
                user,
            ),
        )
    await conn.execute(
        "insert into gba.journal_entries "
        "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
        "values (%s,%s,%s,'2026-10-03','USD','credit',%s,%s)",
        (business, entry, book, str(document), user),
    )
    rows: list[tuple[UUID | None, str, int]] = [(counter, "debit", total)]
    if applied:
        rows.append((control, "credit", applied))
    if refund_obligation is not None:
        rows.append((refund_account, "credit", total - applied))
    for number, (account, side, amount) in enumerate(rows, 1):
        await conn.execute(
            "insert into gba.journal_lines "
            "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
            "values (%s,%s,%s,%s,%s,%s,%s)",
            (business, entry, number, book, account, side, amount),
        )
    if refund_obligation is not None:
        await conn.execute(
            "insert into gba.financial_operation_entries "
            "(tenant_id,book_id,document_id,revision,component,entry_id,obligation_id) "
            "values (%s,%s,%s,2,'principal',%s,%s)",
            (business, book, document, entry, refund_obligation),
        )
    await conn.execute("set constraints all immediate")


async def test_sql_alone_cannot_choose_another_split_exceed_a_line_or_skip_a_reserve(
    credits: CreditWorld,
    app_pool: RuntimePool,
) -> None:
    business = credits.ledger.business
    refund_account = credits.chart["2100"]
    obligation, (line,) = await credits.invoice()
    await credits.paid(obligation, "70.00", "FAKE-CN-DIRECT")
    # Unpaid 30 of a credit of 50: 20 to C and 30 refunded is not the split.
    with pytest.raises(psycopg.errors.CheckViolation, match="unpaid balance"):
        async with tenant_transaction(app_pool, business) as conn:
            await _write_credit_directly(
                credits,
                conn,
                obligation,
                line,
                total=5000,
                applied=2000,
                refund_account=refund_account,
            )
    with pytest.raises(psycopg.errors.CheckViolation, match="credit cap"):
        async with tenant_transaction(app_pool, business) as conn:
            await _write_credit_directly(
                credits, conn, obligation, line, total=5000, applied=5000, refund_account=None
            )
    with pytest.raises(psycopg.errors.CheckViolation, match="exceeds its original line"):
        async with tenant_transaction(app_pool, business) as conn:
            await _write_credit_directly(
                credits,
                conn,
                obligation,
                line,
                total=10001,
                applied=3000,
                refund_account=refund_account,
            )
    async with tenant_transaction(app_pool, business) as conn:
        await _write_credit_directly(
            credits,
            conn,
            obligation,
            line,
            total=5000,
            applied=3000,
            refund_account=refund_account,
        )
    balance = await credits.settlements.balance(obligation)
    assert (balance["paid"], balance["credited"], balance["available"]) == (
        "70.00",
        "30.00",
        "0.00",
    )
    # 50 of the line of 100 is credited: another 60 of it would exceed what remains.
    with pytest.raises(psycopg.errors.CheckViolation, match="uncredited"):
        async with tenant_transaction(app_pool, business) as conn:
            await _write_credit_directly(
                credits,
                conn,
                obligation,
                line,
                total=6000,
                applied=0,
                refund_account=refund_account,
            )
    held, (held_line,) = await credits.invoice()
    await credits.settlements.reserved(held, "1.00")
    with pytest.raises(psycopg.errors.CheckViolation, match="active reserves"):
        async with tenant_transaction(app_pool, business) as conn:
            await _write_credit_directly(
                credits, conn, held, held_line, total=1000, applied=1000, refund_account=None
            )


async def test_issued_credit_history_and_journal_stay_unchanged(
    credits: CreditWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    business, book = credits.ledger.business, credits.ledger.book
    obligation, (line,) = await credits.invoice()
    view = await credits.credit(obligation, [(line, "10.00")])
    entry = view["entry_id"]
    reversal = await credits.ledger.client.post(
        f"{credits.ledger.base}/entries/{entry}/reverse",
        json={"schema_version": 1, "reversal_entry_id": str(uuid7()), "entry_date": "2026-10-04"},
        headers=credits.ledger.headers(),
    )
    assert reversal.status_code == 409, reversal.text
    assert reversal.json()["error"]["code"] == "LEDGER_STATE_INVALID"
    with pytest.raises(psycopg.errors.CheckViolation, match="H-owned journal correction"):
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute(
                "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,"
                "source_kind,source_id,reverses_entry_id,created_by) "
                "values (%s,%s,%s,'2026-10-04','USD','reversal',%s,%s,%s)",
                (business, uuid7(), book, entry, entry, credits.ledger.user.user_id),
            )
    changes = {
        "financial_document_versions": "applied_minor=0",
        "financial_document_lines": "reason='FAKE'",
    }
    for table, change in changes.items():
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="kept unchanged"),
            owner_tenant_transaction(owner_conn, business),
        ):
            owner_conn.execute(
                sql.SQL("update gba.{} set " + change + " where document_id=%s").format(
                    sql.Identifier(table)
                ),
                (UUID(str(view["document_id"])),),
            )
    assert (await credits.settlements.balance(obligation))["credited"] == "10.00"


async def test_off_and_withdrawn_readiness_block_credits_but_keep_history(
    credits: CreditWorld,
    idp: FakeIdp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    obligation, (line,) = await credits.invoice()
    view = await credits.credit(obligation, [(line, "10.00")])
    document = await credits.drafted(obligation, [(line, "10.00")])
    feature = modules.MODULES_BY_ID["finance_documents"]
    with monkeypatch.context() as patch:
        patch.setitem(
            modules.MODULES_BY_ID,
            "finance_documents",
            feature.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
        )
        unready = await credits.issue(document)
        assert unready.status_code == 409
        assert unready.json()["error"]["code"] == "MODULE_NOT_READY"
    config = Config(credits.ledger.client, idp)
    await config.publish(credits.ledger.user, credits.ledger.business, 2, ["booking_resources"])
    off = await credits.issue(document)
    assert off.status_code == 409
    assert off.json()["error"]["code"] == "MODULE_DISABLED"
    blocked = await credits.save(uuid7(), credits.draft(obligation, [(line, "1.00")]))
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "MODULE_DISABLED"
    read = await credits.ledger.client.get(
        f"{credits.base}/{view['document_id']}", headers=credits.ledger.auth
    )
    assert read.status_code == 200
    assert read.json() == view
    assert (await credits.settlements.balance(obligation))["credited"] == "10.00"


async def test_credit_replay_recovery_and_cancel_before_late_original(
    credits: CreditWorld,
    owner_conn: psycopg.Connection,
) -> None:
    obligation, (line,) = await credits.invoice()
    document, key = await credits.drafted(obligation, [(line, "10.00")]), str(uuid7())
    issued = await credits.issue(document, key=key)
    assert issued.status_code == 200, issued.text
    business = credits.ledger.business
    with owner_tenant_transaction(owner_conn, business):
        deleted = owner_conn.execute(
            "delete from gba.idempotency_keys where tenant_id=%s "
            "and operation='business.finance.credit_issue' and idempotency_key=%s",
            (business, key),
        )
        assert deleted.rowcount == 1
    command = f"/v1/businesses/{business}/financial-documents/commands"
    reference = {
        "schema_version": 1,
        "operation": "credit_issue",
        "book_id": str(credits.ledger.book),
        "subject_id": str(document),
        "revision": 2,
    }
    http, auth = credits.ledger.client, credits.ledger.auth
    resolved = await http.post(f"{command}/{key}/resolve", json=reference, headers=auth)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "committed"
    assert (await credits.issue(document, key=key)).json() == issued.json()
    late, late_key = await credits.drafted(obligation, [(line, "5.00")]), str(uuid7())
    cancelled = await http.post(
        f"{command}/{late_key}/cancel",
        json={**reference, "subject_id": str(late)},
        headers=auth,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    sealed = await credits.issue(late, key=late_key)
    assert sealed.status_code == 409
    assert sealed.json()["error"]["code"] == "FINANCIAL_COMMAND_CANCELLED"
    assert (await credits.settlements.balance(obligation))["credited"] == "10.00"


@pytest.mark.parametrize(
    ("role", "branch", "expected"),
    [
        ("owner", False, 200),
        ("front_desk", False, 403),
        ("artist", False, 403),
        ("manager", True, 403),
    ],
)
async def test_credit_routes_keep_company_finance_permissions(
    credits: CreditWorld,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
    branch: bool,
    expected: int,
) -> None:
    obligation, (line,) = await credits.invoice()
    document = await credits.drafted(obligation, [(line, "10.00")])
    member = seed_user(owner_conn, f"FAKE-H3-credit-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=credits.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    auth = idp.bearer(member.subject, email=member.email)
    read = await credits.ledger.client.get(f"{credits.base}/{document}", headers=auth)
    assert read.status_code == expected, read.text
    if expected != 200:
        keyed = {**auth, "Idempotency-Key": str(uuid7())}
        assert (await credits.issue(document, headers=keyed)).status_code == 403
        drafted = await credits.save(
            uuid7(), credits.draft(obligation, [(line, "1.00")]), headers=keyed
        )
        assert drafted.status_code == 403
        assert (await credits.settlements.balance(obligation))["credited"] == "0.00"


async def test_another_company_cannot_read_or_credit_these_obligations(
    credits: CreditWorld,
    world: BookingWorld,
    manager_b: object,
    idp: FakeIdp,
) -> None:
    obligation, (line,) = await credits.invoice()
    document = await credits.drafted(obligation, [(line, "10.00")])
    foreign = Config(credits.ledger.client, idp).auth(manager_b)  # type: ignore[arg-type]
    http = credits.ledger.client
    assert (await http.get(f"{credits.base}/{document}", headers=foreign)).status_code == 403
    keyed = {**foreign, "Idempotency-Key": str(uuid7())}
    assert (await credits.issue(document, headers=keyed)).status_code == 403
    other = credits.base.replace(str(credits.ledger.business), str(world.b.tenant_id))
    stolen = await http.put(
        f"{other}/{uuid7()}",
        json=credits.draft(obligation, [(line, "10.00")]),
        headers={**foreign, "Idempotency-Key": str(uuid7())},
    )
    assert stolen.status_code in (403, 404, 409, 422), stolen.text
    assert (await credits.settlements.balance(obligation))["credited"] == "0.00"


_ISSUED_REFS = ("financial_document_versions", "financial_versions_issued_refs")
_OBLIGATION_SOURCE = ("financial_obligations", "financial_obligations_source_kind_check")


@pytest.mark.parametrize(
    ("change", "restore"),
    [
        (
            "alter table gba.financial_document_versions "
            "drop constraint financial_versions_issued_refs",
            approved_check(*_ISSUED_REFS),
        ),
        (
            widened_check(*_OBLIGATION_SOURCE, "source_kind = 'refund'"),
            approved_check(*_OBLIGATION_SOURCE),
        ),
        (
            "alter table gba.financial_document_versions "
            "drop constraint financial_versions_credited_fk",
            "alter table gba.financial_document_versions add constraint "
            "financial_versions_credited_fk foreign key (tenant_id, book_id, "
            "credited_obligation_id) references gba.financial_obligations(tenant_id, book_id, id)",
        ),
        (
            "alter table gba.financial_document_lines drop constraint financial_lines_credit_refs",
            approved_check("financial_document_lines", "financial_lines_credit_refs"),
        ),
        (
            "grant update on gba.financial_document_lines to gba_runtime",
            "revoke update on gba.financial_document_lines from gba_runtime",
        ),
        (
            "create or replace function gba.obligation_balance(tenant uuid, book uuid, "
            "obligation uuid) returns table (principal_minor bigint, paid_minor bigint, "
            "credited_minor bigint, reserved_minor bigint) language plpgsql as $$ begin "
            "return query select 1::bigint, 0::bigint, 0::bigint, 0::bigint; end; $$",
            packaged_function("obligation_balance"),
        ),
        (
            "create or replace function gba.enforce_financial_line() returns trigger "
            "language plpgsql as $$ begin return new; end; $$",
            packaged_function("enforce_financial_line"),
        ),
    ],
)
async def test_damaged_credit_controls_fail_readiness_with_503(
    credits: CreditWorld,
    owner_conn: psycopg.Connection,
    change: str,
    restore: str,
) -> None:
    http, auth, base = credits.ledger.client, credits.ledger.auth, credits.ledger.base
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
