"""Delegation between independent businesses in real PostgreSQL (ADR-0016).

Business A owns the data and grants access; business B serves A and designates its own
employee. Every check below runs through the real API, runtime role and RLS policies.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.auth.permissions import Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.booking.service import BookingService
from gorgona_booking.business.delegation_contracts import DelegationGrantInput
from gorgona_booking.business.delegations import lock_grant, save_grant
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    owner_tenant_transaction,
    set_membership_status,
)
from gorgona_booking.tenancy.authorization import TenantAccessDeniedError, authorized_tenant
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.customer_support import customer_day
from tests.integration.seed import FakeUser, Salon, seed_other_branch, seed_salon, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp

WRITE = ["booking.read", "booking.write", "catalog.read", "staff.read"]
READ = ["booking.read", "catalog.read", "staff.read"]


@dataclass(frozen=True, slots=True)
class Parties:
    owner_a: FakeUser
    owner_b: FakeUser
    delegate: FakeUser
    delegate_membership: UUID


@pytest.fixture
def parties(world: BookingWorld, owner_conn: psycopg.Connection) -> Parties:
    owner_a = seed_user(owner_conn, f"grantor-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner_a.user_id, role="owner")
    owner_b = seed_user(owner_conn, f"serving-owner-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.b.tenant_id, user_id=owner_b.user_id, role="owner")
    delegate = seed_user(owner_conn, f"dispatcher-{uuid7()}")
    membership = add_membership(
        owner_conn, tenant_id=world.b.tenant_id, user_id=delegate.user_id, role="front_desk"
    )
    return Parties(owner_a, owner_b, delegate, membership)


def _headers(idp: FakeIdp, user: FakeUser, *, key: str | None = None) -> dict[str, str]:
    headers = idp.bearer(user.subject, email=user.email)
    return {**headers, "Idempotency-Key": key or str(uuid7())}


def _terms(grantee: UUID, **changes: object) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "expected_revision": 0,
        "grantee_business_id": str(grantee),
        "purpose": "FAKE call-centre bookings",
        "permissions": WRITE,
        "location_id": None,
        "valid_from": (now - timedelta(minutes=5)).isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
        **changes,
    }


def _grant_path(owner: Salon, grant_id: UUID) -> str:
    return f"/v1/businesses/{owner.tenant_id}/delegations/{grant_id}"


def _delegate_path(serving: Salon, grant_id: UUID, membership_id: UUID) -> str:
    return (
        f"/v1/businesses/{serving.tenant_id}/incoming-delegations/{grant_id}"
        f"/delegates/{membership_id}"
    )


async def _grant(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    parties: Parties,
    **changes: object,
) -> UUID:
    grant_id = uuid7()
    response = await client.put(
        _grant_path(world.a, grant_id),
        json=_terms(world.b.tenant_id, **changes),
        headers=_headers(idp, parties.owner_a),
    )
    assert response.status_code == 200, response.text
    return grant_id


async def _designate(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    parties: Parties,
    grant_id: UUID,
    membership_id: UUID | None = None,
) -> httpx.Response:
    return await client.put(
        _delegate_path(world.b, grant_id, membership_id or parties.delegate_membership),
        headers=_headers(idp, parties.owner_b),
    )


async def _delegation(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    parties: Parties,
    **changes: object,
) -> UUID:
    grant_id = await _grant(client, idp, world, parties, **changes)
    designated = await _designate(client, idp, world, parties, grant_id)
    assert designated.status_code == 200, designated.text
    return grant_id


async def _revoke(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    parties: Parties,
    grant_id: UUID,
    expected_revision: int,
) -> httpx.Response:
    return await client.post(
        f"{_grant_path(world.a, grant_id)}/revoke",
        json={"expected_revision": expected_revision},
        headers=_headers(idp, parties.owner_a),
    )


def _start(hour: int) -> str:
    return (
        datetime.fromisoformat(f"{customer_day()}T{hour:02d}:00:00")
        .replace(tzinfo=ZoneInfo("America/New_York"))
        .isoformat()
    )


def _booking(world: BookingWorld, hour: int = 11, **changes: str) -> dict[str, str]:
    return {
        "location_id": str(world.a.location_id),
        "resource_id": str(world.artist_a1),
        "variant_id": str(world.catalog_a.base_variant_id),
        "starts_at": _start(hour),
        "customer_name": "FAKE delegated guest",
        "customer_email": "delegated@example.com",
        "customer_phone": "+15551234569",
        **changes,
    }


def _actor(world: BookingWorld, parties: Parties, grant_id: UUID) -> str:
    return f"delegate:{parties.delegate.user_id}@{world.b.tenant_id}/grant:{grant_id}"


def _principal(user: FakeUser) -> Principal:
    return Principal(user.user_id, "FAKE delegated employee", frozenset())


async def _count(pool: RuntimePool, tenant: UUID, sql: str, *args: object) -> int:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (await conn.execute(sql, args)).fetchone()
    assert row is not None
    return int(row[0])


# --- Owner grant lifecycle ------------------------------------------------------------------


async def test_owner_grant_history_replay_conflicts_and_revocation(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    grant_id = uuid7()
    path = _grant_path(world.a, grant_id)
    key = str(uuid7())
    payload = _terms(world.b.tenant_id, permissions=["staff.read", *WRITE[:3]])
    first = await client.put(path, json=payload, headers=_headers(idp, parties.owner_a, key=key))
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["business_id"] == str(world.a.tenant_id)
    assert body["grantee_business_id"] == str(world.b.tenant_id)
    assert (body["revision"], body["current_revision"]) == (1, 1)
    assert (body["state"], body["effective_state"]) == ("active", "active")
    assert body["permissions"] == WRITE
    assert body["delegates"] == []
    replay = await client.put(path, json=payload, headers=_headers(idp, parties.owner_a, key=key))
    assert replay.json() == body
    reused = await client.put(
        _grant_path(world.a, uuid7()), json=payload, headers=_headers(idp, parties.owner_a, key=key)
    )
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    narrowed = await client.put(
        path,
        json={**payload, "expected_revision": 1, "permissions": READ},
        headers=_headers(idp, parties.owner_a),
    )
    assert narrowed.status_code == 200, narrowed.text
    assert (narrowed.json()["revision"], narrowed.json()["permissions"]) == (2, READ)
    history = await client.get(path, params={"revision": 1}, headers=_headers(idp, parties.owner_a))
    assert history.json()["permissions"] == WRITE
    assert history.json()["current_revision"] == 2
    assert (
        await client.get(path, headers=_headers(idp, parties.owner_a))
    ).json() == narrowed.json()
    missing = await client.get(path, params={"revision": 3}, headers=_headers(idp, parties.owner_a))
    assert missing.status_code == 404

    stale = await client.put(path, json=payload, headers=_headers(idp, parties.owner_a))
    assert stale.status_code == 409
    assert stale.json()["error"]["details"]["revision"] == 2
    moved = await client.put(
        path,
        json={**payload, "expected_revision": 2, "grantee_business_id": str(uuid7())},
        headers=_headers(idp, parties.owner_a),
    )
    assert moved.status_code == 422
    assert moved.json()["error"]["code"] == "INVALID_REFERENCE"

    revoked = await _revoke(client, idp, world, parties, grant_id, 2)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revision"] == 3
    assert (revoked.json()["state"], revoked.json()["effective_state"]) == ("revoked", "revoked")
    assert revoked.json()["permissions"] == READ
    assert (await _revoke(client, idp, world, parties, grant_id, 3)).status_code == 409
    after = await client.put(
        path, json={**payload, "expected_revision": 3}, headers=_headers(idp, parties.owner_a)
    )
    assert after.status_code == 409

    second = await _grant(client, idp, world, parties)
    page = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/delegations",
        params={"limit": 1},
        headers=_headers(idp, parties.owner_a),
    )
    assert [item["grant_id"] for item in page.json()["items"]] == [str(grant_id)]
    assert page.json()["next_cursor"] == str(grant_id)
    rest = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/delegations",
        params={"after": str(grant_id)},
        headers=_headers(idp, parties.owner_a),
    )
    assert [item["grant_id"] for item in rest.json()["items"]] == [str(second)]
    assert rest.json()["next_cursor"] is None

    assert (
        await _count(
            app_pool,
            world.a.tenant_id,
            "select count(*) from gba.audit_events where action = 'delegation_grant.saved'",
        )
        == 3
    )
    assert (
        await _count(
            app_pool,
            world.a.tenant_id,
            "select count(*) from gba.audit_events where action = 'delegation_grant.revoked'",
        )
        == 1
    )
    assert (
        await _count(
            app_pool,
            world.b.tenant_id,
            "select count(*) from gba.audit_events where action like 'delegation_grant.%%'",
        )
        == 0
    )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("self", "A business cannot delegate to itself"),
        ("unknown", "This serving business cannot receive a delegation"),
        ("foreign_location", "Unknown location"),
        ("ended", "The delegation must end in the future"),
    ],
)
async def test_unusable_references_are_rejected_without_a_record(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
    case: str,
    message: str,
) -> None:
    now = datetime.now(UTC)
    payload = {
        "self": _terms(world.a.tenant_id),
        "unknown": _terms(uuid7()),
        "foreign_location": _terms(world.b.tenant_id, location_id=str(world.b.location_id)),
        "ended": _terms(
            world.b.tenant_id,
            valid_from=(now - timedelta(days=2)).isoformat(),
            valid_until=(now - timedelta(days=1)).isoformat(),
        ),
    }[case]
    response = await client.put(
        _grant_path(world.a, uuid7()), json=payload, headers=_headers(idp, parties.owner_a)
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["message"] == message
    for table in ("delegation_grants", "delegation_grant_versions", "idempotency_keys"):
        # Fixed test-only table names, never supplied by a request.
        assert await _count(app_pool, world.a.tenant_id, f"select count(*) from gba.{table}") == 0


async def test_delegation_management_is_owner_only_and_company_bound(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    grant_id = await _grant(client, idp, world, parties)
    outgoing = f"/v1/businesses/{world.a.tenant_id}/delegations"
    incoming = f"/v1/businesses/{world.b.tenant_id}/incoming-delegations"
    manager = seed_user(owner_conn, f"delegation-manager-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=manager.user_id, role="manager")
    scoped_owner = seed_user(owner_conn, f"delegation-scoped-owner-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=scoped_owner.user_id,
        role="owner",
        location_id=world.a.location_id,
    )
    for user, expected in (
        (manager, "PERMISSION_DENIED"),
        (scoped_owner, "PERMISSION_DENIED"),
        (parties.owner_b, "TENANT_ACCESS_DENIED"),
        (parties.delegate, "TENANT_ACCESS_DENIED"),
    ):
        for response in (
            await client.get(outgoing, headers=_headers(idp, user)),
            await client.get(f"{outgoing}/{grant_id}", headers=_headers(idp, user)),
            await client.put(
                f"{outgoing}/{uuid7()}",
                json=_terms(world.b.tenant_id),
                headers=_headers(idp, user),
            ),
            await client.post(
                f"{outgoing}/{grant_id}/revoke",
                json={"expected_revision": 1},
                headers=_headers(idp, user),
            ),
        ):
            assert response.status_code == 403, (user, response.text)
            assert response.json()["error"]["code"] == expected
    serving_manager = seed_user(owner_conn, f"serving-manager-{uuid7()}")
    add_membership(
        owner_conn, tenant_id=world.b.tenant_id, user_id=serving_manager.user_id, role="manager"
    )
    for user in (serving_manager, parties.delegate, parties.owner_a):
        assert (await client.get(incoming, headers=_headers(idp, user))).status_code == 403
        designation = await client.put(
            _delegate_path(world.b, grant_id, parties.delegate_membership),
            headers=_headers(idp, user),
        )
        assert designation.status_code == 403


# --- Serving business designations --------------------------------------------------------


async def test_serving_business_sees_only_its_grants_and_designates_own_members(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    grant_id = await _grant(client, idp, world, parties)
    third = seed_salon(owner_conn, "c")
    owner_c = seed_user(owner_conn, f"third-owner-{uuid7()}")
    add_membership(owner_conn, tenant_id=third.tenant_id, user_id=owner_c.user_id, role="owner")
    other_grant = uuid7()
    elsewhere = await client.put(
        _grant_path(world.a, other_grant),
        json=_terms(third.tenant_id),
        headers=_headers(idp, parties.owner_a),
    )
    assert elsewhere.status_code == 200, elsewhere.text
    third_incoming = await client.get(
        f"/v1/businesses/{third.tenant_id}/incoming-delegations", headers=_headers(idp, owner_c)
    )
    assert [item["grant_id"] for item in third_incoming.json()["items"]] == [str(other_grant)]

    listed = await client.get(
        f"/v1/businesses/{world.b.tenant_id}/incoming-delegations",
        headers=_headers(idp, parties.owner_b),
    )
    assert listed.status_code == 200, listed.text
    [item] = listed.json()["items"]
    assert item["grant_id"] == str(grant_id)
    assert item["grantor_business_id"] == str(world.a.tenant_id)
    assert item["purpose"] == "FAKE call-centre bookings"
    assert item["delegates"] == []

    key = str(uuid7())
    path = _delegate_path(world.b, grant_id, parties.delegate_membership)
    designated = await client.put(path, headers=_headers(idp, parties.owner_b, key=key))
    assert designated.status_code == 200, designated.text
    [delegate] = designated.json()["delegates"]
    assert delegate["user_id"] == str(parties.delegate.user_id)
    assert delegate["display_name"].startswith("FAKE user dispatcher-")
    replay = await client.put(path, headers=_headers(idp, parties.owner_b, key=key))
    assert replay.json() == designated.json()
    again = await client.put(path, headers=_headers(idp, parties.owner_b))
    assert again.status_code == 200
    assert len(again.json()["delegates"]) == 1

    owner_view = await client.get(
        _grant_path(world.a, grant_id), headers=_headers(idp, parties.owner_a)
    )
    [visible] = owner_view.json()["delegates"]
    assert visible["user_id"] == str(parties.delegate.user_id)
    assert "display_name" not in visible

    # Members of other companies and grants addressed elsewhere stay out of reach.
    a_member = add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=seed_user(owner_conn, f"grantor-staff-{uuid7()}").user_id,
        role="artist",
    )
    foreign = await _designate(client, idp, world, parties, grant_id, a_member)
    assert foreign.status_code == 404
    unaddressed = await _designate(client, idp, world, parties, other_grant)
    assert unaddressed.status_code == 404
    suspended = seed_user(owner_conn, f"suspended-dispatcher-{uuid7()}")
    suspended_membership = add_membership(
        owner_conn, tenant_id=world.b.tenant_id, user_id=suspended.user_id, role="artist"
    )
    set_membership_status(
        owner_conn,
        tenant_id=world.b.tenant_id,
        membership_id=suspended_membership,
        status="suspended",
    )
    assert (
        await _designate(client, idp, world, parties, grant_id, suspended_membership)
    ).status_code == 409

    remove_key = str(uuid7())
    removed = await client.delete(path, headers=_headers(idp, parties.owner_b, key=remove_key))
    assert removed.status_code == 200, removed.text
    assert removed.json()["delegates"] == []
    assert (
        await client.delete(path, headers=_headers(idp, parties.owner_b, key=remove_key))
    ).json() == removed.json()
    assert (await client.delete(path, headers=_headers(idp, parties.owner_b))).status_code == 404
    assert (
        await _count(
            app_pool,
            world.b.tenant_id,
            "select count(*) from gba.audit_events where target_type = 'delegation_designation'",
        )
        == 2
    )
    assert (
        await _count(
            app_pool,
            world.a.tenant_id,
            "select count(*) from gba.audit_events where target_type = 'delegation_designation'",
        )
        == 0
    )
    assert (await _revoke(client, idp, world, parties, grant_id, 1)).status_code == 200
    assert (await _designate(client, idp, world, parties, grant_id)).status_code == 409


# --- Delegated work ------------------------------------------------------------------------


async def test_designated_employee_books_for_owner_and_records_stay_with_owner(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    grant_id = await _delegation(client, idp, world, parties)
    headers = idp.bearer(parties.delegate.subject, email=parties.delegate.email)
    me = await client.get("/v1/me", headers=headers)
    [access] = me.json()["delegations"]
    assert access["business_id"] == str(world.a.tenant_id)
    assert access["serving_business_id"] == str(world.b.tenant_id)
    assert access["grant_id"] == str(grant_id)
    assert access["permissions"] == WRITE
    path = f"/v1/salons/{world.a.tenant_id}"
    for suffix in ("workspace", "staff", "services", "bookings", "clients", "overview"):
        response = await client.get(f"{path}/{suffix}", headers=headers)
        assert response.status_code == 200, (suffix, response.text)
    assert (await client.get(f"{path}/overview", headers=headers)).json()["recent_activity"] == []
    selection = {key: _booking(world)[key] for key in ("location_id", "resource_id", "variant_id")}
    slots = await client.post(
        f"{path}/availability", headers=headers, json={**selection, "day": customer_day()}
    )
    assert slots.status_code == 200, slots.text
    created = await client.post(
        f"{path}/bookings",
        headers={**headers, "Idempotency-Key": str(uuid7())},
        json=_booking(world),
    )
    assert created.status_code == 201, created.text
    actor = _actor(world, parties, grant_id)
    assert created.json()["created_by"] == actor
    booking_id = created.json()["booking_id"]
    detail = await client.get(f"{path}/bookings/{booking_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    moved = await client.post(
        f"{path}/bookings/{booking_id}/reschedule",
        headers=headers,
        json={"new_starts_at": _start(13)},
    )
    assert moved.status_code == 200, moved.text
    cancelled = await client.post(
        f"{path}/bookings/{moved.json()['booking_id']}/cancel", headers=headers, json={}
    )
    assert cancelled.json()["status"] == "CANCELLED"

    # Operations outside the grant or outside operational work stay closed.
    for method, url, body in (
        ("get", f"/v1/businesses/{world.a.tenant_id}", None),
        ("get", f"/v1/businesses/{world.a.tenant_id}/legal-entities", None),
        ("get", f"/v1/businesses/{world.a.tenant_id}/delegations", None),
        ("get", f"{path}/members", None),
        ("get", f"{path}/settings", None),
        ("get", f"{path}/activity", None),
        ("get", f"{path}/readiness", None),
        ("post", f"{path}/staff", {"location_id": str(world.a.location_id), "display_name": "x"}),
        ("patch", f"{path}/staff/{world.artist_a1}", {"display_name": "FAKE changed"}),
        ("put", f"{path}/staff/{world.artist_a1}/schedule", {"hours": []}),
    ):
        response = await client.request(method, url, headers=headers, json=body)
        assert response.status_code == 403, (url, response.text)

    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        bookings = await (
            await conn.execute(
                "select tenant_id, created_by, status from gba.bookings order by created_at"
            )
        ).fetchall()
        assert [row[1] for row in bookings] == [actor, actor]
        assert {row[0] for row in bookings} == {world.a.tenant_id}
        events = await (
            await conn.execute("select distinct actor from gba.booking_events")
        ).fetchall()
        assert events == [(actor,)]
        audits = await (
            await conn.execute(
                "select actor, details from gba.audit_events where action = 'delegation.access'"
            )
        ).fetchall()
        assert len(audits) >= 10
        assert {row[0] for row in audits} == {actor}
        assert {row[1]["serving_business_id"] for row in audits} == {str(world.b.tenant_id)}
        assert {row[1]["permission"] for row in audits} == set(WRITE)
        assert {row[1]["revision"] for row in audits} == {1}
    assert await _count(app_pool, world.b.tenant_id, "select count(*) from gba.bookings") == 0
    assert (
        await _count(
            app_pool,
            world.b.tenant_id,
            "select count(*) from gba.audit_events where action = 'delegation.access'",
        )
        == 0
    )
    # The employee's own company access is unchanged.
    own = await client.get(f"/v1/salons/{world.b.tenant_id}/bookings", headers=headers)
    assert own.status_code == 200


async def test_read_only_and_location_limited_grants_hold_their_limits(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    headers = idp.bearer(parties.delegate.subject, email=parties.delegate.email)
    path = f"/v1/salons/{world.a.tenant_id}"
    read_only = await _delegation(client, idp, world, parties, permissions=READ)
    assert (await client.get(f"{path}/bookings", headers=headers)).status_code == 200
    denied = await client.post(f"{path}/bookings", headers=headers, json=_booking(world))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
    assert (await _revoke(client, idp, world, parties, read_only, 1)).status_code == 200

    other_location, other_resource = seed_other_branch(owner_conn, world.a)
    private = await BookingService(app_pool).create_confirmed_booking(
        world.a.tenant_id,
        world.request(datetime(2031, 6, 2, 15, tzinfo=UTC), resource=other_resource),
        actor="test:private",
        idempotency_key=None,
    )
    await _delegation(client, idp, world, parties, location_id=str(world.a.location_id))
    workspace = await client.get(f"{path}/workspace", headers=headers)
    assert [row["id"] for row in workspace.json()["locations"]] == [str(world.a.location_id)]
    staff = await client.get(f"{path}/staff", headers=headers)
    assert {row["location_id"] for row in staff.json()} == {str(world.a.location_id)}
    listed = await client.get(f"{path}/bookings", headers=headers)
    assert str(private.booking_id) not in listed.text
    hidden = await client.get(f"{path}/bookings/{private.booking_id}", headers=headers)
    assert hidden.status_code == 404
    outside = _booking(world, location_id=str(other_location), resource_id=str(other_resource))
    assert (await client.post(f"{path}/bookings", headers=headers, json=outside)).status_code == 403
    inside = await client.post(f"{path}/bookings", headers=headers, json=_booking(world))
    assert inside.status_code == 201, inside.text
    me = await client.get("/v1/me", headers=headers)
    assert [item["location_id"] for item in me.json()["delegations"]] == [str(world.a.location_id)]


# --- Revocation and changes on either side -------------------------------------------------


async def test_revocation_blocks_next_request_replays_and_prepared_commands(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    headers = idp.bearer(parties.delegate.subject, email=parties.delegate.email)
    path = f"/v1/salons/{world.a.tenant_id}"
    grant_id = await _delegation(client, idp, world, parties)
    receipt_key = str(uuid7())
    created = await client.post(
        f"{path}/bookings",
        headers={**headers, "Idempotency-Key": receipt_key},
        json=_booking(world),
    )
    assert created.status_code == 201, created.text
    assert (await _revoke(client, idp, world, parties, grant_id, 1)).status_code == 200

    for response in (
        await client.get(f"{path}/bookings", headers=headers),
        await client.post(
            f"{path}/bookings",
            headers={**headers, "Idempotency-Key": receipt_key},
            json=_booking(world),
        ),
        await client.post(
            f"{path}/bookings",
            headers={**headers, "Idempotency-Key": str(uuid7())},
            json=_booking(world, 14),
        ),
    ):
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"
    assert (await client.get("/v1/me", headers=headers)).json()["delegations"] == []

    # A replacement grant retrieves the earlier receipt instead of booking twice.
    await _delegation(client, idp, world, parties)
    replay = await client.post(
        f"{path}/bookings",
        headers={**headers, "Idempotency-Key": receipt_key},
        json=_booking(world),
    )
    assert replay.status_code == 201, replay.text
    assert replay.json() == created.json()
    assert await _count(app_pool, world.a.tenant_id, "select count(*) from gba.bookings") == 1


async def test_expiry_schedule_designation_and_membership_changes_block_access(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    headers = idp.bearer(parties.delegate.subject, email=parties.delegate.email)
    bookings = f"/v1/salons/{world.a.tenant_id}/bookings"

    async def status() -> tuple[int, str]:
        response = await client.get(bookings, headers=headers)
        code = "" if response.status_code == 200 else response.json()["error"]["code"]
        return response.status_code, code

    grant_id = await _delegation(client, idp, world, parties)
    assert await status() == (200, "")

    remove = _delegate_path(world.b, grant_id, parties.delegate_membership)
    assert (await client.delete(remove, headers=_headers(idp, parties.owner_b))).status_code == 200
    assert await status() == (403, "TENANT_ACCESS_DENIED")
    assert (await _designate(client, idp, world, parties, grant_id)).status_code == 200
    assert await status() == (200, "")

    for membership_status in ("suspended", "active"):
        set_membership_status(
            owner_conn,
            tenant_id=world.b.tenant_id,
            membership_id=parties.delegate_membership,
            status=membership_status,
        )
        expected = (200, "") if membership_status == "active" else (403, "TENANT_ACCESS_DENIED")
        assert await status() == expected

    for salon, code in ((world.b, "TENANT_ACCESS_DENIED"), (world.a, "TENANT_SUSPENDED")):
        with owner_tenant_transaction(owner_conn, salon.tenant_id):
            owner_conn.execute(
                "update gba.tenants set status = 'suspended' where id = %s", (salon.tenant_id,)
            )
        assert await status() == (403, code)
        with owner_tenant_transaction(owner_conn, salon.tenant_id):
            owner_conn.execute(
                "update gba.tenants set status = 'active' where id = %s", (salon.tenant_id,)
            )
        assert await status() == (200, "")

    own_membership = add_membership(
        owner_conn, tenant_id=world.a.tenant_id, user_id=parties.delegate.user_id, role="artist"
    )
    set_membership_status(
        owner_conn, tenant_id=world.a.tenant_id, membership_id=own_membership, status="suspended"
    )
    assert await status() == (403, "TENANT_ACCESS_DENIED")
    assert (await client.get("/v1/me", headers=headers)).json()["delegations"] == []
    set_membership_status(
        owner_conn, tenant_id=world.a.tenant_id, membership_id=own_membership, status="revoked"
    )
    assert await status() == (200, "")

    # An expired current revision, appended owner-side, ends access at once.
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "insert into gba.delegation_grant_versions (tenant_id, grant_id, grantee_business_id, "
            "revision, state, purpose, permissions, valid_from, valid_until, created_by) "
            "select tenant_id, grant_id, grantee_business_id, 2, 'active', purpose, permissions, "
            "now() - interval '2 hours', now() - interval '1 hour', created_by "
            "from gba.delegation_grant_versions where grant_id = %s and revision = 1",
            (grant_id,),
        )
    assert await status() == (403, "TENANT_ACCESS_DENIED")
    expired = await client.get(
        _grant_path(world.a, grant_id), headers=_headers(idp, parties.owner_a)
    )
    assert expired.json()["effective_state"] == "expired"

    scheduled = await _delegation(
        client,
        idp,
        world,
        parties,
        valid_from=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
        valid_until=(datetime.now(UTC) + timedelta(days=2)).isoformat(),
    )
    incoming = await client.get(
        f"/v1/businesses/{world.b.tenant_id}/incoming-delegations",
        headers=_headers(idp, parties.owner_b),
    )
    states = {item["grant_id"]: item["effective_state"] for item in incoming.json()["items"]}
    assert states == {str(grant_id): "expired", str(scheduled): "scheduled"}
    assert await status() == (403, "TENANT_ACCESS_DENIED")

    set_membership_status(
        owner_conn,
        tenant_id=world.b.tenant_id,
        membership_id=parties.delegate_membership,
        status="revoked",
    )
    assert (await client.get("/v1/me", headers=headers)).json()["delegations"] == []


async def test_membership_in_owner_business_takes_precedence(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    await _delegation(client, idp, world, parties)
    add_membership(
        owner_conn, tenant_id=world.a.tenant_id, user_id=parties.delegate.user_id, role="artist"
    )
    headers = idp.bearer(parties.delegate.subject, email=parties.delegate.email)
    path = f"/v1/salons/{world.a.tenant_id}"
    assert (await client.get(f"{path}/bookings", headers=headers)).status_code == 200
    # The artist role, not the broader grant, decides: artists do not create bookings.
    write = await client.post(f"{path}/bookings", headers=headers, json=_booking(world))
    assert write.status_code == 403
    assert write.json()["error"]["code"] == "PERMISSION_DENIED"
    assert (await client.get("/v1/me", headers=headers)).json()["delegations"] == []
    assert (
        await _count(
            app_pool,
            world.a.tenant_id,
            "select count(*) from gba.audit_events where action = 'delegation.access'",
        )
        == 0
    )


@pytest.mark.parametrize("change", ["revoke_grant", "remove_designation", "revoke_membership"])
async def test_changes_wait_for_in_flight_delegated_work_and_apply_next(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
    change: str,
) -> None:
    grant_id = await _delegation(client, idp, world, parties)
    entered, release = asyncio.Event(), asyncio.Event()

    async def delegated_work() -> None:
        async with authorized_tenant(
            app_pool,
            _principal(parties.delegate),
            world.a.tenant_id,
            Permission.BOOKING_READ,
            allow_location_scope=True,
            allow_delegation=True,
        ) as access:
            assert access.via == "delegation"
            entered.set()
            await release.wait()

    async def change_access() -> httpx.Response:
        if change == "revoke_grant":
            return await _revoke(client, idp, world, parties, grant_id, 1)
        if change == "remove_designation":
            return await client.delete(
                _delegate_path(world.b, grant_id, parties.delegate_membership),
                headers=_headers(idp, parties.owner_b),
            )
        return await client.post(
            f"/v1/salons/{world.b.tenant_id}/members/{parties.delegate_membership}/revoke",
            headers=_headers(idp, parties.owner_b),
        )

    work = asyncio.create_task(delegated_work())
    await asyncio.wait_for(entered.wait(), 10)
    changing = asyncio.create_task(change_access())
    await asyncio.sleep(0.5)
    assert not changing.done(), "the change must wait for the in-flight delegated request"
    release.set()
    await asyncio.wait_for(work, 10)
    response = await asyncio.wait_for(changing, 10)
    assert response.status_code == 200, response.text
    with pytest.raises(TenantAccessDeniedError):
        async with authorized_tenant(
            app_pool,
            _principal(parties.delegate),
            world.a.tenant_id,
            Permission.BOOKING_READ,
            allow_location_scope=True,
            allow_delegation=True,
        ):
            pass


@pytest.mark.parametrize("change", ["location", "narrowed", "revoked"])
async def test_revision_committed_during_authorization_is_checked_again(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    change: str,
) -> None:
    grant_id = await _delegation(client, idp, world, parties)
    locked, release = asyncio.Event(), asyncio.Event()

    async def writer() -> None:
        # Holds the grant lock like a concurrent save, then commits a narrower revision.
        async with app_pool.connection() as conn, conn.transaction():
            await conn.execute(
                "select pg_catalog.set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),)
            )
            await lock_grant(conn, world.a.tenant_id, grant_id, shared=False)
            locked.set()
            await release.wait()
            await conn.execute(
                "insert into gba.delegation_grant_versions (tenant_id, grant_id, "
                "grantee_business_id, revision, state, purpose, permissions, location_id, "
                "valid_from, valid_until, created_by) select tenant_id, grant_id, "
                "grantee_business_id, 2, %s, purpose, %s, %s, valid_from, valid_until, "
                "created_by from gba.delegation_grant_versions where grant_id = %s",
                (
                    "revoked" if change == "revoked" else "active",
                    ["catalog.read", "staff.read"] if change == "narrowed" else WRITE,
                    world.a.location_id if change == "location" else None,
                    grant_id,
                ),
            )

    async def delegated() -> None:
        async with authorized_tenant(
            app_pool,
            _principal(parties.delegate),
            world.a.tenant_id,
            Permission.BOOKING_READ,
            allow_delegation=True,
        ):
            pass

    writing = asyncio.create_task(writer())
    await asyncio.wait_for(locked.wait(), 10)
    request = asyncio.create_task(delegated())
    for _ in range(100):
        waiting = owner_conn.execute(
            "select count(*) from pg_catalog.pg_locks where locktype = 'advisory' and not granted"
        ).fetchone()
        if waiting == (1,):
            break
        await asyncio.sleep(0.05)
    assert waiting == (1,), "the delegated request must wait for the grant lock"
    release.set()
    await asyncio.wait_for(writing, 10)
    with pytest.raises(TenantAccessDeniedError):
        await asyncio.wait_for(request, 10)


async def test_handlers_without_review_never_admit_delegated_callers(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    await _delegation(client, idp, world, parties)
    principal = _principal(parties.delegate)
    for permission in (Permission.BOOKING_READ, Permission.BUSINESS_READ, Permission.STAFF_MANAGE):
        with pytest.raises(TenantAccessDeniedError):
            async with authorized_tenant(app_pool, principal, world.a.tenant_id, permission):
                pass
    async with authorized_tenant(
        app_pool,
        principal,
        world.a.tenant_id,
        Permission.BOOKING_READ,
        allow_delegation=True,
    ) as access:
        assert access.role is None
        assert access.location_id is None
        assert access.delegation is not None
        assert access.delegation.permissions == frozenset(Permission(p) for p in WRITE)


# --- Database boundaries ---------------------------------------------------------------------


async def test_delegated_transaction_sees_operational_data_only(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    await _delegation(client, idp, world, parties)
    entity = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/legal-entities/{uuid7()}",
        json={"expected_revision": 0, "code": "MAIN", "legal_name": "FAKE Owner LLC"},
        headers=_headers(idp, parties.owner_a),
    )
    assert entity.status_code == 200, entity.text
    async with authorized_tenant(
        app_pool,
        _principal(parties.delegate),
        world.a.tenant_id,
        Permission.BOOKING_WRITE,
        allow_location_scope=True,
        allow_delegation=True,
    ) as access:
        conn = access.conn
        for table in (
            "memberships",
            "invitations",
            "legal_entities",
            "legal_entity_versions",
            "business_profile_versions",
            "salon_fact_confirmations",
            "tenant_embed_origins",
            "audit_events",
            "delegation_grants",
            "delegation_grant_versions",
            "delegation_designations",
        ):
            # Fixed test-only table names, never supplied by a request.
            rows = await (await conn.execute(f"select * from gba.{table}")).fetchall()
            assert rows == [], table
        users = await (await conn.execute("select id from gba.users")).fetchall()
        assert users == [(parties.delegate.user_id,)]
        policies = await (await conn.execute("select count(*) from gba.salon_policies")).fetchone()
        assert policies == (1,)
        resources = await (await conn.execute("select count(*) from gba.resources")).fetchone()
        assert resources is not None
        assert resources[0] >= 2
        for statement, args in (
            (
                "insert into gba.memberships (tenant_id, user_id, role) values (%s, %s, 'owner')",
                (world.a.tenant_id, parties.delegate.user_id),
            ),
            (
                "insert into gba.audit_events (tenant_id, actor, action, target_type, target_id) "
                "values (%s, 'x', 'x.y', 'x', 'x') returning id",
                (world.a.tenant_id,),
            ),
            (
                "update gba.users set display_name = 'FAKE renamed' where id = %s",
                (parties.delegate.user_id,),
            ),
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute(statement, args)


async def test_cross_tenant_visibility_of_delegation_records_is_minimal(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    grant_id = await _delegation(client, idp, world, parties)
    third = seed_salon(owner_conn, "c")
    elsewhere = uuid7()
    assert (
        await client.put(
            _grant_path(world.a, elsewhere),
            json=_terms(third.tenant_id),
            headers=_headers(idp, parties.owner_a),
        )
    ).status_code == 200

    async def visible(tenant: UUID | None, user: UUID | None, location: UUID | None = None) -> Any:
        async with app_pool.connection() as conn, conn.transaction():
            await conn.execute(
                "select pg_catalog.set_config('gba.tenant_id', %s, true), "
                "pg_catalog.set_config('gba.user_id', %s, true), "
                "pg_catalog.set_config('gba.location_id', %s, true)",
                (str(tenant or ""), str(user or ""), str(location or "")),
            )
            result = []
            for table, column in (
                ("delegation_grants", "id"),
                ("delegation_grant_versions", "grant_id"),
            ):
                rows = await (
                    await conn.execute(f"select distinct {column} from gba.{table}")
                ).fetchall()
                result.append({row[0] for row in rows})
            designations = await (
                await conn.execute("select user_id from gba.delegation_designations")
            ).fetchall()
            tenants = await (await conn.execute("select id from gba.tenants")).fetchall()
            result.extend([{row[0] for row in designations}, {row[0] for row in tenants}])
            return result

    delegate = parties.delegate.user_id
    assert await visible(world.a.tenant_id, None) == [
        {grant_id, elsewhere},
        {grant_id, elsewhere},
        {delegate},
        {world.a.tenant_id},
    ]
    assert await visible(world.b.tenant_id, None) == [
        {grant_id},
        {grant_id},
        {delegate},
        {world.b.tenant_id},
    ]
    assert await visible(third.tenant_id, None) == [
        {elsewhere},
        {elsewhere},
        set(),
        {third.tenant_id},
    ]
    # The designated person alone sees its own records; tenant rows are not widened.
    assert await visible(None, delegate) == [
        {grant_id},
        {grant_id},
        {delegate},
        {world.b.tenant_id},
    ]
    assert await visible(None, parties.owner_b.user_id) == [
        set(),
        set(),
        set(),
        {world.b.tenant_id},
    ]
    assert await visible(world.a.tenant_id, None, world.a.location_id) == [
        set(),
        set(),
        set(),
        {world.a.tenant_id},
    ]


async def test_database_keeps_grants_and_designations_consistent(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    grant_id = await _delegation(client, idp, world, parties)
    owner = parties.owner_a.user_id

    def version(revision: int, **changes: object) -> tuple[str, tuple[object, ...]]:
        values: dict[str, object] = {
            "state": "active",
            "permissions": READ,
            "location_id": None,
            "valid_from": datetime.now(UTC),
            "valid_until": datetime.now(UTC) + timedelta(days=1),
            "grantee": world.b.tenant_id,
            "grant": grant_id,
            **changes,
        }
        return (
            "insert into gba.delegation_grant_versions (tenant_id, grant_id, grantee_business_id, "
            "revision, state, purpose, permissions, location_id, valid_from, valid_until, "
            "created_by) values (%s, %s, %s, %s, %s, 'FAKE', %s, %s, %s, %s, %s)",
            (
                world.a.tenant_id,
                values["grant"],
                values["grantee"],
                revision,
                values["state"],
                values["permissions"],
                values["location_id"],
                values["valid_from"],
                values["valid_until"],
                owner,
            ),
        )

    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        for statement in (
            "update gba.delegation_grants set grantee_business_id = tenant_id where id = %s",
            "delete from gba.delegation_grants where id = %s",
            "update gba.delegation_grant_versions set purpose = 'changed' where grant_id = %s",
            "delete from gba.delegation_grant_versions where grant_id = %s",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(statement, (grant_id,))
        for revision, changes in (
            (3, {}),
            (1, {}),
            (2, {"permissions": ["booking.write"]}),
            (2, {"permissions": ["staff.read", "booking.read"]}),
            (2, {"permissions": ["booking.read", "booking.read"]}),
            (2, {"permissions": ["business.manage"]}),
            (2, {"valid_until": datetime.now(UTC) + timedelta(days=400)}),
        ):
            statement, args = version(revision, **changes)
            with pytest.raises(psycopg.errors.IntegrityError), owner_conn.transaction():
                owner_conn.execute(statement, args)
        statement, args = version(2, location_id=world.b.location_id)
        with pytest.raises(psycopg.errors.ForeignKeyViolation), owner_conn.transaction():
            owner_conn.execute(statement, args)
        statement, args = version(2, grantee=uuid7())
        with pytest.raises(psycopg.errors.ForeignKeyViolation), owner_conn.transaction():
            owner_conn.execute(statement, args)
        owner_conn.execute(*version(2, state="revoked"))
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="revoked"),
            owner_conn.transaction(),
        ):
            owner_conn.execute(*version(3))
        fresh = uuid7()
        owner_conn.execute(
            "insert into gba.delegation_grants (tenant_id, id, grantee_business_id, created_by) "
            "values (%s, %s, %s, %s)",
            (world.a.tenant_id, fresh, world.b.tenant_id, owner),
        )
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="starts active"),
            owner_conn.transaction(),
        ):
            owner_conn.execute(*version(1, state="revoked", grant=fresh))
        with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
            owner_conn.execute(
                "insert into gba.delegation_grants "
                "(tenant_id, id, grantee_business_id, created_by) values (%s, %s, %s, %s)",
                (world.a.tenant_id, uuid7(), world.a.tenant_id, owner),
            )

    third = seed_salon(owner_conn, "c")
    stranger = seed_user(owner_conn, f"third-staff-{uuid7()}")
    stranger_membership = add_membership(
        owner_conn, tenant_id=third.tenant_id, user_id=stranger.user_id, role="artist"
    )
    # A grant addressed to B cannot be designated by C.
    with (
        owner_tenant_transaction(owner_conn, third.tenant_id),
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        owner_conn.transaction(),
    ):
        owner_conn.execute(
            "insert into gba.delegation_designations (tenant_id, grantor_business_id, "
            "grant_id, membership_id, user_id, created_by) values (%s, %s, %s, %s, %s, %s)",
            (
                third.tenant_id,
                world.a.tenant_id,
                grant_id,
                stranger_membership,
                stranger.user_id,
                stranger.user_id,
            ),
        )
    colleague = seed_user(owner_conn, f"serving-colleague-{uuid7()}")
    colleague_membership = add_membership(
        owner_conn, tenant_id=world.b.tenant_id, user_id=colleague.user_id, role="artist"
    )
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        # The stored person must own the membership.
        with pytest.raises(psycopg.errors.ForeignKeyViolation), owner_conn.transaction():
            owner_conn.execute(
                "insert into gba.delegation_designations (tenant_id, grantor_business_id, "
                "grant_id, membership_id, user_id, created_by) values (%s, %s, %s, %s, %s, %s)",
                (
                    world.b.tenant_id,
                    world.a.tenant_id,
                    grant_id,
                    colleague_membership,
                    parties.owner_b.user_id,
                    parties.owner_b.user_id,
                ),
            )
        for statement in (
            "delete from gba.delegation_designations where membership_id = %s",
            "update gba.delegation_designations set user_id = created_by where membership_id = %s",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(statement, (parties.delegate_membership,))
        owner_conn.execute(
            "update gba.delegation_designations set status = 'removed', removed_by = created_by, "
            "removed_at = now() where membership_id = %s",
            (parties.delegate_membership,),
        )
        with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
            owner_conn.execute(
                "update gba.delegation_designations set status = 'active', removed_by = null, "
                "removed_at = null where membership_id = %s",
                (parties.delegate_membership,),
            )


async def test_failed_save_rolls_back_grant_revision_audit_and_receipt(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    grant_id, key = uuid7(), str(uuid7())
    body = DelegationGrantInput.model_validate(_terms(world.b.tenant_id))
    principal = _principal(parties.owner_a)

    async def abort_after_save() -> None:
        async with authorized_tenant(
            app_pool,
            principal,
            world.a.tenant_id,
            Permission.DELEGATION_MANAGE,
            exclusive="delegations",
        ) as access:
            await save_grant(
                access.conn,
                owner_id=world.a.tenant_id,
                grant_id=grant_id,
                user_id=parties.owner_a.user_id,
                actor=principal.actor,
                key=key,
                body=body,
            )
            raise RuntimeError("FAKE abort")

    with pytest.raises(RuntimeError, match="FAKE abort"):
        await abort_after_save()
    for table in ("delegation_grants", "delegation_grant_versions", "idempotency_keys"):
        assert await _count(app_pool, world.a.tenant_id, f"select count(*) from gba.{table}") == 0
    assert (
        await _count(
            app_pool,
            world.a.tenant_id,
            "select count(*) from gba.audit_events where action like 'delegation%%'",
        )
        == 0
    )
    response = await client.put(
        _grant_path(world.a, grant_id),
        json=body.model_dump(mode="json"),
        headers=_headers(idp, parties.owner_a, key=key),
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1


@pytest.mark.parametrize(
    ("damage", "restore"),
    [
        (
            "alter policy delegation_grants_grantee_read on gba.delegation_grants using (true)",
            "alter policy delegation_grants_grantee_read on gba.delegation_grants "
            "using (grantee_business_id = gba.current_tenant_id())",
        ),
        (
            "alter policy memberships_delegation_scope on gba.memberships "
            "using (true) with check (true)",
            "alter policy memberships_delegation_scope on gba.memberships "
            "using (gba.current_delegation_grant_id() is null) "
            "with check (gba.current_delegation_grant_id() is null)",
        ),
        (
            "create policy delegation_open on gba.delegation_designations for select using (true)",
            "drop policy delegation_open on gba.delegation_designations",
        ),
    ],
)
async def test_damaged_delegation_boundary_fails_closed(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: Parties,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    damage: str,
    restore: str,
) -> None:
    await _delegation(client, idp, world, parties)
    headers = idp.bearer(parties.delegate.subject, email=parties.delegate.email)
    path = f"/v1/salons/{world.a.tenant_id}/bookings"
    assert (await client.get(path, headers=headers)).status_code == 200
    try:
        # Privileged damage is confined to the disposable database and restored below.
        owner_conn.execute(damage)
        delegated = await client.get(path, headers=headers)
        assert delegated.status_code == 503, delegated.text
        assert (await client.get("/health/ready")).status_code == 503
        # Business-wide members do not depend on the delegated boundary.
        owner = await client.get(path, headers=idp.bearer(parties.owner_a.subject))
        assert owner.status_code == 200
    finally:
        owner_conn.execute(restore)
    assert (await client.get(path, headers=headers)).status_code == 200
