"""I1 workforce contracts and invariants against real PostgreSQL 18."""

from dataclasses import dataclass
from unittest.mock import patch
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.booking.models import ResourceUnavailableError
from gorgona_booking.booking.service import BookingService
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from gorgona_booking.db.workforce_guard import assert_workforce_ready
from gorgona_booking.onboarding import readiness as booking_readiness
from gorgona_booking.onboarding.service import _fingerprint
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


async def test_packaged_workforce_schema_passes_guard(
    app_pool: RuntimePool, world: BookingWorld
) -> None:
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        await assert_workforce_ready(conn)


async def test_workforce_guard_uses_five_real_catalog_round_trips(
    app_pool: RuntimePool,
    world: BookingWorld,
) -> None:
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        with patch.object(conn, "execute", wraps=conn.execute) as recorder:
            await assert_workforce_ready(conn)
            assert recorder.call_count == 5


async def test_unaccepted_workforce_refuses_writes(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    response = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/workforce/skills/{uuid7()}",
        json={"schema_version": 1, "expected_revision": 0, "code": "FAKE", "name": "FAKE"},
        headers={
            **idp.bearer(manager_a.subject, email=manager_a.email),
            "Idempotency-Key": str(uuid7()),
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "MODULE_NOT_READY"


@dataclass(frozen=True)
class Workforce:
    client: httpx.AsyncClient
    world: BookingWorld
    headers: dict[str, str]
    membership: UUID
    user: FakeUser

    @property
    def base(self) -> str:
        return f"/v1/businesses/{self.world.a.tenant_id}/workforce"

    async def put(
        self, path: str, body: dict[str, object], key: str | None = None
    ) -> httpx.Response:
        return await self.client.put(
            self.base + path,
            json={"schema_version": 1, **body},
            headers={**self.headers, "Idempotency-Key": key or str(uuid7())},
        )

    async def profile(self) -> dict[str, object]:
        response = await self.put(
            f"/staff/{uuid7()}",
            {
                "membership_id": str(self.membership),
                "location_id": str(self.world.a.location_id),
            },
        )
        assert response.status_code == 200, response.text
        return dict(response.json())

    def shift(self, **changes: object) -> dict[str, object]:
        return {
            "expected_revision": 0,
            "location_id": str(self.world.a.location_id),
            "position": "FAKE position",
            "starts_at": at(10).isoformat(),
            "ends_at": at(11).isoformat(),
            "status": "published",
            **changes,
        }


@pytest.fixture
async def workforce(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> Workforce:
    current = modules.MODULES_BY_ID["workforce"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "workforce",
        current.model_copy(
            update={
                "enableable": True,
                "readiness": Readiness.TECHNICALLY_VERIFIED,
            }
        ),
    )
    config = Config(client, idp)
    await config.profile(manager_a, world.a.tenant_id, 0, [1])
    await config.publish(manager_a, world.a.tenant_id, 0, ["booking_resources", "workforce"])
    user = seed_user(owner_conn, f"workforce-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=user.user_id,
        role="artist",
        location_id=world.a.location_id,
    )
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s", (user.user_id,)
        ).fetchone()
    assert row is not None
    return Workforce(
        client, world, idp.bearer(manager_a.subject, email=manager_a.email), row[0], user
    )


async def test_profile_shift_and_occupancy_are_atomic_and_idempotent(workforce: Workforce) -> None:
    profile = await workforce.profile()
    shift, key = uuid7(), str(uuid7())
    body = workforce.shift(staff_profile_id=profile["profile_id"])
    created = await workforce.put(f"/shifts/{shift}", body, key)
    assert created.status_code == 200, created.text
    assert created.json()["revision"] == 1
    replay = await workforce.put(f"/shifts/{shift}", body, key)
    assert replay.json() == created.json()
    conflict = await workforce.put(f"/shifts/{uuid7()}", body)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "WORKFORCE_CONFLICT"
    read = await workforce.client.get(f"{workforce.base}/shifts/{shift}", headers=workforce.headers)
    assert read.json() == created.json()


async def test_assignment_rechecks_effective_skills(workforce: Workforce) -> None:
    profile, skill = await workforce.profile(), uuid7()
    response = await workforce.put(
        f"/skills/{skill}", {"expected_revision": 0, "code": "FAKE", "name": "FAKE"}
    )
    assert response.status_code == 200, response.text
    body = workforce.shift(staff_profile_id=profile["profile_id"], required_skill_ids=[str(skill)])
    refused = await workforce.put(f"/shifts/{uuid7()}", body)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "WORKFORCE_SKILL_REQUIRED"
    granted = await workforce.put(
        f"/staff/{profile['profile_id']}/skills/{skill}",
        {
            "expected_revision": 0,
            "effective_at": at(9).isoformat(),
            "granted": True,
        },
    )
    assert granted.status_code == 200, granted.text
    assigned = await workforce.put(f"/shifts/{uuid7()}", body)
    assert assigned.status_code == 200, assigned.text


async def test_staff_resource_is_absent_from_booking_setup_and_fingerprint(
    workforce: Workforce,
    owner_conn: psycopg.Connection,
) -> None:
    tenant = workforce.world.a.tenant_id
    before = _fingerprint(owner_conn, tenant)
    profile = await workforce.profile()
    resource = profile["resource_id"]
    assert _fingerprint(owner_conn, tenant) == before
    base = f"/v1/salons/{tenant}"
    listed = await workforce.client.get(base + "/staff", headers=workforce.headers)
    assert resource not in {r["id"] for r in listed.json()}
    overview = await workforce.client.get(base + "/overview", headers=workforce.headers)
    assert overview.json()["stats"]["active_staff_count"] == 2
    for method, path, body in (
        ("get", f"/staff/{resource}/schedule", None),
        ("put", f"/staff/{resource}/schedule", {"hours": []}),
        ("put", f"/staff/{resource}/services", {"service_ids": []}),
        ("patch", f"/staff/{resource}", {"display_name": "FAKE rename"}),
    ):
        response = await workforce.client.request(
            method, base + path, json=body, headers=workforce.headers
        )
        assert response.status_code == 404, response.text


async def test_staff_resource_does_not_change_booking_readiness(
    workforce: Workforce, owner_conn: psycopg.Connection
) -> None:
    tenant = workforce.world.a.tenant_id
    with owner_tenant_transaction(owner_conn, tenant):
        before = booking_readiness._snapshot(
            owner_conn.execute(booking_readiness._SNAPSHOT).fetchone()
        )
    profile = await workforce.profile()
    assert profile["resource_id"]
    with owner_tenant_transaction(owner_conn, tenant):
        after = booking_readiness._snapshot(
            owner_conn.execute(booking_readiness._SNAPSHOT).fetchone()
        )
    assert before.active_artists == 2
    assert after == before
    assert booking_readiness.evaluate(after) == booking_readiness.evaluate(before)


async def test_staff_resource_refused_by_service_holds_and_reservations(
    workforce: Workforce,
    app_pool: RuntimePool,
) -> None:
    profile = await workforce.profile()
    resource = UUID(str(profile["resource_id"]))
    with pytest.raises(ResourceUnavailableError):
        await BookingService(app_pool).create_confirmed_booking(
            workforce.world.a.tenant_id,
            workforce.world.request(at(10), resource=resource),
            actor="test:workforce",
            idempotency_key=None,
        )
    response = await workforce.client.post(
        "/v1/holds",
        headers={
            "Host": workforce.world.a.host,
            "Idempotency-Key": str(uuid7()),
        },
        json={
            "resource_id": str(resource),
            "variant_id": str(workforce.world.catalog_a.base_variant_id),
            "start_at": at(10).isoformat(),
        },
    )
    assert response.status_code == 422, response.text
    reservation = await workforce.client.put(
        f"/v1/businesses/{workforce.world.a.tenant_id}/resource-reservations/{uuid7()}",
        headers={**workforce.headers, "Idempotency-Key": str(uuid7())},
        json={
            "schema_version": 1,
            "location_id": str(workforce.world.a.location_id),
            "resource_ids": [str(resource)],
            "starts_at": at(10).isoformat(),
            "ends_at": at(11).isoformat(),
        },
    )
    assert reservation.status_code == 422, reservation.text


async def test_revision_history_and_cancellation_release_only_old_allocation(
    workforce: Workforce,
    app_pool: RuntimePool,
) -> None:
    profile, shift = await workforce.profile(), uuid7()
    response = await workforce.put(
        f"/shifts/{shift}", workforce.shift(staff_profile_id=profile["profile_id"])
    )
    assert response.status_code == 200, response.text
    second = await workforce.put(
        f"/shifts/{shift}",
        workforce.shift(
            expected_revision=1,
            starts_at=at(12).isoformat(),
            ends_at=at(13).isoformat(),
            staff_profile_id=profile["profile_id"],
        ),
    )
    assert second.status_code == 200, second.text
    old = await workforce.client.get(
        f"{workforce.base}/shifts/{shift}?revision=1", headers=workforce.headers
    )
    assert old.json() == response.json()
    cancelled = await workforce.put(
        f"/shifts/{shift}", workforce.shift(expected_revision=2, status="cancelled")
    )
    assert cancelled.status_code == 200, cancelled.text
    async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select state from gba.resource_allocations where resource_id=%s",
                (profile["resource_id"],),
            )
        ).fetchall()
    assert [r[0] for r in rows] == ["released", "released"]


async def test_failed_assignment_rolls_back_head_version_audit_and_receipt(
    workforce: Workforce,
    app_pool: RuntimePool,
) -> None:
    profile = await workforce.profile()
    success = await workforce.put(
        f"/shifts/{uuid7()}", workforce.shift(staff_profile_id=profile["profile_id"])
    )
    assert success.status_code == 200
    failed, key = uuid7(), str(uuid7())
    refused = await workforce.put(
        f"/shifts/{failed}", workforce.shift(staff_profile_id=profile["profile_id"]), key
    )
    assert refused.status_code == 409, refused.text
    async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
        for table, column, value in (
            ("work_shifts", "id", failed),
            ("work_shift_versions", "shift_id", failed),
            ("shift_assignments", "shift_id", failed),
            ("audit_events", "target_id", str(failed)),
            ("idempotency_keys", "idempotency_key", key),
        ):
            row = await (
                await conn.execute(f"select count(*) from gba.{table} where {column}=%s", (value,))
            ).fetchone()
            assert row == (0,)


async def test_shift_does_not_block_artist_booking(
    workforce: Workforce, app_pool: RuntimePool
) -> None:
    profile = await workforce.profile()
    response = await workforce.put(
        f"/shifts/{uuid7()}", workforce.shift(staff_profile_id=profile["profile_id"])
    )
    assert response.status_code == 200, response.text
    booked = await BookingService(app_pool).create_confirmed_booking(
        workforce.world.a.tenant_id,
        workforce.world.request(at(10)),
        actor="test:workforce",
        idempotency_key=None,
    )
    assert booked.status == "CONFIRMED"


@pytest.mark.parametrize(("effective", "granted"), [(12, True), (9, False)])
async def test_future_and_revoked_skills_refuse_assignment(
    workforce: Workforce, effective: int, granted: bool
) -> None:
    profile, skill = await workforce.profile(), uuid7()
    assert (
        await workforce.put(
            f"/skills/{skill}", {"expected_revision": 0, "code": "FAKE", "name": "FAKE"}
        )
    ).status_code == 200
    assert (
        await workforce.put(
            f"/staff/{profile['profile_id']}/skills/{skill}",
            {"expected_revision": 0, "effective_at": at(effective).isoformat(), "granted": granted},
        )
    ).status_code == 200
    response = await workforce.put(
        f"/shifts/{uuid7()}",
        workforce.shift(staff_profile_id=profile["profile_id"], required_skill_ids=[str(skill)]),
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "WORKFORCE_SKILL_REQUIRED"


async def test_module_off_history_reads_and_sql_refuses_new_versions(
    workforce: Workforce,
    client: httpx.AsyncClient,
    manager_a: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    shift = uuid7()
    assert (await workforce.put(f"/shifts/{shift}", workforce.shift())).status_code == 200
    await Config(client, idp).publish(
        manager_a, workforce.world.a.tenant_id, 1, ["booking_resources"]
    )
    assert (
        await client.get(f"{workforce.base}/shifts/{shift}", headers=workforce.headers)
    ).status_code == 200
    refused = await workforce.put(f"/shifts/{uuid7()}", workforce.shift())
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "MODULE_DISABLED"
    with pytest.raises(psycopg.DatabaseError) as caught:
        async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.work_shifts (tenant_id,id,location_id) values (%s,%s,%s)",
                (workforce.world.a.tenant_id, uuid7(), workforce.world.a.location_id),
            )
    assert caught.value.sqlstate == "GBM01"


async def test_branch_manager_and_employee_permissions(
    workforce: Workforce,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
) -> None:
    world = workforce.world
    other, _ = seed_other_branch(owner_conn, world.a)
    manager = seed_user(owner_conn, f"scoped-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=manager.user_id,
        role="manager",
        location_id=world.a.location_id,
    )
    profile = await workforce.profile()
    shift = uuid7()
    assert (
        await workforce.put(
            f"/shifts/{shift}",
            workforce.shift(location_id=str(other), staff_profile_id=profile["profile_id"]),
        )
    ).status_code == 200
    scoped = idp.bearer(manager.subject, email=manager.email)
    invisible = await workforce.client.get(f"{workforce.base}/shifts/{shift}", headers=scoped)
    assert invisible.status_code == 404, invisible.text
    refused = await workforce.client.put(
        f"{workforce.base}/shifts/{uuid7()}",
        json=workforce.shift(location_id=str(other)),
        headers={**scoped, "Idempotency-Key": str(uuid7())},
    )
    assert refused.status_code == 403, refused.text
    employee = idp.bearer(workforce.user.subject, email=workforce.user.email)
    assert (
        await workforce.client.get(workforce.base + "/staff", headers=employee)
    ).status_code == 403
    response = await workforce.client.get(
        workforce.base + "/my-shifts",
        headers=employee,
        params={"starts": at(9).isoformat(), "ends": at(14).isoformat()},
    )
    assert response.status_code == 200, response.text
    assert [r["shift_id"] for r in response.json()["items"]] == [str(shift)]


async def test_raw_sql_cannot_create_orphan_shift(
    workforce: Workforce, app_pool: RuntimePool
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, workforce.world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.work_shifts (tenant_id,id,location_id) values (%s,%s,%s)",
                (workforce.world.a.tenant_id, uuid7(), workforce.world.a.location_id),
            )


async def test_revoked_workforce_readiness_refuses_write_and_keeps_history_readable(
    workforce: Workforce,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shift = uuid7()
    assert (await workforce.put(f"/shifts/{shift}", workforce.shift())).status_code == 200
    current = modules.MODULES_BY_ID["workforce"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "workforce",
        current.model_copy(update={"enableable": False, "readiness": Readiness.PLANNED}),
    )
    assert (
        await workforce.client.get(f"{workforce.base}/shifts/{shift}", headers=workforce.headers)
    ).status_code == 200
    refused = await workforce.put(f"/shifts/{uuid7()}", workforce.shift())
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "MODULE_NOT_READY"


async def test_schedule_window_near_max_datetime_does_not_overflow(workforce: Workforce) -> None:
    response = await workforce.client.get(
        workforce.base + "/shifts",
        headers=workforce.headers,
        params={"starts": "9999-12-20T00:00:00Z", "ends": "9999-12-21T00:00:00Z"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
