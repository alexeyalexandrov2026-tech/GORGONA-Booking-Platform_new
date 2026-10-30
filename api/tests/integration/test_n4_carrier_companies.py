"""N4: a carrier answers in its own company and tracks its tendered work (FAKE data only).

docs/plan/PACKAGE_N4_DESIGN_2026-10-28.md: the broker links a carrier to its company; the
company's delegates answer through a grant with the right transport.tender and record stop
events only on the legs tendered to their carrier and accepted.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_m1_transport_planning import Transport, accepted, error, transport
from tests.integration.test_m3_transport_events import event
from tests.integration.test_m4_dispatcher_grants import acting, dispatcher
from tests.integration.test_n1_broker_carriers import authority, carrier, profile
from tests.integration.test_n2_tenders import _broker, _trip, answer, offer, state
from tests.integration.test_n3_rate_confirmations import proposal
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
__all__ = [
    "accepted",
    "client",
    "dispatcher",
    "idp",
    "manager_a",
    "owner_a",
    "owner_b",
    "parties",
    "transport",
]

CARRIER = ["transport.read", "transport.tender", "transport.events"]


def link(company: UUID | None, revision: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "expected_revision": revision,
        "carrier_business_id": None if company is None else str(company),
    }


def at(hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def fresh_offer(trip: UUID, party: UUID, legs: list[int], **changes: Any) -> dict[str, Any]:
    """N8: an offer open now, since a carrier answers at the server's time."""
    return offer(trip, party, legs, offered_at=at(-1), expires_at=at(24), **changes)


async def fresh_broker(t: Transport) -> UUID:
    """Authority and one carrier profile checked today, never stale at the server's time."""
    today = datetime.now(UTC).date().isoformat()
    assert (await t.put("/broker-authority", authority(0, checked_on=today))).status_code == 200
    party = await carrier(t, "FAKE Fresh Carrier")
    saved = await t.put(f"/carriers/{party}/profile", profile(0, checked_on=today))
    assert saved.status_code == 200, saved.text
    return party


async def carrier_answer(t: Transport, tender: UUID, kind: str) -> httpx.Response:
    return await t.client.post(
        f"{t.base}/tenders/{tender}/carrier-answers",
        json={"schema_version": 1, "kind": kind},
        headers={**t.headers, "Idempotency-Key": str(uuid7())},
    )


async def carrier_agree(t: Transport, tender: UUID, revision: int, kind: str) -> httpx.Response:
    return await t.client.post(
        f"{t.base}/tenders/{tender}/rate-confirmation/{revision}/carrier-answers",
        json={"schema_version": 1, "kind": kind},
        headers={**t.headers, "Idempotency-Key": str(uuid7())},
    )


async def linked(t: Transport, world: BookingWorld) -> tuple[UUID, UUID, UUID]:
    """A trip, its carrier linked to business B, and a tender of leg 2 (stops 1 and 3)."""
    trip = await _trip(t)
    party = await fresh_broker(t)
    saved = await t.put(f"/carriers/{party}/company", link(world.b.tenant_id, 0))
    assert saved.status_code == 200, saved.text
    tender = uuid7()
    assert (await t.put(f"/tenders/{tender}", fresh_offer(trip, party, [2]))).status_code == 200
    return trip, party, tender


async def _answers(pool: RuntimePool, tenant: UUID, table: str) -> list[tuple[str, str | None]]:
    async with tenant_transaction(pool, tenant) as conn:
        rows = await (
            await conn.execute(f"select source, servicer_business_id::text from gba.{table}")
        ).fetchall()
    return [(row[0], row[1]) for row in rows]


# N4-01 ------------------------------------------------------------------------------


async def test_the_broker_links_a_carrier_to_its_company_in_versions(
    transport: Transport, world: BookingWorld
) -> None:
    t = transport
    party = await _broker(t)
    other = await carrier(t, "FAKE Other Carrier")
    first = await t.put(f"/carriers/{party}/company", link(world.b.tenant_id, 0))
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 1
    assert first.json()["carrier_business_id"] == str(world.b.tenant_id)
    stale = await t.put(f"/carriers/{party}/company", link(world.b.tenant_id, 0))
    assert error(stale) == (409, "TRANSPORT_CARRIER_COMPANY_CONFLICT")
    taken = await t.put(f"/carriers/{other}/company", link(world.b.tenant_id, 0))
    assert error(taken) == (409, "TRANSPORT_CARRIER_COMPANY_CONFLICT")
    own = await t.put(f"/carriers/{other}/company", link(world.a.tenant_id, 0))
    assert own.status_code == 422, own.text
    unlinked = await t.put(f"/carriers/{party}/company", link(None, 1))
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["revision"] == 2
    assert unlinked.json()["carrier_business_id"] is None
    moved = await t.put(f"/carriers/{other}/company", link(world.b.tenant_id, 0))
    assert moved.status_code == 200, moved.text
    seen = await t.get(f"/carriers/{party}/company")
    assert seen.status_code == 200, seen.text
    assert [v["carrier_business_id"] for v in seen.json()["versions"]] == [
        str(world.b.tenant_id),
        None,
    ]


# N4-02 ------------------------------------------------------------------------------


async def test_the_linked_company_answers_its_tender_through_its_grant(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    world: BookingWorld,
    app_pool: RuntimePool,
) -> None:
    t = transport
    trip, _, tender = await linked(t, world)
    d = acting(t, parties, dispatcher)
    assert (await carrier_answer(d, tender, "accepted")).status_code == 403
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=CARRIER)
    assert (await answer(d, tender, "accepted")).status_code == 403
    assert (await carrier_answer(d, tender, "withdrawn")).status_code == 422
    # A tender to another carrier is not this company's to answer.
    other = await carrier(t, "FAKE Unlinked Carrier")
    assert (await t.put(f"/carriers/{other}/profile", profile(0))).status_code == 200
    foreign = uuid7()
    assert (await t.put(f"/tenders/{foreign}", offer(trip, other, [1]))).status_code == 200
    assert (await carrier_answer(d, foreign, "accepted")).status_code == 403
    took = await carrier_answer(d, tender, "accepted")
    assert took.status_code == 200, took.text
    assert await state(t, tender) == "accepted"
    again = await carrier_answer(d, tender, "declined")
    assert again.status_code == 409, again.text
    assert await _answers(app_pool, t.tenant, "transport_tender_answers") == [
        ("platform", str(world.b.tenant_id))
    ]
    # The broker's own staff never hold the carrier's right.
    assert (await carrier_answer(t, foreign, "accepted")).status_code == 403


# N4-03 ------------------------------------------------------------------------------


async def test_the_linked_company_answers_a_rate_confirmation_version(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    world: BookingWorld,
    app_pool: RuntimePool,
) -> None:
    t = transport
    _, _, tender = await linked(t, world)
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=CARRIER)
    d = acting(t, parties, dispatcher)
    assert (await carrier_answer(d, tender, "accepted")).status_code == 200
    path = f"/tenders/{tender}/rate-confirmation"
    assert (await t.put(path, proposal(1, proposed_at=at(0)))).status_code == 200
    assert (await carrier_agree(d, tender, 1, "agreed")).status_code == 409
    agreed = await carrier_agree(d, tender, 2, "agreed")
    assert agreed.status_code == 200, agreed.text
    assert agreed.json()["in_force"]["revision"] == 2
    assert (await carrier_agree(d, tender, 2, "declined")).status_code == 409
    rows = await _answers(app_pool, t.tenant, "transport_rate_confirmation_answers")
    assert sorted(rows, key=str) == sorted(
        [("platform", str(world.b.tenant_id)), ("platform", str(world.b.tenant_id))], key=str
    )


# N4-04 ------------------------------------------------------------------------------


async def test_a_linked_carrier_tracks_only_its_accepted_legs(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    world: BookingWorld,
) -> None:
    t = transport
    trip, _, tender = await linked(t, world)
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=CARRIER)
    d = acting(t, parties, dispatcher)
    early = await event(d, trip, "loaded", 1, quantities=((2, 6),))
    assert early.status_code == 403, early.text
    assert (await carrier_answer(d, tender, "accepted")).status_code == 200
    loaded = await event(d, trip, "loaded", 1, quantities=((2, 6),), source_id="FAKE-N4-1")
    assert loaded.status_code == 200, loaded.text
    repeat = await event(d, trip, "loaded", 1, quantities=((2, 6),), source_id="FAKE-N4-1")
    assert repeat.status_code == 200, repeat.text
    assert repeat.json() == loaded.json()
    for refused in (
        await event(d, trip, "loaded", 1, quantities=((1, 4),)),
        await event(d, trip, "arrived", 2),
    ):
        assert refused.status_code == 403, refused.text
    withdrawn = await answer(t, tender, "withdrawn", at=at(0.05))
    assert withdrawn.status_code == 200, withdrawn.text
    late = await event(d, trip, "delivered", 3, quantities=((2, 6),))
    assert late.status_code == 403, late.text
    # The broker keeps recording on its own trip.
    assert (await event(t, trip, "arrived", 2)).status_code == 200


# N4-05 ------------------------------------------------------------------------------


async def test_links_are_insert_only_and_need_the_module(
    transport: Transport,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    world: BookingWorld,
) -> None:
    t = transport
    party = await _broker(t)
    saved = await t.put(f"/carriers/{party}/company", link(world.b.tenant_id, 0))
    assert saved.status_code == 200, saved.text
    for statement in (
        "update gba.transport_carrier_companies set carrier_business_id = null",
        "delete from gba.transport_carrier_companies",
        "update gba.transport_tender_answers set source = 'platform'",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, t.tenant) as conn:
                await conn.execute(statement)
    await Config(t.client, idp).publish(
        manager_a, t.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await t.put(f"/carriers/{party}/company", link(None, 1))
    assert off.status_code in (403, 409), off.text
