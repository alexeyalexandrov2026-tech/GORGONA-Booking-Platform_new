"""N2: tenders of trip legs to other carriers (package N; FAKE data only).

docs/plan/PACKAGE_N2_DESIGN_2026-10-27.md: a tender is an insert-only offer of some legs of a trip
to one carrier; answers are insert-only facts with a source; the state is derived; offering and
accepting need an eligible broker and carrier on that date; a leg has at most one accepted tender.
"""

import asyncio
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_delegations import Parties, _member, owner_a, owner_b, parties
from tests.integration.test_m1_transport_planning import (
    Transport,
    accepted,
    error,
    leg,
    load,
    transport,
)
from tests.integration.test_m3_transport_events import INTERSTATE
from tests.integration.test_n1_broker_carriers import TRANSPORT, authority, carrier, profile
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = [
    "accepted",
    "client",
    "idp",
    "manager_a",
    "manager_b",
    "owner_a",
    "owner_b",
    "parties",
    "transport",
]
OFFERED = "2026-10-26T15:00:00+00:00"
EXPIRES = "2026-10-27T15:00:00+00:00"


async def _trip(t: Transport) -> UUID:
    """A trip of two legs: 10 pallets to Indianapolis, 6 crates to New York."""
    first, second = uuid7(), uuid7()
    saved = await t.order(uuid7(), [load(first, 10), load(second, 6, "FAKE crates")])
    assert saved.status_code == 200, saved.text
    trip = uuid7()
    made = await t.trip(trip, INTERSTATE, [leg(first, 10, 1, 2), leg(second, 6, 1, 3)])
    assert made.status_code == 200, made.text
    return trip


async def _broker(t: Transport) -> UUID:
    """An eligible broker and one eligible carrier."""
    assert (await t.put("/broker-authority", authority(0))).status_code == 200
    party = await carrier(t)
    assert (await t.put(f"/carriers/{party}/profile", profile(0))).status_code == 200
    return party


def offer(trip: UUID, party: UUID, legs: list[int], **changes: Any) -> dict[str, Any]:
    return {
        "trip_id": str(trip),
        "legs": legs,
        "counterparty_id": str(party),
        "currency": "USD",
        "basis": "fixed",
        "amount": "900.00",
        "terms": "FAKE terms: pickup on time, detention after 2 hours",
        "offered_at": OFFERED,
        "expires_at": EXPIRES,
        **changes,
    }


async def answer(
    t: Transport,
    tender: UUID,
    kind: str,
    at: str = "2026-10-26T18:00:00+00:00",
    headers: dict[str, str] | None = None,
    **changes: Any,
) -> httpx.Response:
    return await t.client.post(
        f"{t.base}/tenders/{tender}/answers",
        json={"schema_version": 1, "kind": kind, "source": "email", "occurred_at": at, **changes},
        headers={**(headers or t.headers), "Idempotency-Key": str(uuid7())},
    )


async def state(t: Transport, tender: UUID) -> str:
    seen = await t.get(f"/tenders/{tender}")
    assert seen.status_code == 200, seen.text
    return str(seen.json()["state"])


# N2-01 ------------------------------------------------------------------------------


async def test_a_tender_is_offered_for_some_legs_and_read_back(transport: Transport) -> None:
    t = transport
    trip = await _trip(t)
    party = await _broker(t)
    tender = uuid7()
    made = await t.put(f"/tenders/{tender}", offer(trip, party, [1]))
    assert made.status_code == 200, made.text
    body = made.json()
    assert (body["tender_id"], body["legs"], body["amount"], body["answers"]) == (
        str(tender),
        [1],
        "900.00",
        [],
    )
    assert body["state"] in ("offered", "expired")
    again = await t.put(f"/tenders/{tender}", offer(trip, party, [1]))
    assert again.status_code == 200, again.text
    assert again.json()["tender_id"] == str(tender)
    other = await t.put(f"/tenders/{tender}", offer(trip, party, [1], amount="950.00"))
    assert error(other) == (409, "TRANSPORT_TENDER_CONFLICT"), other.text
    listed = await t.get(f"/trips/{trip}/tenders")
    assert listed.status_code == 200, listed.text
    assert [x["tender_id"] for x in listed.json()["items"]] == [str(tender)]
    for invalid in (
        offer(trip, party, [3]),
        offer(trip, party, []),
        offer(trip, party, [1, 1]),
        offer(trip, party, [1], expires_at=OFFERED),
        offer(trip, party, [1], amount="900.005"),
        offer(trip, party, [1], basis="per_ton"),
    ):
        refused = await t.put(f"/tenders/{uuid7()}", invalid)
        assert refused.status_code == 422, (invalid, refused.text)
    missing = await t.put(f"/tenders/{uuid7()}", offer(uuid7(), party, [1]))
    assert missing.status_code in (404, 422), missing.text


# N2-02 ------------------------------------------------------------------------------


async def test_answers_move_the_state_and_a_closed_tender_refuses_more(
    transport: Transport,
) -> None:
    t = transport
    trip = await _trip(t)
    party = await _broker(t)
    accepted_one, declined_one, withdrawn_one, late_one = uuid7(), uuid7(), uuid7(), uuid7()
    for tender, legs in ((accepted_one, [1]), (declined_one, [2]), (withdrawn_one, [2])):
        assert (await t.put(f"/tenders/{tender}", offer(trip, party, legs))).status_code == 200
    took = await answer(t, accepted_one, "accepted")
    assert took.status_code == 200, took.text
    assert took.json()["state"] == "accepted"
    repeat = await answer(t, accepted_one, "accepted")
    assert repeat.status_code == 200, repeat.text
    assert len(repeat.json()["answers"]) == 1
    back = await answer(t, accepted_one, "withdrawn", "2026-10-26T20:00:00+00:00")
    assert back.status_code == 200, back.text
    assert await state(t, accepted_one) == "withdrawn"
    assert (await answer(t, declined_one, "declined")).status_code == 200
    assert await state(t, declined_one) == "declined"
    assert (await answer(t, withdrawn_one, "withdrawn")).status_code == 200
    for closed, kind in (
        (accepted_one, "accepted"),
        (declined_one, "accepted"),
        (withdrawn_one, "declined"),
    ):
        refused = await answer(t, closed, kind, "2026-10-26T21:00:00+00:00")
        assert error(refused) == (409, "TRANSPORT_TENDER_CLOSED"), refused.text
    # An offer that has expired cannot be accepted, and reads as expired.
    old = offer(
        trip,
        party,
        [1],
        offered_at="2026-10-21T15:00:00+00:00",
        expires_at="2026-10-22T15:00:00+00:00",
    )
    assert (await t.put(f"/tenders/{late_one}", old)).status_code == 200
    assert await state(t, late_one) == "expired"
    late = await answer(t, late_one, "accepted", "2026-10-23T15:00:00+00:00")
    assert error(late) == (409, "TRANSPORT_TENDER_CLOSED"), late.text
    early = await answer(t, late_one, "declined", "2026-10-20T15:00:00+00:00")
    assert early.status_code == 422, early.text
    assert (await answer(t, uuid7(), "accepted")).status_code == 404
    bad = await answer(t, late_one, "accepted", source="carrier pigeon")
    assert bad.status_code == 422, bad.text


# N2-03 ------------------------------------------------------------------------------


async def test_offering_and_accepting_need_an_eligible_broker_and_carrier(
    transport: Transport,
) -> None:
    t = transport
    trip = await _trip(t)
    party = await carrier(t)
    no_broker = await t.put(f"/tenders/{uuid7()}", offer(trip, party, [1]))
    assert error(no_broker) == (409, "TRANSPORT_BROKER_NOT_ELIGIBLE"), no_broker.text
    assert no_broker.json()["error"]["details"]["reasons"] == ["no_authority"]
    assert (await t.put("/broker-authority", authority(0))).status_code == 200
    no_profile = await t.put(f"/tenders/{uuid7()}", offer(trip, party, [1]))
    assert error(no_profile) == (409, "TRANSPORT_CARRIER_NOT_ELIGIBLE"), no_profile.text
    assert no_profile.json()["error"]["details"]["reasons"] == ["no_profile"]
    saved = await t.put(f"/carriers/{party}/profile", profile(0, cargo_expires_on="2026-10-26"))
    assert saved.status_code == 200, saved.text
    tender = uuid7()
    assert (await t.put(f"/tenders/{tender}", offer(trip, party, [1]))).status_code == 200
    # The cargo insurance ran out before the carrier accepted (Chicago date 2026-10-27).
    lapsed = await answer(t, tender, "accepted", "2026-10-27T14:00:00+00:00")
    assert error(lapsed) == (409, "TRANSPORT_CARRIER_NOT_ELIGIBLE"), lapsed.text
    assert lapsed.json()["error"]["details"]["reasons"] == ["cargo_expired"]
    # 2026-10-27 03:00 UTC is still 2026-10-26 in Chicago, the trip's first stop.
    in_time = await answer(t, tender, "accepted", "2026-10-27T03:00:00+00:00")
    assert in_time.status_code == 200, in_time.text
    assert (await t.put("/broker-authority", authority(1, status="withdrawn"))).status_code == 200
    withdrawn = await t.put(f"/tenders/{uuid7()}", offer(trip, party, [2]))
    assert error(withdrawn) == (409, "TRANSPORT_BROKER_NOT_ELIGIBLE"), withdrawn.text
    assert withdrawn.json()["error"]["details"]["reasons"] == ["withdrawn"]


# N2-04 ------------------------------------------------------------------------------


async def test_a_leg_has_at_most_one_accepted_tender(transport: Transport) -> None:
    t = transport
    trip = await _trip(t)
    party = await _broker(t)
    whole, first, second = uuid7(), uuid7(), uuid7()
    assert (await t.put(f"/tenders/{whole}", offer(trip, party, [1, 2]))).status_code == 200
    assert (await t.put(f"/tenders/{first}", offer(trip, party, [1]))).status_code == 200
    assert (await t.put(f"/tenders/{second}", offer(trip, party, [2]))).status_code == 200
    assert (await answer(t, first, "accepted")).status_code == 200
    overlap = await answer(t, whole, "accepted")
    assert error(overlap) == (409, "TRANSPORT_LEG_TENDERED"), overlap.text
    assert (await answer(t, second, "accepted")).status_code == 200
    assert (await answer(t, first, "withdrawn", "2026-10-26T19:00:00+00:00")).status_code == 200
    still = await answer(t, whole, "accepted", "2026-10-26T20:00:00+00:00")
    assert error(still) == (409, "TRANSPORT_LEG_TENDERED"), still.text
    assert (await answer(t, second, "withdrawn", "2026-10-26T20:00:00+00:00")).status_code == 200
    freed = await answer(t, whole, "accepted", "2026-10-26T21:00:00+00:00")
    assert freed.status_code == 200, freed.text


async def _wait_for_advisory_wait(owner_conn: psycopg.Connection) -> None:
    """Observe the accept waiting on the held trip-tender lock; a sleep proves no race."""
    for _ in range(300):
        await asyncio.sleep(0.01)
        row = owner_conn.execute(
            "select count(*) from pg_catalog.pg_locks where locktype = 'advisory' and not granted"
        ).fetchone()
        if row and row[0] >= 1:
            return
    pytest.fail("the accept must be observed waiting on the trip-tender lock")


async def test_two_racing_accepts_on_overlapping_legs_leave_one(
    transport: Transport,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    manager_a: FakeUser,
) -> None:
    t = transport
    trip = await _trip(t)
    party = await _broker(t)
    held, racing = uuid7(), uuid7()
    assert (await t.put(f"/tenders/{held}", offer(trip, party, [1]))).status_code == 200
    assert (await t.put(f"/tenders/{racing}", offer(trip, party, [1, 2]))).status_code == 200
    async with tenant_transaction(app_pool, t.tenant) as conn:
        await conn.execute(
            "select pg_catalog.pg_advisory_xact_lock("
            "pg_catalog.hashtextextended('gba:trip-tender:' || %s::text, 0))",
            (trip,),
        )
        await conn.execute(
            "insert into gba.transport_tender_answers (tenant_id, tender_id, kind, source, "
            "occurred_at, created_by) values (%s, %s, 'accepted', 'phone', %s, %s)",
            (t.tenant, held, "2026-10-26T17:00:00+00:00", manager_a.user_id),
        )
        pending = asyncio.create_task(answer(t, racing, "accepted"))
        try:
            await _wait_for_advisory_wait(owner_conn)
        except BaseException:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            raise
    lost = await pending
    assert error(lost) == (409, "TRANSPORT_LEG_TENDERED"), lost.text
    assert await state(t, held) == "accepted"
    assert await state(t, racing) in ("offered", "expired")


# N2-05 ------------------------------------------------------------------------------


async def _rows(pool: RuntimePool, tenant: UUID) -> tuple[int, int]:
    async with tenant_transaction(pool, tenant) as conn:
        a = await (await conn.execute("select count(*) from gba.transport_tenders")).fetchone()
        b = await (
            await conn.execute("select count(*) from gba.transport_tender_answers")
        ).fetchone()
    assert a is not None
    assert b is not None
    return int(a[0]), int(b[0])


async def test_only_owners_and_managers_with_the_broker_right_tender(
    transport: Transport,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    app_pool: RuntimePool,
    idp: FakeIdp,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    manager_b: FakeUser,
    manager_a: FakeUser,
) -> None:
    t = transport
    trip = await _trip(t)
    party = await _broker(t)
    tender = uuid7()
    assert (await t.put(f"/tenders/{tender}", offer(trip, party, [1]))).status_code == 200
    desk = seed_user(owner_conn, f"n2-desk-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=desk.user_id, role="front_desk")
    dispatcher = _member(owner_conn, world.b.tenant_id, "manager", "n2-dispatcher")
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=TRANSPORT)
    before = await _rows(app_pool, t.tenant)
    for person, allowed in ((desk, (403,)), (dispatcher, (403,)), (manager_b, (403, 404))):
        headers = idp.bearer(person.subject, email=person.email)
        put = await t.put(f"/tenders/{uuid7()}", offer(trip, party, [2]), headers)
        assert put.status_code in allowed, (person, put.text)
        post = await answer(t, tender, "accepted", headers=headers)
        assert post.status_code in allowed, (person, post.text)
        for path in (f"/tenders/{tender}", f"/trips/{trip}/tenders"):
            seen = await t.get(path, headers)
            assert seen.status_code in allowed, (person, path, seen.text)
    assert await _rows(app_pool, t.tenant) == before
    for statement in (
        "update gba.transport_tenders set amount = 1",
        "delete from gba.transport_tender_answers",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, t.tenant) as conn:
                await conn.execute(statement)
    await Config(t.client, idp).publish(
        manager_a, t.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await t.put(f"/tenders/{uuid7()}", offer(trip, party, [2]))
    assert off.status_code in (403, 409), off.text
    assert await _rows(app_pool, t.tenant) == before
