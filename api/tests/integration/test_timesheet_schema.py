"""I3 projection constraints, privileged guards and policy damage fail closed."""

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.workforce_guard import assert_workforce_ready
from tests.integration import test_timesheets as shared
from tests.integration.booking_support import at
from tests.integration.test_timesheets import Times

pytestmark = pytest.mark.anyio
times = shared.times
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


@pytest.mark.parametrize(
    "damage",
    [
        "missing_exclusion",
        "deferred_exclusion",
        "weakened_exclusion",
        "projection_guard",
        "actor_guard",
        "apply",
        "policy",
        "xid_default",
        "when",
        "state_grant",
    ],
)
async def test_timesheet_schema_damage_refuses_reads_and_commands(
    times: Times, owner_conn: psycopg.Connection, app_pool: RuntimePool, damage: str
) -> None:
    first = await times.start()
    assert first.status_code == 200, first.text
    entry = dict(first.json())
    if "exclusion" in damage:
        row = owner_conn.execute(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='gba.time_entry_state'::regclass "
            "and conname='time_entry_state_no_overlap'"
        ).fetchone()
        assert row is not None
        definition = str(row[0])
        drop = "alter table gba.time_entry_state drop constraint time_entry_state_no_overlap"
        owner_conn.execute(drop)
        restore = (
            "alter table gba.time_entry_state add constraint time_entry_state_no_overlap "
            + definition
        )
        if damage == "missing_exclusion":
            mutation = None
        elif damage == "deferred_exclusion":
            mutation = restore + " deferrable initially deferred"
        else:
            mutation = restore.replace("approved_revision IS NOT NULL", "false")
            assert mutation != restore
        restoring = drop + "; " + restore
    elif damage in ("projection_guard", "actor_guard"):
        function = (
            "guard_time_entry_state"
            if damage == "projection_guard"
            else "guard_time_entry_revision"
        )
        row = owner_conn.execute(
            "select pg_get_functiondef(('gba.'||%s||'()')::regprocedure)", (function,)
        ).fetchone()
        assert row is not None
        restoring = str(row[0])
        mutation = (
            f"create or replace function gba.{function}() returns trigger "
            "language plpgsql as $$begin return new;end;$$"
        )
    elif damage == "apply":
        mutation = "alter table gba.time_entry_revisions disable trigger time_entry_revisions_apply"
        restoring = "alter table gba.time_entry_revisions enable trigger time_entry_revisions_apply"
    elif damage == "policy":
        row = owner_conn.execute(
            "select pg_get_expr(polqual,polrelid),pg_get_expr(polwithcheck,polrelid) "
            "from pg_policy where polrelid='gba.time_entry_state'::regclass "
            "and polname='time_entry_state_location_scope'"
        ).fetchone()
        assert row is not None
        mutation = (
            "alter policy time_entry_state_location_scope on gba.time_entry_state "
            "using (true) with check (true)"
        )
        restoring = (
            "alter policy time_entry_state_location_scope on gba.time_entry_state "
            f"using ({row[0]}) with check ({row[1]})"
        )
    elif damage == "xid_default":
        mutation = "alter table gba.time_entry_revisions alter column creation_xid drop default"
        restoring = (
            "alter table gba.time_entry_revisions alter column creation_xid "
            "set default pg_current_xact_id()"
        )
    elif damage == "when":
        row = owner_conn.execute(
            "select pg_get_triggerdef(oid) from pg_trigger "
            "where tgrelid='gba.time_entry_state'::regclass "
            "and tgname='time_entry_state_guard'"
        ).fetchone()
        assert row is not None
        owner_conn.execute("drop trigger time_entry_state_guard on gba.time_entry_state")
        mutation = str(row[0]).replace("EXECUTE FUNCTION", "WHEN (false) EXECUTE FUNCTION")
        restoring = "drop trigger time_entry_state_guard on gba.time_entry_state; " + str(row[0])
    else:
        mutation = "grant update (user_id) on gba.time_entry_state to gba_runtime"
        restoring = "revoke update (user_id) on gba.time_entry_state from gba_runtime"
    try:
        if mutation:
            owner_conn.execute(mutation)
        read = await times.changes.workforce.client.get(
            times.base + f"/my-time-entries/{entry['entry_id']}", headers=times.changes.left_headers
        )
        assert read.status_code == 503, read.text
        write = await times.command(entry, "clock_out", at=at(11).isoformat())
        assert write.status_code == 503, write.text
    finally:
        if damage == "missing_exclusion":
            owner_conn.execute(restore)
        else:
            owner_conn.execute(restoring)
    async with tenant_transaction(app_pool, times.changes.workforce.world.a.tenant_id) as conn:
        await assert_workforce_ready(conn)
