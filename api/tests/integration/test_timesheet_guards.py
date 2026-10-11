"""I3 SQL integrity, identity, off-switch closure and current effective work."""

from datetime import timedelta
from uuid import UUID, uuid7

import psycopg
import pytest
from pydantic import BaseModel

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_timesheets as shared
from tests.integration.booking_support import at
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_delegations import Parties
from tests.integration.test_timesheets import Times
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
times = shared.times
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


async def closed(times: Times, starts_hour: int = 10, ends_hour: int = 11) -> dict[str, object]:
    first = await times.start(starts_at=at(starts_hour).isoformat())
    assert first.status_code == 200, first.text
    result = await times.command(dict(first.json()), "clock_out", at=at(ends_hour).isoformat())
    assert result.status_code == 200, result.text
    return dict(result.json())


async def raw_command(
    pool: RuntimePool,
    times: Times,
    entry: dict[str, object],
    user: UUID,
    action: str,
    *,
    actor: UUID | None = None,
    **values: object,
) -> None:
    async with tenant_transaction(pool, times.changes.workforce.world.a.tenant_id) as conn:
        await set_user_context(conn, user)
        await conn.execute(
            "insert into gba.time_entry_revisions "
            "(tenant_id,entry_id,revision,action,occurred_at,starts_at,ends_at,"
            "break_starts,break_ends,reason,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                times.changes.workforce.world.a.tenant_id,
                entry["entry_id"],
                int(str(entry["revision"])) + 1,
                action,
                values.get("at"),
                values.get("starts_at"),
                values.get("ends_at"),
                values.get("break_starts"),
                values.get("break_ends"),
                values.get("reason"),
                actor or user,
            ),
        )


@pytest.mark.parametrize("raw_sql", [False, True])
async def test_approved_full_intervals_exclude_overlap_even_during_a_break(
    times: Times, app_pool: RuntimePool, manager_a: FakeUser, raw_sql: bool
) -> None:
    original = await closed(times)
    correction = await times.command(
        original,
        "correct",
        starts_at=at(10).isoformat(),
        ends_at=at(11).isoformat(),
        reason="FAKE break",
        breaks=[{"starts_at": at(10, 10).isoformat(), "ends_at": at(10, 50).isoformat()}],
    )
    approved = await times.command(
        dict(correction.json()), "approve", times.changes.workforce.headers
    )
    assert approved.status_code == 200, approved.text
    next_start = await times.start(starts_at=at(10, 20).isoformat())
    assert next_start.status_code == 200, next_start.text
    next_close = await times.command(
        dict(next_start.json()), "clock_out", at=at(10, 30).isoformat()
    )
    assert next_close.status_code == 200, next_close.text
    if raw_sql:
        with pytest.raises(psycopg.errors.ExclusionViolation):
            await raw_command(
                app_pool, times, dict(next_close.json()), manager_a.user_id, "approve"
            )
    else:
        refused = await times.command(
            dict(next_close.json()), "approve", times.changes.workforce.headers
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "WORKFORCE_CONFLICT"
    current = await times.changes.workforce.client.get(
        times.base + f"/my-time-entries/{next_close.json()['entry_id']}",
        headers=times.changes.left_headers,
    )
    assert current.json()["revision"] == 2
    assert current.json()["effective"] is None


@pytest.mark.parametrize("decline", [False, True])
async def test_pending_and_declined_correction_keep_the_previous_approved_interval(
    times: Times, decline: bool
) -> None:
    first = await closed(times)
    approved = await times.command(first, "approve", times.changes.workforce.headers)
    assert approved.status_code == 200, approved.text
    correction = await times.command(
        dict(approved.json()),
        "correct",
        starts_at=at(12).isoformat(),
        ends_at=at(13).isoformat(),
        reason="FAKE shift actual time",
        breaks=[],
    )
    assert correction.status_code == 200, correction.text
    current = correction
    if decline:
        current = await times.command(
            dict(correction.json()),
            "decline",
            times.changes.workforce.headers,
            reason="FAKE declined",
        )
        assert current.status_code == 200, current.text
    assert current.json()["effective"] == approved.json()["effective"]
    overlap = await closed(times)
    refused = await times.command(overlap, "approve", times.changes.workforce.headers)
    assert refused.status_code == 409, refused.text


@pytest.mark.parametrize("role", ["manager", "owner"])
@pytest.mark.parametrize("raw_sql", [False, True])
async def test_manager_own_approval_is_forbidden_owner_exception_is_explicit(
    times: Times, owner_conn: psycopg.Connection, app_pool: RuntimePool, role: str, raw_sql: bool
) -> None:
    entry = await closed(times)
    user = times.changes.workforce.user.user_id
    with owner_tenant_transaction(owner_conn, times.changes.workforce.world.a.tenant_id):
        owner_conn.execute("update gba.memberships set role=%s where user_id=%s", (role, user))
    if raw_sql:
        if role == "manager":
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await raw_command(app_pool, times, entry, user, "approve")
            return
        await raw_command(app_pool, times, entry, user, "approve")
        response = await times.changes.workforce.client.get(
            times.base + f"/my-time-entries/{entry['entry_id']}", headers=times.changes.left_headers
        )
    else:
        response = await times.command(entry, "approve")
        if role == "manager":
            assert response.status_code == 403, response.text
            return
    assert response.status_code == 200, response.text
    assert response.json()["self_approved"] is True
    with owner_tenant_transaction(owner_conn, times.changes.workforce.world.a.tenant_id):
        owner_conn.execute("update gba.memberships set role='artist' where user_id=%s", (user,))
    preserved = await times.changes.workforce.client.get(
        times.base + f"/my-time-entries/{entry['entry_id']}", headers=times.changes.left_headers
    )
    assert preserved.json()["self_approved"] is True
    proposal = await times.command(
        dict(preserved.json()),
        "correct",
        starts_at=at(10).isoformat(),
        ends_at=at(12).isoformat(),
        breaks=[],
        reason="FAKE own correction",
    )
    assert proposal.status_code == 200, proposal.text
    assert proposal.json()["self_approved"] is False
    assert proposal.json()["effective"]["self_approved"] is True


@pytest.mark.parametrize("gate", ["module", "readiness"])
@pytest.mark.parametrize("raw_sql", [False, True])
async def test_disabled_gate_closes_only_existing_own_entry_and_active_break(
    times: Times,
    manager_a: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
    monkeypatch: pytest.MonkeyPatch,
    gate: str,
    raw_sql: bool,
) -> None:
    first = await times.start()
    started = await times.command(dict(first.json()), "break_start", at=at(10, 30).isoformat())
    assert started.status_code == 200, started.text
    entry = dict(started.json())
    if gate == "module":
        await Config(times.changes.workforce.client, idp).publish(
            manager_a, times.changes.workforce.world.a.tenant_id, 1, ["booking_resources"]
        )
    else:
        current = modules.MODULES_BY_ID["workforce"]
        monkeypatch.setitem(
            modules.MODULES_BY_ID,
            "workforce",
            current.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
        )
    refused = await times.start()
    assert refused.status_code == 409, refused.text
    if raw_sql:
        await raw_command(
            app_pool, times, entry, times.changes.workforce.user.user_id, "clock_out", at=at(11)
        )
        response = await times.changes.workforce.client.get(
            times.base + f"/my-time-entries/{entry['entry_id']}", headers=times.changes.left_headers
        )
    else:
        response = await times.command(entry, "clock_out", at=at(11).isoformat())
    assert response.status_code == 200, response.text
    assert response.json()["starts_at"] == first.json()["starts_at"]
    assert response.json()["break_started_at"] is None
    assert response.json()["worked_microseconds"] == 30 * 60 * 1_000_000
    assert len(response.json()["breaks"]) == 1
    assert (
        await times.command(dict(response.json()), "approve", times.changes.workforce.headers)
    ).status_code == 409
    if gate == "module":
        with pytest.raises(psycopg.DatabaseError) as error:
            await raw_command(app_pool, times, dict(response.json()), manager_a.user_id, "approve")
        assert error.value.sqlstate == "GBM01"


async def test_module_off_close_cannot_also_replace_start_breaks_or_another_employee(
    times: Times, manager_a: FakeUser, idp: FakeIdp, app_pool: RuntimePool
) -> None:
    entry = dict((await times.start()).json())
    await Config(times.changes.workforce.client, idp).publish(
        manager_a, times.changes.workforce.world.a.tenant_id, 1, ["booking_resources"]
    )
    with pytest.raises(psycopg.errors.CheckViolation, match="cannot replace"):
        await raw_command(
            app_pool,
            times,
            entry,
            times.changes.workforce.user.user_id,
            "clock_out",
            at=at(11),
            starts_at=at(9),
        )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await raw_command(
            app_pool, times, entry, times.changes.right_user.user_id, "clock_out", at=at(11)
        )
    refused = await times.command(entry, "clock_out", at=at(11).isoformat(), breaks=[])
    assert refused.status_code == 422, refused.text


@pytest.mark.parametrize("in_schedule", [False, True])
async def test_shift_link_has_exact_owned_version_and_flag_uses_actual_start(
    times: Times, owner_conn: psycopg.Connection, idp: FakeIdp, in_schedule: bool
) -> None:
    other, _ = seed_other_branch(owner_conn, times.changes.workforce.world.a)
    shift = await times.changes.shift(times.changes.left_profile, location_id=str(other))
    first = await times.start(
        starts_at=at(10 if in_schedule else 9).isoformat(),
        shift_id=shift["shift_id"],
        expected_shift_revision=1,
    )
    assert first.status_code == 200, first.text
    assert first.json()["out_of_schedule"] is (not in_schedule)
    # A home-scoped manager sees the employee accounting, with the captured
    # schedule flag intact even though the linked work-branch shift is hidden.
    manager = seed_user(owner_conn, f"i3-home-manager-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=times.changes.workforce.world.a.tenant_id,
        user_id=manager.user_id,
        role="manager",
        location_id=times.changes.workforce.world.a.location_id,
    )
    viewed = await times.changes.workforce.client.get(
        times.base + f"/time-entries/{first.json()['entry_id']}",
        headers=idp.bearer(manager.subject, email=manager.email),
    )
    assert viewed.status_code == 200, viewed.text
    assert viewed.json()["out_of_schedule"] is (not in_schedule)


@pytest.mark.parametrize("table", ["time_entries", "time_entry_revisions"])
async def test_time_history_never_updates_or_deletes(
    times: Times, owner_conn: psycopg.Connection, table: str
) -> None:
    await closed(times)
    with owner_tenant_transaction(owner_conn, times.changes.workforce.world.a.tenant_id):
        for operation in (
            f"update gba.{table} set tenant_id=tenant_id",
            f"delete from gba.{table}",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(operation)


@pytest.mark.parametrize("operation", ["update", "insert", "delete"])
async def test_raw_sql_cannot_forge_or_remove_the_derived_projection(
    times: Times, app_pool: RuntimePool, operation: str
) -> None:
    entry = await closed(times)
    statements = {
        "update": "update gba.time_entry_state set is_open=true where entry_id=%s",
        "insert": (
            "insert into gba.time_entry_state select * from gba.time_entry_state where entry_id=%s"
        ),
        "delete": "delete from gba.time_entry_state where entry_id=%s",
    }

    async def attempt() -> None:
        async with tenant_transaction(app_pool, times.changes.workforce.world.a.tenant_id) as conn:
            await conn.execute(statements[operation], (entry["entry_id"],))

    with pytest.raises(psycopg.DatabaseError) as error:
        await attempt()
    assert error.value.sqlstate in ("23514", "42501")


async def test_other_people_support_and_foreign_company_cannot_see_or_clock_this_user(
    times: Times, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    entry = await closed(times)
    for suffix in ("", "/history"):
        response = await times.changes.workforce.client.get(
            times.base + f"/my-time-entries/{entry['entry_id']}" + suffix,
            headers=times.changes.right_headers,
        )
        assert response.status_code == 404, response.text
    assert (
        await times.command(
            entry,
            "correct",
            times.changes.right_headers,
            starts_at=at(10).isoformat(),
            ends_at=at(12).isoformat(),
            breaks=[],
            reason="FAKE wrong user",
        )
    ).status_code == 404
    foreign = seed_user(owner_conn, f"i3-foreign-{uuid7()}")
    support = seed_user(owner_conn, f"i3-support-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=times.changes.workforce.world.b.tenant_id,
        user_id=foreign.user_id,
        role="owner",
    )
    grant_platform_admin(owner_conn, user_id=support.user_id, granted_by="test:i3")
    for user in (foreign, support):
        headers = idp.bearer(user.subject, email=user.email)
        for suffix in (
            "/time-entries",
            "/my-time-entries",
            f"/time-entries/{entry['entry_id']}/history",
        ):
            response = await times.changes.workforce.client.get(
                times.base + suffix, headers=headers
            )
            assert response.status_code == 403, response.text
        response = await times.command(entry, "approve", headers)
        assert response.status_code == 403, response.text


async def test_reinvite_cannot_open_another_entry_and_can_close_old_own_entry(
    times: Times, owner_conn: psycopg.Connection
) -> None:
    first = dict((await times.start()).json())
    business = times.changes.workforce.world.a.tenant_id
    user = times.changes.workforce.user.user_id
    with owner_tenant_transaction(owner_conn, business):
        owner_conn.execute("update gba.memberships set status='revoked' where user_id=%s", (user,))
    add_membership(
        owner_conn,
        tenant_id=business,
        user_id=user,
        role="manager",
        location_id=times.changes.workforce.world.a.location_id,
    )
    with owner_tenant_transaction(owner_conn, business):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s and status='active'", (user,)
        ).fetchone()
    assert row is not None
    profile = await times.changes.workforce.put(
        f"/staff/{uuid7()}",
        {
            "membership_id": str(row[0]),
            "location_id": str(times.changes.workforce.world.a.location_id),
        },
    )
    assert profile.status_code == 200, profile.text
    denied = await times.start(staff_profile_id=profile.json()["profile_id"])
    assert denied.status_code == 409, denied.text
    close = await times.command(first, "clock_out", at=at(11).isoformat())
    assert close.status_code == 200, close.text
    self_approval = await times.command(dict(close.json()), "approve")
    assert self_approval.status_code == 403, self_approval.text


@pytest.mark.parametrize("action", ["break_end", "break_start", "clock_out"])
async def test_invalid_clock_state_or_repeated_revision_never_creates_a_partial_effect(
    times: Times, action: str
) -> None:
    first = dict((await times.start()).json())
    if action == "break_start":
        good = await times.command(first, "break_start", at=at(10, 10).isoformat())
    else:
        good = await times.command(first, "clock_out", at=at(11).isoformat())
    assert good.status_code == 200, good.text
    key = str(uuid7())
    stale = await times.command(first, action, key=key, at=at(12).isoformat())
    assert stale.status_code == 409, stale.text
    current = await times.changes.workforce.client.get(
        times.base + f"/my-time-entries/{first['entry_id']}", headers=times.changes.left_headers
    )
    assert current.json() == good.json()


async def test_native_sql_serialization_error_maps_to_conflict_and_rolls_back_key(
    times: Times, app_pool: RuntimePool, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = dict((await times.start()).json())
    original = commands.claim

    async def injected[T: BaseModel](
        conn: RuntimeConnection, scope: IdempotencyScope, request_hash: str, model: type[T]
    ) -> T | None:
        await original(conn, scope, request_hash, model)
        await conn.execute(
            "do $$begin raise exception using errcode='40001',"
            "message='FAKE injected serialization failure';end;$$"
        )
        return None

    monkeypatch.setattr(commands, "claim", injected)
    key = str(uuid7())
    refused = await times.command(entry, "clock_out", key=key, at=at(11).isoformat())
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "WORKFORCE_CONFLICT"
    async with tenant_transaction(app_pool, times.changes.workforce.world.a.tenant_id) as conn:
        assert (
            await (
                await conn.execute(
                    "select count(*) from gba.idempotency_keys where idempotency_key=%s", (key,)
                )
            ).fetchone()
        ) == (0,)
        assert (
            await (
                await conn.execute(
                    "select last_revision,is_open from gba.time_entry_state where entry_id=%s",
                    (entry["entry_id"],),
                )
            ).fetchone()
        ) == (1, True)


async def test_clock_in_replay_and_correction_replay_keep_original_immutable_response(
    times: Times,
) -> None:
    identifier, key = str(uuid7()), str(uuid7())
    first = await times.start(key=key, identifier=identifier)
    assert first.status_code == 200, first.text
    ending = await times.command(dict(first.json()), "clock_out", at=at(11).isoformat())
    approved = await times.command(dict(ending.json()), "approve", times.changes.workforce.headers)
    assert approved.status_code == 200, approved.text
    replay = await times.start(key=key, identifier=identifier)
    assert replay.json() == first.json()
    previous = dict(approved.json())
    correcting_key = str(uuid7())
    corrected = await times.command(
        previous,
        "correct",
        key=correcting_key,
        starts_at=at(10).isoformat(),
        ends_at=at(12).isoformat(),
        breaks=[],
        reason="FAKE replay reason",
    )
    assert corrected.status_code == 200, corrected.text
    assert (
        await times.command(dict(corrected.json()), "approve", times.changes.workforce.headers)
    ).status_code == 200
    replay = await times.command(
        previous,
        "correct",
        key=correcting_key,
        starts_at=at(10).isoformat(),
        ends_at=at(12).isoformat(),
        breaks=[],
        reason="FAKE replay reason",
    )
    assert replay.json() == corrected.json()
    refused = await times.command(
        previous,
        "correct",
        key=correcting_key,
        starts_at=at(10).isoformat(),
        ends_at=at(12).isoformat(),
        breaks=[],
        reason="FAKE changed reason",
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.parametrize("orphan", ["head", "revision"])
async def test_raw_sql_cannot_leave_an_orphan_head_or_incomplete_projection(
    times: Times, app_pool: RuntimePool, owner_conn: psycopg.Connection, orphan: str
) -> None:
    first = dict((await times.start()).json()) if orphan == "revision" else None
    table, trigger = (
        ("time_entry_revisions", "time_entry_revisions_apply")
        if orphan == "revision"
        else ("time_entries", "time_entries_initialize")
    )
    owner_conn.execute(f"alter table gba.{table} disable trigger {trigger}")

    async def attempt() -> None:
        if first is not None:
            await raw_command(
                app_pool, times, first, times.changes.workforce.user.user_id, "clock_out", at=at(11)
            )
        else:
            async with tenant_transaction(
                app_pool, times.changes.workforce.world.a.tenant_id
            ) as conn:
                await set_user_context(conn, times.changes.workforce.user.user_id)
                await conn.execute(
                    "insert into gba.time_entries (tenant_id,id,profile_id,starts_at,created_by) "
                    "values (%s,%s,%s,%s,%s)",
                    (
                        times.changes.workforce.world.a.tenant_id,
                        uuid7(),
                        times.changes.left_profile,
                        at(10),
                        times.changes.workforce.user.user_id,
                    ),
                )

    try:
        with pytest.raises(psycopg.errors.CheckViolation, match="complete immutable history"):
            await attempt()
    finally:
        owner_conn.execute(f"alter table gba.{table} enable trigger {trigger}")


@pytest.mark.parametrize(
    "bad", ["overlap", "outside", "reverse", "null", "nested", "lower_bound", "too_many"]
)
async def test_raw_sql_corrections_require_valid_ordered_bounded_break_arrays(
    times: Times, app_pool: RuntimePool, bad: str
) -> None:
    entry = await closed(times)
    starts: object = [at(10, 10), at(10, 30)]
    ends: object = [at(10, 20), at(10, 40)]
    if bad == "overlap":
        starts = [at(10, 10), at(10, 15)]
    elif bad == "outside":
        ends = [at(10, 20), at(12)]
    elif bad == "reverse":
        starts = [at(10, 30), at(10, 10)]
        ends = [at(10, 40), at(10, 20)]
    elif bad == "null":
        starts = [None, at(10, 30)]
    elif bad == "nested":
        starts = [[at(10, 10)]]
        ends = [[at(10, 20)]]
    elif bad == "lower_bound":
        starts = "[0:0]={2031-06-02 10:10:00+00}"
        ends = "[0:0]={2031-06-02 10:20:00+00}"
    elif bad == "too_many":
        starts = [at(10, 10)] * 101
        ends = [at(10, 20)] * 101
    with pytest.raises(psycopg.errors.CheckViolation):
        await raw_command(
            app_pool,
            times,
            entry,
            times.changes.workforce.user.user_id,
            "correct",
            starts_at=at(10),
            ends_at=at(11),
            break_starts=starts,
            break_ends=ends,
            reason="FAKE bad breaks",
        )


async def test_timesheet_has_no_ledger_or_shared_occupancy_effect(
    times: Times, app_pool: RuntimePool
) -> None:
    business = times.changes.workforce.world.a.tenant_id

    async def counts() -> tuple[object, ...]:
        async with tenant_transaction(app_pool, business) as conn:
            row = await (
                await conn.execute(
                    "select (select count(*) from gba.resource_allocations),"
                    "(select count(*) from gba.journal_entries),"
                    "(select count(*) from gba.journal_lines)"
                )
            ).fetchone()
            assert row is not None
            return row

    before = await counts()
    entry = await closed(times)
    assert (
        await times.command(entry, "approve", times.changes.workforce.headers)
    ).status_code == 200
    assert await counts() == before


@pytest.mark.parametrize("action", ["approve", "decline"])
@pytest.mark.parametrize("raw_sql", [False, True])
async def test_branch_manager_cannot_decide_another_home_entry_with_wide_sql_context(
    times: Times,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    idp: FakeIdp,
    action: str,
    raw_sql: bool,
) -> None:
    entry = await closed(times)
    business = times.changes.workforce.world.a.tenant_id
    other, _ = seed_other_branch(owner_conn, times.changes.workforce.world.a)
    manager = seed_user(owner_conn, f"i3-foreign-home-manager-{uuid7()}")
    add_membership(
        owner_conn, tenant_id=business, user_id=manager.user_id, role="manager", location_id=other
    )
    reason = {"reason": "FAKE decline"} if action == "decline" else {}
    if raw_sql:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await raw_command(
                app_pool, times, entry, manager.user_id, action, reason=reason.get("reason")
            )
    else:
        denied = await times.command(
            entry, action, idp.bearer(manager.subject, email=manager.email), **reason
        )
        assert denied.status_code == 404, denied.text
    async with tenant_transaction(app_pool, business) as conn:
        assert (
            await (
                await conn.execute(
                    "select last_revision,approved_revision from gba.time_entry_state "
                    "where entry_id=%s",
                    (entry["entry_id"],),
                )
            ).fetchone()
        ) == (2, None)


async def test_home_scoped_manager_decision_locks_config_without_widening_scope(
    times: Times, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    entry = await closed(times)
    manager = seed_user(owner_conn, f"i3-scoped-manager-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=times.changes.workforce.world.a.tenant_id,
        user_id=manager.user_id,
        role="manager",
        location_id=times.changes.workforce.world.a.location_id,
    )
    approved = await times.command(
        entry, "approve", idp.bearer(manager.subject, email=manager.email)
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["effective"]["approved_by"] == str(manager.user_id)


async def test_active_delegate_cannot_read_or_mutate_timesheets(
    times: Times, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    entry = await closed(times)
    world = times.changes.workforce.world
    owners = [seed_user(owner_conn, f"i3-grant-owner-{uuid7()}") for _ in range(2)]
    for tenant, user in zip((world.a, world.b), owners, strict=True):
        add_membership(owner_conn, tenant_id=tenant.tenant_id, user_id=user.user_id, role="owner")
    await Parties(times.changes.workforce.client, idp, world).active_grant(
        owners[0], owners[1], [owners[1]]
    )
    auth = idp.bearer(owners[1].subject, email=owners[1].email)
    for prefix in ("time-entries", "my-time-entries"):
        for suffix in ("", f"/{entry['entry_id']}", f"/{entry['entry_id']}/history"):
            response = await times.changes.workforce.client.get(
                times.base + f"/{prefix}" + suffix, headers=auth
            )
            assert response.status_code == 403, response.text
    refused = await times.command(entry, "approve", auth)
    assert refused.status_code == 403, refused.text
    start = await times.changes.workforce.client.put(
        times.base + f"/time-entries/{uuid7()}",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "staff_profile_id": times.changes.left_profile,
            "starts_at": at(10).isoformat(),
        },
    )
    assert start.status_code == 403, start.text


async def entry_with_completed_breaks(
    times: Times, app_pool: RuntimePool, count: int
) -> dict[str, object]:
    first = await times.start()
    assert first.status_code == 200, first.text
    entry = dict(first.json())
    business = times.changes.workforce.world.a.tenant_id
    async with tenant_transaction(app_pool, business) as conn:
        await set_user_context(conn, times.changes.workforce.user.user_id)
        for index in range(count):
            for offset, action in enumerate(("break_start", "break_end"), 1):
                await conn.execute(
                    "insert into gba.time_entry_revisions "
                    "(tenant_id,entry_id,revision,action,occurred_at,created_by) "
                    "values (%s,%s,%s,%s,%s,%s)",
                    (
                        business,
                        entry["entry_id"],
                        1 + index * 2 + offset,
                        action,
                        at(10) + timedelta(seconds=index * 2 + offset),
                        times.changes.workforce.user.user_id,
                    ),
                )
    result = await times.changes.workforce.client.get(
        times.base + f"/my-time-entries/{entry['entry_id']}", headers=times.changes.left_headers
    )
    assert result.status_code == 200, result.text
    assert len(result.json()["breaks"]) == count
    return dict(result.json())


@pytest.mark.parametrize("raw_sql", [False, True])
@pytest.mark.parametrize("disable_before_close", [False, True])
async def test_break_limit_refuses_another_start_without_stranding_open_time(
    times: Times,
    app_pool: RuntimePool,
    manager_a: FakeUser,
    idp: FakeIdp,
    raw_sql: bool,
    disable_before_close: bool,
) -> None:
    entry = await entry_with_completed_breaks(times, app_pool, 100)
    business = times.changes.workforce.world.a.tenant_id
    key = str(uuid7())

    async def state() -> tuple[object, ...]:
        async with tenant_transaction(app_pool, business) as conn:
            row = await (
                await conn.execute(
                    "select s.last_revision,s.is_open,"
                    "(select count(*) from gba.time_entry_revisions),"
                    "(select count(*) from gba.idempotency_keys),"
                    "(select count(*) from gba.audit_events) from gba.time_entry_state s "
                    "where s.entry_id=%s",
                    (entry["entry_id"],),
                )
            ).fetchone()
            assert row is not None
            return row

    before = await state()
    if raw_sql:
        with pytest.raises(psycopg.DatabaseError) as error:
            await raw_command(
                app_pool,
                times,
                entry,
                times.changes.workforce.user.user_id,
                "break_start",
                at=at(10, 10),
            )
        assert error.value.sqlstate == "GBW01"
    else:
        denied = await times.command(entry, "break_start", key=key, at=at(10, 10).isoformat())
        assert denied.status_code == 409, denied.text
        assert denied.json()["error"]["code"] == "WORKFORCE_CONFLICT"
    assert await state() == before
    if disable_before_close:
        await Config(times.changes.workforce.client, idp).publish(
            manager_a, business, 1, ["booking_resources"]
        )
    result = await times.command(entry, "clock_out", at=at(11).isoformat())
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "proposed"
    assert result.json()["break_started_at"] is None
    assert len(result.json()["breaks"]) == 100
    assert result.json()["worked_microseconds"] == 3500 * 1_000_000


@pytest.mark.parametrize("finish", ["break_end", "clock_out"])
async def test_hundredth_break_can_end_normally_or_close_with_the_entry(
    times: Times, app_pool: RuntimePool, finish: str
) -> None:
    entry = await entry_with_completed_breaks(times, app_pool, 99)
    started = await times.command(entry, "break_start", at=at(10, 10).isoformat())
    assert started.status_code == 200, started.text
    ended = await times.command(dict(started.json()), finish, at=at(10, 20).isoformat())
    assert ended.status_code == 200, ended.text
    assert len(ended.json()["breaks"]) == 100
    if finish == "break_end":
        ended = await times.command(dict(ended.json()), "clock_out", at=at(11).isoformat())
        assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "proposed"
