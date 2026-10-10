"""I2 consents and atomic shift changes against real PostgreSQL."""

from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_workforce as shared
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_workforce import Workforce
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
workforce = shared.workforce


@dataclass(frozen=True)
class Changes:
    workforce: Workforce
    left_profile: str
    right_profile: str
    right_user: FakeUser
    left_headers: dict[str, str]
    right_headers: dict[str, str]
    left_resource: UUID
    right_resource: UUID

    async def propose(self, kind: str, shift: dict[str, object], **extra: object) -> httpx.Response:
        return await self.workforce.client.put(
            self.workforce.base + f"/changes/{uuid7()}",
            headers={**self.left_headers, "Idempotency-Key": str(uuid7())},
            json={
                "schema_version": 1,
                "kind": kind,
                "shift_id": shift["shift_id"],
                "expected_shift_revision": shift["revision"],
                "target_profile_id": self.right_profile,
                **extra,
            },
        )

    async def event(
        self,
        request: dict[str, object],
        action: str,
        headers: dict[str, str] | None = None,
        key: str | None = None,
    ) -> httpx.Response:
        return await self.workforce.client.post(
            self.workforce.base + f"/changes/{request['request_id']}/events",
            headers={**(headers or self.right_headers), "Idempotency-Key": key or str(uuid7())},
            json={"schema_version": 1, "expected_revision": request["revision"], "action": action},
        )

    async def shift(self, profile: str | None, **extra: object) -> dict[str, object]:
        response = await self.workforce.put(
            f"/shifts/{uuid7()}", self.workforce.shift(staff_profile_id=profile, **extra)
        )
        assert response.status_code == 200, response.text
        return dict(response.json())


@pytest.fixture
async def changes(workforce: Workforce, owner_conn: psycopg.Connection, idp: FakeIdp) -> Changes:
    left = await workforce.profile()
    other = seed_user(owner_conn, f"shift-changes-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=workforce.world.a.tenant_id,
        user_id=other.user_id,
        role="artist",
        location_id=workforce.world.a.location_id,
    )
    with owner_tenant_transaction(owner_conn, workforce.world.a.tenant_id):
        row = owner_conn.execute(
            "select id from gba.memberships where user_id=%s", (other.user_id,)
        ).fetchone()
    assert row is not None
    right = await workforce.put(
        f"/staff/{uuid7()}",
        {"membership_id": str(row[0]), "location_id": str(workforce.world.a.location_id)},
    )
    assert right.status_code == 200, right.text
    return Changes(
        workforce,
        str(left["profile_id"]),
        str(right.json()["profile_id"]),
        other,
        idp.bearer(workforce.user.subject, email=workforce.user.email),
        idp.bearer(other.subject, email=other.email),
        UUID(str(left["resource_id"])),
        UUID(str(right.json()["resource_id"])),
    )


@pytest.mark.parametrize("kind", ["handover", "swap", "pickup"])
async def test_change_needs_explicit_consent_and_manager_and_applies_atomically(
    changes: Changes, kind: str, app_pool: RuntimePool
) -> None:
    first = await changes.shift(None if kind == "pickup" else changes.left_profile)
    extra: dict[str, object] = {}
    second = None
    if kind == "swap":
        second = await changes.shift(changes.right_profile)
        extra = {
            "other_shift_id": second["shift_id"],
            "expected_other_shift_revision": second["revision"],
        }
    if kind == "pickup":
        extra = {"target_profile_id": changes.left_profile}
    proposed = await changes.propose(kind, first, **extra)
    assert proposed.status_code == 200, proposed.text
    request = dict(proposed.json())
    assert request["status"] == "proposed"
    premature = await changes.event(request, "approve", changes.workforce.headers)
    assert premature.status_code == 409, premature.text
    consent = changes.left_headers if kind == "pickup" else changes.right_headers
    accepted = await changes.event(request, "accept", consent)
    assert accepted.status_code == 200, accepted.text
    request = dict(accepted.json())
    assert request["status"] == "accepted"
    employee = await changes.event(request, "approve", consent)
    assert employee.status_code == 403, employee.text
    key = str(uuid7())
    approved = await changes.event(request, "approve", changes.workforce.headers, key)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    replay = await changes.event(request, "approve", changes.workforce.headers, key)
    assert replay.json() == approved.json()
    updated = await changes.workforce.client.get(
        changes.workforce.base + f"/shifts/{first['shift_id']}", headers=changes.workforce.headers
    )
    assert updated.json()["revision"] == 2
    assert updated.json()["staff_profile_id"] == (
        changes.left_profile if kind == "pickup" else changes.right_profile
    )
    if second:
        updated_other = await changes.workforce.client.get(
            changes.workforce.base + f"/shifts/{second['shift_id']}",
            headers=changes.workforce.headers,
        )
        assert updated_other.json()["staff_profile_id"] == changes.left_profile
    async with tenant_transaction(app_pool, changes.workforce.world.a.tenant_id) as conn:
        state = await (
            await conn.execute(
                "select count(*) from gba.resource_allocations "
                "where source_kind='shift' and state='confirmed' "
                "and source_id in (select id from gba.shift_assignments where shift_id=any(%s))",
                (
                    [UUID(str(first["shift_id"]))]
                    + ([UUID(str(second["shift_id"]))] if second else []),
                ),
            )
        ).fetchone()
        assert state == (2 if second else 1,)


async def test_one_version_per_shift_per_sql_statement(
    changes: Changes, app_pool: RuntimePool
) -> None:
    first = await changes.shift(changes.left_profile)
    with pytest.raises(psycopg.errors.CheckViolation, match="one version per shift"):
        async with tenant_transaction(app_pool, changes.workforce.world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.work_shift_versions "
                "(tenant_id,shift_id,revision,position,starts_at,ends_at,"
                "required_skill_ids,status,profile_id,created_by) "
                "select v.tenant_id,v.shift_id,v.revision+x.n,v.position,"
                "v.starts_at+x.n*interval '1 hour',v.ends_at+x.n*interval '1 hour',"
                "v.required_skill_ids,v.status,v.profile_id,v.created_by "
                "from gba.work_shift_versions v cross join (values (1),(2)) x(n) "
                "where v.shift_id=%s and v.revision=1 order by x.n",
                (first["shift_id"],),
            )
    current = await changes.workforce.client.get(
        changes.workforce.base + f"/shifts/{first['shift_id']}", headers=changes.workforce.headers
    )
    assert current.json()["revision"] == 1
