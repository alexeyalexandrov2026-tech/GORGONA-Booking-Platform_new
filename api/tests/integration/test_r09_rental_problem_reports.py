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

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_salon, seed_user
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


def customer_report(revision: int, **changes: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "binding_revision": revision,
        "kind": "breakdown",
        "description": "FAKE engine warning light on the highway",
        "occurred_at": ago(1),
        **changes,
    }


SCOPE = "rental_problem_reports_customer_scope"
FORGED = (
    "insert into gba.rental_problem_reports (tenant_id, booking_id, number, kind, "
    "description, occurred_at, source, company_id, grant_id, binding_revision, recorded_by) "
    "values (%s, %s, %s, 'other', 'FAKE forged', now() - interval '1 hour', 'platform', "
    "%s, %s, 1, %s)"
)


async def forge_report(
    app_pool: RuntimePool,
    rental: Rental,
    booking: str,
    grant: UUID,
    user: FakeUser,
    *,
    number: int = 1,
    location: UUID | None = None,
) -> str | None:
    """Insert a platform report row by SQL as `user`; the refused constraint, or None."""
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        await set_user_context(conn, user.user_id)
        if location is not None:
            await conn.execute(
                "select pg_catalog.set_config('gba.location_id', %s, true)", (str(location),)
            )
        async with conn.transaction(force_rollback=True):
            try:
                async with conn.transaction():
                    await conn.execute(
                        FORGED,
                        (
                            rental.tenant,
                            booking,
                            number,
                            rental.world.b.tenant_id,
                            grant,
                            user.user_id,
                        ),
                    )
            except psycopg.errors.CheckViolation as exc:
                return exc.diag.constraint_name
    return None


def company_name(rental: Rental, company: UUID) -> str:
    """The name the company gave when it accepted its latest grant from the rental business."""
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        row = rental.owner_conn.execute(
            "select servicer_display_name from gba.delegation_grants "
            "where owner_tenant_id = %s and servicer_tenant_id = %s "
            "order by created_at desc limit 1",
            (rental.tenant, company),
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    return str(row[0])


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
    resaved = await rental.put(
        f"/bookings/{booking}/customer-company",
        {"expected_revision": 1, "company_id": str(rental.world.b.tenant_id)},
    )
    assert resaved.status_code == 200, resaved.text
    retried = await post(rental, path, report, headers, key)
    assert (retried.status_code, retried.json()) == (200, saved), retried.text
    for invalid in (
        {**report, "binding_revision": 2, "occurred_at": "1999-12-31T23:59:00+00:00"},
        {**report, "binding_revision": 2, "description": "FAKE\x00nul"},
        {**report, "binding_revision": 2, "description": "FAKE\x1bescape"},
    ):
        refused = await post(rental, path, invalid, headers)
        assert refused.status_code == 422, (invalid, refused.text)

    mine = await rental.get(path, headers)
    assert [r["number"] for r in mine.json()["items"]] == [1], mine.text
    staff = await rental.get(f"/bookings/{booking}/problems")
    assert [(r["number"], r["source"], r["company_name"]) for r in staff.json()["items"]] == [
        (1, "platform", company_name(rental, rental.world.b.tenant_id))
    ]
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
        # R-09 review: before 2000, NUL and control characters are invalid requests, not 500s.
        staff_report(occurred_at="1999-12-31T23:59:59+00:00"),
        staff_report(description="FAKE\x00nul"),
        staff_report(description="FAKE\x07bell"),
        staff_report(reported_by="FAKE\x00Renter"),
        staff_report(reported_by="FAKE\nRenter"),
    ):
        refused = await post(rental, path, invalid, rental.headers)
        assert refused.status_code == 422, (invalid, refused.text)
    lines = await post(
        rental,
        path,
        staff_report(
            description="FAKE line one\nline two\ttabbed", occurred_at="2000-01-01T00:00:00Z"
        ),
        rental.headers,
    )
    assert lines.status_code == 200, lines.text
    assert lines.json()["number"] == 3
    assert lines.json()["company_name"] is None
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
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
) -> None:
    booking = await _linked_booking(rental)
    grant = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"]
    )
    path = f"/bookings/{booking}/problems"
    assert (await post(rental, path, staff_report(), rental.headers)).status_code == 200
    for statement in (
        "update gba.rental_problem_reports set description = 'FAKE edited'",
        "delete from gba.rental_problem_reports",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, rental.tenant) as conn:
                await conn.execute(statement)
    # A company-wide employee who is no delegate cannot record a platform report under a real
    # grant and binding; the next number is right, so only the grant check refuses it.
    assert await forge_report(app_pool, rental, booking, grant, manager_a, number=2) == SCOPE
    assert (
        await forge_report(app_pool, rental, booking, grant, manager_a, number=5)
        == "rental_problem_reports_sequence_check"
    )
    # The delegate itself passes every rule (the row is rolled back).
    assert await forge_report(app_pool, rental, booking, grant, owner_b, number=2) is None

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


async def test_branch_scoped_sql_rechecks_the_customer_grant(
    rental: Rental,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    manager_a: FakeUser,
    app_pool: RuntimePool,
) -> None:
    """R-09 review: in a branch-scoped session the guard rechecks the grant (0126)."""
    booking = await _linked_booking(rental)
    here = rental.world.a.location_id
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    elsewhere = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"], location_id=str(away)
    )
    # Another branch's grant does not cover a booking of this branch.
    assert await forge_report(app_pool, rental, booking, elsewhere, owner_b, location=here) == SCOPE
    revoked = await parties.act(owner_a, rental.tenant, elsewhere, "revoke", 2)
    assert revoked.status_code == 200, revoked.text

    live = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"], location_id=str(here)
    )
    # The live delegate passes in its branch (the row is rolled back); a user who is no
    # delegate does not, whatever it names as the recording user.
    assert await forge_report(app_pool, rental, booking, live, owner_b, location=here) is None
    assert await forge_report(app_pool, rental, booking, live, manager_a, location=here) == SCOPE
    revoked = await parties.act(owner_a, rental.tenant, live, "revoke", 2)
    assert revoked.status_code == 200, revoked.text
    # A revoked grant is refused in the branch as well.
    assert await forge_report(app_pool, rental, booking, live, owner_b, location=here) == SCOPE
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        row = await (
            await conn.execute(
                "select count(*) from gba.rental_problem_reports where booking_id = %s", (booking,)
            )
        ).fetchone()
    assert row == (0,)


async def test_a_delegate_sees_only_its_own_company_reports(
    rental: Rental, parties: Parties, owner_a: FakeUser, owner_b: FakeUser
) -> None:
    """R-09 review: the customer list holds only the reports of the grant's own company."""
    booking = await _linked_booking(rental)
    here = str(rental.world.a.location_id)
    grant_b = await parties.active_grant(
        owner_a, owner_b, [owner_b], permissions=["rental.customer_answer"], location_id=here
    )
    path_b = f"/bookings/{booking}/customer-problems/{grant_b}"
    made_b = await post(rental, path_b, customer_report(1), parties.headers(owner_b))
    assert made_b.status_code == 200, made_b.text

    other = seed_salon(rental.owner_conn, "r09c")
    owner_c = seed_user(rental.owner_conn, f"r09-owner-c-{uuid7()}")
    add_membership(
        rental.owner_conn, tenant_id=other.tenant_id, user_id=owner_c.user_id, role="owner"
    )
    grant_c = uuid7()
    issued = await parties.issue(
        owner_a,
        grant_c,
        terms={
            "servicer_business_id": str(other.tenant_id),
            "permissions": ["rental.customer_answer"],
            "location_id": here,
        },
    )
    assert issued.status_code == 200, issued.text
    taken = await parties.act(owner_c, other.tenant_id, grant_c, "accept", 1, [owner_c])
    assert taken.status_code == 200, taken.text
    rebound = await rental.put(
        f"/bookings/{booking}/customer-company",
        {"expected_revision": 1, "company_id": str(other.tenant_id)},
    )
    assert rebound.status_code == 200, rebound.text

    path_c = f"/bookings/{booking}/customer-problems/{grant_c}"
    headers_c = parties.headers(owner_c)
    shown_c = await rental.get(path_c, headers_c)
    assert shown_c.status_code == 200, shown_c.text
    assert (shown_c.json()["binding_revision"], shown_c.json()["items"]) == (2, [])
    made_c = await post(rental, path_c, customer_report(2, kind="damage"), headers_c)
    assert made_c.status_code == 200, made_c.text
    assert (made_c.json()["number"], made_c.json()["company_id"]) == (2, str(other.tenant_id))
    assert made_c.json()["company_name"] == company_name(rental, other.tenant_id)
    unbound = await rental.get(path_b, parties.headers(owner_b))
    assert error(unbound) == (404, "NOT_FOUND"), unbound.text

    back = await rental.put(
        f"/bookings/{booking}/customer-company",
        {"expected_revision": 2, "company_id": str(rental.world.b.tenant_id)},
    )
    assert back.status_code == 200, back.text
    shown_b = await rental.get(path_b, parties.headers(owner_b))
    assert shown_b.status_code == 200, shown_b.text
    assert [(r["number"], r["company_id"]) for r in shown_b.json()["items"]] == [
        (1, str(rental.world.b.tenant_id))
    ]
    staff = await rental.get(f"/bookings/{booking}/problems")
    assert [(r["number"], r["company_name"]) for r in staff.json()["items"]] == [
        (1, company_name(rental, rental.world.b.tenant_id)),
        (2, company_name(rental, other.tenant_id)),
    ]
