"""M7a: transport money through FIN-03 (package M; FAKE data only).

ADR-0033 and docs/plan/PACKAGE_M7A_DESIGN_2026-10-25.md: the order's agreed rate is kept as
versions; one customer invoice per order once nothing is open; a trip's pay components are stable
sources of separate payable obligations, accrued once each on a closed trip; FIN-03 keeps every
payment within the open balance. Money is a company-wide finance task, never a carrier dispatcher's.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_external_payments as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_delegations import Parties, _member, owner_a, owner_b, parties
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l5_commissions import MODULES, Kit, make_kit
from tests.integration.test_m1_transport_planning import Transport, accepted, leg, load
from tests.integration.test_m3_transport_events import INTERSTATE, event
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
__all__ = [
    "accepted",
    "client",
    "enabled",
    "idp",
    "invoices",
    "manager_a",
    "manager_b",
    "owner_a",
    "owner_b",
    "parties",
    "payments",
]
TRANSPORT = ["transport.read", "transport.plan", "transport.assign", "transport.events"]


@dataclass(frozen=True)
class Money:
    payments: PaymentWorld
    t: Transport
    kit: Kit
    dispatch_company: UUID

    @property
    def accounts(self) -> dict[str, UUID]:
        return self.kit.accounts

    def headers(self, key: str | None = None) -> dict[str, str]:
        return self.payments.ledger.headers(key)

    async def put(
        self,
        path: str,
        body: dict[str, Any],
        *,
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self.t.client.put(
            self.t.base + path,
            json={"schema_version": 1, **body},
            headers=headers or self.headers(key),
        )

    async def post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self.t.client.post(
            self.t.base + path,
            json={"schema_version": 1, **body},
            headers=headers or self.headers(key),
        )

    async def get(self, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.t.client.get(
            self.t.base + path, headers=headers or self.payments.ledger.auth
        )

    async def rate(self, order: UUID, revision: int, **formula: str) -> httpx.Response:
        body = {"expected_revision": revision, "currency": "USD", **formula}
        return await self.put(f"/orders/{order}/rate", body)

    def invoice_body(self, **changes: object) -> dict[str, Any]:
        world = self.payments.settlements.invoices
        return {
            "book_id": str(world.ledger.book),
            "control_account_id": str(world.control),
            "revenue_account_id": str(world.counter),
            "invoice_date": "2026-10-02",
            "number": f"FAKE-TI-{uuid7().hex[-6:]}",
            **changes,
        }

    def prepare(self, obligation: UUID, amount: str, party: UUID, direction: str) -> Any:
        """A FIN-03 settlement draft for the obligation's own counterparty and direction."""
        return self.payments.settlements.prepare(
            uuid7(), [(obligation, amount)], counterparty_id=str(party), direction=direction
        )

    async def settle(
        self, obligation: UUID, amount: str, party: UUID, direction: str, reference: str
    ) -> None:
        settlements = self.payments.settlements
        settlement = uuid7()
        prepared = await settlements.prepare(
            settlement, [(obligation, amount)], counterparty_id=str(party), direction=direction
        )
        assert prepared.status_code == 200, prepared.text
        for action, sequence in (("approve", 1), ("reserve", 2)):
            acted = await settlements.act(settlement, action, sequence)
            assert acted.status_code == 200, acted.text
        paid = await self.payments.confirm(settlement, 3, [(obligation, amount)], amount, reference)
        assert paid.status_code == 200, paid.text

    def accrual_body(self, **changes: object) -> dict[str, Any]:
        return {
            "book_id": str(self.payments.ledger.book),
            "expense_account_id": str(self.accounts["6000"]),
            "payable_account_id": str(self.accounts["2200"]),
            "accrual_date": "2026-10-02",
            "number": f"FAKE-TP-{uuid7().hex[-6:]}",
            **changes,
        }


@pytest.fixture
async def money(
    payments: PaymentWorld,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    idp: FakeIdp,
    accepted: None,
) -> Money:
    ledger = payments.ledger
    await Config(ledger.client, idp).publish(
        ledger.user, ledger.business, 2, [*MODULES, "transport"]
    )
    kit = await make_kit(payments, app_pool)
    parties_made: list[UUID] = []
    for name, roles in (("FAKE Shipper", ["customer"]), ("FAKE Dispatch Co", ["supplier"])):
        party = uuid7()
        saved = await ledger.client.put(
            f"/v1/businesses/{ledger.business}/counterparties/{party}",
            json=card(display_name=name, roles=roles),
            headers=ledger.headers(),
        )
        assert saved.status_code == 200, saved.text
        parties_made.append(party)
    t = Transport(ledger.client, world, owner_conn, ledger.auth, parties_made[0])
    return Money(payments, t, kit, parties_made[1])


async def shipped(
    m: Money,
    *,
    close: bool = True,
    before: Callable[[UUID], Awaitable[None]] | None = None,
) -> tuple[UUID, UUID]:
    """10 pallets and 6 crates on one interstate trip; closed: all delivered or refused.

    `before` runs on the planned trip ahead of any event (a brokered leg is tendered first).
    """
    order, pallets, crates = uuid7(), uuid7(), uuid7()
    saved = await m.t.order(order, [load(pallets, 10), load(crates, 6, "FAKE crates")])
    assert saved.status_code == 200, saved.text
    trip = uuid7()
    made = await m.t.trip(trip, INTERSTATE, [leg(pallets, 10, 1, 2), leg(crates, 6, 1, 3)])
    assert made.status_code == 200, made.text
    if before is not None:
        await before(trip)
    loaded = await event(m.t, trip, "loaded", 1, quantities=((1, 10), (2, 6)), hour=9)
    assert loaded.status_code == 200, loaded.text
    first = await event(m.t, trip, "delivered", 2, quantities=((1, 10),), hour=15)
    assert first.status_code == 200, first.text
    if close:
        for kind, quantity in (("delivered", 4), ("refused", 2)):
            done = await event(m.t, trip, kind, 3, quantities=((2, quantity),), hour=21)
            assert done.status_code == 200, done.text
    return order, trip


def code(response: httpx.Response) -> str:
    return str(response.json()["error"]["code"])


# M7a-01 ------------------------------------------------------------------------------


async def test_an_order_rate_is_versioned_and_frozen_by_its_invoice(money: Money) -> None:
    m = money
    order, _ = await shipped(m)
    empty = await m.get(f"/orders/{order}/rate")
    assert empty.status_code == 200, empty.text
    assert (empty.json()["current"], empty.json()["versions"]) == (None, [])
    first = await m.rate(order, 0, basis="fixed", amount="1250.00")
    assert first.status_code == 200, first.text
    assert first.json()["current"]["revision"] == 1
    stale = await m.rate(order, 0, basis="fixed", amount="1300.00")
    assert stale.status_code == 409, stale.text
    second = await m.rate(order, 1, basis="per_mile", amount="2.35")
    assert second.status_code == 200, second.text
    view = second.json()
    assert (view["current"]["revision"], view["current"]["basis"], view["current"]["amount"]) == (
        2,
        "per_mile",
        "2.35",
    )
    assert [v["revision"] for v in view["versions"]] == [1, 2]
    billed = await m.post(f"/orders/{order}/invoice", m.invoice_body(miles="412.5"))
    assert billed.status_code == 200, billed.text
    frozen = await m.rate(order, 2, basis="fixed", amount="1000.00")
    assert frozen.status_code == 409, frozen.text
    assert code(frozen) == "TRANSPORT_ORDER_INVOICED"


# M7a-02 ------------------------------------------------------------------------------


async def test_an_order_is_invoiced_once_when_nothing_is_open(money: Money) -> None:
    m = money
    order, trip = await shipped(m, close=False)
    no_rate = await m.post(f"/orders/{order}/invoice", m.invoice_body(miles="412.5"))
    assert no_rate.status_code == 409, no_rate.text
    assert code(no_rate) == "TRANSPORT_ORDER_RATE_MISSING"
    assert (await m.rate(order, 0, basis="per_mile", amount="2.35")).status_code == 200
    open_leg = await m.post(f"/orders/{order}/invoice", m.invoice_body(miles="412.5"))
    assert open_leg.status_code == 409, open_leg.text
    assert code(open_leg) == "TRANSPORT_ORDER_NOT_BILLABLE"
    for kind, quantity in (("delivered", 4), ("refused", 2)):
        assert (await event(m.t, trip, kind, 3, quantities=((2, quantity),))).status_code == 200
    no_miles = await m.post(f"/orders/{order}/invoice", m.invoice_body())
    assert no_miles.status_code == 422, no_miles.text
    assert code(no_miles) == "TRANSPORT_MILES_REQUIRED"
    revenue = str(m.payments.settlements.invoices.counter)
    body = m.invoice_body(
        miles="412.5",
        extra_lines=[{"description": "FAKE detention", "amount": "75.00", "account_id": revenue}],
    )
    saved = await m.post(f"/orders/{order}/invoice", body, key="m7a-invoice-1")
    assert saved.status_code == 200, saved.text
    view = saved.json()
    invoice = view["invoice"]
    assert (invoice["direction"], invoice["state"], invoice["counterparty_id"]) == (
        "receivable",
        "draft",
        str(m.t.customer),
    )
    # 2.35 x 412.5 = 969.375, half up to cents.
    assert [(x["amount"], x["counter_account_id"]) for x in invoice["lines"]] == [
        ("969.38", revenue),
        ("75.00", revenue),
    ]
    assert invoice["lines"][0]["description"].startswith("Freight FAKE-SO-")
    assert invoice["total"] == "1044.38"
    assert (view["rate_revision"], view["miles"], view["obligation"]) == (1, "412.5", None)
    again = await m.post(f"/orders/{order}/invoice", body, key="m7a-invoice-1")
    assert (again.status_code, again.json()) == (200, view)
    twice = await m.post(f"/orders/{order}/invoice", body)
    assert twice.status_code == 409, twice.text
    assert code(twice) == "TRANSPORT_ORDER_INVOICED"
    # An order whose loads are not all planned is never billable.
    partial, rest = uuid7(), uuid7()
    item = uuid7()
    made = await m.t.order(partial, [load(item, 5), load(rest, 3, "FAKE rest")])
    assert made.status_code == 200, made.text
    assert (await m.rate(partial, 0, basis="fixed", amount="300.00")).status_code == 200
    half = uuid7()
    planned = await m.t.trip(half, INTERSTATE[:2], [leg(item, 5, 1, 2)])
    assert planned.status_code == 200, planned.text
    for kind, stop, quantities in (("loaded", 1, ((1, 5),)), ("delivered", 2, ((1, 5),))):
        assert (await event(m.t, half, kind, stop, quantities=quantities)).status_code == 200
    unplanned = await m.post(f"/orders/{partial}/invoice", m.invoice_body())
    assert unplanned.status_code == 409, unplanned.text
    assert code(unplanned) == "TRANSPORT_ORDER_NOT_BILLABLE"


# M7a-03 ------------------------------------------------------------------------------


async def test_the_customer_invoice_is_paid_through_fin03(money: Money) -> None:
    m = money
    order, _ = await shipped(m)
    assert (await m.rate(order, 0, basis="fixed", amount="1250.00")).status_code == 200
    saved = await m.post(f"/orders/{order}/invoice", m.invoice_body())
    assert saved.status_code == 200, saved.text
    assert [x["amount"] for x in saved.json()["invoice"]["lines"]] == ["1250.00"]
    document = UUID(saved.json()["invoice"]["document_id"])
    issued = await m.payments.settlements.invoices.issue(document)
    assert issued.status_code == 200, issued.text
    obligation = UUID(issued.json()["obligation_id"])
    seen = await m.get(f"/orders/{order}/invoice")
    assert seen.status_code == 200, seen.text
    assert (seen.json()["obligation"]["paid"], seen.json()["obligation"]["available"]) == (
        "0.00",
        "1250.00",
    )
    too_much = await m.prepare(obligation, "1300.00", m.t.customer, "receivable")
    assert too_much.status_code in (409, 422), too_much.text
    await m.settle(obligation, "1250.00", m.t.customer, "receivable", "FAKE-T")
    final = (await m.get(f"/orders/{order}/invoice")).json()["obligation"]
    assert (final["paid"], final["available"]) == ("1250.00", "0.00")


# M7a-04 ------------------------------------------------------------------------------


async def test_pay_components_are_registered_once_per_recipient_and_role(money: Money) -> None:
    m = money
    _, trip = await shipped(m)
    driver = {
        "counterparty_id": str(m.kit.payee),
        "role": "driver",
        "currency": "USD",
        "basis": "per_mile",
        "rate": "0.55",
    }
    first = uuid7()
    saved = await m.put(f"/trips/{trip}/pay/{first}", driver)
    assert saved.status_code == 200, saved.text
    component = saved.json()
    assert (component["component_id"], component["basis"], component["rate"]) == (
        str(first),
        "per_mile",
        "0.55",
    )
    again = await m.put(f"/trips/{trip}/pay/{first}", driver)
    assert (again.status_code, again.json()) == (200, component)
    other = await m.put(f"/trips/{trip}/pay/{first}", {**driver, "rate": "0.60"})
    assert other.status_code == 409, other.text
    assert code(other) == "TRANSPORT_PAY_COMPONENT_CONFLICT"
    twin = await m.put(f"/trips/{trip}/pay/{uuid7()}", driver)
    assert twin.status_code == 409, twin.text
    assert code(twin) == "TRANSPORT_PAY_COMPONENT_CONFLICT"
    for invalid in (
        {**driver, "rate": None},
        {**driver, "basis": "percent", "percent": "10"},
        {**driver, "basis": "percent", "percent": "120", "base": "100.00"},
    ):
        refused = await m.put(f"/trips/{trip}/pay/{uuid7()}", invalid)
        assert refused.status_code == 422, refused.text
    fee = {
        "counterparty_id": str(m.dispatch_company),
        "role": "dispatch_fee",
        "currency": "USD",
        "basis": "percent",
        "percent": "7.5",
        "base": "1250.00",
    }
    assert (await m.put(f"/trips/{trip}/pay/{uuid7()}", fee)).status_code == 200
    listed = await m.get(f"/trips/{trip}/pay")
    assert listed.status_code == 200, listed.text
    assert sorted(c["role"] for c in listed.json()["components"]) == ["dispatch_fee", "driver"]
    assert all(c["accrual"] is None for c in listed.json()["components"])


# M7a-05 ------------------------------------------------------------------------------


async def test_each_component_accrues_once_as_its_own_obligation(money: Money) -> None:
    m = money
    _, trip = await shipped(m, close=False)
    driver, fee, bonus = uuid7(), uuid7(), uuid7()
    for component, body in (
        (
            driver,
            {
                "counterparty_id": str(m.kit.payee),
                "role": "driver",
                "basis": "per_mile",
                "rate": "0.55",
            },
        ),
        (
            fee,
            {
                "counterparty_id": str(m.dispatch_company),
                "role": "dispatch_fee",
                "basis": "percent",
                "percent": "7.5",
                "base": "1250.00",
            },
        ),
        (
            bonus,
            {
                "counterparty_id": str(m.kit.payee),
                "role": "other",
                "basis": "fixed",
                "amount": "40.00",
            },
        ),
    ):
        saved = await m.put(f"/trips/{trip}/pay/{component}", {"currency": "USD", **body})
        assert saved.status_code == 200, saved.text
    still_open = await m.post(f"/trips/{trip}/pay/{driver}/accrue", m.accrual_body(miles="412.5"))
    assert still_open.status_code == 409, still_open.text
    assert code(still_open) == "TRANSPORT_TRIP_NOT_CLOSED"
    for kind, quantity in (("delivered", 4), ("refused", 2)):
        assert (await event(m.t, trip, kind, 3, quantities=((2, quantity),))).status_code == 200
    no_miles = await m.post(f"/trips/{trip}/pay/{driver}/accrue", m.accrual_body())
    assert no_miles.status_code == 422, no_miles.text
    assert code(no_miles) == "TRANSPORT_MILES_REQUIRED"
    body = m.accrual_body(miles="412.5")
    accrued = await m.post(f"/trips/{trip}/pay/{driver}/accrue", body, key="m7a-accrue-1")
    assert accrued.status_code == 200, accrued.text
    view = accrued.json()
    accrual = view["accrual"]["accrual"]
    assert (accrual["kind"], accrual["direction"], accrual["counterparty_id"]) == (
        "manual_accrual",
        "payable",
        str(m.kit.payee),
    )
    # 0.55 x 412.5 = 226.875, half up to cents.
    assert [(x["amount"], x["counter_account_id"]) for x in accrual["lines"]] == [
        ("226.88", str(m.accounts["6000"])),
    ]
    again = await m.post(f"/trips/{trip}/pay/{driver}/accrue", body, key="m7a-accrue-1")
    assert (again.status_code, again.json()) == (200, view)
    twice = await m.post(f"/trips/{trip}/pay/{driver}/accrue", body)
    assert twice.status_code == 409, twice.text
    assert code(twice) == "TRANSPORT_ALREADY_ACCRUED"
    amounts = {}
    obligations = {}
    for component in (driver, fee, bonus):
        if component != driver:
            made = await m.post(f"/trips/{trip}/pay/{component}/accrue", m.accrual_body())
            assert made.status_code == 200, made.text
        listed = (await m.get(f"/trips/{trip}/pay")).json()["components"]
        mine = next(c for c in listed if c["component_id"] == str(component))
        document = mine["accrual"]["accrual"]["document_id"]
        amounts[component] = mine["accrual"]["accrual"]["total"]
        issued = await m.payments.ledger.client.post(
            f"/v1/businesses/{m.payments.ledger.business}/financial-documents/books/"
            f"{m.payments.ledger.book}/accruals/{document}/issue",
            json={
                "schema_version": 1,
                "expected_revision": 1,
                "entry_date": "2026-10-02",
                "attestation": "confirmed_account_treatment",
            },
            headers=m.headers(),
        )
        assert issued.status_code == 200, issued.text
        obligations[component] = UUID(issued.json()["obligation_id"])
    # 7.5% of the agreed 1250.00; the bonus is fixed.
    assert amounts == {driver: "226.88", fee: "93.75", bonus: "40.00"}
    assert len(set(obligations.values())) == 3
    await m.settle(obligations[driver], "100.00", m.kit.payee, "payable", "FAKE-DRIVER-1")
    balance = await m.payments.settlements.balance(obligations[driver])
    assert (balance["direction"], balance["paid"], balance["available"]) == (
        "payable",
        "100.00",
        "126.88",
    )
    # FIN-03 reserves atomically against the open balance: 130.00 is more than the 126.88 left.
    beyond = await m.prepare(obligations[driver], "130.00", m.kit.payee, "payable")
    assert beyond.status_code == 200, beyond.text
    settlement = UUID(beyond.json()["settlement_id"])
    approved = await m.payments.settlements.act(settlement, "approve", 1)
    assert approved.status_code == 200, approved.text
    refused = await m.payments.settlements.act(settlement, "reserve", 2)
    assert refused.status_code in (409, 422), refused.text
    listed = (await m.get(f"/trips/{trip}/pay")).json()["components"]
    driven = next(c for c in listed if c["component_id"] == str(driver))
    assert (driven["accrual"]["obligation"]["paid"], driven["accrual"]["miles"]) == (
        "100.00",
        "412.5",
    )


# M7a-06 ------------------------------------------------------------------------------


async def _rows(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        counts = []
        for table in (
            "transport_order_rates",
            "transport_order_invoices",
            "transport_pay_components",
            "transport_pay_accruals",
        ):
            row = await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()
            assert row is not None
            counts.append(int(row[0]))
    return tuple(counts)


async def test_money_is_a_company_finance_task_only(
    money: Money,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    app_pool: RuntimePool,
    idp: FakeIdp,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    manager_b: FakeUser,
) -> None:
    m = money
    order, trip = await shipped(m)
    desk = seed_user(owner_conn, f"m7a-desk-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=desk.user_id, role="front_desk")
    dispatcher = _member(owner_conn, world.b.tenant_id, "manager", "m7a-dispatcher")
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=TRANSPORT)
    before = await _rows(app_pool, world.a.tenant_id)
    component = {
        "counterparty_id": str(m.kit.payee),
        "role": "driver",
        "currency": "USD",
        "basis": "fixed",
        "amount": "10.00",
    }
    for person, allowed in ((desk, (403,)), (dispatcher, (403,)), (manager_b, (403, 404))):
        auth = idp.bearer(person.subject, email=person.email)
        for method, path, body in (
            (
                "put",
                f"/orders/{order}/rate",
                {"expected_revision": 0, "currency": "USD", "basis": "fixed", "amount": "1.00"},
            ),
            ("post", f"/orders/{order}/invoice", m.invoice_body()),
            ("put", f"/trips/{trip}/pay/{uuid7()}", component),
            ("get", f"/orders/{order}/rate", None),
            ("get", f"/orders/{order}/invoice", None),
            ("get", f"/trips/{trip}/pay", None),
        ):
            headers = {**auth, "Idempotency-Key": str(uuid7())}
            if method == "get":
                answer = await m.get(path, headers=auth)
            elif method == "put":
                answer = await m.put(path, body or {}, headers=headers)
            else:
                answer = await m.post(path, body or {}, headers=headers)
            assert answer.status_code in allowed, (person, path, answer.text)
    assert await _rows(app_pool, world.a.tenant_id) == before
    # With the transport module switched off, money on transport is refused too.
    ledger = m.payments.ledger
    await Config(ledger.client, idp).publish(ledger.user, ledger.business, 3, MODULES)
    off = await m.rate(order, 0, basis="fixed", amount="1.00")
    assert off.status_code in (403, 409), off.text
    assert await _rows(app_pool, world.a.tenant_id) == before
