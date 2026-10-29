"""N5: the carrier's pay per accepted tender and the margin per order (FAKE data only).

docs/plan/PACKAGE_N5_DESIGN_2026-10-28.md: an accepted tender with closed legs accrues once as a
FIN-03 payable to its carrier for the rate confirmation in force; the margin of an order is its
invoice total less the accrued pay of its own tenders, derived and never stored.
"""

from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_external_payments as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser
from tests.integration.test_delegations import owner_a, owner_b, parties
from tests.integration.test_l5_commissions import MODULES
from tests.integration.test_m1_transport_planning import accepted, leg, load
from tests.integration.test_m3_transport_events import INTERSTATE, event
from tests.integration.test_m7a_transport_money import Money, code, money, shipped
from tests.integration.test_n1_broker_carriers import carrier, profile
from tests.integration.test_n2_tenders import _broker, answer, offer
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
    "money",
    "owner_a",
    "owner_b",
    "parties",
    "payments",
]


async def tender(m: Money, trip: UUID, party: UUID, legs: list[int], **changes: str) -> UUID:
    made = uuid7()
    offered = await m.t.put(f"/tenders/{made}", offer(trip, party, legs, **changes))
    assert offered.status_code == 200, offered.text
    took = await answer(m.t, made, "accepted")
    assert took.status_code == 200, took.text
    return made


async def second_carrier(m: Money) -> UUID:
    party = await carrier(m.t, "FAKE Second Carrier")
    assert (await m.t.put(f"/carriers/{party}/profile", profile(0))).status_code == 200
    return party


# N5-01 ------------------------------------------------------------------------------


async def test_an_accepted_tender_accrues_once_for_the_version_in_force(money: Money) -> None:
    m = money
    _, trip = await shipped(m)
    party = await _broker(m.t)
    fixed = await tender(m, trip, party, [2])
    path = f"/tenders/{fixed}/accrual"
    assert (await m.get(path)).status_code == 404
    body = m.accrual_body()
    first = await m.post(path, body, key="n5-accrual-1")
    assert first.status_code == 200, first.text
    view = first.json()
    assert view["revision"] == 1
    accrual = view["accrual"]
    assert (
        accrual["direction"],
        accrual["kind"],
        accrual["counterparty_id"],
        accrual["total"],
    ) == (
        "payable",
        "manual_accrual",
        str(party),
        "900.00",
    )
    replay = await m.post(path, body, key="n5-accrual-1")
    assert replay.status_code == 200, replay.text
    assert replay.json() == view
    twice = await m.post(path, m.accrual_body())
    assert twice.status_code == 409, twice.text
    assert code(twice) == "TRANSPORT_ALREADY_ACCRUED"
    assert (await m.get(path)).json() == view
    # A per-mile rate needs the miles: 2.10 x 412.5 = 866.25.
    _, other_trip = await shipped(m)
    per_mile = await tender(
        m, other_trip, await second_carrier(m), [1], basis="per_mile", amount="2.10"
    )
    no_miles = await m.post(f"/tenders/{per_mile}/accrual", m.accrual_body())
    assert no_miles.status_code == 422, no_miles.text
    assert code(no_miles) == "TRANSPORT_MILES_REQUIRED"
    miles = await m.post(f"/tenders/{per_mile}/accrual", m.accrual_body(miles="412.5"))
    assert miles.status_code == 200, miles.text
    assert miles.json()["accrual"]["total"] == "866.25"


# N5-02 ------------------------------------------------------------------------------


async def test_open_legs_and_closed_tenders_are_refused(money: Money) -> None:
    m = money
    _, trip = await shipped(m, close=False)
    party = await _broker(m.t)
    open_leg = await tender(m, trip, party, [2])
    refused = await m.post(f"/tenders/{open_leg}/accrual", m.accrual_body())
    assert refused.status_code == 409, refused.text
    assert code(refused) == "TRANSPORT_TRIP_NOT_CLOSED"
    # Only the tendered legs count: leg 1 is delivered in full.
    done = await m.post(f"/tenders/{await tender(m, trip, party, [1])}/accrual", m.accrual_body())
    assert done.status_code == 200, done.text
    _, closed = await shipped(m)
    withdrawn = await tender(m, closed, party, [2])
    took_back = await answer(m.t, withdrawn, "withdrawn", at="2026-10-26T19:00:00+00:00")
    assert took_back.status_code == 200, took_back.text
    declined = uuid7()
    assert (await m.t.put(f"/tenders/{declined}", offer(closed, party, [1]))).status_code == 200
    assert (await answer(m.t, declined, "declined")).status_code == 200
    for closed_tender in (withdrawn, declined):
        no = await m.post(f"/tenders/{closed_tender}/accrual", m.accrual_body())
        assert no.status_code == 409, no.text
        assert code(no) == "TRANSPORT_TENDER_CLOSED"


# N5-03 ------------------------------------------------------------------------------


async def test_the_margin_of_an_order_is_derived_from_its_own_tenders(money: Money) -> None:
    m = money
    order, trip = await shipped(m)
    party = await _broker(m.t)
    own = await tender(m, trip, party, [2])
    assert (await m.post(f"/tenders/{own}/accrual", m.accrual_body())).status_code == 200
    before = await m.get(f"/orders/{order}/margin")
    assert before.status_code == 200, before.text
    assert (before.json()["revenue"], before.json()["margin"]) == (None, None)
    assert before.json()["carrier_cost"] == "900.00"
    assert (await m.rate(order, 0, basis="fixed", amount="1500.00")).status_code == 200
    assert (await m.post(f"/orders/{order}/invoice", m.invoice_body())).status_code == 200
    seen = await m.get(f"/orders/{order}/margin")
    assert seen.status_code == 200, seen.text
    view = seen.json()
    assert (view["currency"], view["revenue"], view["carrier_cost"], view["margin"]) == (
        "USD",
        "1500.00",
        "900.00",
        "600.00",
    )
    assert view["tenders"] == [{"tender_id": str(own), "amount": "900.00"}]
    assert view["shared"] == []
    # A tender that also carries another order's load is listed, never subtracted.
    first, second, pallets, crates = uuid7(), uuid7(), uuid7(), uuid7()
    assert (await m.t.order(first, [load(pallets, 10)])).status_code == 200
    assert (await m.t.order(second, [load(crates, 6, "FAKE crates")])).status_code == 200
    mixed = uuid7()
    made = await m.t.trip(mixed, INTERSTATE, [leg(pallets, 10, 1, 2), leg(crates, 6, 1, 3)])
    assert made.status_code == 200, made.text
    for kind, stop, lines in (
        ("loaded", 1, ((1, 10), (2, 6))),
        ("delivered", 2, ((1, 10),)),
        ("delivered", 3, ((2, 6),)),
    ):
        assert (await event(m.t, mixed, kind, stop, quantities=lines)).status_code == 200
    both = await tender(m, mixed, party, [1, 2])
    assert (await m.post(f"/tenders/{both}/accrual", m.accrual_body())).status_code == 200
    split = (await m.get(f"/orders/{first}/margin")).json()
    assert (split["carrier_cost"], split["tenders"]) == ("0.00", [])
    assert split["shared"] == [{"tender_id": str(both), "amount": "900.00"}]


# N5-04 ------------------------------------------------------------------------------


async def _accruals(pool: RuntimePool, tenant: UUID) -> int:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (
            await conn.execute("select count(*) from gba.transport_tender_accruals")
        ).fetchone()
    assert row is not None
    return int(row[0])


async def test_carrier_pay_is_a_broker_task_only(
    money: Money,
    world: BookingWorld,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_b: FakeUser,
) -> None:
    m = money
    order, trip = await shipped(m)
    party = await _broker(m.t)
    made = await tender(m, trip, party, [2])
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    refused = await m.post(
        f"/tenders/{made}/accrual",
        m.accrual_body(),
        headers={**other, "Idempotency-Key": str(uuid7())},
    )
    assert refused.status_code in (403, 404), refused.text
    assert (await m.get(f"/orders/{order}/margin", headers=other)).status_code in (403, 404)
    assert await _accruals(app_pool, world.a.tenant_id) == 0
    ledger = m.payments.ledger
    await Config(ledger.client, idp).publish(ledger.user, ledger.business, 3, MODULES)
    off = await m.post(f"/tenders/{made}/accrual", m.accrual_body())
    assert off.status_code in (403, 409), off.text
    assert await _accruals(app_pool, world.a.tenant_id) == 0
    await Config(ledger.client, idp).publish(
        ledger.user, ledger.business, 4, [*MODULES, "transport"]
    )
    assert (await m.post(f"/tenders/{made}/accrual", m.accrual_body())).status_code == 200
    for statement in (
        "update gba.transport_tender_accruals set miles = 1",
        "delete from gba.transport_tender_accruals",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
                await conn.execute(statement)
    assert await _accruals(app_pool, world.a.tenant_id) == 1
