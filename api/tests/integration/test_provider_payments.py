"""K3a: an observed provider payment or refund confirms a reserved H settlement; synthetic only.

No provider account, real key, network call or real money is involved. A finance user applies;
the amount, currency and date come from attested and decided provider facts.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import settlements
from gorgona_booking.business.settlement_contracts import ProviderPaymentConfirmInput
from gorgona_booking.db.pool import RuntimePool, set_tenant_context, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.errors import NotFoundError
from gorgona_booking.providers import receipt_worker as worker
from tests.integration import test_credit_notes as credit_shared
from tests.integration import test_external_payments as payment_shared
from tests.integration import test_invoice_issue as invoice_shared
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_credit_notes import CreditWorld
from tests.integration.test_provider_receipt_attestations import Routed
from tests.integration.test_settlements import SettlementWorld, _wait_for_blocked
from tests.support.fake_idp import FakeIdp
from tests.unit import test_stripe_event_boundary as signed

pytestmark = pytest.mark.anyio
client = invoice_shared.client
idp = invoice_shared.idp
manager_a = invoice_shared.manager_a
manager_b = invoice_shared.manager_b
enabled = invoice_shared.enabled
invoices = invoice_shared.invoices
payments = payment_shared.payments
credits = credit_shared.credits
inbox = attested.inbox
writer_pool = attested.writer_pool
routed = attested.routed
worker_pool = decided.worker_pool
blocked_by = decided.blocked_by
backend = decided.backend
# 2026-10-05 12:00 UTC: every synthetic event is created then, before every entry date below.
CREATED = 1_791_201_600
ENTRY = "2026-10-06"


def event(kind: str, **changes: Any) -> bytes:
    """One synthetic Stripe-shaped event with its own ID, created at a fixed past instant."""
    value = json.loads(decided.stripe(kind, **changes))
    value["created"] = CREATED
    return signed.body(value)


@dataclass(frozen=True)
class Money:
    credits: CreditWorld
    routed: Routed
    writer: RuntimePool
    worker: RuntimePool

    @property
    def world(self) -> SettlementWorld:
        return self.credits.settlements

    @property
    def root(self) -> str:
        return self.credits.payments.root

    @property
    def http(self) -> httpx.AsyncClient:
        return self.credits.ledger.client

    @property
    def clearing(self) -> UUID:
        return self.credits.chart["1000"]

    async def register(self, account: UUID | None = None) -> httpx.Response:
        return await self.http.put(
            f"{self.root}/provider-connections/{self.routed.connection_id}/clearing-account",
            json={"schema_version": 1, "account_id": str(account or self.clearing)},
            headers=self.credits.ledger.headers(),
        )

    async def observe(self, *raws: bytes) -> list[UUID]:
        events = await decided.receive_all(self.writer, self.routed, *raws)
        await worker.process_batch(self.worker, tenant_id=self.routed.tenant_id)
        return events

    async def operation(self, object_id: str = "pi_FAKEpayment1") -> UUID:
        async with tenant_transaction(self.worker, self.routed.tenant_id) as conn:
            row = await (
                await conn.execute(
                    "select id from gba.provider_operations where tenant_id=%s "
                    "and provider_object_id=%s",
                    (self.routed.tenant_id, object_id),
                )
            ).fetchone()
        assert row is not None
        return UUID(str(row[0]))

    def body(
        self,
        operation: UUID,
        allocations: list[tuple[UUID, str]],
        sequence: int = 3,
        **changes: object,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "expected_sequence": sequence,
            "operation_id": str(operation),
            "entry_date": ENTRY,
            "allocations": [
                {"obligation_id": str(obligation), "amount": amount}
                for obligation, amount in allocations
            ],
            **changes,
        }

    async def apply(
        self,
        settlement: UUID,
        operation: UUID,
        allocations: list[tuple[UUID, str]],
        *,
        sequence: int = 3,
        payment: UUID | None = None,
        key: str | None = None,
        headers: dict[str, str] | None = None,
        **changes: object,
    ) -> httpx.Response:
        return await self.http.post(
            f"{self.root}/settlements/{settlement}/provider-confirmations/{payment or uuid7()}",
            json=self.body(operation, allocations, sequence, **changes),
            headers=headers or self.credits.ledger.headers(key),
        )

    async def listed(self) -> list[dict[str, Any]]:
        response = await self.http.get(
            f"{self.root}/provider-operations", headers=self.credits.ledger.auth
        )
        assert response.status_code == 200, response.text
        items: list[dict[str, Any]] = response.json()["items"]
        return items

    async def payment(self, payment: UUID) -> dict[str, Any]:
        response = await self.http.get(
            f"{self.root}/payments/{payment}", headers=self.credits.ledger.auth
        )
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result

    async def count(self, app_pool: RuntimePool, table: str) -> int:
        return await self.credits.count(
            app_pool,
            f"select count(*) from gba.{table} where book_id=%s",
            self.credits.ledger.book,
        )

    async def reserved(self, amount: str = "10.00") -> tuple[UUID, UUID]:
        obligation = await self.world.obligation(amount)
        return obligation, await self.world.reserved(obligation, amount)

    async def paid(self, amount: str = "10.00") -> tuple[UUID, UUID, UUID]:
        """A reserved receivable settlement, an observed payment and its application."""
        obligation, settlement = await self.reserved(amount)
        await self.observe(event("payment_intent.succeeded"))
        payment = uuid7()
        applied = await self.apply(
            settlement, await self.operation(), [(obligation, amount)], payment=payment
        )
        assert applied.status_code == 200, applied.text
        return obligation, settlement, payment


@pytest.fixture
async def money(
    credits: CreditWorld, routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> Money:
    assert routed.book_id == credits.ledger.book
    result = Money(credits, routed, writer_pool, worker_pool)
    registered = await result.register()
    assert registered.status_code == 200, registered.text
    return result


def actual_date(owner_conn: psycopg.Connection, business: UUID) -> str:
    row = owner_conn.execute(
        "select (pg_catalog.to_timestamp(%s) at time zone gba.business_timezone(%s))::date",
        (CREATED, business),
    ).fetchone()
    assert row is not None
    return str(row[0].isoformat())


def error(response: httpx.Response) -> tuple[int, str, dict[str, Any]]:
    body = response.json()["error"]
    return response.status_code, body["code"], body.get("details") or {}


async def _cancel(*pending: asyncio.Task[Any]) -> None:
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


async def test_provider_money_routes_require_authentication(client: httpx.AsyncClient) -> None:
    base = f"/v1/businesses/{uuid7()}/financial-documents/books/{uuid7()}"
    assert (await client.get(f"{base}/provider-operations")).status_code == 401
    refused = await client.post(
        f"{base}/settlements/{uuid7()}/provider-confirmations/{uuid7()}", json={}
    )
    assert refused.status_code == 401
    registered = await client.put(
        f"{base}/provider-connections/{uuid7()}/clearing-account", json={}
    )
    assert registered.status_code == 401


# M-01 -----------------------------------------------------------------------


async def test_an_observed_payment_posts_once_with_provider_provenance(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(
        event("payment_intent.succeeded"), event("charge.succeeded", object_id="ch_FAKEcharge1")
    )
    operation = await money.operation()
    (listed,) = await money.listed()
    assert listed["operation_id"] == str(operation)
    assert (listed["kind"], listed["provider_object_id"], listed["currency"]) == (
        "payment",
        "pi_FAKEpayment1",
        "USD",
    )
    assert (listed["amount"], listed["state"], listed["payment_id"]) == ("10.00", "observed", None)
    payment, key = uuid7(), str(uuid7())
    applied = await money.apply(
        settlement, operation, [(obligation, "10.00")], payment=payment, key=key
    )
    assert applied.status_code == 200, applied.text
    assert (applied.json()["status"], applied.json()["sequence"]) == ("confirmed", 4)
    replay = await money.apply(
        settlement, operation, [(obligation, "10.00")], payment=payment, key=key
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == applied.json()
    recorded = await money.payment(payment)
    assert (recorded["attestation"], recorded["provider_operation_id"]) == (
        "provider_observed",
        str(operation),
    )
    assert (recorded["amount"], recorded["cash_account_id"]) == ("10.00", str(money.clearing))
    assert (recorded["source_account_alias"], recorded["external_reference"]) == (
        "stripe_connect",
        "pi_FAKEpayment1",
    )
    assert recorded["actual_external_date"] == actual_date(owner_conn, money.routed.tenant_id)
    assert recorded["entry_date"] == ENTRY
    assert await money.credits.journal(recorded["entry_id"]) == [
        (str(money.clearing), "debit", "10.00"),
        (str(money.world.invoices.control), "credit", "10.00"),
    ]
    balance = await money.world.balance(obligation)
    assert (balance["paid"], balance["reserved"]) == ("10.00", "0.00")
    assert await money.count(app_pool, "external_payment_provenance") == 1
    (after,) = await money.listed()
    assert (after["state"], after["payment_id"]) == ("applied", str(payment))


# M-02 -----------------------------------------------------------------------


async def test_an_operation_is_applied_once_across_settlements_and_keys(
    money: Money, app_pool: RuntimePool
) -> None:
    obligation, _, payment = await money.paid()
    again, other = await money.reserved()
    refused = await money.apply(other, await money.operation(), [(again, "10.00")])
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_APPLIED")
    assert error(refused)[2]["payment_id"] == str(payment)
    assert (await money.world.balance(again))["paid"] == "0.00"
    assert (await money.world.balance(obligation))["paid"] == "10.00"
    assert await money.count(app_pool, "external_payments") == 1


async def test_two_applications_of_one_operation_wait_and_one_wins(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    targets = [await money.reserved() for _ in range(2)]
    business = money.credits.ledger.business
    async with tenant_transaction(app_pool, business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (business,))
        pending = [
            asyncio.create_task(money.apply(settlement, operation, [(obligation, "10.00")]))
            for obligation, settlement in targets
        ]
        try:
            await _wait_for_blocked(owner_conn, 2)
        except BaseException:
            await _cancel(*pending)
            raise
    results = await asyncio.gather(*pending)
    assert sorted(r.status_code for r in results) == [200, 409]
    loser = next(r for r in results if r.status_code == 409)
    assert error(loser)[1] == "PROVIDER_OPERATION_APPLIED"
    assert await money.count(app_pool, "external_payments") == 1
    assert await money.count(app_pool, "external_payment_provenance") == 1


# M-03 -----------------------------------------------------------------------


async def test_amount_currency_and_direction_come_from_the_provider(
    money: Money, app_pool: RuntimePool
) -> None:
    world = money.world
    obligation, settlement = await money.reserved()
    await money.observe(
        event("payment_intent.succeeded"),
        event("payment_intent.succeeded", object_id="pi_FAKEeuro1", currency="eur"),
    )
    operation = await money.operation()
    # The amount is the provider's: allocations must add up to it, and no amount is accepted.
    short = await money.apply(settlement, operation, [(obligation, "9.00")])
    assert error(short)[:2] == (422, "FINANCIAL_AMOUNT_INVALID")
    typed = await money.apply(settlement, operation, [(obligation, "10.00")], amount="10.00")
    assert typed.status_code == 422, typed.text
    # USD only (owner decision); another currency never posts.
    euro = await money.apply(
        settlement, await money.operation("pi_FAKEeuro1"), [(obligation, "10.00")]
    )
    assert error(euro)[:2] == (409, "PROVIDER_PAYMENT_MISMATCH")
    assert error(euro)[2]["reason"] == "currency"
    # A payment confirms money owed to the business, never a payable settlement.
    invoice, (line,) = await money.credits.invoice("10.00")
    await money.credits.paid(invoice, "10.00", "FAKE-K3A-PAID")
    refund, payable = await _refund_settlement(money, invoice, line, "4.00")
    wrong = await money.apply(payable, operation, [(refund, "4.00")])
    assert error(wrong)[:2] == (409, "PROVIDER_PAYMENT_MISMATCH")
    assert error(wrong)[2]["reason"] == "direction"
    # The reserve caps the line and the accrual bounds the entry date, as for any payment.
    small = await world.obligation("10.00")
    capped = await world.reserved(small, "5.00")
    over = await money.apply(capped, operation, [(small, "10.00")])
    assert error(over)[:2] == (409, "FINANCIAL_CAP_EXCEEDED")
    early = await money.apply(
        settlement, operation, [(obligation, "10.00")], entry_date="2026-09-01"
    )
    assert error(early)[1] == "LEDGER_DATE_INVALID"
    missing = await money.apply(settlement, uuid7(), [(obligation, "10.00")])
    assert error(missing)[:2] == (404, "NOT_FOUND")
    assert await money.count(app_pool, "external_payment_provenance") == 0
    assert (await world.balance(obligation))["paid"] == "0.00"


async def test_the_clearing_account_is_registered_once_and_is_never_a_control(
    credits: CreditWorld,
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    app_pool: RuntimePool,
) -> None:
    money = Money(credits, routed, writer_pool, worker_pool)
    obligation, settlement = await money.reserved()
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    unregistered = await money.apply(settlement, operation, [(obligation, "10.00")])
    assert error(unregistered)[:2] == (409, "PROVIDER_CLEARING_ACCOUNT_REQUIRED")
    # A control account or a liability is never the clearing account.
    for account in (money.world.invoices.control, credits.chart["2100"]):
        wrong = await money.register(account)
        assert error(wrong)[:2] == (409, "FINANCIAL_STATE_INVALID")
    first = await money.register()
    assert first.status_code == 200, first.text
    assert (first.json()["account_id"], first.json()["connection_id"]) == (
        str(money.clearing),
        str(routed.connection_id),
    )
    assert (await money.register()).json() == first.json()
    other = await money.register(credits.chart["1400"])
    assert error(other)[:2] == (409, "PROVIDER_CLEARING_ACCOUNT_REGISTERED")
    applied = await money.apply(settlement, operation, [(obligation, "10.00")])
    assert applied.status_code == 200, applied.text
    assert await money.count(app_pool, "provider_clearing_accounts") == 1


# M-04 -----------------------------------------------------------------------


_NOT_READY = [
    ("not_final", [event("payment_intent.processing", status="processing")], False),
    (
        "needs_review",
        [
            event("payment_intent.succeeded"),
            event("charge.succeeded", object_id="ch_FAKEcharge1", amount=900),
        ],
        False,
    ),
    ("pending", [event("payment_intent.succeeded")], True),
]


@pytest.mark.parametrize(
    ("reason", "raws", "late"), _NOT_READY, ids=[reason for reason, _, _ in _NOT_READY]
)
async def test_an_operation_that_is_not_ready_moves_no_money(
    money: Money, app_pool: RuntimePool, reason: str, raws: list[bytes], late: bool
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(*raws)
    if late:
        # Attested but not decided yet: its decision is still to come.
        await decided.receive_all(
            money.writer, money.routed, event("charge.succeeded", object_id="ch_FAKEcharge2")
        )
    refused = await money.apply(settlement, await money.operation(), [(obligation, "10.00")])
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_NOT_READY")
    assert error(refused)[2]["reason"] == reason
    (listed,) = await money.listed()
    assert listed["state"] == reason
    assert await money.count(app_pool, "external_payments") == 0


async def test_a_mismatching_delivery_refuses_the_operation(
    money: Money, app_pool: RuntimePool
) -> None:
    obligation, settlement = await money.reserved()
    raw = event("payment_intent.succeeded")
    await money.observe(raw)
    variant = raw.replace(b'"amount_received":1000', b'"amount_received":900')
    assert variant != raw
    received = await attested.receive(money.writer, money.routed, variant)
    assert received.disposition == "conflict"
    refused = await money.apply(settlement, await money.operation(), [(obligation, "10.00")])
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_NOT_READY")
    assert error(refused)[2]["reason"] == "delivery_conflict"
    assert await money.count(app_pool, "external_payments") == 0


@pytest.mark.parametrize("table", ["provider_receipt_connections", "provider_verification_configs"])
async def test_a_revoked_connection_or_config_refuses_new_money(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection, table: str
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    target = (
        money.routed.connection_id
        if table == "provider_receipt_connections"
        else money.routed.verification_config_id
    )
    with owner_tenant_transaction(owner_conn, money.routed.tenant_id):
        owner_conn.execute(
            f"update gba.{table} set revoked=true,revoked_reason='compromise' "
            "where tenant_id=%s and id=%s",
            (money.routed.tenant_id, target),
        )
    refused = await money.apply(settlement, operation, [(obligation, "10.00")])
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_NOT_READY")
    assert error(refused)[2]["reason"] == "revoked"
    assert await money.count(app_pool, "external_payments") == 0


# M-05 -----------------------------------------------------------------------


async def test_a_worker_decision_and_an_application_wait_for_each_other(
    money: Money, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    (late,) = await decided.receive_all(
        money.writer, money.routed, event("charge.succeeded", object_id="ch_FAKEcharge3")
    )
    holder = uuid4()
    async with tenant_transaction(money.worker, money.routed.tenant_id) as conn:
        generation = await worker.claim(
            conn, money.routed.tenant_id, late, holder=holder, lease_seconds=60
        )
    assert generation is not None
    follower = None
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        async with money.worker.connection() as conn, conn.transaction():
            await set_tenant_context(conn, money.routed.tenant_id)
            decision = await worker.decide(
                conn, money.routed.tenant_id, late, holder=holder, generation=generation
            )
            follower = asyncio.create_task(
                money.apply(settlement, operation, [(obligation, "10.00")])
            )
            # The application waits on the operation row the decision holds.
            await blocked_by(monitor, await backend(conn), "")
            assert not follower.done()
        applied = await asyncio.wait_for(follower, 15)
    finally:
        if follower is not None and not follower.done():
            await _cancel(follower)
        await monitor.close()
    assert (decision.outcome, decision.reason) == ("observed", "success")
    # It saw the committed decision: both events agree, so the payment posts.
    assert applied.status_code == 200, applied.text
    assert await money.count(app_pool, "external_payment_provenance") == 1


# M-06 -----------------------------------------------------------------------


async def _refund_settlement(
    money: Money, invoice: UUID, line: UUID, amount: str
) -> tuple[UUID, UUID]:
    """A credit note's refund obligation and its reserved payable settlement."""
    view = await money.credits.credit(invoice, [(line, amount)], refund=money.credits.chart["2100"])
    refund = UUID(str(view["refund_obligation_id"]))
    settlement = uuid7()
    prepared = await money.world.prepare(settlement, [(refund, amount)], direction="payable")
    assert prepared.status_code == 200, prepared.text
    for action, sequence in (("approve", 1), ("reserve", 2)):
        assert (await money.world.act(settlement, action, sequence)).status_code == 200
    return refund, settlement


async def test_a_refund_applies_after_its_parent_within_its_amount(
    money: Money, app_pool: RuntimePool
) -> None:
    invoice, (line,) = await money.credits.invoice("10.00")
    settlement = await money.world.reserved(invoice, "10.00")
    await money.observe(
        event("payment_intent.succeeded"),
        event("refund.updated", object_id="re_FAKErefund1", amount=400),
        event("refund.updated", object_id="re_FAKErefund2", amount=700),
    )
    paid = await money.apply(settlement, await money.operation(), [(invoice, "10.00")])
    assert paid.status_code == 200, paid.text
    refund, payable = await _refund_settlement(money, invoice, line, "4.00")
    refund_operation = await money.operation("re_FAKErefund1")
    # A refund confirms only a refund obligation, never an ordinary receivable.
    other, receivable = await money.reserved("4.00")
    wrong = await money.apply(receivable, refund_operation, [(other, "4.00")])
    assert error(wrong)[:2] == (409, "PROVIDER_PAYMENT_MISMATCH")
    assert error(wrong)[2]["reason"] == "direction"
    payment = uuid7()
    refunded = await money.apply(payable, refund_operation, [(refund, "4.00")], payment=payment)
    assert refunded.status_code == 200, refunded.text
    recorded = await money.payment(payment)
    assert (recorded["direction"], recorded["external_reference"]) == ("payable", "re_FAKErefund1")
    assert await money.credits.journal(recorded["entry_id"]) == [
        (str(money.clearing), "credit", "4.00"),
        (str(money.credits.chart["2100"]), "debit", "4.00"),
    ]
    # 4.00 + 7.00 would exceed the 10.00 its parent received.
    second, payable_2 = await _refund_settlement(money, invoice, line, "6.00")
    over = await money.apply(payable_2, await money.operation("re_FAKErefund2"), [(second, "6.00")])
    assert error(over)[:2] == (409, "PROVIDER_PAYMENT_MISMATCH")
    assert error(over)[2]["reason"] == "refund_cap"
    assert await money.count(app_pool, "external_payment_provenance") == 2


async def test_a_refund_before_its_parent_payment_is_refused(
    money: Money, app_pool: RuntimePool
) -> None:
    invoice, (line,) = await money.credits.invoice("10.00")
    # The money arrived through a manual confirmation, not the provider path.
    await money.credits.paid(invoice, "10.00", "FAKE-K3A-MANUAL")
    await money.observe(event("refund.updated", object_id="re_FAKErefund3", amount=400))
    refund, payable = await _refund_settlement(money, invoice, line, "4.00")
    early = await money.apply(payable, await money.operation("re_FAKErefund3"), [(refund, "4.00")])
    assert error(early)[:2] == (409, "PROVIDER_PAYMENT_MISMATCH")
    assert error(early)[2]["reason"] == "refund_parent"
    assert await money.count(app_pool, "external_payment_provenance") == 0


# M-07 -----------------------------------------------------------------------


async def test_a_closed_period_and_a_concurrent_close_have_one_outcome(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    obligation, settlement = await money.reserved()
    # Everything later steps need is issued before October closes.
    again, other = await money.reserved()
    await money.observe(
        event("payment_intent.succeeded"),
        event("payment_intent.succeeded", object_id="pi_FAKElater1"),
    )
    operation = await money.operation()
    ledger = money.credits.ledger
    async with tenant_transaction(app_pool, ledger.business) as conn:
        await conn.execute("select gba.lock_ledger(%s)", (ledger.business,))
        pending = [
            asyncio.create_task(money.apply(settlement, operation, [(obligation, "10.00")])),
            asyncio.create_task(
                ledger.client.post(
                    f"{ledger.base}/periods/2026-10/close",
                    json={"schema_version": 1, "expected_sequence": 0},
                    headers=ledger.headers(),
                )
            ),
        ]
        try:
            await _wait_for_blocked(owner_conn, 2)
        except BaseException:
            await _cancel(*pending)
            raise
    applied, closed = await asyncio.gather(*pending)
    assert closed.status_code == 200, closed.text
    posted = await money.count(app_pool, "external_payments")
    if applied.status_code == 200:
        assert posted == 1
    else:
        assert error(applied)[:2] == (409, "LEDGER_PERIOD_CLOSED")
        assert posted == 0
        assert await money.count(app_pool, "external_payment_provenance") == 0
        assert (await money.world.balance(obligation))["reserved"] == "10.00"
    # Once closed, the period refuses every later application with no partial row.
    late = await money.apply(other, await money.operation("pi_FAKElater1"), [(again, "10.00")])
    assert error(late)[:2] == (409, "LEDGER_PERIOD_CLOSED")
    assert await money.count(app_pool, "external_payments") == posted


# M-08 -----------------------------------------------------------------------


async def _forge(
    money: Money, app_pool: RuntimePool, settlement: UUID, obligation: UUID, attestation: str
) -> None:
    """Write a whole confirmation by SQL alone; provenance only on a manual one."""
    ledger = money.credits.ledger
    business, book, user = ledger.business, ledger.book, ledger.user.user_id
    payment, entry = uuid7(), uuid7()
    control = money.world.invoices.control
    operation = await money.operation()
    async with tenant_transaction(app_pool, business) as conn:
        await conn.execute(
            "insert into gba.settlement_events (tenant_id,book_id,settlement_id,sequence,kind,"
            "created_by) values (%s,%s,%s,3,'confirmed',%s)",
            (business, book, settlement, user),
        )
        await conn.execute(
            "insert into gba.external_payments (tenant_id,book_id,id,settlement_id,sequence,"
            "direction,currency,amount_minor,actual_external_date,entry_date,cash_account_id,"
            "source_account_alias,external_reference,attestation,entry_id,created_by) "
            "values (%s,%s,%s,%s,3,'receivable','USD',1000,'2026-10-05',%s,%s,"
            "'stripe_connect','pi_FAKEpayment1',%s,%s,%s)",
            (business, book, payment, settlement, ENTRY, money.clearing, attestation, entry, user),
        )
        await conn.execute(
            "insert into gba.external_payment_allocations "
            "(tenant_id,book_id,payment_id,line_no,obligation_id,amount_minor) "
            "values (%s,%s,%s,1,%s,1000)",
            (business, book, payment, obligation),
        )
        await conn.execute(
            "insert into gba.journal_entries "
            "(tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
            "values (%s,%s,%s,%s,'USD','payment',%s,%s)",
            (business, entry, book, ENTRY, str(payment), user),
        )
        await conn.execute(
            "insert into gba.journal_lines "
            "(tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) values "
            "(%s,%s,1,%s,%s,'debit',1000),(%s,%s,2,%s,%s,'credit',1000)",
            (business, entry, book, money.clearing, business, entry, book, control),
        )
        if attestation == "manual_attestation":
            await conn.execute(
                "insert into gba.external_payment_provenance "
                "(tenant_id,book_id,payment_id,operation_id,created_by) values (%s,%s,%s,%s,%s)",
                (business, book, payment, operation, user),
            )


@pytest.mark.parametrize("attestation", ["provider_observed", "manual_attestation"])
async def test_sql_alone_cannot_forge_provider_provenance(
    money: Money, app_pool: RuntimePool, attestation: str
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(event("payment_intent.succeeded"))
    # An observed payment without provenance, or provenance on a manual one, never commits.
    with pytest.raises(psycopg.Error):
        await _forge(money, app_pool, settlement, obligation, attestation)
    assert await money.count(app_pool, "external_payments") == 0


async def test_provenance_is_permanent_and_scoped_to_its_company(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    _, _, payment = await money.paid()
    business = money.credits.ledger.business
    for statement in (
        "update gba.external_payment_provenance set created_by=created_by where payment_id=%s",
        "delete from gba.external_payment_provenance where payment_id=%s",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, business) as conn:
                await conn.execute(statement, (payment,))
    with pytest.raises(psycopg.Error), owner_tenant_transaction(owner_conn, business):
        owner_conn.execute(
            "delete from gba.external_payment_provenance where payment_id=%s", (payment,)
        )
    # Another company reads no provider operation, decision, provenance or clearing account.
    async with tenant_transaction(app_pool, uuid7()) as conn:
        for table in (
            "provider_operations",
            "provider_event_decisions",
            "external_payment_provenance",
            "provider_clearing_accounts",
        ):
            row = await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()
            assert row == (0,)


async def test_worker_and_writer_cannot_reach_provider_money(money: Money) -> None:
    await money.paid()
    for pool in (money.worker, money.writer):
        for table in (
            "external_payments",
            "external_payment_provenance",
            "provider_clearing_accounts",
            "settlement_documents",
            "journal_entries",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with tenant_transaction(pool, money.routed.tenant_id) as conn:
                    await conn.execute(f"select 1 from gba.{table} limit 1")


# M-09 -----------------------------------------------------------------------


async def test_a_manual_payment_naming_the_provider_id_needs_linking(
    money: Money, app_pool: RuntimePool
) -> None:
    obligation, settlement = await money.reserved("20.00")
    manual = uuid7()
    recorded = await money.credits.payments.confirm(
        settlement,
        3,
        [(obligation, "10.00")],
        "10.00",
        "FAKE Stripe pi_FAKEpayment1",
        payment=manual,
    )
    assert recorded.status_code == 200, recorded.text
    await money.observe(event("payment_intent.succeeded"))
    refused = await money.apply(
        settlement, await money.operation(), [(obligation, "10.00")], sequence=4
    )
    assert error(refused)[:2] == (409, "PROVIDER_PAYMENT_LINK_REQUIRED")
    assert error(refused)[2]["payment_id"] == str(manual)
    assert await money.count(app_pool, "external_payments") == 1


async def test_a_provider_payment_is_voided_like_a_manual_one_and_never_reapplied(
    money: Money, app_pool: RuntimePool
) -> None:
    obligation, _, payment = await money.paid()
    # A fully confirmed settlement is final; the void goes through the existing H path.
    settlement = (await money.payment(payment))["settlement_id"]
    voided = await money.http.post(
        f"{money.root}/settlements/{settlement}/confirmations/{payment}/void",
        json={
            "schema_version": 1,
            "expected_sequence": 4,
            "entry_date": ENTRY,
            "attestation": "attested_erroneous_confirmation",
            "reason": "FAKE applied to the wrong invoice",
            "evidence_source": "FAKE finance review",
        },
        headers=money.credits.ledger.headers(),
    )
    assert voided.status_code == 200, voided.text
    recorded = await money.payment(payment)
    assert (recorded["state"], recorded["attestation"]) == ("voided", "provider_observed")
    assert recorded["provider_operation_id"] == str(await money.operation())
    assert (await money.world.balance(obligation))["paid"] == "0.00"
    # The external identity stays bound: the operation never posts again.
    again, other = await money.reserved()
    refused = await money.apply(other, await money.operation(), [(again, "10.00")])
    assert error(refused)[:2] == (409, "PROVIDER_OPERATION_APPLIED")
    (listed,) = await money.listed()
    assert (listed["state"], listed["payment_id"]) == ("applied", str(payment))
    assert await money.count(app_pool, "external_payment_provenance") == 1


# M-10 -----------------------------------------------------------------------


async def test_later_facts_change_no_money_and_show_a_conflict(
    money: Money, app_pool: RuntimePool
) -> None:
    obligation, _, payment = await money.paid()
    journals = await money.count(app_pool, "journal_entries")
    await money.observe(event("charge.succeeded", object_id="ch_FAKElate", amount=900))
    (listed,) = await money.listed()
    assert (listed["state"], listed["payment_id"]) == ("applied_with_conflict", str(payment))
    assert (await money.payment(payment))["amount"] == "10.00"
    assert (await money.world.balance(obligation))["paid"] == "10.00"
    assert await money.count(app_pool, "journal_entries") == journals


# M-11 -----------------------------------------------------------------------


_DRIFT = [
    (
        "alter table gba.external_payment_provenance "
        "disable trigger external_payment_provenance_check",
        "alter table gba.external_payment_provenance "
        "enable trigger external_payment_provenance_check",
    ),
    (
        "revoke select on gba.provider_event_decisions from gba_runtime",
        "grant select on gba.provider_event_decisions to gba_runtime",
    ),
]


@pytest.mark.parametrize(("change", "restore"), _DRIFT, ids=["h_trigger", "k_grant"])
async def test_damaged_provider_money_controls_fail_with_503(
    money: Money,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    change: str,
    restore: str,
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(event("payment_intent.succeeded"))
    operation = await money.operation()
    owner_conn.execute(change)
    try:
        refused = await money.apply(settlement, operation, [(obligation, "10.00")])
        assert error(refused)[:2] == (503, "DATABASE_UNAVAILABLE")
    finally:
        owner_conn.execute(restore)
    assert await money.count(app_pool, "external_payments") == 0
    applied = await money.apply(settlement, operation, [(obligation, "10.00")])
    assert applied.status_code == 200, applied.text


# Rights ---------------------------------------------------------------------


async def test_another_company_cannot_list_or_apply(
    money: Money, manager_b: FakeUser, idp: FakeIdp
) -> None:
    obligation, settlement = await money.reserved()
    await money.observe(event("payment_intent.succeeded"))
    config = Config(money.http, idp)
    listed = await money.http.get(
        f"{money.root}/provider-operations", headers=config.auth(manager_b)
    )
    assert listed.status_code in (403, 404), listed.text
    refused = await money.apply(
        settlement,
        await money.operation(),
        [(obligation, "10.00")],
        headers=config.headers(manager_b),
    )
    assert refused.status_code in (403, 404), refused.text


async def test_the_service_refuses_an_unknown_operation(
    money: Money, app_pool: RuntimePool
) -> None:
    obligation, settlement = await money.reserved()
    ledger = money.credits.ledger
    body = ProviderPaymentConfirmInput.model_validate(money.body(uuid7(), [(obligation, "10.00")]))
    with pytest.raises(NotFoundError):
        async with tenant_transaction(app_pool, ledger.business) as conn:
            await settlements.confirm_provider(
                conn,
                business_id=ledger.business,
                book_id=ledger.book,
                settlement_id=settlement,
                payment_id=uuid7(),
                user_id=ledger.user.user_id,
                actor=f"user:{ledger.user.user_id}",
                key=str(uuid7()),
                body=body,
            )
