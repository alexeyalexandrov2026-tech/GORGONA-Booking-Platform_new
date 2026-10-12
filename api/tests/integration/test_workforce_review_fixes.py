"""Findings of the independent review of 2026-10-11, each pinned by a test.

F1: a hidden branch refuses a new swap, so a known shift id reveals nothing.
F2: the outside-schedule mark of the time in effect does not follow a later version.
F3: a long valid key can be discarded. F9: discarding has a daily limit per person.
N1: the directory skips a disabled account.
"""

from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import owner_tenant_transaction, set_user_status
from tests.integration import test_timesheets as shared
from tests.integration.booking_support import at
from tests.integration.seed import FakeUser
from tests.integration.test_timesheets import Times
from tests.integration.test_workforce_desk import WINDOW, _get, _member, _outcome
from tests.integration.test_workforce_visibility import _set
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
times = shared.times
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


def _count(owner_conn: psycopg.Connection, tenant: UUID, query: str) -> int:
    with owner_tenant_transaction(owner_conn, tenant):
        row = owner_conn.execute(query.encode("utf-8")).fetchone()
    assert row is not None
    return int(row[0])


async def _swap(
    times: Times, mine: dict[str, object], theirs: dict[str, object], **extra: object
) -> httpx.Response:
    body: dict[str, object] = {
        "other_shift_id": theirs["shift_id"],
        "expected_other_shift_revision": theirs["revision"],
        **extra,
    }
    return await times.changes.propose("swap", mine, **body)


def _effective(entry: dict[str, object]) -> dict[str, object]:
    value = entry["effective"]
    assert isinstance(value, dict)
    return value


async def test_a_hidden_branch_refuses_a_new_swap_and_tells_nothing_about_the_holder(
    times: Times, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    changes = times.changes
    world = changes.workforce.world
    tenant, location = world.a.tenant_id, world.a.location_id
    mine = await changes.shift(changes.left_profile)
    # The employee once saw this shift while it was open; a manager then assigned it.
    seen = await changes.shift(None, starts_at=at(12).isoformat(), ends_at=at(13).isoformat())
    listed = await _get(times, "/open-shifts", changes.left_headers, **WINDOW)
    assert seen["shift_id"] in [item["shift_id"] for item in listed.json()["items"]]
    assigned = await changes.workforce.put(
        f"/shifts/{seen['shift_id']}",
        changes.workforce.shift(
            expected_revision=1,
            staff_profile_id=changes.right_profile,
            starts_at=at(12).isoformat(),
            ends_at=at(13).isoformat(),
        ),
    )
    assert assigned.status_code == 200, assigned.text
    taken = dict(assigned.json())
    # While shown, the swap is an ordinary request and stays readable afterwards.
    earlier = await _swap(times, mine, taken)
    assert earlier.status_code == 200, earlier.text
    assert (await _set(times, location, False, 0)).status_code == 200
    kept = await _get(
        times, f"/my-changes/{earlier.json()['request_id']}/shifts", changes.left_headers
    )
    assert kept.status_code == 200, kept.text
    withdrawn = await changes.event(dict(earlier.json()), "withdraw", changes.left_headers)
    assert withdrawn.status_code == 200, withdrawn.text
    before = _count(owner_conn, tenant, "select count(*) from gba.shift_change_requests")
    # Hidden: the holder, another colleague and a stale version are answered alike.
    third = _member(owner_conn, tenant, location, "artist")
    with owner_tenant_transaction(owner_conn, tenant):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s", (third.user_id,)
        ).fetchone()
    assert row is not None
    other = await changes.workforce.put(
        f"/staff/{uuid7()}", {"membership_id": str(row[0]), "location_id": str(location)}
    )
    assert other.status_code == 200, other.text
    probes: tuple[dict[str, object], ...] = (
        {},
        {"target_profile_id": other.json()["profile_id"]},
        {"expected_other_shift_revision": 1},
    )
    for extra in probes:
        refused = await _swap(times, mine, taken, **extra)
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "COLLEAGUE_SHIFTS_HIDDEN"
    # The same answer under the id of an existing request: no holder oracle.
    for target in (changes.right_profile, other.json()["profile_id"]):
        probe = await changes.workforce.client.put(
            times.base + f"/changes/{earlier.json()['request_id']}",
            headers={**changes.left_headers, "Idempotency-Key": str(uuid7())},
            json={
                "schema_version": 1,
                "kind": "swap",
                "shift_id": mine["shift_id"],
                "expected_shift_revision": mine["revision"],
                "target_profile_id": target,
                "other_shift_id": taken["shift_id"],
                "expected_other_shift_revision": taken["revision"],
            },
        )
        assert probe.status_code == 403, probe.text
        assert probe.json()["error"]["code"] == "COLLEAGUE_SHIFTS_HIDDEN"
    assert _count(owner_conn, tenant, "select count(*) from gba.shift_change_requests") == before
    # A handover and an open-shift request are not swaps and still work.
    handover = await changes.propose("handover", mine)
    assert handover.status_code == 200, handover.text
    vacant = await changes.shift(None, starts_at=at(16).isoformat(), ends_at=at(17).isoformat())
    pickup = await changes.propose("pickup", vacant, target_profile_id=changes.left_profile)
    assert pickup.status_code == 200, pickup.text
    # Shown again: the swap is possible again.
    assert (await _set(times, location, True, 1)).status_code == 200
    free = await changes.shift(
        changes.left_profile, starts_at=at(18).isoformat(), ends_at=at(19).isoformat()
    )
    again = await _swap(times, free, taken)
    assert again.status_code == 200, again.text


async def test_a_swap_sent_while_shown_replays_its_first_answer_after_hiding(
    times: Times,
) -> None:
    changes = times.changes
    location = changes.workforce.world.a.location_id
    mine = await changes.shift(changes.left_profile)
    theirs = await changes.shift(changes.right_profile)
    request, key = str(uuid7()), str(uuid7())

    async def send() -> httpx.Response:
        return await changes.workforce.client.put(
            times.base + f"/changes/{request}",
            headers={**changes.left_headers, "Idempotency-Key": key},
            json={
                "schema_version": 1,
                "kind": "swap",
                "shift_id": mine["shift_id"],
                "expected_shift_revision": mine["revision"],
                "target_profile_id": changes.right_profile,
                "other_shift_id": theirs["shift_id"],
                "expected_other_shift_revision": theirs["revision"],
            },
        )

    first = await send()
    assert first.status_code == 200, first.text
    assert (await _set(times, location, False, 0)).status_code == 200
    replay = await send()
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()


async def test_the_outside_schedule_mark_of_the_time_in_effect_ignores_later_versions(
    times: Times,
) -> None:
    changes = times.changes
    manager = changes.workforce.headers

    async def approved(shift: dict[str, object], start: int, end: int) -> dict[str, object]:
        started = await times.start(
            starts_at=at(start).isoformat(),
            shift_id=shift["shift_id"],
            expected_shift_revision=shift["revision"],
        )
        assert started.status_code == 200, started.text
        closed = await times.command(dict(started.json()), "clock_out", at=at(end).isoformat())
        assert closed.status_code == 200, closed.text
        decided = await times.command(dict(closed.json()), "approve", manager)
        assert decided.status_code == 200, decided.text
        return dict(decided.json())

    async def corrected(entry: dict[str, object], start: int, end: int) -> dict[str, object]:
        response = await times.command(
            entry,
            "correct",
            starts_at=at(start).isoformat(),
            ends_at=at(end).isoformat(),
            breaks=[],
            reason="FAKE correction",
        )
        assert response.status_code == 200, response.text
        return dict(response.json())

    async def declined(entry: dict[str, object]) -> dict[str, object]:
        response = await times.command(entry, "decline", manager, reason="FAKE no proof")
        assert response.status_code == 200, response.text
        return dict(response.json())

    # A: in effect inside the shift; a correction outside it is proposed and declined.
    inside = await changes.shift(
        changes.left_profile, starts_at=at(10).isoformat(), ends_at=at(12).isoformat()
    )
    entry = await approved(inside, 10, 11)
    assert (entry["out_of_schedule"], _effective(entry)["out_of_schedule"]) == (False, False)
    pending = await corrected(entry, 9, 11)
    assert pending["out_of_schedule"] is True
    assert _effective(pending)["out_of_schedule"] is False
    refused = await declined(pending)
    assert _effective(refused)["revision"] == entry["revision"]
    assert _effective(refused)["out_of_schedule"] is False
    # B: in effect outside the shift; a correction inside it is proposed and declined.
    later = await changes.shift(
        changes.left_profile, starts_at=at(15).isoformat(), ends_at=at(17).isoformat()
    )
    early = await approved(later, 14, 16)
    assert _effective(early)["out_of_schedule"] is True
    moved = await corrected(early, 15, 16)
    assert moved["out_of_schedule"] is False
    assert _effective(moved)["out_of_schedule"] is True
    kept = await declined(moved)
    assert _effective(kept)["out_of_schedule"] is True
    # Approving the correction moves the mark with the time that now counts.
    again = await corrected(kept, 15, 16)
    accepted = await times.command(again, "approve", manager)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["effective"]["revision"] == accepted.json()["revision"]
    assert accepted.json()["effective"]["out_of_schedule"] is False
    # Work without a shift is outside the schedule in every version.
    free = await times.start(starts_at=at(19).isoformat())
    done = await times.command(dict(free.json()), "clock_out", at=at(20).isoformat())
    loose = await times.command(dict(done.json()), "approve", manager)
    assert loose.json()["effective"]["out_of_schedule"] is True


async def test_a_long_valid_key_can_be_discarded(
    times: Times, owner_conn: psycopg.Connection
) -> None:
    tenant = times.changes.workforce.world.a.tenant_id
    for length in (200, 201, 255):
        key = "k" * length
        entry = str(uuid7())
        reference: dict[str, object] = {
            "operation": "time.clock_in",
            "subject_id": entry,
            "revision": 1,
        }
        assert (await _outcome(times, "resolve", key, reference)).json()["state"] == "unresolved"
        cancelled = await _outcome(times, "cancel", key, reference)
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "cancelled"
        refused = await times.start(key, entry)
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    with owner_tenant_transaction(owner_conn, tenant):
        targets = [
            row[0]
            for row in owner_conn.execute(
                "select target_id from gba.audit_events "
                "where action='workforce.command_cancelled' order by id"
            )
        ]
    # The audit target is the key itself while it fits, else its digest.
    assert targets[0] == "k" * 200
    assert all(len(target) <= 200 for target in targets)
    assert all(target.startswith("sha256:") for target in targets[1:])
    assert len(set(targets)) == 3


async def test_discarding_has_a_daily_limit_per_person(
    times: Times, owner_conn: psycopg.Connection
) -> None:
    changes = times.changes
    tenant = changes.workforce.world.a.tenant_id

    def reference() -> dict[str, object]:
        return {"operation": "time.clock_in", "subject_id": str(uuid7()), "revision": 1}

    for _ in range(20):
        discarded = await _outcome(times, "cancel", str(uuid7()), reference())
        assert discarded.status_code == 200, discarded.text
        assert discarded.json()["state"] == "cancelled"
    over = await _outcome(times, "cancel", str(uuid7()), reference())
    assert over.status_code == 429, over.text
    assert over.json()["error"]["code"] == "TOO_MANY_DISCARDED_COMMANDS"
    markers = "select count(*) from gba.idempotency_keys where response_status=410"
    assert _count(owner_conn, tenant, markers) == 20
    # Asking for an outcome and repeating an earlier discard are not limited.
    assert (await _outcome(times, "resolve", str(uuid7()), reference())).status_code == 200
    # Another person has their own limit.
    theirs = await _outcome(times, "cancel", str(uuid7()), reference(), changes.right_headers)
    assert theirs.status_code == 200, theirs.text
    # A real command of the limited person still works, and so does its outcome.
    key, entry = str(uuid7()), str(uuid7())
    started = await times.start(key, entry)
    assert started.status_code == 200, started.text
    settled = await _outcome(
        times, "cancel", key, {"operation": "time.clock_in", "subject_id": entry, "revision": 1}
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["state"] == "committed"
    # A day later the earlier discards no longer count.
    with owner_tenant_transaction(owner_conn, tenant):
        owner_conn.execute(
            "update gba.idempotency_keys set created_at=created_at-interval '25 hours' "
            "where response_status=410"
        )
    fresh = await _outcome(times, "cancel", str(uuid7()), reference())
    assert fresh.status_code == 200, fresh.text


async def test_the_directory_skips_a_disabled_account(
    times: Times, owner_conn: psycopg.Connection, manager_a: FakeUser
) -> None:
    changes = times.changes
    world = changes.workforce.world
    gone = _member(owner_conn, world.a.tenant_id, world.a.location_id, "artist")
    listed = await _get(times, "/directory", changes.workforce.headers)
    assert str(gone.user_id) in {item["user_id"] for item in listed.json()["items"]}
    set_user_status(owner_conn, user_id=gone.user_id, status="disabled")
    after = await _get(times, "/directory", changes.workforce.headers)
    assert after.status_code == 200, after.text
    users = {item["user_id"] for item in after.json()["items"]}
    assert str(gone.user_id) not in users
    assert {str(manager_a.user_id), str(changes.workforce.user.user_id)} <= users
