"""I4 screen support: own desk, scoped directory, swap candidates, command outcomes.

These reads and the reference-only outcome of a command exist for the screens. They
add no new workforce effect; every check runs against real PostgreSQL 18.
"""

from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_management_api as api_shared
from tests.integration import test_timesheets as shared
from tests.integration.booking_support import at
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_timesheets import Times
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
times = shared.times
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = api_shared.manager_b

WINDOW = {"starts": at(0).isoformat(), "ends": at(23).isoformat()}


async def _get(times: Times, path: str, headers: dict[str, str], **params: str) -> httpx.Response:
    return await times.changes.workforce.client.get(
        times.base + path, headers=headers, params=params
    )


async def _outcome(
    times: Times,
    action: str,
    key: str,
    reference: dict[str, object],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await times.changes.workforce.client.post(
        times.base + f"/commands/{key}/{action}",
        headers=headers or times.changes.left_headers,
        json={"schema_version": 1, **reference},
    )


def _member(conn: psycopg.Connection, tenant: UUID, location: UUID | None, role: str) -> FakeUser:
    user = seed_user(conn, f"desk-{role}-{uuid7()}")
    add_membership(conn, tenant_id=tenant, user_id=user.user_id, role=role, location_id=location)
    return user


async def test_desk_names_own_profile_and_whether_new_actions_are_open(
    times: Times, manager_a: FakeUser, idp: FakeIdp, monkeypatch: pytest.MonkeyPatch
) -> None:
    changes = times.changes
    tenant = changes.workforce.world.a.tenant_id
    own = await _get(times, "/desk", changes.left_headers)
    assert own.status_code == 200, own.text
    assert own.json() == {
        "schema_version": 1,
        "business_id": str(tenant),
        "writes": "open",
        "profile": {
            "schema_version": 1,
            "business_id": str(tenant),
            "profile_id": changes.left_profile,
            "membership_id": str(changes.workforce.membership),
            "resource_id": str(changes.left_resource),
            "location_id": str(changes.workforce.world.a.location_id),
            "user_id": str(changes.workforce.user.user_id),
        },
        "colleague_shifts": "visible",
    }
    # A manager who takes no shifts has no profile; the desk still answers.
    manager = await _get(times, "/desk", changes.workforce.headers)
    assert manager.status_code == 200, manager.text
    assert manager.json()["profile"] is None
    await Config(changes.workforce.client, idp).publish(manager_a, tenant, 1, ["booking_resources"])
    off = await _get(times, "/desk", changes.left_headers)
    assert off.status_code == 200, off.text
    assert off.json()["writes"] == "module_disabled"
    assert off.json()["profile"]["profile_id"] == changes.left_profile
    current = modules.MODULES_BY_ID["workforce"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "workforce",
        current.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
    )
    revoked = await _get(times, "/desk", changes.left_headers)
    assert revoked.json()["writes"] == "not_accepted"


async def test_directory_names_staff_only_inside_the_managers_scope(
    times: Times, owner_conn: psycopg.Connection, idp: FakeIdp, manager_a: FakeUser
) -> None:
    changes = times.changes
    world = changes.workforce.world
    listed = await _get(times, "/directory", changes.workforce.headers)
    assert listed.status_code == 200, listed.text
    items = {item["user_id"]: item for item in listed.json()["items"]}
    left = items[str(changes.workforce.user.user_id)]
    assert left["profile_id"] == changes.left_profile
    assert left["home_location_id"] == str(world.a.location_id)
    assert left["membership_id"] == str(changes.workforce.membership)
    assert left["display_name"]
    assert items[str(changes.right_user.user_id)]["profile_id"] == changes.right_profile
    # The manager's own membership is a candidate without a profile.
    assert items[str(manager_a.user_id)]["profile_id"] is None
    assert items[str(manager_a.user_id)]["home_location_id"] is None
    refused = await _get(times, "/directory", changes.left_headers)
    assert refused.status_code == 403, refused.text
    other_location, _ = seed_other_branch(owner_conn, world.a)
    branch = _member(owner_conn, world.a.tenant_id, other_location, "manager")
    scoped = await _get(times, "/directory", idp.bearer(branch.subject, email=branch.email))
    assert scoped.status_code == 200, scoped.text
    assert {item["user_id"] for item in scoped.json()["items"]} == {str(branch.user_id)}
    paged = await _get(times, "/directory", changes.workforce.headers, limit="1")
    assert len(paged.json()["items"]) == 1
    assert paged.json()["next_cursor"] == paged.json()["items"][0]["membership_id"]


async def test_swap_candidates_are_a_home_colleagues_published_assigned_shifts(
    times: Times, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    changes = times.changes
    world = changes.workforce.world
    theirs = await changes.shift(changes.right_profile)
    await changes.shift(None, starts_at=at(12).isoformat(), ends_at=at(13).isoformat())
    await changes.shift(
        changes.left_profile, starts_at=at(14).isoformat(), ends_at=at(15).isoformat()
    )
    cancelled = await changes.shift(
        changes.right_profile, starts_at=at(16).isoformat(), ends_at=at(17).isoformat()
    )
    dropped = await changes.workforce.put(
        f"/shifts/{cancelled['shift_id']}",
        changes.workforce.shift(
            expected_revision=1,
            starts_at=at(16).isoformat(),
            ends_at=at(17).isoformat(),
            status="cancelled",
        ),
    )
    assert dropped.status_code == 200, dropped.text
    path = f"/colleagues/{changes.right_profile}/shifts"
    listed = await _get(times, path, changes.left_headers, **WINDOW)
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == [theirs]
    wide = await _get(
        times, path, changes.left_headers, starts=at(0).isoformat(), ends="2031-09-02T00:00:00Z"
    )
    assert wide.status_code == 422, wide.text
    unknown = await _get(times, f"/colleagues/{uuid7()}/shifts", changes.left_headers, **WINDOW)
    assert unknown.status_code == 404, unknown.text
    # A person without a staff profile has no colleagues to swap with.
    manager = await _get(times, path, changes.workforce.headers, **WINDOW)
    assert manager.status_code == 404, manager.text
    # A profile of another branch is not a colleague, even with a published shift.
    other_location, _ = seed_other_branch(owner_conn, world.a)
    away = _member(owner_conn, world.a.tenant_id, other_location, "artist")
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s", (away.user_id,)
        ).fetchone()
    assert row is not None
    profile = await changes.workforce.put(
        f"/staff/{uuid7()}", {"membership_id": str(row[0]), "location_id": str(other_location)}
    )
    assert profile.status_code == 200, profile.text
    far = await changes.workforce.put(
        f"/shifts/{uuid7()}",
        changes.workforce.shift(
            location_id=str(other_location),
            staff_profile_id=profile.json()["profile_id"],
            starts_at=at(18).isoformat(),
            ends_at=at(19).isoformat(),
        ),
    )
    assert far.status_code == 200, far.text
    hidden = await _get(
        times, f"/colleagues/{profile.json()['profile_id']}/shifts", changes.left_headers, **WINDOW
    )
    assert hidden.status_code == 404, hidden.text


async def test_command_outcome_is_resolved_by_its_original_key_without_a_body(
    times: Times,
) -> None:
    changes = times.changes
    tenant = changes.workforce.world.a.tenant_id
    entry, key = str(uuid7()), str(uuid7())
    reference: dict[str, object] = {
        "operation": "time.clock_in",
        "subject_id": entry,
        "revision": 1,
    }
    before = await _outcome(times, "resolve", key, reference)
    assert before.status_code == 200, before.text
    assert before.json() == {
        "schema_version": 1,
        "business_id": str(tenant),
        "key": key,
        "operation": "time.clock_in",
        "state": "unresolved",
    }
    created = await times.start(key, entry)
    assert created.status_code == 200, created.text
    committed = await _outcome(times, "resolve", key, reference)
    assert committed.status_code == 200, committed.text
    assert committed.json()["state"] == "committed"
    # One key names one subject and version, for the person who sent it.
    for wrong in ({"subject_id": str(uuid7())}, {"revision": 2}):
        refused = await _outcome(times, "resolve", key, {**reference, **wrong})
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "INVALID_REFERENCE"
    stranger = await _outcome(times, "resolve", key, reference, changes.right_headers)
    assert stranger.json()["state"] == "unresolved"
    # Cancelling after the commit reports the commit and leaves the replay intact.
    late = await _outcome(times, "cancel", key, reference)
    assert late.status_code == 200, late.text
    assert late.json()["state"] == "committed"
    replay = await times.start(key, entry)
    assert replay.status_code == 200, replay.text
    assert replay.json() == created.json()
    malformed = await _outcome(times, "resolve", key, {**reference, "operation": "payroll"})
    assert malformed.status_code == 422, malformed.text
    extra = await _outcome(times, "resolve", key, {**reference, "reason": "FAKE private"})
    assert extra.status_code == 422, extra.text


async def test_cancelled_unresolved_command_can_never_commit(
    times: Times, owner_conn: psycopg.Connection
) -> None:
    changes = times.changes
    tenant = changes.workforce.world.a.tenant_id
    entry, key = str(uuid7()), str(uuid7())
    reference: dict[str, object] = {
        "operation": "time.clock_in",
        "subject_id": entry,
        "revision": 1,
    }
    cancelled = await _outcome(times, "cancel", key, reference)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    assert (await _outcome(times, "cancel", key, reference)).json()["state"] == "cancelled"
    assert (await _outcome(times, "resolve", key, reference)).json()["state"] == "cancelled"
    other = await _outcome(times, "resolve", key, {**reference, "revision": 2})
    assert other.status_code == 422, other.text
    refused = await times.start(key, entry)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    with owner_tenant_transaction(owner_conn, tenant):
        count = owner_conn.execute("select count(*) from gba.time_entries").fetchone()
    assert count == (0,)
    # The person may then start again with a new key: one entry, no second effect.
    fresh = await times.start(str(uuid7()), entry)
    assert fresh.status_code == 200, fresh.text


async def test_outcomes_stay_available_while_the_module_is_off(
    times: Times, manager_a: FakeUser, idp: FakeIdp
) -> None:
    changes = times.changes
    tenant = changes.workforce.world.a.tenant_id
    created = await times.start()
    assert created.status_code == 200, created.text
    entry = dict(created.json())
    await Config(changes.workforce.client, idp).publish(manager_a, tenant, 1, ["booking_resources"])
    key = str(uuid7())
    closed = await times.command(entry, "clock_out", key=key, at=at(11).isoformat())
    assert closed.status_code == 200, closed.text
    reference: dict[str, object] = {
        "operation": "time.event",
        "subject_id": entry["entry_id"],
        "revision": 2,
    }
    assert (await _outcome(times, "resolve", key, reference)).json()["state"] == "committed"
    unsent = await _outcome(times, "cancel", str(uuid7()), {**reference, "revision": 3})
    assert unsent.status_code == 200, unsent.text
    assert unsent.json()["state"] == "cancelled"


async def test_another_company_and_plain_staff_get_no_management_reads(
    times: Times, manager_b: FakeUser, idp: FakeIdp
) -> None:
    changes = times.changes
    # Plain staff: the two management reads are refused; their own reads answer.
    location = changes.workforce.world.a.location_id
    for path in ("/directory", f"/locations/{location}/settings"):
        refused = await _get(times, path, changes.left_headers)
        assert refused.status_code == 403, refused.text
    for path in ("/desk", f"/colleagues/{changes.right_profile}/shifts"):
        own = await _get(times, path, changes.left_headers, **WINDOW)
        assert own.status_code == 200, own.text
    foreign = idp.bearer(manager_b.subject, email=manager_b.email)
    reference: dict[str, object] = {
        "operation": "time.clock_in",
        "subject_id": str(uuid7()),
        "revision": 1,
    }
    for path in ("/desk", "/directory", f"/colleagues/{changes.right_profile}/shifts"):
        response = await _get(times, path, foreign, **WINDOW)
        assert response.status_code == 403, response.text
    for action in ("resolve", "cancel"):
        response = await _outcome(times, action, str(uuid7()), reference, foreign)
        assert response.status_code == 403, response.text
