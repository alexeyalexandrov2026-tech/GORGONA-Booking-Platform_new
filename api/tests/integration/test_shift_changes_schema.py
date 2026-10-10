"""Every new actor/snapshot/transition trigger is part of the approved boundary."""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.workforce_guard import assert_workforce_ready
from tests.integration import test_shift_changes as shared
from tests.integration.test_shift_changes import Changes

pytestmark = pytest.mark.anyio
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


@pytest.mark.parametrize(
    "damage",
    [
        "policy",
        "actor_function",
        "snapshot_function",
        "event_apply",
        "default",
        "snapshot_fk",
        "transition_alias",
        "transition_row",
        "when",
    ],
)
async def test_i2_schema_damage_refuses_history_and_new_actions(
    changes: Changes,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    damage: str,
) -> None:
    if damage in ("actor_function", "snapshot_function"):
        function = (
            "guard_shift_change_event"
            if damage == "actor_function"
            else "guard_shift_change_snapshot"
        )
        row = owner_conn.execute(
            "select pg_get_functiondef(('gba.'||%s||'()')::regprocedure)", (function,)
        ).fetchone()
        assert row is not None
        restore = str(row[0])
        mutation = (
            f"create or replace function gba.{function}() returns trigger "
            "language plpgsql as $$begin return new;end;$$"
        )
    elif damage == "event_apply":
        mutation = "alter table gba.shift_change_events disable trigger shift_change_events_apply"
        restore = "alter table gba.shift_change_events enable trigger shift_change_events_apply"
    elif damage == "default":
        mutation = (
            "alter table gba.shift_change_skill_snapshots alter column creation_xid drop default"
        )
        restore = (
            "alter table gba.shift_change_skill_snapshots alter column creation_xid "
            "set default pg_current_xact_id()"
        )
    elif damage == "snapshot_fk":
        row = owner_conn.execute(
            "select conname,pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='gba.shift_change_skill_snapshots'::regclass "
            "and confrelid='gba.shift_change_requests'::regclass"
        ).fetchone()
        assert row is not None
        mutation = f"alter table gba.shift_change_skill_snapshots drop constraint {row[0]}"
        restore = f"alter table gba.shift_change_skill_snapshots add constraint {row[0]} {row[1]}"
    elif damage == "policy":
        row = owner_conn.execute(
            "select pg_get_expr(polqual,polrelid),pg_get_expr(polwithcheck,polrelid) "
            "from pg_policy where polrelid='gba.shift_change_requests'::regclass "
            "and polname='shift_change_requests_location_scope'"
        ).fetchone()
        assert row is not None
        restore = (
            "alter policy shift_change_requests_location_scope on gba.shift_change_requests "
            f"using ({row[0]}) with check ({row[1]})"
        )
        mutation = (
            "alter policy shift_change_requests_location_scope on gba.shift_change_requests "
            "using (true) with check (true)"
        )
    else:
        table = "shift_change_events" if damage == "when" else "work_shift_versions"
        trigger = "shift_change_events_guard" if damage == "when" else "work_shift_versions_apply"
        row = owner_conn.execute(
            "select pg_get_triggerdef(oid) from pg_trigger "
            "where tgrelid=('gba.'||%s)::regclass and tgname=%s",
            (table, trigger),
        ).fetchone()
        assert row is not None
        restore = f"drop trigger {trigger} on gba.{table}; " + str(row[0])
        owner_conn.execute(f"drop trigger {trigger} on gba.{table}")
        if damage == "transition_alias":
            mutation = str(row[0]).replace("inserted_versions", "wrong_versions")
        elif damage == "transition_row":
            mutation = (
                "create trigger work_shift_versions_apply after insert on gba.work_shift_versions "
                "for each row execute function gba.apply_work_shift_version()"
            )
        else:
            mutation = (
                "create trigger shift_change_events_guard before insert on gba.shift_change_events "
                "for each row when (false) execute function gba.guard_shift_change_event()"
            )
    try:
        owner_conn.execute(mutation)
        history = await changes.workforce.client.get(
            changes.workforce.base + "/my-changes", headers=changes.left_headers
        )
        assert history.status_code == 503, history.text
        proposed = await changes.propose(
            "pickup",
            {"shift_id": str(uuid7()), "revision": 1},
            target_profile_id=changes.left_profile,
        )
        assert proposed.status_code == 503, proposed.text
    finally:
        owner_conn.execute(restore)
    async with tenant_transaction(app_pool, changes.workforce.world.a.tenant_id) as conn:
        await assert_workforce_ready(conn)
