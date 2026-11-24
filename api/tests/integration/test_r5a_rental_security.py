"""R5a: recorded security of payment for a rental booking (FAKE data).

docs/plan/PACKAGE_R5A_DESIGN_2026-11-07.md: a security request per booking with an agreement, in
the agreement currency; its states are derived from insert-only events (held, captured, released,
expired) checked by the database, separate from charges.
"""

from typing import Any
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
    rental,
)
from tests.integration.test_r2_rental_bookings import at
from tests.integration.test_r3a_rental_assignment import booked
from tests.integration.test_r4b_rental_agreements import SIGNED
from tests.integration.test_r4c_rental_extensions import agreed
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]

DAMAGE = "FAKE scratched door"


async def request(
    rental: Rental,
    booking: str,
    amount: int = 20_000,
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/security",
        json={"schema_version": 1, "amount": amount, "method": "card_hold", **fields},
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


async def event(
    rental: Rental,
    booking: str,
    kind: str,
    amount: int,
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/security/events",
        json={
            "schema_version": 1,
            "kind": kind,
            "amount": amount,
            "occurred_at": SIGNED,
            **fields,
        },
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


async def cancel(rental: Rental, booking: str) -> None:
    cancelled = await rental.client.post(
        f"{rental.base}/bookings/{booking}/cancellation",
        json={"schema_version": 1, "reason": "FAKE plans changed"},
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert cancelled.status_code == 200, cancelled.text


def figures(body: dict[str, Any]) -> tuple[Any, ...]:
    keys = ("state", "amount", "held", "captured", "released", "expired", "remaining")
    return tuple(body[k] for k in keys)


# R5a-01 -----------------------------------------------------------------------------


async def test_a_security_is_held_captured_in_parts_and_released(rental: Rental) -> None:
    _, _, _, booking = await agreed(rental, 1)
    made = await request(rental, booking)
    assert made.status_code == 200, made.text
    body = made.json()
    assert (body["currency"], body["method"]) == ("EUR", "card_hold")
    assert figures(body) == ("requested", 20_000, 0, 0, 0, 0, 0)
    held = await event(rental, booking, "held", 20_000, reference="FAKE-TERM-1")
    assert held.status_code == 200, held.text
    assert figures(held.json()) == ("held", 20_000, 20_000, 0, 0, 0, 20_000)
    for part in (3_000, 2_000):
        taken = await event(rental, booking, "captured", part, basis=DAMAGE)
        assert taken.status_code == 200, taken.text
    assert figures(taken.json()) == ("held", 20_000, 20_000, 5_000, 0, 0, 15_000)
    freed = await event(rental, booking, "released", 15_000)
    assert freed.status_code == 200, freed.text
    view = (await rental.get(f"/bookings/{booking}/security")).json()
    assert figures(view) == ("released", 20_000, 20_000, 5_000, 15_000, 0, 0)
    assert [(e["sequence"], e["kind"], e["amount"]) for e in view["events"]] == [
        (1, "held", 20_000),
        (2, "captured", 3_000),
        (3, "captured", 2_000),
        (4, "released", 15_000),
    ]
    assert view["events"][1]["basis"] == DAMAGE
    assert view["events"][0]["reference"] == "FAKE-TERM-1"


# R5a-02 -----------------------------------------------------------------------------


async def test_events_follow_the_states(rental: Rental) -> None:
    _, _, _, booking = await agreed(rental, 1)
    assert (await request(rental, booking)).status_code == 200
    early = await event(rental, booking, "released", 20_000)
    assert error(early) == (409, "RENTAL_SECURITY_STATE"), early.text
    partial = await event(rental, booking, "held", 10_000, reference="FAKE-TERM-2")
    assert error(partial) == (409, "RENTAL_SECURITY_STATE"), partial.text
    assert (await event(rental, booking, "held", 20_000, reference="FAKE-TERM-2")).is_success
    again = await event(rental, booking, "held", 20_000, reference="FAKE-TERM-3")
    assert error(again) == (409, "RENTAL_SECURITY_STATE"), again.text
    above = await event(rental, booking, "captured", 20_001, basis=DAMAGE)
    assert error(above) == (409, "RENTAL_SECURITY_STATE"), above.text
    bare = await event(rental, booking, "captured", 1_000)
    assert bare.status_code == 422, bare.text
    short = await event(rental, booking, "expired", 19_000)
    assert error(short) == (409, "RENTAL_SECURITY_STATE"), short.text
    lapsed = await event(rental, booking, "expired", 20_000)
    assert lapsed.status_code == 200, lapsed.text
    assert figures(lapsed.json()) == ("expired", 20_000, 20_000, 0, 0, 20_000, 0)
    after = await event(rental, booking, "captured", 1_000, basis=DAMAGE)
    assert error(after) == (409, "RENTAL_SECURITY_STATE"), after.text
    _, _, _, other = await agreed(rental, 1)
    assert (await request(rental, other, method="cash")).status_code == 200
    never = await event(rental, other, "expired", 0)
    assert never.status_code == 200, never.text
    assert figures(never.json()) == ("expired", 20_000, 0, 0, 0, 0, 0)


# R5a-03 -----------------------------------------------------------------------------


async def test_refusals(rental: Rental) -> None:
    car, _, customer, booking = await agreed(rental, 2)
    plain = await booked(rental, car, customer, at(10), at(11))
    assert error(await request(rental, plain)) == (404, "NOT_FOUND")
    assert error(await event(rental, booking, "held", 1, reference="x")) == (404, "NOT_FOUND")
    for refused in (
        await request(rental, booking, amount=0),
        await request(rental, booking, method="crypto"),
        await request(rental, booking, amount=10**13),
    ):
        assert refused.status_code == 422, refused.text
    assert (await request(rental, booking)).status_code == 200
    second = await request(rental, booking)
    assert error(second) == (409, "RENTAL_SECURITY_EXISTS"), second.text
    assert (await event(rental, booking, "held", 20_000, reference="FAKE-TERM-4")).is_success
    desk = rental.member("front_desk", rental.world.a.location_id)
    denied = await event(rental, booking, "captured", 1_000, headers=desk, basis=DAMAGE)
    assert denied.status_code == 403, denied.text
    await cancel(rental, booking)
    freed = await event(rental, booking, "released", 20_000)
    assert freed.status_code == 200, freed.text
    _, _, _, late = await agreed(rental, 1)
    await cancel(rental, late)
    gone = await request(rental, late)
    assert error(gone) == (409, "RENTAL_BOOKING_CANCELLED"), gone.text


# R5a-04 -----------------------------------------------------------------------------


async def test_sql_keeps_securities_whole(rental: Rental, app_pool: RuntimePool) -> None:
    _, _, _, booking = await agreed(rental, 1)
    assert (await request(rental, booking)).status_code == 200
    assert (await event(rental, booking, "held", 20_000, reference="FAKE-TERM-5")).is_success
    tenant = rental.tenant
    for statement in (
        "update gba.rental_securities set amount = amount + 1",
        "delete from gba.rental_securities",
        "update gba.rental_security_events set amount = amount + 1",
        "delete from gba.rental_security_events",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    copy = (
        "insert into gba.rental_security_events (tenant_id, security_id, sequence, kind, "
        "amount, basis, occurred_at, recorded_by) select tenant_id, security_id, {seq}, "
        "'captured', {amount}, 'FAKE forged', occurred_at, recorded_by "
        "from gba.rental_security_events where sequence = 1 and security_id = "
        "(select id from gba.rental_securities where booking_id = %s)"
    )
    for seq, amount in ((5, 100), (2, 20_001)):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(copy.format(seq=seq, amount=amount), (booking,))
    await agreed(rental, 1)
    currency = (
        "insert into gba.rental_securities (tenant_id, id, booking_id, amount, currency, method, "
        "requested_by) select s.tenant_id, %s, b.id, 100, 'USD', 'cash', s.requested_by "
        "from gba.rental_securities s join gba.rental_bookings b on b.tenant_id = s.tenant_id "
        "and b.id <> s.booking_id join gba.rental_agreements a on a.tenant_id = b.tenant_id "
        "and a.booking_id = b.id limit 1"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(currency, (uuid7(),))
    view = (await rental.get(f"/bookings/{booking}/security")).json()
    assert figures(view) == ("held", 20_000, 20_000, 0, 0, 0, 20_000)


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    _, _, _, booking = await agreed(rental, 1)
    branch = rental.member("manager", away)
    hidden = await request(rental, booking, headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await request(rental, booking, headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await request(rental, booking)
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    count = "select count(*) from gba.rental_securities"
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        mine = await (await conn.execute(count)).fetchone()
    assert mine == (0,)
    async with tenant_transaction(app_pool, rental.world.b.tenant_id) as conn:
        row = await (await conn.execute(count)).fetchone()
    assert row == (0,)
