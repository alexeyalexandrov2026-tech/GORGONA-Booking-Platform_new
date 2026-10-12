"""Permanent regressions for the three findings of independent review 2."""

import asyncio
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.business import modules, timesheets, workforce_desk
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.business.timesheet_contracts import ClockInInput
from gorgona_booking.business.workforce_desk_contracts import CommandReference
from gorgona_booking.db.pool import RuntimePool, set_tenant_context
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from tests.integration import test_timesheets as shared
from tests.integration.booking_support import at
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_timesheets import Times
from tests.integration.test_workforce_desk import WINDOW, _get, _outcome
from tests.integration.test_workforce_desk_races import _receipt_writer, _wait_for_key_waiter
from tests.integration.test_workforce_visibility import _set
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
times = shared.times
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


@pytest.mark.parametrize("visible", [False, True])
@pytest.mark.parametrize("company_wide", [False, True])
async def test_swap_after_same_home_reinvitation_uses_the_stable_home(
    times: Times, owner_conn: psycopg.Connection, visible: bool, company_wide: bool
) -> None:
    changes = times.changes
    staff = changes.workforce
    tenant, home = staff.world.a.tenant_id, staff.world.a.location_id
    mine = await changes.shift(changes.left_profile)
    theirs = await changes.shift(
        changes.right_profile, starts_at=at(12).isoformat(), ends_at=at(13).isoformat()
    )
    request, key = uuid7(), str(uuid7())
    body = {
        "schema_version": 1,
        "kind": "swap",
        "shift_id": mine["shift_id"],
        "expected_shift_revision": mine["revision"],
        "other_shift_id": theirs["shift_id"],
        "expected_other_shift_revision": theirs["revision"],
        "target_profile_id": changes.right_profile,
    }

    async def send() -> httpx.Response:
        return await staff.client.put(
            times.base + f"/changes/{request}",
            headers={**changes.left_headers, "Idempotency-Key": key},
            json=body,
        )

    recorded = await send()
    assert recorded.status_code == 200, recorded.text
    assert (await _set(times, home, visible, 0)).status_code == 200
    with owner_tenant_transaction(owner_conn, tenant):
        owner_conn.execute(
            "update gba.memberships set status='revoked' where id=%s", (staff.membership,)
        )
    add_membership(
        owner_conn,
        tenant_id=tenant,
        user_id=staff.user.user_id,
        role="artist",
        location_id=None if company_wide else home,
    )
    desk = await _get(times, "/desk", changes.left_headers)
    assert desk.status_code == 200, desk.text
    assert desk.json()["profile"] is None
    # Already shared versions and their original receipt survive reinvitation/privacy.
    replay = await send()
    assert replay.status_code == 200, replay.text
    assert replay.json() == recorded.json()
    history = await _get(times, f"/my-changes/{request}/shifts", changes.left_headers)
    assert history.status_code == 200, history.text
    assert len(history.json()["items"]) == 2
    proposed = await changes.propose(
        "swap", mine, other_shift_id=theirs["shift_id"], expected_other_shift_revision=1
    )
    assert proposed.status_code == (200 if visible else 403), proposed.text
    assert desk.json()["colleague_shifts"] == ("visible" if visible else "hidden")
    if not visible:
        assert proposed.json()["error"]["code"] == "COLLEAGUE_SHIFTS_HIDDEN"
        unknown = await changes.propose(
            "swap", mine, other_shift_id=str(uuid7()), expected_other_shift_revision=1
        )
        assert unknown.status_code == 403, unknown.text
        assert unknown.json()["error"]["code"] == "COLLEAGUE_SHIFTS_HIDDEN"
        browsed = await _get(
            times, f"/colleagues/{changes.right_profile}/shifts", changes.left_headers, **WINDOW
        )
        assert browsed.status_code == 403, browsed.text


async def test_reinvitation_to_another_branch_does_not_authorize_the_old_home(
    times: Times, owner_conn: psycopg.Connection
) -> None:
    changes = times.changes
    staff = changes.workforce
    tenant = staff.world.a.tenant_id
    mine = await changes.shift(changes.left_profile)
    theirs = await changes.shift(
        changes.right_profile, starts_at=at(12).isoformat(), ends_at=at(13).isoformat()
    )
    other, _ = seed_other_branch(owner_conn, staff.world.a)
    with owner_tenant_transaction(owner_conn, tenant):
        owner_conn.execute(
            "update gba.memberships set status='revoked' where id=%s", (staff.membership,)
        )
    add_membership(
        owner_conn, tenant_id=tenant, user_id=staff.user.user_id, role="artist", location_id=other
    )
    refused = await changes.propose(
        "swap", mine, other_shift_id=theirs["shift_id"], expected_other_shift_revision=1
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "COLLEAGUE_SHIFTS_HIDDEN"
    browsed = await _get(
        times, f"/colleagues/{changes.right_profile}/shifts", changes.left_headers, **WINDOW
    )
    assert browsed.status_code == 404, browsed.text


@pytest.mark.parametrize("gate", ["open", "off", "not_accepted"])
async def test_different_cancel_keys_cannot_both_take_the_last_daily_slot(
    times: Times,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    manager_a: FakeUser,
    idp: FakeIdp,
    monkeypatch: pytest.MonkeyPatch,
    gate: str,
) -> None:
    tenant = times.changes.workforce.world.a.tenant_id
    actor = f"user:{times.changes.workforce.user.user_id}"
    reference: dict[str, object] = {
        "operation": "time.clock_in",
        "subject_id": str(uuid7()),
        "revision": 1,
    }
    for _ in range(19):
        assert (await _outcome(times, "cancel", str(uuid7()), reference)).status_code == 200
    if gate == "off":
        await Config(times.changes.workforce.client, idp).publish(
            manager_a, tenant, 1, ["booking_resources"]
        )
    elif gate == "not_accepted":
        current = modules.MODULES_BY_ID["workforce"]
        monkeypatch.setitem(
            modules.MODULES_BY_ID,
            "workforce",
            current.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
        )
    barrier = await psycopg.AsyncConnection.connect(test_database.owner_dsn)
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    tasks: list[asyncio.Task[httpx.Response]] = []
    try:
        async with barrier.transaction():
            await barrier.execute("lock table gba.idempotency_keys in share mode")
            tasks = [
                asyncio.create_task(_outcome(times, "cancel", str(uuid7()), reference))
                for _ in range(2)
            ]
            deadline = asyncio.get_running_loop().time() + 10
            observed = 0
            while asyncio.get_running_loop().time() < deadline:
                row = await (
                    await monitor.execute(
                        "select count(distinct l.pid) from pg_locks l "
                        "join pg_stat_activity a on a.pid=l.pid "
                        "cross join (select pg_catalog.hashtextextended(%s,0) as k) x "
                        "where not l.granted and a.datname=current_database() and ("
                        "(l.locktype='relation' and l.mode='RowExclusiveLock' "
                        "and l.relation='gba.idempotency_keys'::regclass "
                        "and position('insert into gba.idempotency_keys' in lower(a.query))>0) "
                        "or (l.locktype='advisory' and l.objsubid=1 "
                        "and l.classid=((x.k >> 32) & 4294967295)::oid "
                        "and l.objid=(x.k & 4294967295)::oid))",
                        (f"gba:workforce-discards:{tenant}:{actor}",),
                    )
                ).fetchone()
                assert row is not None
                observed = int(row[0])
                if observed == 2:
                    break
                await asyncio.sleep(0.01)
            # Before the fix both wait on INSERT; after it one waits on the actor lock.
            assert observed == 2, "two relevant PostgreSQL lock waiters were not observed"
            assert all(not task.done() for task in tasks)
        responses = await asyncio.wait_for(asyncio.gather(*tasks), 15)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await barrier.close()
        await monitor.close()
    assert sorted(response.status_code for response in responses) == [200, 429]
    with owner_tenant_transaction(owner_conn, tenant):
        row = owner_conn.execute(
            "select count(*) from gba.idempotency_keys where response_status=410"
        ).fetchone()
    assert row == (20,)
    with owner_tenant_transaction(owner_conn, tenant):
        assert owner_conn.execute(
            "select count(*) from gba.idempotency_keys where response_status is null"
        ).fetchone() == (0,)


async def test_at_the_daily_cap_cancel_still_waits_for_the_real_command_outcome(
    times: Times, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    staff = times.changes.workforce
    business, user = staff.world.a.tenant_id, staff.user.user_id
    entry, key = uuid7(), str(uuid7())
    reference: dict[str, object] = {
        "operation": "time.clock_in",
        "subject_id": str(entry),
        "revision": 1,
    }
    for _ in range(20):
        assert (await _outcome(times, "cancel", str(uuid7()), reference)).status_code == 200
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    task: asyncio.Task[httpx.Response] | None = None
    try:
        async with app_pool.connection() as conn, conn.transaction():
            await set_tenant_context(conn, business)
            await set_user_context(conn, user)
            await timesheets.clock_in(
                conn,
                business,
                entry,
                user,
                f"user:{user}",
                key,
                ClockInInput(staff_profile_id=UUID(times.changes.left_profile), starts_at=at(10)),
            )
            writer = await _receipt_writer(conn, business, key)
            task = asyncio.create_task(_outcome(times, "cancel", key, reference))
            await _wait_for_key_waiter(monitor, writer)
            assert not task.done()
        response = await asyncio.wait_for(task, 15)
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "committed"
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await monitor.close()


async def test_refused_discard_leaves_no_receipt_even_when_the_caller_catches_the_error(
    times: Times, app_pool: RuntimePool
) -> None:
    staff = times.changes.workforce
    business, user = staff.world.a.tenant_id, staff.user.user_id
    reference = CommandReference(operation="time.clock_in", subject_id=uuid7(), revision=1)
    for _ in range(20):
        assert (
            await _outcome(times, "cancel", str(uuid7()), reference.model_dump(mode="json"))
        ).status_code == 200
    key = str(uuid7())
    async with app_pool.connection() as conn, conn.transaction():
        await set_tenant_context(conn, business)
        await set_user_context(conn, user)
        with pytest.raises(workforce_desk.TooManyDiscardsError):
            await workforce_desk.cancel_command(conn, business, f"user:{user}", key, reference)
        assert (
            await workforce_desk.resolve_command(conn, business, f"user:{user}", key, reference)
        ).state == "unresolved"


@pytest.mark.parametrize("isolation", ["repeatable read", "serializable", "read uncommitted"])
@pytest.mark.parametrize("already_recorded", [False, True])
async def test_cancellation_isolation_guard_preserves_known_outcomes(
    times: Times, app_pool: RuntimePool, isolation: str, already_recorded: bool
) -> None:
    staff = times.changes.workforce
    business, user = staff.world.a.tenant_id, staff.user.user_id
    reference = CommandReference(operation="time.clock_in", subject_id=uuid7(), revision=1)
    key = str(uuid7())
    if already_recorded:
        assert (
            await _outcome(times, "cancel", key, reference.model_dump(mode="json"))
        ).status_code == 200
    statements = {
        "repeatable read": "set transaction isolation level repeatable read",
        "serializable": "set transaction isolation level serializable",
        "read uncommitted": "set transaction isolation level read uncommitted",
    }
    async with app_pool.connection() as conn, conn.transaction():
        await conn.execute(statements[isolation])
        await set_tenant_context(conn, business)
        await set_user_context(conn, user)
        if already_recorded:
            assert (
                await workforce_desk.cancel_command(conn, business, f"user:{user}", key, reference)
            ).state == "cancelled"
        else:
            with pytest.raises(DatabaseUnavailableError):
                await workforce_desk.cancel_command(conn, business, f"user:{user}", key, reference)
            assert (
                await workforce_desk.resolve_command(conn, business, f"user:{user}", key, reference)
            ).state == "unresolved"


@pytest.mark.parametrize("reason", ["Clock-in", "Break start", "Break end", "Recorded clock-out"])
async def test_time_reason_provenance_survives_approval_and_history(
    times: Times, reason: str
) -> None:
    created = await times.start()
    break_started = await times.command(
        dict(created.json()), "break_start", at=at(10, 10).isoformat()
    )
    assert break_started.status_code == 200, break_started.text
    break_ended = await times.command(
        dict(break_started.json()), "break_end", at=at(10, 20).isoformat()
    )
    assert break_ended.status_code == 200, break_ended.text
    closed = await times.command(dict(break_ended.json()), "clock_out", at=at(11).isoformat())
    assert closed.status_code == 200, closed.text
    approved_clock = await times.command(
        dict(closed.json()), "approve", times.changes.workforce.headers
    )
    assert approved_clock.status_code == 200, approved_clock.text
    corrected = await times.command(
        dict(approved_clock.json()),
        "correct",
        starts_at=created.json()["starts_at"],
        ends_at=closed.json()["ends_at"],
        breaks=[],
        reason=reason,
    )
    assert corrected.status_code == 200, corrected.text
    approved_note = await times.command(
        dict(corrected.json()), "approve", times.changes.workforce.headers
    )
    assert approved_note.status_code == 200, approved_note.text
    assert approved_note.json()["reason"] == reason
    history = await _get(
        times, f"/my-time-entries/{created.json()['entry_id']}/history", times.changes.left_headers
    )
    assert history.status_code == 200, history.text
    assert [item["reason_source"] for item in history.json()["items"]] == [
        "system",
        "system",
        "system",
        "system",
        "system",
        "human",
        "human",
    ]
    assert [item["reason"] for item in history.json()["items"]][-2:] == [reason, reason]
    corrected_again = await times.command(
        dict(approved_note.json()),
        "correct",
        starts_at=created.json()["starts_at"],
        ends_at=closed.json()["ends_at"],
        breaks=[],
        reason=reason,
    )
    assert corrected_again.status_code == 200, corrected_again.text
    declined = await times.command(
        dict(corrected_again.json()), "decline", times.changes.workforce.headers, reason=reason
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["reason_source"] == "human"
    assert declined.json()["reason"] == reason
