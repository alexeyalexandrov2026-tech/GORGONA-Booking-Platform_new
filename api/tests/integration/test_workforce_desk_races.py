"""Cancelling a command races the command itself: one observed wait, one outcome.

A race counts only when the second transaction is seen waiting in pg_locks for the
first one's uncommitted receipt key.
"""

import asyncio
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.business import timesheets, workforce_desk
from gorgona_booking.business.timesheet_contracts import ClockInInput
from gorgona_booking.business.workforce_desk_contracts import CommandReference
from gorgona_booking.db.pool import RuntimePool, set_tenant_context
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_timesheets as shared
from tests.integration.booking_support import at
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_timesheets import Times
from tests.integration.test_workforce_desk import _outcome

pytestmark = pytest.mark.anyio
times = shared.times
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


async def _wait_for_key_waiter(monitor: psycopg.AsyncConnection) -> None:
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        row = await (
            await monitor.execute(
                "select count(*) from pg_locks l join pg_stat_activity a on a.pid=l.pid "
                "where l.locktype='transactionid' and not l.granted "
                "and a.datname=current_database()"
            )
        ).fetchone()
        if row is not None and row[0] >= 1:
            return
        await asyncio.sleep(0.01)
    pytest.fail("no observed wait for the running transaction in pg_locks")


def _entries(owner_conn: psycopg.Connection, tenant: UUID) -> int:
    with owner_tenant_transaction(owner_conn, tenant):
        row = owner_conn.execute("select count(*) from gba.time_entries").fetchone()
    assert row is not None
    return int(row[0])


async def test_cancel_waits_for_a_running_command_and_reports_its_commit(
    times: Times,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    owner_conn: psycopg.Connection,
) -> None:
    changes = times.changes
    business = changes.workforce.world.a.tenant_id
    user = changes.workforce.user.user_id
    entry, key = uuid7(), str(uuid7())
    reference: dict[str, object] = {
        "operation": "time.clock_in",
        "subject_id": str(entry),
        "revision": 1,
    }
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        async with app_pool.connection() as conn, conn.transaction():
            await set_tenant_context(conn, business)
            await set_user_context(conn, user)
            # The command as its route runs it, recorded but not yet committed.
            await timesheets.clock_in(
                conn,
                business,
                entry,
                user,
                f"user:{user}",
                key,
                ClockInInput(staff_profile_id=UUID(changes.left_profile), starts_at=at(10)),
            )
            task = asyncio.create_task(_outcome(times, "cancel", key, reference))
            await _wait_for_key_waiter(monitor)
            assert not task.done()
        response = await task
    finally:
        await monitor.close()
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "committed"
    assert _entries(owner_conn, business) == 1
    replay = await times.start(key, str(entry))
    assert replay.status_code == 200, replay.text
    assert replay.json()["revision"] == 1


async def test_command_waits_for_a_running_cancel_and_is_then_refused(
    times: Times,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    owner_conn: psycopg.Connection,
) -> None:
    changes = times.changes
    business = changes.workforce.world.a.tenant_id
    user = changes.workforce.user.user_id
    entry, key = uuid7(), str(uuid7())
    reference = CommandReference(operation="time.clock_in", subject_id=entry, revision=1)
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        async with app_pool.connection() as conn, conn.transaction():
            await set_tenant_context(conn, business)
            await set_user_context(conn, user)
            cancelled = await workforce_desk.cancel_command(
                conn, business, f"user:{user}", key, reference
            )
            assert cancelled.state == "cancelled"
            task = asyncio.create_task(times.start(key, str(entry)))
            await _wait_for_key_waiter(monitor)
            assert not task.done()
        response = await task
    finally:
        await monitor.close()
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert _entries(owner_conn, business) == 0
    settled = await _outcome(times, "resolve", key, reference.model_dump(mode="json"))
    assert settled.json()["state"] == "cancelled"
