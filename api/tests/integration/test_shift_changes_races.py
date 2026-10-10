"""I-05 races count only after a real pg_locks waiter is observed."""

import asyncio
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.booking.repository import lock_resource_schedule
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_shift_changes as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_shift_changes import Changes
from tests.integration.test_shift_changes_guards import accepted, raw_event, skill
from tests.integration.test_workforce_guards import wait_for_resource_waiters

pytestmark = pytest.mark.anyio
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


@pytest.mark.parametrize("raw_sql", [False, True])
@pytest.mark.parametrize("race", ["pickup", "withdraw", "manual", "opposite_swap"])
async def test_i05_ordered_races_have_one_winner_without_deadlock(
    changes: Changes,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    manager_a: FakeUser,
    race: str,
    raw_sql: bool,
) -> None:
    business = changes.workforce.world.a.tenant_id
    first = await changes.shift(None if race == "pickup" else changes.left_profile)
    requests: list[dict[str, object]] = []
    if race == "pickup":
        for profile, headers in (
            (changes.left_profile, changes.left_headers),
            (changes.right_profile, changes.right_headers),
        ):
            proposed = await changes.workforce.client.put(
                changes.workforce.base + f"/changes/{uuid7()}",
                headers={**headers, "Idempotency-Key": str(uuid7())},
                json={
                    "schema_version": 1,
                    "kind": "pickup",
                    "shift_id": first["shift_id"],
                    "expected_shift_revision": 1,
                    "target_profile_id": profile,
                },
            )
            assert proposed.status_code == 200, proposed.text
            consent = await changes.event(dict(proposed.json()), "accept", headers)
            assert consent.status_code == 200, consent.text
            requests.append(dict(consent.json()))
    elif race == "opposite_swap":
        other = await changes.shift(changes.right_profile)
        for primary, secondary, target, proposer, recipient in (
            (first, other, changes.right_profile, changes.left_headers, changes.right_headers),
            (other, first, changes.left_profile, changes.right_headers, changes.left_headers),
        ):
            proposed = await changes.workforce.client.put(
                changes.workforce.base + f"/changes/{uuid7()}",
                headers={**proposer, "Idempotency-Key": str(uuid7())},
                json={
                    "schema_version": 1,
                    "kind": "swap",
                    "shift_id": primary["shift_id"],
                    "expected_shift_revision": 1,
                    "other_shift_id": secondary["shift_id"],
                    "expected_other_shift_revision": 1,
                    "target_profile_id": target,
                },
            )
            assert proposed.status_code == 200, proposed.text
            consent = await changes.event(dict(proposed.json()), "accept", recipient)
            assert consent.status_code == 200, consent.text
            requests.append(dict(consent.json()))
    else:
        requests = [await accepted(changes, first)]

    async def run(index: int) -> str:
        request = requests[index] if len(requests) == 2 else requests[0]
        action = "withdraw" if race == "withdraw" and index == 1 else "approve"
        user = changes.workforce.user.user_id if action == "withdraw" else manager_a.user_id
        if raw_sql:
            try:
                if race == "manual" and index == 1:
                    async with tenant_transaction(app_pool, business) as conn:
                        await set_user_context(conn, user)
                        await conn.execute(
                            "insert into gba.work_shift_versions "
                            "(tenant_id,shift_id,revision,position,starts_at,ends_at,"
                            "required_skill_ids,status,profile_id,created_by) "
                            "select tenant_id,shift_id,2,position,starts_at,ends_at,"
                            "required_skill_ids,status,%s,%s "
                            "from gba.work_shift_versions where shift_id=%s and revision=1",
                            (changes.right_profile, user, first["shift_id"]),
                        )
                else:
                    await raw_event(app_pool, changes, request, user, action)
                return "success"
            except psycopg.DatabaseError as error:
                if error.sqlstate != "GBW01":
                    raise
                return "conflict"
        if race == "manual" and index == 1:
            response = await changes.workforce.put(
                f"/shifts/{first['shift_id']}",
                changes.workforce.shift(
                    expected_revision=1, staff_profile_id=changes.right_profile
                ),
            )
        else:
            headers = changes.left_headers if action == "withdraw" else changes.workforce.headers
            response = await changes.event(request, action, headers)
        if response.status_code == 409:
            assert response.json()["error"]["code"] == "WORKFORCE_CONFLICT", response.text
            return "conflict"
        assert response.status_code == 200, response.text
        return "success"

    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    tasks: list[asyncio.Task[str]] = []
    try:
        async with tenant_transaction(app_pool, business) as barrier:
            if race == "pickup":
                await barrier.execute(
                    "select id from gba.work_shifts where id=%s for update", (first["shift_id"],)
                )
            else:
                await lock_resource_schedule(
                    barrier, business, min(changes.left_resource, changes.right_resource)
                )
            tasks = [asyncio.create_task(run(index)) for index in range(2)]
            if race == "pickup":
                deadline = asyncio.get_running_loop().time() + 8
                while asyncio.get_running_loop().time() < deadline:
                    row = await (
                        await monitor.execute(
                            "select count(distinct pid) from pg_locks "
                            "where locktype in ('transactionid','tuple') and not granted "
                            "and pid in (select pid from pg_stat_activity "
                            "where datname=current_database())"
                        )
                    ).fetchone()
                    if row is not None and row[0] >= 2:
                        break
                    await asyncio.sleep(0.01)
                else:
                    pytest.fail("I-05 pickup requires two observed row-lock waiters")
            else:
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
        rows = await (
            await conn.execute(
                "select r.id,e.status from gba.shift_change_requests r join lateral "
                "(select status from gba.shift_change_events where request_id=r.id "
                "order by revision desc limit 1) e on true "
                "where r.id=any(%s) order by r.id",
                ([UUID(str(request["request_id"])) for request in requests],),
            )
        ).fetchall()
        if len(requests) == 2:
            assert sorted(row[1] for row in rows) == ["accepted", "approved"]
        else:
            assert rows[0][1] in ("approved", "withdrawn", "accepted")
        assert (
            await (
                await conn.execute(
                    "select count(*) from gba.resource_allocations r join gba.shift_assignments a "
                    "on a.tenant_id=r.tenant_id and a.id=r.source_id "
                    "where r.source_kind='shift' and r.state='confirmed' and a.shift_id=%s",
                    (first["shift_id"],),
                )
            ).fetchone()
        ) == (1,)


@pytest.mark.parametrize("raw_sql", [False, True])
async def test_catalogue_rename_is_locked_before_the_stale_snapshot_comparison(
    changes: Changes,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    owner_conn: psycopg.Connection,
    manager_a: FakeUser,
    raw_sql: bool,
) -> None:
    identifier = await skill(changes)
    first = await changes.shift(changes.left_profile, required_skill_ids=[identifier])
    request = await accepted(changes, first)
    business = changes.workforce.world.a.tenant_id

    async def approve() -> str:
        if raw_sql:
            try:
                await raw_event(app_pool, changes, request, manager_a.user_id, "approve")
                return "success"
            except psycopg.DatabaseError as error:
                if error.sqlstate != "GBW01":
                    raise
                return "conflict"
        response = await changes.event(request, "approve", changes.workforce.headers)
        assert response.status_code == 409, response.text
        return "conflict"

    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    task: asyncio.Task[str] | None = None
    try:
        with owner_tenant_transaction(owner_conn, business):
            owner_conn.execute(
                "select id from gba.work_skills where id=%s for update", (identifier,)
            )
            task = asyncio.create_task(approve())
            deadline = asyncio.get_running_loop().time() + 8
            while asyncio.get_running_loop().time() < deadline:
                row = await (
                    await monitor.execute(
                        "select count(*) from pg_locks where not granted "
                        "and locktype in ('transactionid','tuple') "
                        "and pid in (select pid from pg_stat_activity "
                        "where datname=current_database())"
                    )
                ).fetchone()
                if row is not None and row[0] >= 1:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Catalog test requires an observed pg_locks waiter")
            assert not task.done()
            owner_conn.execute(
                "insert into gba.work_skill_versions "
                "(tenant_id,skill_id,revision,name,archived,created_by) "
                "values (%s,%s,2,'FAKE harmless rename',false,%s)",
                (business, identifier, manager_a.user_id),
            )
        assert await asyncio.wait_for(task, 10) == "conflict"
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await monitor.close()
    async with tenant_transaction(app_pool, business) as conn:
        assert (
            await (
                await conn.execute(
                    "select max(revision) from gba.shift_change_events where request_id=%s",
                    (request["request_id"],),
                )
            ).fetchone()
        ) == (2,)
