"""SQL, races and damaged boundaries of I1, on the executor's disposable database."""

import asyncio
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.booking.repository import lock_resource_schedule
from gorgona_booking.business.workforce import save_profile
from gorgona_booking.business.workforce_contracts import ProfileInput
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from gorgona_booking.db.workforce_guard import WORKFORCE_TABLES, assert_workforce_ready
from tests.integration import test_workforce as shared
from tests.integration.booking_support import at
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_workforce import Workforce
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


async def wait_for_resource_waiters(conn: psycopg.AsyncConnection, minimum: int) -> None:
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        row = await (
            await conn.execute(
                "select count(*) from pg_locks where locktype='advisory' and not granted "
                "and database=(select oid from pg_database where datname=current_database())"
            )
        ).fetchone()
        if row is not None and row[0] >= minimum:
            return
        await asyncio.sleep(0.01)
    pytest.fail("I-02: no observed waiting advisory lock in pg_locks")


@pytest.mark.parametrize("raw_sql", [False, True])
async def test_i02_overlapping_cross_branch_assignments_wait_and_admit_one(
    workforce: Workforce,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    owner_conn: psycopg.Connection,
    manager_a: FakeUser,
    idp: FakeIdp,
    raw_sql: bool,
) -> None:
    profile = await workforce.profile()
    business, resource = workforce.world.a.tenant_id, UUID(str(profile["resource_id"]))
    other_location, _ = seed_other_branch(owner_conn, workforce.world.a)
    second = seed_user(owner_conn, f"other-manager-{uuid7()}")
    add_membership(owner_conn, tenant_id=business, user_id=second.user_id, role="manager")
    keys = (uuid7(), uuid7())
    locations = (workforce.world.a.location_id, other_location)

    async def insert(index: int) -> str:
        if not raw_sql:
            auth = (
                workforce.headers if index == 0 else idp.bearer(second.subject, email=second.email)
            )
            response = await workforce.client.put(
                f"{workforce.base}/shifts/{keys[index]}",
                headers={**auth, "Idempotency-Key": str(uuid7())},
                json=workforce.shift(
                    location_id=str(locations[index]), staff_profile_id=profile["profile_id"]
                ),
            )
            if response.status_code == 409:
                assert response.json()["error"]["code"] == "WORKFORCE_CONFLICT", response.text
                return "conflict"
            assert response.status_code == 200, response.text
            return "success"
        try:
            async with tenant_transaction(app_pool, business) as conn:
                await conn.execute(
                    "insert into gba.work_shifts (tenant_id,id,location_id) values (%s,%s,%s)",
                    (business, keys[index], locations[index]),
                )
                await conn.execute(
                    "insert into gba.work_shift_versions "
                    "(tenant_id,shift_id,revision,position,starts_at,ends_at,required"
                    "_skill_ids,status,profile_id,created_by) "
                    "values (%s,%s,1,'FAKE',%s,%s,'{}','published',%s,%s)",
                    (
                        business,
                        keys[index],
                        at(10),
                        at(11),
                        profile["profile_id"],
                        manager_a.user_id,
                    ),
                )
            return "success"
        except psycopg.errors.ExclusionViolation as exc:
            if exc.diag.constraint_name != "resource_allocations_no_overlap":
                raise
            return "conflict"

    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    tasks: list[asyncio.Task[str]] = []
    try:
        async with tenant_transaction(app_pool, business) as conn:
            await lock_resource_schedule(conn, business, resource)
            tasks = [asyncio.create_task(insert(i)) for i in range(2)]
            await wait_for_resource_waiters(monitor, 2)
            assert all(not t.done() for t in tasks)
        assert sorted(await asyncio.wait_for(asyncio.gather(*tasks), 10)) == ["conflict", "success"]
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await monitor.close()


@pytest.mark.parametrize("table", WORKFORCE_TABLES)
async def test_workforce_rows_are_immutable_even_for_owner(
    workforce: Workforce,
    owner_conn: psycopg.Connection,
    table: str,
) -> None:
    profile, skill, shift = await workforce.profile(), uuid7(), uuid7()
    assert (
        await workforce.put(
            f"/skills/{skill}", {"expected_revision": 0, "code": "FAKE", "name": "FAKE"}
        )
    ).status_code == 200
    assert (
        await workforce.put(
            f"/staff/{profile['profile_id']}/skills/{skill}",
            {"expected_revision": 0, "effective_at": at(9).isoformat(), "granted": True},
        )
    ).status_code == 200
    assert (
        await workforce.put(
            f"/shifts/{shift}",
            workforce.shift(
                staff_profile_id=profile["profile_id"], required_skill_ids=[str(skill)]
            ),
        )
    ).status_code == 200
    with owner_tenant_transaction(owner_conn, workforce.world.a.tenant_id):
        for operation in (
            f"update gba.{table} set tenant_id=tenant_id",
            f"delete from gba.{table}",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(operation)


@pytest.mark.parametrize(
    "damage",
    [
        "policy",
        "function",
        "trigger",
        "default",
        "constraint",
        "when",
        "quoted_function",
        "source_kind",
        "shared_literal",
    ],
)
async def test_damaged_workforce_schema_refuses_reads_and_writes(
    workforce: Workforce,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    damage: str,
) -> None:
    shift = uuid7()
    assert (await workforce.put(f"/shifts/{shift}", workforce.shift())).status_code == 200
    if damage == "shared_literal":
        row = owner_conn.execute(
            "select pg_get_functiondef('gba.guard_resource_allocation()'::regprocedure)"
        ).fetchone()
        assert row is not None
        restore = str(row[0])
        change = restore.replace("new.source_kind='shift' then", "new.source_kind='shift ' then", 1)
        assert change != restore
    elif damage == "source_kind":
        change = (
            "alter table gba.resource_allocations drop constraint resource_allocations_source_kind"
        )
        restore = (
            "alter table gba.resource_allocations add constraint "
            "resource_allocations_source_kind check (source_kind in "
            "('booking','reservation','shift'))"
        )
    elif damage == "policy":
        change = (
            "alter policy work_shifts_location_scope on gba.work_shifts "
            "using (true) with check (true)"
        )
        restore = (
            "alter policy work_shifts_location_scope on gba.work_shifts "
            "using (gba.current_location_id() is null or "
            "location_id=gba.current_location_id()) with check "
            "(gba.current_location_id() is null or "
            "location_id=gba.current_location_id())"
        )
    elif damage == "function":
        row = owner_conn.execute(
            "select pg_get_functiondef('gba.guard_work_shift_version()'::regprocedure)"
        ).fetchone()
        assert row is not None
        restore = str(row[0])
        change = (
            "create or replace function gba.guard_work_shift_version() "
            "returns trigger language plpgsql as $$ begin return new; end; $$"
        )
    elif damage == "trigger":
        change = "alter table gba.work_shift_versions disable trigger work_shift_versions_apply"
        restore = "alter table gba.work_shift_versions enable trigger work_shift_versions_apply"
    elif damage == "default":
        change = "alter table gba.work_shift_versions alter column creation_xid drop default"
        restore = (
            "alter table gba.work_shift_versions alter column creation_xid "
            "set default pg_current_xact_id()"
        )
    elif damage == "quoted_function":
        owner_conn.execute(
            'create function gba."CURRENT_LOCATION_ID"() returns uuid '
            "language sql as $$select null::uuid$$"
        )
        change = (
            "alter policy work_shifts_location_scope on gba.work_shifts "
            'using (gba."CURRENT_LOCATION_ID"() is null or '
            'location_id=gba."CURRENT_LOCATION_ID"()) with check '
            '(gba."CURRENT_LOCATION_ID"() is null or '
            'location_id=gba."CURRENT_LOCATION_ID"())'
        )
        restore = (
            "alter policy work_shifts_location_scope on gba.work_shifts "
            "using (gba.current_location_id() is null or "
            "location_id=gba.current_location_id()) with check "
            "(gba.current_location_id() is null or "
            "location_id=gba.current_location_id()); drop function "
            'gba."CURRENT_LOCATION_ID"()'
        )
    elif damage == "when":
        owner_conn.execute("drop trigger work_shift_versions_guard on gba.work_shift_versions")
        change = (
            "create trigger work_shift_versions_guard before insert on "
            "gba.work_shift_versions for each row when (false) execute "
            "function gba.guard_work_shift_version()"
        )
        restore = (
            "drop trigger work_shift_versions_guard on "
            "gba.work_shift_versions; create trigger "
            "work_shift_versions_guard before insert on "
            "gba.work_shift_versions for each row execute function "
            "gba.guard_work_shift_version()"
        )
    else:
        change = (
            "alter table gba.work_shift_versions drop constraint work_shift_versions_interval_check"
        )
        approved = owner_conn.execute(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='gba.work_shift_versions'::regclass "
            "and conname='work_shift_versions_interval_check'"
        ).fetchone()
        assert approved is not None
        restore = (
            "alter table gba.work_shift_versions add constraint "
            "work_shift_versions_interval_check " + str(approved[0])
        )
    try:
        owner_conn.execute(change)
        read = await workforce.client.get(
            f"{workforce.base}/shifts/{shift}", headers=workforce.headers
        )
        assert read.status_code == 503, read.text
        write = await workforce.put(f"/shifts/{uuid7()}", workforce.shift())
        assert write.status_code == 503, write.text
    finally:
        owner_conn.execute(restore)
    async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
        await assert_workforce_ready(conn)


async def test_other_company_and_platform_support_cannot_access_workforce(
    workforce: Workforce,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
) -> None:
    foreign = seed_user(owner_conn, f"foreign-{uuid7()}")
    support = seed_user(owner_conn, f"support-{uuid7()}")
    add_membership(
        owner_conn, tenant_id=workforce.world.b.tenant_id, user_id=foreign.user_id, role="owner"
    )
    grant_platform_admin(owner_conn, user_id=support.user_id, granted_by="test:workforce")
    for user in (foreign, support):
        response = await workforce.client.get(
            workforce.base + "/staff", headers=idp.bearer(user.subject, email=user.email)
        )
        assert response.status_code == 403, response.text


async def test_reinviting_one_user_keeps_one_resource_and_rejects_overlapping_shift(
    workforce: Workforce,
    owner_conn: psycopg.Connection,
) -> None:
    first = await workforce.profile()
    assert (
        await workforce.put(
            f"/shifts/{uuid7()}", workforce.shift(staff_profile_id=first["profile_id"])
        )
    ).status_code == 200
    with owner_tenant_transaction(owner_conn, workforce.world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set status='revoked' where id=%s", (workforce.membership,)
        )
    add_membership(
        owner_conn,
        tenant_id=workforce.world.a.tenant_id,
        user_id=workforce.user.user_id,
        role="artist",
        location_id=workforce.world.a.location_id,
    )
    with owner_tenant_transaction(owner_conn, workforce.world.a.tenant_id):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s and status='active'",
            (workforce.user.user_id,),
        ).fetchone()
    assert row is not None
    response = await workforce.put(
        f"/staff/{uuid7()}",
        {"membership_id": str(row[0]), "location_id": str(workforce.world.a.location_id)},
    )
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["resource_id"] == first["resource_id"]
    refused = await workforce.put(
        f"/shifts/{uuid7()}", workforce.shift(staff_profile_id=second["profile_id"])
    )
    assert refused.status_code == 409, refused.text


async def test_staff_membership_home_cannot_be_silently_changed(
    workforce: Workforce,
    owner_conn: psycopg.Connection,
) -> None:
    await workforce.profile()
    other, _ = seed_other_branch(owner_conn, workforce.world.a)
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        owner_tenant_transaction(owner_conn, workforce.world.a.tenant_id),
    ):
        owner_conn.execute(
            "update gba.memberships set location_id=%s where id=%s", (other, workforce.membership)
        )


async def test_raw_sql_rejects_nonfinite_skill_date(
    workforce: Workforce,
    app_pool: RuntimePool,
    manager_a: FakeUser,
) -> None:
    profile, skill = await workforce.profile(), uuid7()
    assert (
        await workforce.put(
            f"/skills/{skill}", {"expected_revision": 0, "code": "FAKE", "name": "FAKE"}
        )
    ).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.staff_skill_events "
                "(tenant_id,profile_id,skill_id,revision,effective_at,granted,created_by) "
                "values (%s,%s,%s,1,'infinity',true,%s)",
                (workforce.world.a.tenant_id, profile["profile_id"], skill, manager_a.user_id),
            )


async def test_raw_sql_rechecks_required_skills(
    workforce: Workforce,
    app_pool: RuntimePool,
    manager_a: FakeUser,
) -> None:
    profile, skill, shift = await workforce.profile(), uuid7(), uuid7()
    assert (
        await workforce.put(
            f"/skills/{skill}", {"expected_revision": 0, "code": "FAKE", "name": "FAKE"}
        )
    ).status_code == 200

    async def attempt_sql() -> None:
        async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.work_shifts (tenant_id,id,location_id) values (%s,%s,%s)",
                (workforce.world.a.tenant_id, shift, workforce.world.a.location_id),
            )
            await conn.execute(
                "insert into gba.work_shift_versions "
                "(tenant_id,shift_id,revision,position,starts_at,ends_at,required"
                "_skill_ids,status,profile_id,created_by) "
                "values (%s,%s,1,'FAKE',%s,%s,%s,'published',%s,%s)",
                (
                    workforce.world.a.tenant_id,
                    shift,
                    at(10),
                    at(11),
                    [skill],
                    profile["profile_id"],
                    manager_a.user_id,
                ),
            )

    with pytest.raises(psycopg.DatabaseError) as caught:
        await attempt_sql()
    assert caught.value.sqlstate == "GBW02"


async def test_raw_sql_rejects_multidimensional_required_skills(
    workforce: Workforce,
    app_pool: RuntimePool,
    manager_a: FakeUser,
) -> None:
    skill, shift = uuid7(), uuid7()
    assert (
        await workforce.put(
            f"/skills/{skill}", {"expected_revision": 0, "code": "FAKE", "name": "FAKE"}
        )
    ).status_code == 200

    async def attempt_sql() -> None:
        async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.work_shifts (tenant_id,id,location_id) values (%s,%s,%s)",
                (workforce.world.a.tenant_id, shift, workforce.world.a.location_id),
            )
            await conn.execute(
                "insert into gba.work_shift_versions "
                "(tenant_id,shift_id,revision,position,starts_at,ends_at,required"
                "_skill_ids,status,created_by) "
                "values (%s,%s,1,'FAKE',%s,%s,%s,'published',%s)",
                (workforce.world.a.tenant_id, shift, at(10), at(11), [[skill]], manager_a.user_id),
            )

    with pytest.raises(psycopg.DatabaseError):
        await attempt_sql()


@pytest.mark.parametrize("source", ["booking", "reservation", "shift"])
async def test_sql_booking_reservation_staff_and_shift_artist_boundaries(
    workforce: Workforce,
    app_pool: RuntimePool,
    manager_a: FakeUser,
    source: str,
) -> None:
    profile = await workforce.profile()
    tenant = workforce.world.a.tenant_id
    resource = profile["resource_id"] if source != "shift" else workforce.world.artist_a1

    async def attempt_sql() -> None:
        async with tenant_transaction(app_pool, tenant) as conn:
            subject = uuid7()
            if source == "booking":
                row = await (
                    await conn.execute(
                        "insert into gba.bookings "
                        "(tenant_id,location_id,variant_id,status,starts_at,ends_at,total"
                        "_cents,currency,quote,created_by) "
                        "values "
                        "(%s,%s,%s,'CONFIRMED',%s,%s,5000,'USD','{}','test:workforce') "
                        "returning id",
                        (
                            tenant,
                            workforce.world.a.location_id,
                            workforce.world.catalog_a.base_variant_id,
                            at(10),
                            at(11),
                        ),
                    )
                ).fetchone()
                assert row is not None
                await conn.execute(
                    "insert into gba.booking_allocations "
                    "(tenant_id,booking_id,booking_status,resource_id,during) "
                    "values (%s,%s,'CONFIRMED',%s,tstzrange(%s,%s,'[)'))",
                    (tenant, row[0], resource, at(10), at(11)),
                )
            else:
                if source == "reservation":
                    await conn.execute(
                        "insert into gba.resource_reservations "
                        "(tenant_id,id,location_id,starts_at,ends_at,resource_count,created_by) "
                        "values (%s,%s,%s,%s,%s,1,%s)",
                        (
                            tenant,
                            subject,
                            workforce.world.a.location_id,
                            at(10),
                            at(11),
                            manager_a.user_id,
                        ),
                    )
                await conn.execute(
                    "insert into gba.resource_allocations "
                    "(tenant_id,resource_id,source_kind,source_id,during,state) "
                    "values (%s,%s,%s,%s,tstzrange(%s,%s,'[)'),'confirmed')",
                    (tenant, resource, source, subject, at(10), at(11)),
                )

    with pytest.raises(psycopg.errors.CheckViolation, match="staff occupancy is only for shifts"):
        await attempt_sql()


async def test_reinvite_other_home_refuses_new_resource_without_changing_history(
    workforce: Workforce,
    owner_conn: psycopg.Connection,
) -> None:
    first = await workforce.profile()
    other, _ = seed_other_branch(owner_conn, workforce.world.a)
    with owner_tenant_transaction(owner_conn, workforce.world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set status='revoked' where id=%s", (workforce.membership,)
        )
    add_membership(
        owner_conn,
        tenant_id=workforce.world.a.tenant_id,
        user_id=workforce.user.user_id,
        role="artist",
        location_id=other,
    )
    with owner_tenant_transaction(owner_conn, workforce.world.a.tenant_id):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s and status='active'",
            (workforce.user.user_id,),
        ).fetchone()
    assert row is not None
    refused = await workforce.put(
        f"/staff/{uuid7()}", {"membership_id": str(row[0]), "location_id": str(other)}
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "WORKFORCE_CONFLICT"
    listed = await workforce.client.get(workforce.base + "/staff", headers=workforce.headers)
    assert [r["resource_id"] for r in listed.json()["items"]] == [first["resource_id"]]


async def test_profile_creation_locks_membership_against_home_move(
    workforce: Workforce,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    manager_a: FakeUser,
) -> None:
    other, _ = seed_other_branch(owner_conn, workforce.world.a)

    async def move_home() -> str:
        try:
            async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
                await conn.execute(
                    "update gba.memberships set location_id=%s where id=%s",
                    (other, workforce.membership),
                )
            return "moved"
        except psycopg.errors.CheckViolation:
            return "refused"

    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    task: asyncio.Task[str] | None = None
    try:
        async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
            await save_profile(
                conn,
                workforce.world.a.tenant_id,
                uuid7(),
                manager_a.user_id,
                f"user:{manager_a.user_id}",
                str(uuid7()),
                ProfileInput(
                    membership_id=workforce.membership, location_id=workforce.world.a.location_id
                ),
            )
            task = asyncio.create_task(move_home())
            observed = False
            deadline = asyncio.get_running_loop().time() + 8
            while not task.done() and asyncio.get_running_loop().time() < deadline:
                row = await (
                    await monitor.execute(
                        "select exists(select 1 from pg_locks l "
                        "join pg_stat_activity a using(pid) where a.datname=current_database() "
                        "and l.locktype='transactionid' and not l.granted)"
                    )
                ).fetchone()
                if row == (True,):
                    observed = True
                    break
                await asyncio.sleep(0.01)
            assert observed, "The membership move did not wait in pg_locks"
        assert await asyncio.wait_for(task, 10) == "refused"
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await monitor.close()


async def test_scoped_sql_cannot_move_a_membership_whose_profile_is_hidden(
    workforce: Workforce,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    await workforce.profile()
    other, _ = seed_other_branch(owner_conn, workforce.world.a)

    async def attempt_sql() -> None:
        async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
            await conn.execute("select set_config('gba.location_id',%s,true)", (str(other),))
            await conn.execute(
                "update gba.memberships set location_id=%s where id=%s",
                (other, workforce.membership),
            )

    with pytest.raises(psycopg.errors.CheckViolation):
        await attempt_sql()


async def test_raw_sql_refuses_finite_shift_dates_outside_python_range(
    workforce: Workforce,
    app_pool: RuntimePool,
    manager_a: FakeUser,
) -> None:
    shift = uuid7()

    async def attempt_sql() -> None:
        async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.work_shifts (tenant_id,id,location_id) values (%s,%s,%s)",
                (workforce.world.a.tenant_id, shift, workforce.world.a.location_id),
            )
            await conn.execute(
                "insert into gba.work_shift_versions "
                "(tenant_id,shift_id,revision,position,starts_at,ends_at,required"
                "_skill_ids,status,created_by) "
                "values (%s,%s,1,'FAKE','10000-01-01 UTC','10000-01-01 01:00 "
                "UTC','{}','published',%s)",
                (workforce.world.a.tenant_id, shift, manager_a.user_id),
            )

    with pytest.raises(psycopg.errors.CheckViolation):
        await attempt_sql()
