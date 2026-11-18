"""RENT-01 R-09: problem reports on a rental booking (FAKE data).

A customer company reports a problem only through a live grant with rental.customer_answer, for
the booking it is bound to now; otherwise the business records the report with its source and the
reporter's name. Reports are insert-only, numbered per booking and rechecked by the database.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_r09_rental_customer_answer import _linked_booking
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    error,
    idp,
    manager_a,
    rental,
)
from tests.integration.test_r4b_rental_agreements import priced_booking
from tests.integration.test_r5a_rental_security import cancel
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "client", "idp", "manager_a", "owner_a", "owner_b", "parties", "rental"]
pytestmark = pytest.mark.anyio


def ago(hours: int) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def staff_report(**changes: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "damage",
        "description": "FAKE scratch on the door, reported by phone",
        "occurred_at": ago(2),
        "source": "phone",
        "reported_by": "FAKE Renter",
        **changes,
    }


async def post(
    rental: Rental, path: str, body: dict[str, Any], headers: dict[str, str], key: str | None = None
) -> Any:
    return await rental.client.post(
        rental.base + path,
        json=body,
        headers={**headers, "Idempotency-Key": key or str(uuid7())},
    )


async def test_a_customer_reports_a_problem_through_a_live_grant(
    rental: Rental, parties: Parties, owner_a: FakeUser, owner_b: FakeUser, app_pool: RuntimePool
) -> None:
    booking = await _linked_booking(rental)
    grant = await parties.active_grant(
        owner_a,
        owner_b,
        [owner_b],
        permissions=["rental.customer_answer"],
        location_id=str(rental.world.a.location_id),
    )
    path = f"/bookings/{booking}/customer-problems/{grant}"
    headers = parties.headers(owner_b)
    shown = await rental.get(path, headers)
    assert shown.status_code == 200, shown.text
    assert (shown.json()["binding_revision"], shown.json()["items"]) == (1, [])

    report = {
        "schema_version": 1,
        "binding_revision": 1,
        "kind": "breakdown",
        "description": "FAKE engine warning light on the highway",
        "occurred_at": ago(1),
    }
    stale = await post(rental, path, {**report, "binding_revision": 2}, headers)
    assert error(stale) == (409, "RENTAL_REVISION_CONFLICT"), stale.text
    key = str(uuid7())
    made = await post(rental, path, report, headers, key)
    assert made.status_code == 200, made.text
    saved = made.json()
    assert (saved["number"], saved["source"], saved["company_id"], saved["reported_by"]) == (
        1,
        "platform",
        str(rental.world.b.tenant_id),
        None,
    )
    replay = await post(rental, path, report, headers, key)
    assert (replay.status_code, replay.json()) == (200, saved), replay.text
    reused = await post(rental, path, {**report, "description": "FAKE other words"}, headers, key)
    assert error(reused) == (422, "IDEMPOTENCY_KEY_REUSED"), reused.text

    mine = await rental.get(path, headers)
    assert [r["number"] for r in mine.json()["items"]] == [1], mine.text
    staff = await rental.get(f"/bookings/{booking}/problems")
    assert [(r["number"], r["source"]) for r in staff.json()["items"]] == [(1, "platform")]
    assert (await rental.get(f"/bookings/{booking}/problems", headers)).status_code == 403
    wrong = await rental.get(f"/bookings/{booking}/customer-problems/{uuid7()}", headers)
    assert wrong.status_code == 403, wrong.text
    _, unbound = await priced_booking(rental)
    hidden = await rental.get(f"/bookings/{unbound}/customer-problems/{grant}", headers)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text

    async with tenant_transaction(app_pool, rental.tenant) as conn:
        proof = await (
            await conn.execute(
                "select source, company_id, grant_id, binding_revision, recorded_by, reported_by "
                "from gba.rental_problem_reports where booking_id = %s",
                (booking,),
            )
        ).fetchall()
    assert proof == [
        ("platform", rental.world.b.tenant_id, UUID(str(grant)), 1, owner_b.user_id, None)
    ]

    revoked = await parties.act(owner_a, rental.tenant, grant, "revoke", 2)
    assert revoked.status_code == 200, revoked.text
    after = await post(rental, path, {**report, "description": "FAKE again"}, headers)
    assert after.status_code == 403, after.text


async def test_the_business_records_off_platform_reports_with_their_source(
    rental: Rental,
) -> None:
    _, booking = await priced_booking(rental)
    path = f"/bookings/{booking}/problems"
    key = str(uuid7())
    sent = staff_report()
    first = await post(rental, path, sent, rental.headers, key)
    assert first.status_code == 200, first.text
    saved = first.json()
    assert (saved["number"], saved["kind"], saved["source"], saved["reported_by"]) == (
        1,
        "damage",
        "phone",
        "FAKE Renter",
    )
    assert saved["company_id"] is None
    again = await post(rental, path, sent, rental.headers, key)
    assert (again.status_code, again.json()) == (200, saved), again.text
    second = await post(rental, path, staff_report(source="email", kind="other"), rental.headers)
    assert second.status_code == 200, second.text
    listed = await rental.get(path)
    assert [(r["number"], r["source"]) for r in listed.json()["items"]] == [
        (1, "phone"),
        (2, "email"),
    ]

    for invalid in (
        staff_report(source="platform"),
        staff_report(reported_by=" "),
        staff_report(description=""),
        staff_report(kind="theft"),
        staff_report(occurred_at="2031-06-01T10:00:00"),
    ):
        refused = await post(rental, path, invalid, rental.headers)
        assert refused.status_code == 422, (invalid, refused.text)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    future = await post(rental, path, staff_report(occurred_at=tomorrow), rental.headers)
    assert error(future) == (409, "RENTAL_FUTURE_TIME"), future.text

    desk = rental.member("front_desk", rental.world.a.location_id)
    assert (await post(rental, path, staff_report(), desk)).status_code == 403
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    branch = rental.member("manager", away)
    assert error(await post(rental, path, staff_report(), branch)) == (404, "NOT_FOUND")
    assert error(await rental.get(path, branch)) == (404, "NOT_FOUND")
    missing = await post(rental, f"/bookings/{uuid7()}/problems", staff_report(), rental.headers)
    assert error(missing) == (404, "NOT_FOUND"), missing.text

    await cancel(rental, booking)
    late = await post(rental, path, staff_report(), rental.headers)
    assert error(late) == (409, "RENTAL_BOOKING_CANCELLED"), late.text


async def test_sql_keeps_problem_reports_whole_and_the_module_gate_holds(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    _, booking = await priced_booking(rental)
    path = f"/bookings/{booking}/problems"
    assert (await post(rental, path, staff_report(), rental.headers)).status_code == 200
    for statement in (
        "update gba.rental_problem_reports set description = 'FAKE edited'",
        "delete from gba.rental_problem_reports",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, rental.tenant) as conn:
                await conn.execute(statement)
    forged = (
        "insert into gba.rental_problem_reports (tenant_id, booking_id, number, kind, "
        "description, occurred_at, source, company_id, grant_id, binding_revision, recorded_by) "
        "values (%s, %s, %s, 'other', 'FAKE forged', now() - interval '1 hour', 'platform', "
        "%s, %s, 1, %s)"
    )
    for number in (2, 5):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, rental.tenant) as conn:
                await conn.execute(
                    forged,
                    (
                        rental.tenant,
                        booking,
                        number,
                        rental.world.b.tenant_id,
                        uuid7(),
                        manager_a.user_id,
                    ),
                )

    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await post(rental, path, staff_report(), rental.headers)
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        row = await (
            await conn.execute("select count(*) from gba.rental_problem_reports")
        ).fetchone()
    assert row == (1,)
