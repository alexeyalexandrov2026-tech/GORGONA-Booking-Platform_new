"""Location grants exercised through real authentication, SQL and booking flows."""

from datetime import UTC, datetime
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.auth.permissions import Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.migrate import load_migrations
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from gorgona_booking.tenancy.authorization import authorized_tenant
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.customer_support import customer_day
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


@pytest.fixture
def branch_manager(
    manager_a: FakeUser, world: BookingWorld, owner_conn: psycopg.Connection
) -> FakeUser:
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = %s where user_id = %s",
            (world.a.location_id, manager_a.user_id),
        )
    return manager_a


@pytest.fixture
def other_location(world: BookingWorld, owner_conn: psycopg.Connection) -> tuple[UUID, UUID]:
    return seed_other_branch(owner_conn, world.a)


async def test_location_member_can_open_workspace_without_other_branch(
    client: httpx.AsyncClient,
    branch_manager: FakeUser,
    world: BookingWorld,
    other_location: tuple[UUID, UUID],
    idp: FakeIdp,
) -> None:
    headers = idp.bearer(branch_manager.subject, email=branch_manager.email)
    path = f"/v1/salons/{world.a.tenant_id}"
    staff = await client.get(f"{path}/staff", headers=headers)
    assert staff.status_code == 200, staff.text
    assert {row["location_id"] for row in staff.json()} == {str(world.a.location_id)}
    workspace = await client.get(f"{path}/workspace", headers=headers)
    assert workspace.status_code == 200, workspace.text
    assert [row["id"] for row in workspace.json()["locations"]] == [str(world.a.location_id)]
    assert "embed_origins" not in workspace.json()
    assert "fact_confirmations" not in workspace.json()
    me = await client.get("/v1/me", headers=headers)
    assert me.json()["memberships"][0]["location_id"] == str(world.a.location_id)
    for suffix in ("bookings", "clients", "services", "overview"):
        response = await client.get(f"{path}/{suffix}", headers=headers)
        assert response.status_code == 200, response.text
        assert str(other_location[0]) not in response.text
    for suffix in ("settings", "activity", "members", "readiness"):
        assert (await client.get(f"{path}/{suffix}", headers=headers)).status_code == 403
    assert (
        await client.get(f"/v1/businesses/{world.a.tenant_id}", headers=headers)
    ).status_code == 403


async def _private_booking(
    world: BookingWorld,
    other_location: tuple[UUID, UUID],
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> UUID:
    booking = await BookingService(app_pool).create_confirmed_booking(
        world.a.tenant_id,
        world.request(datetime(2031, 6, 2, 15, tzinfo=UTC), resource=other_location[1]),
        actor="test:private",
        idempotency_key=None,
    )
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "insert into gba.booking_customers "
            "(tenant_id, booking_id, capability_hash, customer_name, email, phone) "
            "values (%s, %s, %s, 'FAKE private client', 'private@example.com', '+15551234567')",
            (world.a.tenant_id, booking.booking_id, uuid7().hex + uuid7().hex),
        )
    return booking.booking_id


def _start(hour: int) -> str:
    return (
        datetime.fromisoformat(f"{customer_day()}T{hour:02d}:00:00")
        .replace(tzinfo=ZoneInfo("America/New_York"))
        .isoformat()
    )


def _payload(world: BookingWorld) -> dict[str, str]:
    return {
        "location_id": str(world.a.location_id),
        "resource_id": str(world.artist_a1),
        "variant_id": str(world.catalog_a.base_variant_id),
        "starts_at": _start(11),
        "customer_name": "FAKE branch guest",
        "customer_email": "branch@example.com",
        "customer_phone": "+15551234568",
    }


async def test_branch_booking_cycle_and_foreign_references(
    client: httpx.AsyncClient,
    branch_manager: FakeUser,
    world: BookingWorld,
    other_location: tuple[UUID, UUID],
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    headers = idp.bearer(branch_manager.subject, email=branch_manager.email)
    path = f"/v1/salons/{world.a.tenant_id}"
    private_id = await _private_booking(world, other_location, app_pool, owner_conn)
    key_headers = {**headers, "Idempotency-Key": str(uuid7())}
    created = await client.post(f"{path}/bookings", headers=key_headers, json=_payload(world))
    assert created.status_code == 201, created.text
    own_id = created.json()["booking_id"]
    replay = await client.post(f"{path}/bookings", headers=key_headers, json=_payload(world))
    assert replay.json() == created.json()
    listed = await client.get(f"{path}/bookings", headers=headers)
    assert [row["booking_id"] for row in listed.json()] == [own_id]
    clients = await client.get(f"{path}/clients", headers=headers)
    assert [row["email"] for row in clients.json()] == ["branch@example.com"]
    history = await client.get(f"{path}/clients/history?email=private@example.com", headers=headers)
    assert history.json() == []
    overview = await client.get(f"{path}/overview", headers=headers)
    assert overview.json()["recent_activity"] == []
    assert "private" not in overview.text
    own_schedule = f"{path}/staff/{world.artist_a1}/schedule"
    hours = [{"weekday": 7, "opens_minute": 600, "closes_minute": 960}]
    schedule = await client.put(own_schedule, headers=headers, json={"hours": hours})
    assert schedule.status_code == 200, schedule.text
    assert (await client.get(own_schedule, headers=headers)).json() == schedule.json()
    services = await client.get(f"{path}/services", headers=headers)
    assigned = await client.put(
        f"{path}/staff/{world.artist_a1}/services",
        headers=headers,
        json={"service_ids": [services.json()[0]["service_id"]]},
    )
    assert assigned.status_code == 200, assigned.text
    # Restore the tested day before the reschedule below.
    assert (
        await client.put(
            own_schedule,
            headers=headers,
            json={
                "hours": [
                    {"weekday": day, "opens_minute": 600, "closes_minute": 960}
                    for day in range(1, 8)
                ]
            },
        )
    ).status_code == 200
    # Guessed IDs of another branch or tenant are invisible for reads and mutations.
    for hidden in (str(private_id), str(uuid7())):
        assert (await client.get(f"{path}/bookings/{hidden}", headers=headers)).status_code == 404
        for action, body in (
            ("cancel", {}),
            ("reschedule", {"new_starts_at": _payload(world)["starts_at"]}),
        ):
            response = await client.post(
                f"{path}/bookings/{hidden}/{action}", headers=headers, json=body
            )
            assert response.status_code == 404, response.text
    for location, resource in (other_location, (world.b.location_id, world.artist_b1)):
        foreign = {**_payload(world), "location_id": str(location), "resource_id": str(resource)}
        assert (
            await client.post(f"{path}/bookings", headers=headers, json=foreign)
        ).status_code == 403
        mixed = {**_payload(world), "resource_id": str(resource)}
        assert (
            await client.post(f"{path}/bookings", headers=headers, json=mixed)
        ).status_code == 404
        selection = {key: foreign[key] for key in ("location_id", "resource_id", "variant_id")}
        availability = await client.post(
            f"{path}/availability", headers=headers, json={**selection, "day": customer_day()}
        )
        assert availability.status_code == 403
        assert (
            await client.get(f"{path}/staff/{resource}/schedule", headers=headers)
        ).status_code == 404
        assert (
            await client.patch(
                f"{path}/staff/{resource}", headers=headers, json={"display_name": "changed"}
            )
        ).status_code == 404
        staff_commands: tuple[tuple[str, dict[str, list[str]]], ...] = (
            ("schedule", {"hours": []}),
            ("services", {"service_ids": []}),
        )
        for suffix, staff_body in staff_commands:
            assert (
                await client.put(
                    f"{path}/staff/{resource}/{suffix}", headers=headers, json=staff_body
                )
            ).status_code == 404
        assert (
            await client.post(
                f"{path}/staff",
                headers=headers,
                json={"location_id": str(location), "display_name": "fake"},
            )
        ).status_code == 403
    moved = await client.post(
        f"{path}/bookings/{own_id}/reschedule",
        headers=headers,
        json={"new_starts_at": _start(13)},
    )
    assert moved.status_code == 200, moved.text
    cancelled = await client.post(
        f"{path}/bookings/{moved.json()['booking_id']}/cancel", headers=headers, json={}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        assert owner_conn.execute(
            "select status from gba.bookings where id = %s", (private_id,)
        ).fetchone() == ("CONFIRMED",)


async def test_location_rls_protects_parent_child_reads_writes_and_pool_reuse(
    client: httpx.AsyncClient,
    branch_manager: FakeUser,
    world: BookingWorld,
    other_location: tuple[UUID, UUID],
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    private_id = await _private_booking(world, other_location, app_pool, owner_conn)
    principal = Principal(branch_manager.user_id, "FAKE branch manager", frozenset())
    async with authorized_tenant(
        app_pool, principal, world.a.tenant_id, Permission.BOOKING_WRITE, allow_location_scope=True
    ) as access:
        for table in ("bookings", "booking_customers", "booking_events", "booking_allocations"):
            rows = await (await access.conn.execute(f"select * from gba.{table}")).fetchall()
            assert rows == []
        assert (
            await (await access.conn.execute("select * from gba.audit_events")).fetchall()
        ) == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with access.conn.transaction():
                await access.conn.execute(
                    "insert into gba.resource_hours "
                    "(tenant_id, resource_id, weekday, opens_minute, closes_minute) "
                    "values (%s, %s, 1, 600, 960)",
                    (world.a.tenant_id, other_location[1]),
                )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with access.conn.transaction():
                await access.conn.execute(
                    "update gba.resources set location_id = %s where id = %s",
                    (other_location[0], world.artist_a1),
                )
        assert (
            await access.conn.execute(
                "delete from gba.resource_hours where resource_id = %s", (other_location[1],)
            )
        ).rowcount == 0
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        assert (await (await conn.execute("select id from gba.bookings")).fetchone()) == (
            private_id,
        )
        assert (await (await conn.execute("select gba.current_location_id()")).fetchone()) == (
            None,
        )


async def test_receipt_cannot_escape_changed_location_grant_and_revoke_is_immediate(
    client: httpx.AsyncClient,
    branch_manager: FakeUser,
    world: BookingWorld,
    other_location: tuple[UUID, UUID],
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    headers = idp.bearer(branch_manager.subject, email=branch_manager.email)
    key_headers = {**headers, "Idempotency-Key": str(uuid7())}
    path = f"/v1/salons/{world.a.tenant_id}"
    payload = _payload(world)
    created = await client.post(f"{path}/bookings", headers=key_headers, json=payload)
    assert created.status_code == 201, created.text
    # Previous releases stored the same receipt without this additive response field.
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.idempotency_keys set response_body = response_body - 'location_timezone' "
            "where idempotency_key = %s",
            (key_headers["Idempotency-Key"],),
        )
    legacy = await client.post(f"{path}/bookings", headers=key_headers, json=payload)
    assert legacy.status_code == 201, legacy.text
    assert legacy.json() == created.json()
    cancel_headers = {**headers, "Idempotency-Key": str(uuid7())}
    cancel_path = f"{path}/bookings/{created.json()['booking_id']}/cancel"
    assert (await client.post(cancel_path, headers=cancel_headers, json={})).status_code == 200
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = %s where user_id = %s",
            (other_location[0], branch_manager.user_id),
        )
    assert (
        await client.post(f"{path}/bookings", headers=key_headers, json=payload)
    ).status_code == 403
    assert (await client.post(cancel_path, headers=cancel_headers, json={})).status_code == 403
    assert (await client.get(f"{path}/bookings", headers=headers)).json() == []
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set status = 'revoked' where user_id = %s",
            (branch_manager.user_id,),
        )
    assert (await client.get(f"{path}/workspace", headers=headers)).status_code == 403


@pytest.mark.parametrize(
    "damage", ["missing_boundary", "missing_policy", "weakened_policy", "weakened_function"]
)
async def test_scoped_work_fails_closed_when_schema_boundary_is_missing(
    client: httpx.AsyncClient,
    branch_manager: FakeUser,
    world: BookingWorld,
    other_location: tuple[UUID, UUID],
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    damage: str,
) -> None:
    headers = idp.bearer(branch_manager.subject, email=branch_manager.email)
    boundary = next(m.sql for m in load_migrations() if m.version == 9).partition(
        "-- A company owner can invite"
    )[0]
    try:
        if damage == "missing_boundary":
            # Operational tables now have the pre-0009 policies: a custom GUC alone
            # must not be accepted as isolation. Restore in finally for later tests.
            owner_conn.execute("drop function gba.current_location_id() cascade")
        elif damage == "weakened_function":
            owner_conn.execute(
                "create or replace function gba.current_location_id() returns uuid "
                "language sql stable parallel safe as $$ select null::uuid $$"
            )
        elif damage == "weakened_policy":
            owner_conn.execute(
                "alter policy resources_location_scope on gba.resources "
                "using (true) with check (true)"
            )
        else:
            owner_conn.execute("drop policy resources_location_scope on gba.resources")
        for suffix in ("staff", "bookings", "workspace", "overview"):
            response = await client.get(f"/v1/salons/{world.a.tenant_id}/{suffix}", headers=headers)
            assert response.status_code == 503, response.text
            assert str(other_location[0]) not in response.text
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        if damage == "missing_boundary":
            owner_conn.execute(boundary.encode("utf-8"))
            for version, marker in (
                (10, "-- Legal-entity branch scope:"),
                (11, "-- Department branch scope:"),
                (12, "-- Delegation branch scope:"),
                (13, "-- Group branch scope:"),
                (14, "-- Company-wide scope:"),
                (15, "-- Counterparty branch scope:"),
                (16, "-- Document branch scope:"),
                (17, "-- Agreement branch scope:"),
                (18, "-- Occupancy branch scope:"),
                (19, "-- Reservation branch scope:"),
                (20, "-- Ledger branch scope:"),
                (21, "-- Invoice branch scope:"),
            ):
                scope = next(m.sql for m in load_migrations() if m.version == version).partition(
                    marker
                )[2]
                owner_conn.execute(scope[scope.index("\n") :].encode("utf-8"))
        elif damage == "weakened_function":
            definition = boundary.partition("create policy locations_location_scope")[0]
            owner_conn.execute(
                definition.replace("create function", "create or replace function", 1).encode(
                    "utf-8"
                )
            )
        else:
            if damage == "weakened_policy":
                owner_conn.execute("drop policy resources_location_scope on gba.resources")
            owner_conn.execute(
                "create policy resources_location_scope on gba.resources "
                "as restrictive to gba_runtime "
                "using (gba.current_location_id() is null "
                "or location_id = gba.current_location_id()) "
                "with check (gba.current_location_id() is null "
                "or location_id = gba.current_location_id())"
            )


async def test_owner_can_issue_immutable_branch_invitation_and_acceptance_keeps_scope(
    client: httpx.AsyncClient,
    world: BookingWorld,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    owner = seed_user(owner_conn, f"branch-owner-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    headers = idp.bearer(owner.subject, email=owner.email)
    path = f"/v1/salons/{world.a.tenant_id}"
    invitee = seed_user(owner_conn, f"branch-invitee-{uuid7()}")
    body = {"email": invitee.email, "role": "manager", "location_id": str(world.a.location_id)}
    invalid = await client.post(
        f"{path}/invitations",
        headers=headers,
        json={**body, "location_id": str(world.b.location_id)},
    )
    assert invalid.status_code == 422
    assert (
        await client.post(f"{path}/invitations", headers=headers, json={**body, "role": "owner"})
    ).status_code == 422
    created = await client.post(f"{path}/invitations", headers=headers, json=body)
    assert created.status_code == 201, created.text
    invite = created.json()
    assert invite["location_id"] == str(world.a.location_id)
    with (
        owner_tenant_transaction(owner_conn, world.a.tenant_id),
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        owner_conn.execute(
            "update gba.invitations set location_id = null where id = %s",
            (invite["invitation_id"],),
        )
    invite_headers = idp.bearer(invitee.subject, email=invitee.email)
    for expected in (201, 200):
        accepted = await client.post(
            "/v1/invitations/accept",
            headers=invite_headers,
            json={"salon_id": str(world.a.tenant_id), "token": invite["token"]},
        )
        assert accepted.status_code == expected, accepted.text
        assert accepted.json()["location_id"] == str(world.a.location_id)
    assert (await client.get(f"{path}/workspace", headers=invite_headers)).status_code == 200
    assert (await client.get(f"{path}/members", headers=invite_headers)).status_code == 403
    assert (
        await client.post(f"{path}/invitations", headers=invite_headers, json=body)
    ).status_code == 403
    members = await client.get(f"{path}/members", headers=headers)
    grant = next(row for row in members.json() if row["user_id"] == str(invitee.user_id))
    assert grant["location_id"] == str(world.a.location_id)


@pytest.mark.parametrize("role", ["artist", "front_desk"])
async def test_branch_scope_does_not_expand_role_permissions(
    client: httpx.AsyncClient,
    branch_manager: FakeUser,
    world: BookingWorld,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    role: str,
) -> None:
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set role = %s where user_id = %s",
            (role, branch_manager.user_id),
        )
    headers = idp.bearer(branch_manager.subject, email=branch_manager.email)
    path = f"/v1/salons/{world.a.tenant_id}"
    assert (await client.get(f"{path}/staff", headers=headers)).status_code == 200
    assert (
        await client.patch(
            f"{path}/staff/{world.artist_a1}", headers=headers, json={"display_name": "fake"}
        )
    ).status_code == 403
    booking = await client.post(f"{path}/bookings", headers=headers, json=_payload(world))
    assert booking.status_code == (403 if role == "artist" else 201), booking.text
