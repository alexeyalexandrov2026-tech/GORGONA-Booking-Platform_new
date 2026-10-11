"""I-08 races require two observed waiters; include old-snapshot raw SQL."""

import asyncio
from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.booking.repository import lock_resource_schedule
from gorgona_booking.business.configuration_contracts import ConfigurationCommand
from gorgona_booking.business.configurations import publish_version
from gorgona_booking.db.pool import RuntimePool, set_tenant_context, tenant_transaction
from tests.integration import test_timesheets as shared
from tests.integration.booking_support import at
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_timesheet_guards import closed
from tests.integration.test_timesheets import Times
from tests.integration.test_workforce_guards import wait_for_resource_waiters
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
times = shared.times
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


@pytest.mark.parametrize("mode", ["api", "sql", "sql_rr"])
@pytest.mark.parametrize("race", ["clock_in", "correction", "approval", "approve_correct"])
async def test_time_races_wait_then_admit_one_effect(
    times: Times,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    manager_a: FakeUser,
    mode: str,
    race: str,
) -> None:
    business = times.changes.workforce.world.a.tenant_id
    entries = [] if race == "clock_in" else [await closed(times)]
    if race == "approval":
        entries.append(await closed(times))

    async def run(index: int) -> str:
        action = (
            "correct"
            if race == "correction" or (race == "approve_correct" and index == 1)
            else "approve"
        )
        employee = times.changes.workforce.user.user_id
        user = employee if action == "correct" or race == "clock_in" else manager_a.user_id
        entry = entries[index] if race == "approval" else entries[0] if entries else None
        if mode == "api":
            if race == "clock_in":
                response = await times.start()
            elif action == "correct":
                assert entry is not None
                response = await times.command(
                    entry,
                    "correct",
                    starts_at=at(10).isoformat(),
                    ends_at=at(12 + index).isoformat(),
                    breaks=[],
                    reason=f"FAKE race{index}",
                )
            else:
                assert entry is not None
                response = await times.command(entry, "approve", times.changes.workforce.headers)
            if response.status_code == 409:
                assert response.json()["error"]["code"] == "WORKFORCE_CONFLICT", response.text
                return "conflict"
            assert response.status_code == 200, response.text
            return "success"
        try:
            async with app_pool.connection() as conn, conn.transaction():
                if mode == "sql_rr":
                    await conn.execute("set transaction isolation level repeatable read")
                await set_tenant_context(conn, business)
                await set_user_context(conn, user)
                # Establish BOTH snapshots before the advisory barrier releases.
                await conn.execute("select count(*) from gba.time_entry_state")
                if race == "clock_in":
                    await conn.execute(
                        "insert into gba.time_entries "
                        "(tenant_id,id,profile_id,starts_at,created_by) values (%s,%s,%s,%s,%s)",
                        (business, uuid7(), times.changes.left_profile, at(10), user),
                    )
                else:
                    assert entry is not None
                    await conn.execute(
                        "insert into gba.time_entry_revisions "
                        "(tenant_id,entry_id,revision,action,starts_at,ends_at,"
                        "break_starts,break_ends,reason,created_by) "
                        "values (%s,%s,3,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            business,
                            entry["entry_id"],
                            action,
                            at(10) if action == "correct" else None,
                            at(12 + index) if action == "correct" else None,
                            [] if action == "correct" else None,
                            [] if action == "correct" else None,
                            "FAKE SQL race" if action == "correct" else None,
                            user,
                        ),
                    )
            return "success"
        except psycopg.DatabaseError as error:
            if error.sqlstate not in ("GBW01", "23P01", "23505", "40001"):
                raise
            return "conflict"

    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    tasks = []
    try:
        async with tenant_transaction(app_pool, business) as barrier:
            await lock_resource_schedule(barrier, business, times.changes.left_resource)
            tasks = [asyncio.create_task(run(index)) for index in range(2)]
            await wait_for_resource_waiters(monitor, 2)
            assert all(not task.done() for task in tasks)
        assert sorted(await asyncio.wait_for(asyncio.gather(*tasks), 10)) == ["conflict", "success"]
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await monitor.close()
    async with tenant_transaction(app_pool, business) as conn:
        if race == "clock_in":
            row = await (
                await conn.execute("select count(*) from gba.time_entry_state where is_open")
            ).fetchone()
            assert row == (1,)
        elif race == "approval":
            row = await (
                await conn.execute(
                    "select count(*) from gba.time_entry_state where approved_revision is not null"
                )
            ).fetchone()
            assert row == (1,)
        else:
            row = await (
                await conn.execute(
                    "select max(revision) from gba.time_entry_revisions where entry_id=%s",
                    (entries[0]["entry_id"],),
                )
            ).fetchone()
            assert row == (3,)


@pytest.mark.parametrize("change", ["cancel", "reassign"])
async def test_rr_shift_link_refuses_assignment_replaced_while_clockin_waits(
    times: Times,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    manager_a: FakeUser,
    change: str,
) -> None:
    shift = await times.changes.shift(times.changes.left_profile)
    business = times.changes.workforce.world.a.tenant_id

    async def clockin() -> str | None:
        try:
            async with app_pool.connection() as conn, conn.transaction():
                await conn.execute("set transaction isolation level repeatable read")
                await set_tenant_context(conn, business)
                await set_user_context(conn, times.changes.workforce.user.user_id)
                await conn.execute("select count(*) from gba.work_shift_versions")
                await conn.execute(
                    "insert into gba.time_entries "
                    "(tenant_id,id,profile_id,shift_id,shift_revision,starts_at,created_by) "
                    "values (%s,%s,%s,%s,1,%s,%s)",
                    (
                        business,
                        uuid7(),
                        times.changes.left_profile,
                        shift["shift_id"],
                        at(10),
                        times.changes.workforce.user.user_id,
                    ),
                )
            return None
        except psycopg.DatabaseError as error:
            return error.sqlstate

    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    task: asyncio.Task[str | None] | None = None
    try:
        async with tenant_transaction(app_pool, business) as barrier:
            await lock_resource_schedule(barrier, business, times.changes.left_resource)
            task = asyncio.create_task(clockin())
            await wait_for_resource_waiters(monitor, 1)
            assert not task.done()
            await set_user_context(barrier, manager_a.user_id)
            await barrier.execute(
                "insert into gba.work_shift_versions "
                "(tenant_id,shift_id,revision,position,starts_at,ends_at,required_skill_ids,"
                "status,profile_id,created_by) "
                "values (%s,%s,2,'FAKE replacement',%s,%s,'{}',%s,%s,%s)",
                (
                    business,
                    shift["shift_id"],
                    at(10),
                    at(11),
                    "cancelled" if change == "cancel" else "published",
                    None if change == "cancel" else times.changes.right_profile,
                    manager_a.user_id,
                ),
            )
        assert await asyncio.wait_for(task, 10) in ("40001", "42501")
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await monitor.close()
    async with tenant_transaction(app_pool, business) as conn:
        assert (await (await conn.execute("select count(*) from gba.time_entries")).fetchone()) == (
            0,
        )


@pytest.mark.parametrize("action", ["clock_in", "correct", "approve"])
async def test_rr_module_disable_before_waiting_action_is_visible_or_conflicts(
    times: Times,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    manager_a: FakeUser,
    idp: FakeIdp,
    action: str,
) -> None:
    business = times.changes.workforce.world.a.tenant_id
    entry = None if action == "clock_in" else await closed(times)
    config = Config(times.changes.workforce.client, idp)
    drafted = await config.draft(manager_a, business, 1, ["booking_resources"])
    assert drafted.status_code == 200, drafted.text
    version = int(drafted.json()["version"])
    validated = await config.step(manager_a, business, version, "validate", 1)
    assert validated.status_code == 200, validated.text

    async def attempt() -> str | None:
        try:
            async with app_pool.connection() as conn, conn.transaction():
                await conn.execute("set transaction isolation level repeatable read")
                await set_tenant_context(conn, business)
                user = (
                    manager_a.user_id
                    if action == "approve"
                    else times.changes.workforce.user.user_id
                )
                await set_user_context(conn, user)
                await conn.execute("select enabled from gba.business_module_states")
                if entry is None:
                    await conn.execute(
                        "insert into gba.time_entries "
                        "(tenant_id,id,profile_id,starts_at,created_by) "
                        "values (%s,%s,%s,%s,%s)",
                        (business, uuid7(), times.changes.left_profile, at(10), user),
                    )
                else:
                    await conn.execute(
                        "insert into gba.time_entry_revisions "
                        "(tenant_id,entry_id,revision,action,starts_at,ends_at,"
                        "break_starts,break_ends,reason,created_by) "
                        "values (%s,%s,3,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            business,
                            entry["entry_id"],
                            action,
                            at(10) if action == "correct" else None,
                            at(12) if action == "correct" else None,
                            [] if action == "correct" else None,
                            [] if action == "correct" else None,
                            "FAKE correction" if action == "correct" else None,
                            user,
                        ),
                    )
            return None
        except psycopg.DatabaseError as error:
            return error.sqlstate

    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    task: asyncio.Task[str | None] | None = None
    try:
        async with tenant_transaction(app_pool, business) as barrier:
            await barrier.execute(
                "select pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended("
                "'gba:business-configuration:'||%s::text,0))",
                (business,),
            )
            task = asyncio.create_task(attempt())
            await wait_for_resource_waiters(monitor, 1)
            assert not task.done()
            await publish_version(
                barrier,
                business_id=business,
                version=version,
                user_id=manager_a.user_id,
                actor=f"user:{manager_a.user_id}",
                key=str(uuid7()),
                body=ConfigurationCommand(expected_revision=2),
            )
        assert await asyncio.wait_for(task, 10) in ("40001", "GBM01")
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await monitor.close()
    async with tenant_transaction(app_pool, business) as conn:
        if entry is None:
            assert (
                await (await conn.execute("select count(*) from gba.time_entries")).fetchone()
            ) == (0,)
        else:
            row = await (
                await conn.execute(
                    "select last_revision,approved_revision from gba.time_entry_state "
                    "where entry_id=%s",
                    (entry["entry_id"],),
                )
            ).fetchone()
            assert row == (2, None)
