"""N8: fixes of the package N review RN-01..RN-09 (docs/plan/PACKAGE_N8_DESIGN_2026-10-30.md).

FAKE data only. A carrier's platform answer takes the server time, so its offers are dated from now.
"""

from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_external_payments as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_m1_transport_planning import (
    Transport,
    accepted,
    error,
    leg,
    load,
    transport,
)
from tests.integration.test_m3_transport_events import INTERSTATE, event
from tests.integration.test_m4_dispatcher_grants import acting, dispatcher
from tests.integration.test_m7a_transport_money import Money, code, money, shipped
from tests.integration.test_manual_accruals import AccrualWorld
from tests.integration.test_n2_tenders import answer, offer
from tests.integration.test_n3_rate_confirmations import agree, proposal
from tests.integration.test_n4_carrier_companies import (
    CARRIER,
    at,
    carrier_answer,
    fresh_broker,
    fresh_offer,
    link,
)

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
    "dispatcher",
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
    "transport",
]


async def two_legs(t: Transport) -> tuple[UUID, UUID, UUID, list[dict[str, Any]]]:
    """A planned trip: leg 1 10 pallets stop 1 to 2, leg 2 6 crates stop 1 to 3."""
    pallets, crates = uuid7(), uuid7()
    saved = await t.order(uuid7(), [load(pallets, 10), load(crates, 6, "FAKE crates")])
    assert saved.status_code == 200, saved.text
    trip = uuid7()
    legs = [leg(pallets, 10, 1, 2), leg(crates, 6, 1, 3)]
    made = await t.trip(trip, INTERSTATE, legs)
    assert made.status_code == 200, made.text
    return trip, pallets, crates, legs


async def carrier_on_leg_2(
    t: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    world: BookingWorld,
) -> tuple[UUID, UUID, UUID, Transport]:
    """Leg 2 accepted by the carrier linked to business B, acting through its grant."""
    trip, *_ = await two_legs(t)
    party = await fresh_broker(t)
    linked = await t.put(f"/carriers/{party}/company", link(world.b.tenant_id, 0))
    assert linked.status_code == 200, linked.text
    tender = uuid7()
    assert (await t.put(f"/tenders/{tender}", fresh_offer(trip, party, [2]))).status_code == 200
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=CARRIER)
    d = acting(t, parties, dispatcher)
    took = await carrier_answer(d, tender, "accepted")
    assert took.status_code == 200, took.text
    return trip, party, tender, d


async def brokered(m: Money, *, close: bool = True, **changes: str) -> tuple[UUID, UUID, UUID]:
    """Leg 2 tendered and accepted before any event, then the trip runs."""
    tenders: list[UUID] = []

    async def before(trip: UUID) -> None:
        party = await fresh_broker(m.t)
        made = uuid7()
        offered = await m.t.put(f"/tenders/{made}", offer(trip, party, [2], **changes))
        assert offered.status_code == 200, offered.text
        took = await answer(m.t, made, "accepted")
        assert took.status_code == 200, took.text
        tenders.append(made)

    order, trip = await shipped(m, close=close, before=before)
    return order, trip, tenders[0]


# RN-01 ------------------------------------------------------------------------------


async def test_rn01_the_tender_accrual_draft_is_frozen(money: Money) -> None:
    m = money
    _, _, made = await brokered(m)
    accrued = await m.post(f"/tenders/{made}/accrual", m.accrual_body())
    assert accrued.status_code == 200, accrued.text
    document = UUID(accrued.json()["accrual"]["document_id"])
    accruals = AccrualWorld(m.payments.settlements.invoices)
    moved = await accruals.save(
        document=document, body=accruals.body(expected_revision=1, number="FAKE-MOVED")
    )
    assert (moved.status_code, code(moved)) == (409, "FINANCIAL_DOCUMENT_LINKED"), moved.text
    assert (await m.get(f"/tenders/{made}/accrual")).json()["accrual"]["total"] == "900.00"


# RN-02 ------------------------------------------------------------------------------


async def test_rn02_a_tendered_trip_is_not_replanned(
    transport: Transport, app_pool: RuntimePool
) -> None:
    t = transport
    trip, pallets, crates, _ = await two_legs(t)
    party = await fresh_broker(t)
    made = uuid7()
    assert (await t.put(f"/tenders/{made}", fresh_offer(trip, party, [2]))).status_code == 200
    swapped = [leg(crates, 6, 1, 2), leg(pallets, 10, 1, 3)]
    # An open offer, then the accepted tender, both hold the plan.
    held = await t.trip(trip, INTERSTATE, swapped, revision=1)
    assert error(held) == (409, "TRANSPORT_TRIP_TENDERED"), held.text
    assert (await answer(t, made, "accepted", at=at(0))).status_code == 200
    moved = await t.trip(trip, INTERSTATE, swapped, revision=1)
    assert error(moved) == (409, "TRANSPORT_TRIP_TENDERED"), moved.text
    with pytest.raises(psycopg.Error):
        async with tenant_transaction(app_pool, t.tenant) as conn:
            await conn.execute("delete from gba.transport_legs where trip_id = %s", (trip,))
    withdrawn = await answer(t, made, "withdrawn", at=at(0.05))
    assert withdrawn.status_code == 200, withdrawn.text
    again = await t.trip(trip, INTERSTATE, swapped, revision=1)
    assert again.status_code == 200, again.text


# RN-03 ------------------------------------------------------------------------------


async def test_rn03_a_carrier_never_closes_a_shared_stop(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    world: BookingWorld,
) -> None:
    trip, _, _, d = await carrier_on_leg_2(transport, parties, owner_a, owner_b, dispatcher, world)
    loaded = await event(d, trip, "loaded", 1, quantities=((2, 6),), source_id="FAKE-N8-3")
    assert loaded.status_code == 200, loaded.text
    departed = await event(d, trip, "departed", 1)
    assert error(departed) == (403, "TRANSPORT_EVENT_OUT_OF_SCOPE"), departed.text
    # Stop 3 serves only its own leg 2.
    assert (await event(d, trip, "arrived", 3)).status_code == 200


# RN-04 ------------------------------------------------------------------------------


async def test_rn04_an_accrued_tender_is_neither_withdrawn_nor_repriced(money: Money) -> None:
    m = money
    _, _, made = await brokered(m)
    assert (await m.post(f"/tenders/{made}/accrual", m.accrual_body())).status_code == 200
    withdrawn = await answer(m.t, made, "withdrawn", at="2026-10-26T23:00:00+00:00")
    assert (withdrawn.status_code, code(withdrawn)) == (409, "TRANSPORT_ALREADY_ACCRUED")
    repriced = await m.t.put(f"/tenders/{made}/rate-confirmation", proposal(1))
    assert (repriced.status_code, code(repriced)) == (409, "TRANSPORT_ALREADY_ACCRUED")


async def test_rn04_a_withdrawn_tender_agrees_no_pending_version(transport: Transport) -> None:
    t = transport
    trip, *_ = await two_legs(t)
    party = await fresh_broker(t)
    made = uuid7()
    assert (await t.put(f"/tenders/{made}", offer(trip, party, [2]))).status_code == 200
    assert (await answer(t, made, "accepted")).status_code == 200
    assert (await t.put(f"/tenders/{made}/rate-confirmation", proposal(1))).status_code == 200
    took_back = await answer(t, made, "withdrawn", at="2026-10-26T22:00:00+00:00")
    assert took_back.status_code == 200, took_back.text
    late = await agree(t, made, 2)
    assert late.status_code == 409, late.text


# RN-05 ------------------------------------------------------------------------------


async def _raw_carrier_answer(d: Transport, tender: UUID, body: dict[str, Any]) -> httpx.Response:
    return await d.client.post(
        f"{d.base}/tenders/{tender}/carrier-answers",
        json={"schema_version": 1, **body},
        headers={**d.headers, "Idempotency-Key": str(uuid7())},
    )


async def test_rn05_a_carrier_answers_at_the_server_time(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    world: BookingWorld,
) -> None:
    t = transport
    trip, *_ = await two_legs(t)
    party = await fresh_broker(t)
    linked = await t.put(f"/carriers/{party}/company", link(world.b.tenant_id, 0))
    assert linked.status_code == 200, linked.text
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=CARRIER)
    d = acting(t, parties, dispatcher)
    expired = uuid7()
    body = offer(trip, party, [2], offered_at=at(-3), expires_at=at(-1))
    assert (await t.put(f"/tenders/{expired}", body)).status_code == 200
    backdated = await _raw_carrier_answer(d, expired, {"kind": "accepted", "occurred_at": at(-2)})
    assert backdated.status_code == 422, backdated.text
    late = await _raw_carrier_answer(d, expired, {"kind": "accepted"})
    assert error(late) == (409, "TRANSPORT_TENDER_CLOSED"), late.text


# RN-06 ------------------------------------------------------------------------------


async def test_rn06_an_unlinked_carrier_keeps_its_restriction(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    world: BookingWorld,
) -> None:
    t = transport
    trip, party, _, d = await carrier_on_leg_2(t, parties, owner_a, owner_b, dispatcher, world)
    assert (await t.put(f"/carriers/{party}/company", link(None, 1))).status_code == 200
    stray = await event(d, trip, "arrived", 2)
    assert stray.status_code == 403, stray.text


# RN-07 ------------------------------------------------------------------------------


async def test_rn07_a_carrier_reads_only_its_own_trips(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    world: BookingWorld,
) -> None:
    t = transport
    trip, _, _, d = await carrier_on_leg_2(t, parties, owner_a, owner_b, dispatcher, world)
    other, *_ = await two_legs(t)
    listed = await d.get("/trips")
    assert listed.status_code == 200, listed.text
    assert [row["trip_id"] for row in listed.json()["items"]] == [str(trip)]
    assert (await d.get(f"/trips/{other}")).status_code == 404
    for path in ("/orders", "/drivers", "/vehicles"):
        assert (await d.get(path)).status_code == 403, path


# RN-08 ------------------------------------------------------------------------------


async def test_rn08_the_margin_never_adds_currencies(money: Money) -> None:
    m = money
    order, _, made = await brokered(m, currency="CAD")
    accrued = await m.post(f"/tenders/{made}/accrual", m.accrual_body())
    assert accrued.status_code == 200, accrued.text
    assert (await m.rate(order, 0, basis="fixed", amount="1500.00")).status_code == 200
    assert (await m.post(f"/orders/{order}/invoice", m.invoice_body())).status_code == 200
    margin = (await m.get(f"/orders/{order}/margin")).json()
    assert (margin["carrier_cost"], margin["margin"], margin["currencies_differ"]) == (
        None,
        None,
        True,
    )


# RN-09 ------------------------------------------------------------------------------


async def test_rn09_a_started_leg_is_not_tendered(money: Money) -> None:
    m = money
    _, trip = await shipped(m, close=False)
    party = await fresh_broker(m.t)
    late = await m.t.put(f"/tenders/{uuid7()}", offer(trip, party, [2]))
    assert (late.status_code, code(late)) == (409, "TRANSPORT_LEG_STARTED"), late.text
