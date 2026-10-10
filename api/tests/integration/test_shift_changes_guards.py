"""I2 stale data, direct SQL, actor boundaries and complete rollback."""

from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
from tests.integration import test_shift_changes as shared
from tests.integration.booking_support import at
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_shift_changes import Changes
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
changes = shared.changes
workforce = shared.workforce
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


async def skill(changes: Changes, right: bool = True) -> str:
    identifier = str(uuid7())
    created = await changes.workforce.put(
        f"/skills/{identifier}", {"expected_revision": 0, "code": "I2_SKILL", "name": "FAKE skill"}
    )
    assert created.status_code == 200, created.text
    for profile in [changes.left_profile] + ([changes.right_profile] if right else []):
        granted = await changes.workforce.put(
            f"/staff/{profile}/skills/{identifier}",
            {"expected_revision": 0, "effective_at": at(9).isoformat(), "granted": True},
        )
        assert granted.status_code == 200, granted.text
    return identifier


async def accepted(changes: Changes, first: dict[str, object]) -> dict[str, object]:
    proposed = await changes.propose("handover", first)
    assert proposed.status_code == 200, proposed.text
    result = await changes.event(dict(proposed.json()), "accept")
    assert result.status_code == 200, result.text
    return dict(result.json())


async def raw_event(
    pool: RuntimePool,
    changes: Changes,
    request: dict[str, object],
    user: UUID,
    action: str,
    actor: UUID | None = None,
) -> None:
    async with tenant_transaction(pool, changes.workforce.world.a.tenant_id) as conn:
        await set_user_context(conn, user)
        await conn.execute(
            "insert into gba.shift_change_events (tenant_id,request_id,revision,action,created_by) "
            "values (%s,%s,%s,%s,%s)",
            (
                changes.workforce.world.a.tenant_id,
                request["request_id"],
                int(str(request["revision"])) + 1,
                action,
                actor or user,
            ),
        )


@pytest.mark.parametrize("changed", ["shift", "catalogue", "staff_event"])
async def test_approval_refuses_any_changed_expected_fact(
    changes: Changes, changed: str, app_pool: RuntimePool
) -> None:
    identifier = await skill(changes)
    first = await changes.shift(changes.left_profile, required_skill_ids=[identifier])
    request = await accepted(changes, first)
    if changed == "shift":
        mutation = await changes.workforce.put(
            f"/shifts/{first['shift_id']}",
            changes.workforce.shift(
                expected_revision=1,
                staff_profile_id=changes.left_profile,
                required_skill_ids=[identifier],
                position="FAKE changed",
            ),
        )
    elif changed == "catalogue":
        mutation = await changes.workforce.put(
            f"/skills/{identifier}",
            {"expected_revision": 1, "code": "I2_SKILL", "name": "FAKE harmless rename"},
        )
    else:
        mutation = await changes.workforce.put(
            f"/staff/{changes.right_profile}/skills/{identifier}",
            {"expected_revision": 1, "effective_at": at(12).isoformat(), "granted": True},
        )
    assert mutation.status_code == 200, mutation.text
    key = str(uuid7())
    refused = await changes.event(request, "approve", changes.workforce.headers, key)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "WORKFORCE_CONFLICT"
    async with tenant_transaction(app_pool, changes.workforce.world.a.tenant_id) as conn:
        assert (
            await (
                await conn.execute(
                    "select max(revision) from gba.shift_change_events where request_id=%s",
                    (request["request_id"],),
                )
            ).fetchone()
        ) == (2,)
        assert (
            await (
                await conn.execute(
                    "select count(*) from gba.idempotency_keys where idempotency_key=%s", (key,)
                )
            ).fetchone()
        ) == (0,)


@pytest.mark.parametrize("raw_sql", [False, True])
@pytest.mark.parametrize("recipient_skill", ["missing", "future", "revoked"])
async def test_approval_repeats_effective_skill_validation_in_sql(
    changes: Changes,
    app_pool: RuntimePool,
    manager_a: FakeUser,
    raw_sql: bool,
    recipient_skill: str,
) -> None:
    identifier = await skill(changes, right=False)
    if recipient_skill != "missing":
        granted = await changes.workforce.put(
            f"/staff/{changes.right_profile}/skills/{identifier}",
            {
                "expected_revision": 0,
                "effective_at": at(12 if recipient_skill == "future" else 9).isoformat(),
                "granted": recipient_skill == "future",
            },
        )
        assert granted.status_code == 200, granted.text
    first = await changes.shift(changes.left_profile, required_skill_ids=[identifier])
    request = await accepted(changes, first)
    if raw_sql:
        with pytest.raises(psycopg.DatabaseError) as failure:
            await raw_event(app_pool, changes, request, manager_a.user_id, "approve")
        assert failure.value.sqlstate == "GBW02"
    else:
        refused = await changes.event(request, "approve", changes.workforce.headers)
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "WORKFORCE_SKILL_REQUIRED"
    current = await changes.workforce.client.get(
        changes.workforce.base + f"/changes/{request['request_id']}",
        headers=changes.workforce.headers,
    )
    assert current.json()["revision"] == 2
    async with tenant_transaction(app_pool, changes.workforce.world.a.tenant_id) as conn:
        assert (
            await (
                await conn.execute(
                    "select max(revision) from gba.work_shift_versions where shift_id=%s",
                    (first["shift_id"],),
                )
            ).fetchone()
        ) == (1,)
        assert (
            await (
                await conn.execute(
                    "select state from gba.resource_allocations "
                    "where source_kind='shift' and source_id=%s",
                    (first["assignment_id"],),
                )
            ).fetchone()
        ) == ("confirmed",)


async def test_event_replay_returns_original_response_after_later_approval(
    changes: Changes,
) -> None:
    first = await changes.shift(changes.left_profile)
    proposed = await changes.propose("handover", first)
    assert proposed.status_code == 200, proposed.text
    original = dict(proposed.json())
    key = str(uuid7())
    consent = await changes.event(original, "accept", key=key)
    assert consent.status_code == 200, consent.text
    approved = await changes.event(dict(consent.json()), "approve", changes.workforce.headers)
    assert approved.status_code == 200, approved.text
    replay = await changes.event(original, "accept", key=key)
    assert replay.json() == consent.json()
    changed = await changes.event(original, "decline", key=key)
    assert changed.status_code == 422, changed.text
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    history = await changes.workforce.client.get(
        changes.workforce.base + f"/my-changes/{original['request_id']}/history",
        headers=changes.left_headers,
    )
    assert [item["status"] for item in history.json()["items"]] == [
        "proposed",
        "accepted",
        "approved",
    ]


@pytest.mark.parametrize("recipient_role", ["artist", "manager"])
async def test_cross_home_recipient_can_decline_own_request(
    changes: Changes, owner_conn: psycopg.Connection, recipient_role: str
) -> None:
    business = changes.workforce.world.a.tenant_id
    location, _ = seed_other_branch(owner_conn, changes.workforce.world.a)
    with owner_tenant_transaction(owner_conn, business):
        owner_conn.execute(
            "update gba.memberships set role=%s where user_id=%s",
            (recipient_role, changes.right_user.user_id),
        )
    first = await changes.shift(changes.left_profile, location_id=str(location))
    proposed = await changes.propose("handover", first)
    assert proposed.status_code == 200, proposed.text
    declined = await changes.event(dict(proposed.json()), "decline")
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "declined"


async def test_proposer_cannot_forge_the_other_employees_consent(
    changes: Changes, app_pool: RuntimePool
) -> None:
    first = await changes.shift(changes.left_profile)
    proposed = await changes.propose("handover", first)
    assert proposed.status_code == 200, proposed.text
    refused = await changes.event(dict(proposed.json()), "accept", changes.left_headers)
    assert refused.status_code == 403, refused.text
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await raw_event(
            app_pool, changes, dict(proposed.json()), changes.workforce.user.user_id, "accept"
        )


@pytest.mark.parametrize("manager_history", [False, True])
async def test_change_history_exposes_exact_event_actor_and_timestamp(
    changes: Changes, manager_a: FakeUser, manager_history: bool
) -> None:
    first = await changes.shift(changes.left_profile)
    request = await accepted(changes, first)
    approved = await changes.event(request, "approve", changes.workforce.headers)
    assert approved.status_code == 200, approved.text
    route = "changes" if manager_history else "my-changes"
    headers = changes.workforce.headers if manager_history else changes.left_headers
    history = await changes.workforce.client.get(
        changes.workforce.base + f"/{route}/{request['request_id']}/history", headers=headers
    )
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert [item["event_created_by"] for item in items] == [
        str(changes.workforce.user.user_id),
        str(changes.right_user.user_id),
        str(manager_a.user_id),
    ]
    assert all(item["event_created_at"] for item in items)


async def test_conflicting_swap_rolls_back_both_sides_event_audit_and_key(
    changes: Changes, app_pool: RuntimePool
) -> None:
    first = await changes.shift(changes.left_profile)
    second = await changes.shift(
        changes.right_profile, starts_at=at(12).isoformat(), ends_at=at(13).isoformat()
    )
    blocker = await changes.shift(changes.right_profile)
    proposed = await changes.propose(
        "swap", first, other_shift_id=second["shift_id"], expected_other_shift_revision=1
    )
    assert proposed.status_code == 200, proposed.text
    consent = await changes.event(dict(proposed.json()), "accept")
    assert consent.status_code == 200, consent.text
    request, key = dict(consent.json()), str(uuid7())
    refused = await changes.event(request, "approve", changes.workforce.headers, key)
    assert refused.status_code == 409, refused.text
    async with tenant_transaction(app_pool, changes.workforce.world.a.tenant_id) as conn:
        assert (
            await (
                await conn.execute(
                    "select array_agg(revision order by shift_id) "
                    "from gba.work_shift_versions where shift_id=any(%s)",
                    ([first["shift_id"], second["shift_id"]],),
                )
            ).fetchone()
        ) == ([1, 1],)
        assert (
            await (
                await conn.execute(
                    "select max(revision) from gba.shift_change_events where request_id=%s",
                    (request["request_id"],),
                )
            ).fetchone()
        ) == (2,)
        assert (
            await (
                await conn.execute(
                    "select count(*) from gba.audit_events where target_id=%s "
                    "and action='workforce.change.approve'",
                    (request["request_id"],),
                )
            ).fetchone()
        ) == (0,)
        assert (
            await (
                await conn.execute(
                    "select count(*) from gba.idempotency_keys where idempotency_key=%s", (key,)
                )
            ).fetchone()
        ) == (0,)
    cancelled = await changes.workforce.put(
        f"/shifts/{blocker['shift_id']}",
        changes.workforce.shift(expected_revision=1, status="cancelled"),
    )
    assert cancelled.status_code == 200, cancelled.text
    retried = await changes.event(request, "approve", changes.workforce.headers, key)
    assert retried.status_code == 200, retried.text


@pytest.mark.parametrize("action", ["accept", "approve"])
async def test_raw_sql_cannot_forge_recipient_or_manager(
    changes: Changes, app_pool: RuntimePool, manager_a: FakeUser, action: str
) -> None:
    first = await changes.shift(changes.left_profile)
    response = await changes.propose("handover", first)
    request = dict(response.json())
    if action == "approve":
        request = await accepted(changes, first)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await raw_event(
            app_pool, changes, request, changes.workforce.user.user_id, action, manager_a.user_id
        )


@pytest.mark.parametrize(
    "table", ["shift_change_requests", "shift_change_events", "shift_change_skill_snapshots"]
)
async def test_all_change_history_is_immutable_for_owner(
    changes: Changes, owner_conn: psycopg.Connection, table: str
) -> None:
    identifier = await skill(changes)
    first = await changes.shift(changes.left_profile, required_skill_ids=[identifier])
    response = await changes.propose("handover", first)
    assert response.status_code == 200, response.text
    with owner_tenant_transaction(owner_conn, changes.workforce.world.a.tenant_id):
        for operation in (
            f"update gba.{table} set tenant_id=tenant_id",
            f"delete from gba.{table}",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(operation)


async def test_snapshot_cannot_be_appended_to_an_old_request(
    changes: Changes, app_pool: RuntimePool
) -> None:
    identifier = await skill(changes)
    first = await changes.shift(changes.left_profile)
    response = await changes.propose("handover", first)
    assert response.status_code == 200, response.text

    async def append() -> None:
        async with tenant_transaction(app_pool, changes.workforce.world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.shift_change_skill_snapshots "
                "(tenant_id,request_id,profile_id,skill_id,catalogue_revision,staff_revision) "
                "values (%s,%s,%s,%s,1,1)",
                (
                    changes.workforce.world.a.tenant_id,
                    response.json()["request_id"],
                    changes.left_profile,
                    identifier,
                ),
            )

    with pytest.raises(psycopg.errors.CheckViolation, match="proposal construction"):
        await append()


async def test_unrequired_snapshot_cannot_be_forged_in_the_creation_transaction(
    changes: Changes, app_pool: RuntimePool
) -> None:
    identifier = await skill(changes)
    first = await changes.shift(changes.left_profile)
    request = uuid7()
    business = changes.workforce.world.a.tenant_id

    async def forge() -> None:
        async with tenant_transaction(app_pool, business) as conn:
            await set_user_context(conn, changes.workforce.user.user_id)
            await conn.execute(
                "insert into gba.shift_change_requests "
                "(tenant_id,id,kind,shift_id,shift_revision,target_profile_id,proposed_by) "
                "values (%s,%s,'handover',%s,1,%s,%s)",
                (
                    business,
                    request,
                    first["shift_id"],
                    changes.right_profile,
                    changes.workforce.user.user_id,
                ),
            )
            await conn.execute(
                "insert into gba.shift_change_skill_snapshots "
                "(tenant_id,request_id,profile_id,skill_id,catalogue_revision,staff_revision) "
                "values (%s,%s,%s,%s,1,1)",
                (business, request, changes.left_profile, identifier),
            )

    with pytest.raises(psycopg.errors.CheckViolation, match="proposal construction"):
        await forge()
    async with tenant_transaction(app_pool, business) as conn:
        assert (
            await (
                await conn.execute(
                    "select count(*) from gba.shift_change_requests where id=%s", (request,)
                )
            ).fetchone()
        ) == (0,)


async def test_only_participants_can_read_self_request_or_history_and_home_directory(
    changes: Changes, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    first = await changes.shift(changes.left_profile)
    response = await changes.propose("handover", first)
    assert response.status_code == 200, response.text
    stranger = seed_user(owner_conn, f"i2-stranger-{uuid7()}")
    other, _ = seed_other_branch(owner_conn, changes.workforce.world.a)
    add_membership(
        owner_conn,
        tenant_id=changes.workforce.world.a.tenant_id,
        user_id=stranger.user_id,
        role="artist",
        location_id=other,
    )
    bearer = idp.bearer(stranger.subject, email=stranger.email)
    for suffix in ("", "/history"):
        denied = await changes.workforce.client.get(
            changes.workforce.base + f"/my-changes/{response.json()['request_id']}" + suffix,
            headers=bearer,
        )
        assert denied.status_code == 404, denied.text
    listed = await changes.workforce.client.get(
        changes.workforce.base + "/my-changes", headers=bearer
    )
    assert listed.json()["items"] == []
    directory = await changes.workforce.client.get(
        changes.workforce.base + "/colleagues", headers=changes.left_headers
    )
    assert {row["profile_id"] for row in directory.json()["items"]} == {
        changes.left_profile,
        changes.right_profile,
    }


@pytest.mark.parametrize("gate", ["module", "readiness"])
async def test_disabled_workforce_refuses_changes_but_preserves_history(
    changes: Changes,
    manager_a: FakeUser,
    idp: FakeIdp,
    monkeypatch: pytest.MonkeyPatch,
    app_pool: RuntimePool,
    gate: str,
) -> None:
    first = await changes.shift(changes.left_profile)
    response = await changes.propose("handover", first)
    assert response.status_code == 200, response.text
    if gate == "module":
        await Config(changes.workforce.client, idp).publish(
            manager_a, changes.workforce.world.a.tenant_id, 1, ["booking_resources"]
        )
    else:
        current = modules.MODULES_BY_ID["workforce"]
        monkeypatch.setitem(
            modules.MODULES_BY_ID,
            "workforce",
            current.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
        )
    denied = await changes.event(dict(response.json()), "accept")
    assert denied.status_code == 409, denied.text
    history = await changes.workforce.client.get(
        changes.workforce.base + f"/my-changes/{response.json()['request_id']}",
        headers=changes.left_headers,
    )
    assert history.status_code == 200, history.text
    if gate == "module":
        with pytest.raises(psycopg.DatabaseError) as failure:
            await raw_event(
                app_pool, changes, dict(response.json()), changes.right_user.user_id, "accept"
            )
        assert failure.value.sqlstate == "GBM01"


@pytest.mark.parametrize("recipient_role", ["artist", "manager"])
async def test_own_cross_home_consent_and_company_wide_approval(
    changes: Changes, owner_conn: psycopg.Connection, idp: FakeIdp, recipient_role: str
) -> None:
    business = changes.workforce.world.a.tenant_id
    location, _ = seed_other_branch(owner_conn, changes.workforce.world.a)
    with owner_tenant_transaction(owner_conn, business):
        owner_conn.execute(
            "update gba.memberships set role=%s where user_id=%s",
            (recipient_role, changes.right_user.user_id),
        )
    first = await changes.shift(changes.left_profile, location_id=str(location))
    proposed = await changes.propose("handover", first)
    assert proposed.status_code == 200, proposed.text
    consent = await changes.event(dict(proposed.json()), "accept")
    assert consent.status_code == 200, consent.text
    local = seed_user(owner_conn, f"i2-local-manager-{uuid7()}")
    add_membership(
        owner_conn, tenant_id=business, user_id=local.user_id, role="manager", location_id=location
    )
    denied = await changes.event(
        dict(consent.json()), "approve", idp.bearer(local.subject, email=local.email)
    )
    assert denied.status_code == 403, denied.text
    unchanged = await changes.workforce.client.get(
        changes.workforce.base + f"/shifts/{first['shift_id']}", headers=changes.workforce.headers
    )
    assert unchanged.json()["revision"] == 1
    approved = await changes.event(dict(consent.json()), "approve", changes.workforce.headers)
    assert approved.status_code == 200, approved.text


async def test_open_shifts_and_directory_use_home_and_active_memberships(
    changes: Changes, owner_conn: psycopg.Connection
) -> None:
    business = changes.workforce.world.a.tenant_id
    other, _ = seed_other_branch(owner_conn, changes.workforce.world.a)
    outsider = seed_user(owner_conn, f"i2-other-home-{uuid7()}")
    add_membership(
        owner_conn, tenant_id=business, user_id=outsider.user_id, role="artist", location_id=other
    )
    with owner_tenant_transaction(owner_conn, business):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s", (outsider.user_id,)
        ).fetchone()
    assert row is not None
    foreign_profile = await changes.workforce.put(
        f"/staff/{uuid7()}", {"membership_id": str(row[0]), "location_id": str(other)}
    )
    assert foreign_profile.status_code == 200, foreign_profile.text
    open_shift = await changes.shift(None)
    await changes.shift(None, location_id=str(other))
    await changes.shift(None, status="draft")
    cancelled_shift = await changes.shift(None)
    cancelled = await changes.workforce.put(
        f"/shifts/{cancelled_shift['shift_id']}",
        changes.workforce.shift(expected_revision=1, status="cancelled"),
    )
    assert cancelled.status_code == 200, cancelled.text
    await changes.shift(changes.left_profile)
    listed = await changes.workforce.client.get(
        changes.workforce.base + "/open-shifts",
        headers=changes.left_headers,
        params={"starts": at(9).isoformat(), "ends": at(12).isoformat()},
    )
    assert listed.status_code == 200, listed.text
    assert [item["shift_id"] for item in listed.json()["items"]] == [open_shift["shift_id"]]
    with owner_tenant_transaction(owner_conn, business):
        owner_conn.execute(
            "update gba.memberships set status='revoked' where user_id=%s",
            (changes.right_user.user_id,),
        )
    add_membership(
        owner_conn,
        tenant_id=business,
        user_id=changes.right_user.user_id,
        role="artist",
        location_id=changes.workforce.world.a.location_id,
    )
    with owner_tenant_transaction(owner_conn, business):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s and status='active'",
            (changes.right_user.user_id,),
        ).fetchone()
    assert row is not None
    replacement = await changes.workforce.put(
        f"/staff/{uuid7()}",
        {"membership_id": str(row[0]), "location_id": str(changes.workforce.world.a.location_id)},
    )
    assert replacement.status_code == 200, replacement.text
    directory = await changes.workforce.client.get(
        changes.workforce.base + "/colleagues", headers=changes.left_headers
    )
    assert directory.status_code == 200, directory.text
    assert {item["profile_id"] for item in directory.json()["items"]} == {
        changes.left_profile,
        replacement.json()["profile_id"],
    }
    assert all(
        set(item) == {"schema_version", "profile_id", "display_name"}
        for item in directory.json()["items"]
    )


async def test_pickup_manager_needs_another_manager_approval(
    changes: Changes, owner_conn: psycopg.Connection, app_pool: RuntimePool
) -> None:
    with owner_tenant_transaction(owner_conn, changes.workforce.world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set role='manager' where user_id=%s",
            (changes.workforce.user.user_id,),
        )
    first = await changes.shift(None)
    proposed = await changes.propose("pickup", first, target_profile_id=changes.left_profile)
    assert proposed.status_code == 200, proposed.text
    consent = await changes.event(dict(proposed.json()), "accept", changes.left_headers)
    assert consent.status_code == 200, consent.text
    request = dict(consent.json())
    refused = await changes.event(request, "approve", changes.left_headers)
    assert refused.status_code == 403, refused.text
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await raw_event(app_pool, changes, request, changes.workforce.user.user_id, "approve")
    approved = await changes.event(request, "approve", changes.workforce.headers)
    assert approved.status_code == 200, approved.text


async def test_proposal_replay_returns_its_original_event_after_approval(changes: Changes) -> None:
    first = await changes.shift(changes.left_profile)
    identifier, key = uuid7(), str(uuid7())
    body = {
        "schema_version": 1,
        "kind": "handover",
        "shift_id": first["shift_id"],
        "expected_shift_revision": 1,
        "target_profile_id": changes.right_profile,
    }
    url = changes.workforce.base + f"/changes/{identifier}"
    headers = {**changes.left_headers, "Idempotency-Key": key}
    proposed = await changes.workforce.client.put(url, headers=headers, json=body)
    assert proposed.status_code == 200, proposed.text
    consent = await changes.event(dict(proposed.json()), "accept")
    approved = await changes.event(dict(consent.json()), "approve", changes.workforce.headers)
    assert approved.status_code == 200, approved.text
    replay = await changes.workforce.client.put(url, headers=headers, json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json() == proposed.json()
    refused = await changes.workforce.client.put(
        url, headers=headers, json={**body, "kind": "pickup"}
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_manager_decline_probe_restores_scope_for_nonparticipant(
    changes: Changes, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    business = changes.workforce.world.a.tenant_id
    other, _ = seed_other_branch(owner_conn, changes.workforce.world.a)
    local = seed_user(owner_conn, f"i2-decline-manager-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=business,
        user_id=local.user_id,
        role="manager",
        location_id=changes.workforce.world.a.location_id,
    )
    first = await changes.shift(changes.left_profile, location_id=str(other))
    proposed = await changes.propose("handover", first)
    assert proposed.status_code == 200, proposed.text
    refused = await changes.event(
        dict(proposed.json()), "decline", idp.bearer(local.subject, email=local.email)
    )
    assert refused.status_code == 404, refused.text
    current = await changes.workforce.client.get(
        changes.workforce.base + f"/my-changes/{proposed.json()['request_id']}",
        headers=changes.left_headers,
    )
    assert current.json()["revision"] == 1


@pytest.mark.parametrize("action", ["decline", "withdraw"])
async def test_terminal_changes_cannot_apply_or_transition(changes: Changes, action: str) -> None:
    first = await changes.shift(changes.left_profile)
    request = await accepted(changes, first)
    headers = changes.left_headers if action == "withdraw" else changes.right_headers
    terminal = await changes.event(request, action, headers)
    assert terminal.status_code == 200, terminal.text
    refused = await changes.event(dict(terminal.json()), "approve", changes.workforce.headers)
    assert refused.status_code == 409, refused.text
    current = await changes.workforce.client.get(
        changes.workforce.base + f"/shifts/{first['shift_id']}", headers=changes.workforce.headers
    )
    assert current.json()["revision"] == 1


async def test_new_profile_of_same_user_is_not_a_second_employee(
    changes: Changes, owner_conn: psycopg.Connection
) -> None:
    first = await changes.shift(changes.left_profile)
    business = changes.workforce.world.a.tenant_id
    with owner_tenant_transaction(owner_conn, business):
        owner_conn.execute(
            "update gba.memberships set status='revoked' where id=%s",
            (changes.workforce.membership,),
        )
    add_membership(
        owner_conn,
        tenant_id=business,
        user_id=changes.workforce.user.user_id,
        role="artist",
        location_id=changes.workforce.world.a.location_id,
    )
    with owner_tenant_transaction(owner_conn, business):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s and status='active'",
            (changes.workforce.user.user_id,),
        ).fetchone()
    assert row is not None
    replacement = await changes.workforce.put(
        f"/staff/{uuid7()}",
        {"membership_id": str(row[0]), "location_id": str(changes.workforce.world.a.location_id)},
    )
    assert replacement.status_code == 200, replacement.text
    refused = await changes.propose(
        "handover", first, target_profile_id=replacement.json()["profile_id"]
    )
    assert refused.status_code == 403, refused.text


async def test_foreign_company_and_platform_support_cannot_use_change_routes(
    changes: Changes, owner_conn: psycopg.Connection, idp: FakeIdp
) -> None:
    first = await changes.shift(changes.left_profile)
    request = await accepted(changes, first)
    foreign = seed_user(owner_conn, f"i2-foreign-{uuid7()}")
    support = seed_user(owner_conn, f"i2-support-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=changes.workforce.world.b.tenant_id,
        user_id=foreign.user_id,
        role="owner",
    )
    grant_platform_admin(owner_conn, user_id=support.user_id, granted_by="test:i2")
    for user in (foreign, support):
        headers = idp.bearer(user.subject, email=user.email)
        for suffix in (
            "/changes",
            "/my-changes",
            "/colleagues",
            f"/changes/{request['request_id']}/history",
            f"/my-changes/{request['request_id']}/history",
        ):
            refused = await changes.workforce.client.get(
                changes.workforce.base + suffix, headers=headers
            )
            assert refused.status_code == 403, refused.text
        refused = await changes.event(request, "approve", headers)
        assert refused.status_code == 403, refused.text


@pytest.mark.parametrize("raw_sql", [False, True])
async def test_self_pickup_cannot_discover_an_open_shift_outside_home(
    changes: Changes, app_pool: RuntimePool, owner_conn: psycopg.Connection, raw_sql: bool
) -> None:
    business = changes.workforce.world.a.tenant_id
    other, _ = seed_other_branch(owner_conn, changes.workforce.world.a)
    first = await changes.shift(None, location_id=str(other))
    identifier, key = uuid7(), str(uuid7())

    async def propose_raw() -> None:
        async with tenant_transaction(app_pool, business) as conn:
            await set_user_context(conn, changes.workforce.user.user_id)
            await conn.execute(
                "insert into gba.shift_change_requests "
                "(tenant_id,id,kind,shift_id,shift_revision,target_profile_id,proposed_by) "
                "values (%s,%s,'pickup',%s,1,%s,%s)",
                (
                    business,
                    identifier,
                    first["shift_id"],
                    changes.left_profile,
                    changes.workforce.user.user_id,
                ),
            )

    if raw_sql:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await propose_raw()
    else:
        refused = await changes.workforce.client.put(
            changes.workforce.base + f"/changes/{identifier}",
            headers={**changes.left_headers, "Idempotency-Key": key},
            json={
                "schema_version": 1,
                "kind": "pickup",
                "shift_id": first["shift_id"],
                "expected_shift_revision": 1,
                "target_profile_id": changes.left_profile,
            },
        )
        assert refused.status_code == 403, refused.text
    async with tenant_transaction(app_pool, business) as conn:
        for table, column in (
            ("shift_change_requests", "id"),
            ("shift_change_events", "request_id"),
            ("shift_change_skill_snapshots", "request_id"),
        ):
            assert (
                await (
                    await conn.execute(
                        f"select count(*) from gba.{table} where {column}=%s", (identifier,)
                    )
                ).fetchone()
            ) == (0,)
        assert (
            await (
                await conn.execute(
                    "select count(*) from gba.idempotency_keys where idempotency_key=%s", (key,)
                )
            ).fetchone()
        ) == (0,)


@pytest.mark.parametrize("status", ["published", "cancelled"])
async def test_raw_branch_sql_cannot_leave_a_hidden_prior_allocation_active(
    changes: Changes, app_pool: RuntimePool, owner_conn: psycopg.Connection, status: str
) -> None:
    business = changes.workforce.world.a.tenant_id
    other, _ = seed_other_branch(owner_conn, changes.workforce.world.a)
    first = await changes.shift(changes.left_profile, location_id=str(other))

    async def change_raw() -> None:
        async with tenant_transaction(app_pool, business) as conn:
            await conn.execute("select set_config('gba.location_id',%s,true)", (str(other),))
            await conn.execute(
                "insert into gba.work_shift_versions "
                "(tenant_id,shift_id,revision,position,starts_at,ends_at,required_skill_ids,"
                "status,profile_id,created_by) "
                "select tenant_id,shift_id,2,position,starts_at,ends_at,required_skill_ids,"
                "%s,null,created_by from gba.work_shift_versions where shift_id=%s and revision=1",
                (status, first["shift_id"]),
            )

    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="prior assignment"):
        await change_raw()
    async with tenant_transaction(app_pool, business) as conn:
        assert (
            await (
                await conn.execute(
                    "select max(revision) from gba.work_shift_versions where shift_id=%s",
                    (first["shift_id"],),
                )
            ).fetchone()
        ) == (1,)
        assert (
            await (
                await conn.execute(
                    "select state from gba.resource_allocations "
                    "where source_kind='shift' and source_id=%s",
                    (first["assignment_id"],),
                )
            ).fetchone()
        ) == ("confirmed",)
