"""Colleague-shift visibility is a branch setting (owner decision 2026-10-11).

By default an employee sees the published shifts of home-branch colleagues. The
owner, a manager or the manager of that branch may hide them. The setting is
versioned, audited and never changed in place; every check runs on PostgreSQL 18.
"""

import asyncio
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.business import workforce_desk
from gorgona_booking.business.workforce_desk_contracts import LocationSettingInput
from gorgona_booking.db.pool import RuntimePool, set_tenant_context, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.db.workforce_guard import assert_workforce_ready
from tests.integration import test_management_api as api_shared
from tests.integration import test_timesheets as shared
from tests.integration.booking_support import at
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_timesheets import Times
from tests.integration.test_workforce_desk import WINDOW, _get, _member, _outcome
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
times = shared.times
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = api_shared.manager_b

TABLE = "gba.work_location_setting_versions"
INSERT = (
    f"insert into {TABLE} (tenant_id,location_id,revision,colleague_shifts_visible,created_by) "
    "values (%s,%s,%s,%s,%s)"
)


def _path(location: object) -> str:
    return f"/locations/{location}/settings"


async def _set(
    times: Times,
    location: object,
    visible: object,
    expected: int,
    headers: dict[str, str] | None = None,
    key: str | None = None,
    extra: dict[str, object] | None = None,
) -> httpx.Response:
    return await times.changes.workforce.client.put(
        times.base + _path(location),
        headers={
            **(headers or times.changes.workforce.headers),
            "Idempotency-Key": key or str(uuid7()),
        },
        json={
            "schema_version": 1,
            "expected_revision": expected,
            "colleague_shifts_visible": visible,
            **(extra or {}),
        },
    )


async def _run(
    pool: RuntimePool,
    tenant: UUID,
    session: UUID,
    statement: str,
    values: tuple[object, ...],
    branch: UUID | None = None,
) -> None:
    """One statement as the runtime role, for this person and optional branch scope."""
    async with tenant_transaction(pool, tenant) as conn:
        await set_user_context(conn, session)
        if branch is not None:
            await conn.execute("select set_config('gba.location_id',%s,true)", (str(branch),))
        await conn.execute(statement.encode("utf-8"), values)


def _versions(owner_conn: psycopg.Connection, tenant: UUID) -> list[tuple[object, ...]]:
    with owner_tenant_transaction(owner_conn, tenant):
        return owner_conn.execute(
            f"select location_id,revision,colleague_shifts_visible from {TABLE} "
            "order by location_id,revision"
        ).fetchall()


async def test_shifts_are_visible_by_default_and_a_manager_may_hide_and_show_them(
    times: Times, manager_a: FakeUser, owner_conn: psycopg.Connection
) -> None:
    changes = times.changes
    world = changes.workforce.world
    tenant, location = world.a.tenant_id, world.a.location_id
    theirs = await changes.shift(changes.right_profile)
    candidates = f"/colleagues/{changes.right_profile}/shifts"
    desk = await _get(times, "/desk", changes.left_headers)
    assert desk.json()["colleague_shifts"] == "visible"
    initial = await _get(times, _path(location), changes.workforce.headers)
    assert initial.status_code == 200, initial.text
    assert initial.json() == {
        "schema_version": 1,
        "business_id": str(tenant),
        "location_id": str(location),
        "revision": 0,
        "colleague_shifts_visible": True,
        "changed_by": None,
        "changed_at": None,
    }
    hidden = await _set(times, location, False, 0)
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["revision"] == 1
    assert hidden.json()["colleague_shifts_visible"] is False
    assert hidden.json()["changed_by"] == str(manager_a.user_id)
    assert hidden.json()["changed_at"] is not None
    assert (await _get(times, _path(location), changes.workforce.headers)).json() == hidden.json()
    assert (await _get(times, "/desk", changes.left_headers)).json()["colleague_shifts"] == "hidden"
    refused = await _get(times, candidates, changes.left_headers, **WINDOW)
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "COLLEAGUE_SHIFTS_HIDDEN"
    # Hiding stops browsing only: own shifts, the colleague list and a handover remain.
    own = await _get(times, "/my-shifts", changes.left_headers, **WINDOW)
    assert own.status_code == 200, own.text
    names = await _get(times, "/colleagues", changes.left_headers)
    assert names.status_code == 200, names.text
    assert changes.right_profile in [item["profile_id"] for item in names.json()["items"]]
    handover = await changes.propose("handover", await changes.shift(changes.left_profile))
    assert handover.status_code == 200, handover.text
    shown = await _set(times, location, True, 1)
    assert shown.status_code == 200, shown.text
    assert shown.json()["revision"] == 2
    listed = await _get(times, candidates, changes.left_headers, **WINDOW)
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == [theirs]
    assert _versions(owner_conn, tenant) == [(location, 1, False), (location, 2, True)]
    with owner_tenant_transaction(owner_conn, tenant):
        audit = owner_conn.execute(
            "select actor,target_type,target_id,details from gba.audit_events "
            "where action='workforce.location_setting' order by id"
        ).fetchall()
    assert audit == [
        (f"user:{manager_a.user_id}", "location_setting", str(location), {"revision": 1}),
        (f"user:{manager_a.user_id}", "location_setting", str(location), {"revision": 2}),
    ]


async def test_change_is_versioned_idempotent_and_settled_by_its_original_key(
    times: Times, owner_conn: psycopg.Connection
) -> None:
    changes = times.changes
    world = changes.workforce.world
    tenant, location = world.a.tenant_id, world.a.location_id
    manager = changes.workforce.headers
    key = str(uuid7())
    reference: dict[str, object] = {
        "operation": "location_setting",
        "subject_id": str(location),
        "revision": 1,
    }
    assert (await _outcome(times, "resolve", key, reference, manager)).json()[
        "state"
    ] == "unresolved"
    first = await _set(times, location, False, 0, key=key)
    assert first.status_code == 200, first.text
    replay = await _set(times, location, False, 0, key=key)
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    reused = await _set(times, location, True, 0, key=key)
    assert reused.status_code == 422, reused.text
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert (await _outcome(times, "resolve", key, reference, manager)).json()[
        "state"
    ] == "committed"
    wrong = await _outcome(times, "resolve", key, {**reference, "revision": 2}, manager)
    assert wrong.status_code == 422, wrong.text
    stale = await _set(times, location, True, 0)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "WORKFORCE_CONFLICT"
    skipped = await _set(times, location, True, 2)
    assert skipped.status_code == 409, skipped.text
    # A cancelled unresolved key can never write the setting afterwards.
    lost = str(uuid7())
    cancelled = await _outcome(times, "cancel", lost, {**reference, "revision": 2}, manager)
    assert cancelled.json()["state"] == "cancelled"
    late = await _set(times, location, True, 1, key=lost)
    assert late.status_code == 422, late.text
    assert late.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert _versions(owner_conn, tenant) == [(location, 1, False)]
    malformed: tuple[tuple[object, int, dict[str, object]], ...] = (
        ("yes", 1, {}),
        (1, 1, {}),
        (None, 1, {}),
        (True, -1, {}),
        (True, 1, {"reason": "FAKE private"}),
    )
    for visible, expected, extra in malformed:
        refused = await _set(times, location, visible, expected, extra=extra)
        assert refused.status_code == 422, refused.text
    assert _versions(owner_conn, tenant) == [(location, 1, False)]


async def test_only_the_owner_a_manager_or_that_branch_manager_changes_it(
    times: Times, owner_conn: psycopg.Connection, idp: FakeIdp, manager_b: FakeUser
) -> None:
    changes = times.changes
    world = changes.workforce.world
    tenant, location = world.a.tenant_id, world.a.location_id
    other, _ = seed_other_branch(owner_conn, world.a)
    theirs = await changes.shift(changes.right_profile)
    candidates = f"/colleagues/{changes.right_profile}/shifts"

    def bearer(user: FakeUser) -> dict[str, str]:
        return idp.bearer(user.subject, email=user.email)

    desk_staff = bearer(_member(owner_conn, tenant, location, "front_desk"))
    for headers in (changes.left_headers, desk_staff, bearer(manager_b)):
        assert (await _get(times, _path(location), headers)).status_code == 403
        denied = await _set(times, location, False, 0, headers)
        assert denied.status_code == 403, denied.text
    away = bearer(_member(owner_conn, tenant, other, "manager"))
    assert (await _get(times, _path(location), away)).status_code == 403
    outside = await _set(times, location, False, 0, away)
    assert outside.status_code == 403, outside.text
    assert _versions(owner_conn, tenant) == []
    # The other branch hides its own shifts; this branch is not affected.
    elsewhere = await _set(times, other, False, 0, away)
    assert elsewhere.status_code == 200, elsewhere.text
    assert elsewhere.json()["location_id"] == str(other)
    still = await _get(times, candidates, changes.left_headers, **WINDOW)
    assert still.status_code == 200, still.text
    assert still.json()["items"] == [theirs]
    here = bearer(_member(owner_conn, tenant, location, "manager"))
    assert (await _get(times, _path(location), here)).json()["revision"] == 0
    by_branch = await _set(times, location, False, 0, here)
    assert by_branch.status_code == 200, by_branch.text
    assert (await _get(times, candidates, changes.left_headers, **WINDOW)).status_code == 403
    owner = bearer(_member(owner_conn, tenant, None, "owner"))
    by_owner = await _set(times, location, True, 1, owner)
    assert by_owner.status_code == 200, by_owner.text
    assert by_owner.json()["revision"] == 2
    assert (await _set(times, other, True, 1, owner)).json()["revision"] == 2
    assert (await _get(times, candidates, changes.left_headers, **WINDOW)).status_code == 200
    unknown = uuid7()
    assert (await _get(times, _path(unknown), owner)).status_code == 404
    assert (await _set(times, unknown, False, 0, owner)).status_code == 404
    assert _versions(owner_conn, tenant) == sorted(
        [(location, 1, False), (location, 2, True), (other, 1, False), (other, 2, True)]
    )


async def test_setting_stays_readable_and_closed_to_change_while_the_module_is_off(
    times: Times, manager_a: FakeUser, idp: FakeIdp, app_pool: RuntimePool
) -> None:
    changes = times.changes
    world = changes.workforce.world
    tenant, location = world.a.tenant_id, world.a.location_id
    assert (await _set(times, location, False, 0)).status_code == 200
    await Config(changes.workforce.client, idp).publish(manager_a, tenant, 1, ["booking_resources"])
    kept = await _get(times, _path(location), changes.workforce.headers)
    assert kept.status_code == 200, kept.text
    assert (kept.json()["revision"], kept.json()["colleague_shifts_visible"]) == (1, False)
    desk = await _get(times, "/desk", changes.left_headers)
    assert (desk.json()["writes"], desk.json()["colleague_shifts"]) == ("module_disabled", "hidden")
    browse = await _get(
        times, f"/colleagues/{changes.right_profile}/shifts", changes.left_headers, **WINDOW
    )
    assert browse.status_code == 403, browse.text
    assert browse.json()["error"]["code"] == "COLLEAGUE_SHIFTS_HIDDEN"
    refused = await _set(times, location, True, 1)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "MODULE_DISABLED"
    author = manager_a.user_id
    with pytest.raises(psycopg.DatabaseError) as caught:
        await _run(app_pool, tenant, author, INSERT, (tenant, location, 2, True, author))
    assert caught.value.sqlstate == "GBM01"


async def test_sql_keeps_versions_ordered_immutable_and_inside_the_branch(
    times: Times, manager_a: FakeUser, owner_conn: psycopg.Connection, app_pool: RuntimePool
) -> None:
    world = times.changes.workforce.world
    tenant, location = world.a.tenant_id, world.a.location_id
    other, _ = seed_other_branch(owner_conn, world.a)
    user = manager_a.user_id
    artist = times.changes.workforce.user.user_id
    away = _member(owner_conn, tenant, other, "manager").user_id

    async def refused(
        statement: str,
        values: tuple[object, ...],
        branch: UUID | None = None,
        session: UUID = user,
    ) -> str:
        with pytest.raises(psycopg.DatabaseError) as caught:
            await _run(app_pool, tenant, session, statement, values, branch)
        return str(caught.value.sqlstate)

    # The first version is 1 and versions never skip.
    assert await refused(INSERT, (tenant, location, 2, False, user)) == "GBW01"
    assert await refused(INSERT, (tenant, location, 0, False, user)) == "GBW01"
    # The author is the authenticated owner or manager whose membership covers the branch.
    assert await refused(INSERT, (tenant, location, 1, False, artist), session=artist) == "42501"
    assert await refused(INSERT, (tenant, location, 1, False, away), session=away) == "42501"
    assert await refused(INSERT, (tenant, location, 1, False, away)) == "42501"
    assert await refused(INSERT, (tenant, location, 1, False, user), session=away) == "42501"
    # A branch session writes and reads its own branch only.
    assert await refused(INSERT, (tenant, location, 1, False, user), other) == "42501"
    await _run(app_pool, tenant, user, INSERT, (tenant, location, 1, False, user), location)
    async with tenant_transaction(app_pool, tenant) as conn:
        await conn.execute("select set_config('gba.location_id',%s,true)", (str(other),))
        row = await (await conn.execute(f"select count(*) from {TABLE}".encode())).fetchone()
    assert row == (0,)
    assert await refused(INSERT, (tenant, location, 1, True, user)) == "GBW01"
    change = f"update {TABLE} set colleague_shifts_visible=true where tenant_id=%s"
    assert await refused(change, (tenant,)) == "42501"
    assert await refused(f"delete from {TABLE} where tenant_id=%s", (tenant,)) == "42501"
    # Even the schema owner cannot rewrite or remove a recorded version.
    for statement in (f"delete from {TABLE}", f"update {TABLE} set revision=9"):
        with pytest.raises(psycopg.DatabaseError), owner_tenant_transaction(owner_conn, tenant):
            owner_conn.execute(statement.encode())
    assert _versions(owner_conn, tenant) == [(location, 1, False)]


@pytest.mark.parametrize("damage", ["scope", "guard", "module", "grant"])
async def test_damaged_setting_controls_fail_closed_with_503(
    times: Times, owner_conn: psycopg.Connection, app_pool: RuntimePool, damage: str
) -> None:
    world = times.changes.workforce.world
    name = TABLE.removeprefix("gba.")
    if damage == "grant":
        mutation = f"grant update (colleague_shifts_visible) on {TABLE} to gba_runtime"
        restoring = f"revoke update (colleague_shifts_visible) on {TABLE} from gba_runtime"
    elif damage == "scope":
        mutation = f"drop policy {name}_location_scope on {TABLE}"
        restoring = (
            f"create policy {name}_location_scope on {TABLE} as restrictive to gba_runtime "
            "using (gba.current_location_id() is null or location_id=gba.current_location_id()) "
            "with check (gba.current_location_id() is null "
            "or location_id=gba.current_location_id())"
        )
    else:
        trigger = name + ("_guard" if damage == "guard" else "_require_workforce")
        row = owner_conn.execute(
            "select pg_get_triggerdef(oid) from pg_trigger where tgrelid=%s::regclass "
            "and tgname=%s",
            (TABLE, trigger),
        ).fetchone()
        assert row is not None
        mutation = f"drop trigger {trigger} on {TABLE}"
        restoring = str(row[0])
    try:
        owner_conn.execute(mutation.encode("utf-8"))
        read = await _get(times, _path(world.a.location_id), times.changes.workforce.headers)
        assert read.status_code == 503, read.text
        desk = await _get(times, "/desk", times.changes.left_headers)
        assert desk.status_code == 503, desk.text
        write = await _set(times, world.a.location_id, False, 0)
        assert write.status_code == 503, write.text
    finally:
        owner_conn.execute(restoring.encode("utf-8"))
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        await assert_workforce_ready(conn)
    assert _versions(owner_conn, world.a.tenant_id) == []


async def test_participants_read_the_shifts_of_their_request_even_when_hidden(
    times: Times, owner_conn: psycopg.Connection, idp: FakeIdp, manager_b: FakeUser
) -> None:
    changes = times.changes
    world = changes.workforce.world
    tenant, location = world.a.tenant_id, world.a.location_id
    mine = await changes.shift(changes.left_profile)
    theirs = await changes.shift(changes.right_profile)
    swap = await changes.propose(
        "swap",
        mine,
        other_shift_id=theirs["shift_id"],
        expected_other_shift_revision=theirs["revision"],
    )
    assert swap.status_code == 200, swap.text
    assert (await _set(times, location, False, 0)).status_code == 200
    path = f"/my-changes/{swap.json()['request_id']}/shifts"
    # Both sides see exactly the two versions the request was made for.
    for headers in (changes.left_headers, changes.right_headers):
        named = await _get(times, path, headers)
        assert named.status_code == 200, named.text
        assert named.json() == {"schema_version": 1, "items": [mine, theirs], "next_cursor": None}
    browse = await _get(
        times, f"/colleagues/{changes.right_profile}/shifts", changes.left_headers, **WINDOW
    )
    assert browse.status_code == 403, browse.text
    # A person outside the request learns nothing from it, a manager included.
    outsider = _member(owner_conn, tenant, location, "artist")
    for headers in (
        idp.bearer(outsider.subject, email=outsider.email),
        changes.workforce.headers,
    ):
        assert (await _get(times, path, headers)).status_code == 404
    assert (
        await _get(times, f"/my-changes/{uuid7()}/shifts", changes.left_headers)
    ).status_code == 404
    foreign = await _get(times, path, idp.bearer(manager_b.subject, email=manager_b.email))
    assert foreign.status_code == 403, foreign.text
    later = await changes.shift(
        changes.left_profile, starts_at=at(14).isoformat(), ends_at=at(15).isoformat()
    )
    handover = await changes.propose("handover", later)
    assert handover.status_code == 200, handover.text
    single = await _get(
        times, f"/my-changes/{handover.json()['request_id']}/shifts", changes.right_headers
    )
    assert single.status_code == 200, single.text
    assert [item["shift_id"] for item in single.json()["items"]] == [handover.json()["shift_id"]]


async def _wait_for_branch_lock_waiter(
    monitor: psycopg.AsyncConnection, tenant: UUID, location: UUID
) -> None:
    """Seen in pg_locks: a session waits for exactly this branch's setting lock."""
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        row = await (
            await monitor.execute(
                "select count(*) from pg_locks l, "
                "(select pg_catalog.hashtextextended(%s,0) as k) x "
                "where l.locktype='advisory' and not l.granted and l.objsubid=1 "
                "and l.database=(select oid from pg_database where datname=current_database()) "
                "and l.classid=((x.k >> 32) & 4294967295)::oid "
                "and l.objid=(x.k & 4294967295)::oid",
                (f"gba:work-location-setting:{tenant}:{location}",),
            )
        ).fetchone()
        if row is not None and row[0] >= 1:
            return
        await asyncio.sleep(0.01)
    pytest.fail("no observed wait for the branch setting lock in pg_locks")


async def test_two_changes_of_one_version_wait_and_only_the_first_is_recorded(
    times: Times,
    manager_a: FakeUser,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    owner_conn: psycopg.Connection,
) -> None:
    world = times.changes.workforce.world
    tenant, location = world.a.tenant_id, world.a.location_id
    user = manager_a.user_id
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        async with app_pool.connection() as conn, conn.transaction():
            await set_tenant_context(conn, tenant)
            await set_user_context(conn, user)
            # The change as its route runs it, recorded but not yet committed.
            first = await workforce_desk.save_location_setting(
                conn,
                tenant,
                location,
                user,
                f"user:{user}",
                str(uuid7()),
                LocationSettingInput(expected_revision=0, colleague_shifts_visible=False),
            )
            assert first.revision == 1
            task = asyncio.create_task(_set(times, location, True, 0))
            await _wait_for_branch_lock_waiter(monitor, tenant, location)
            assert not task.done()
        response = await task
    finally:
        await monitor.close()
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "WORKFORCE_CONFLICT"
    assert _versions(owner_conn, tenant) == [(location, 1, False)]
