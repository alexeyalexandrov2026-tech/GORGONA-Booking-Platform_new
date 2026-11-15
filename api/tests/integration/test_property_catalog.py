"""PROPERTY-01 internal catalog and authorization (synthetic data)."""

import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = ["client", "idp", "manager_a", "manager_b"]


@dataclass(frozen=True)
class Catalog:
    client: httpx.AsyncClient
    world: BookingWorld
    idp: FakeIdp
    owner_conn: psycopg.Connection
    headers: dict[str, str]

    @property
    def tenant(self) -> UUID:
        return self.world.a.tenant_id

    @property
    def base(self) -> str:
        return f"/v1/businesses/{self.tenant}/property/objects"

    def body(self, kind: str = "parcel", **fields: object) -> dict[str, object]:
        return {
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(self.world.a.location_id),
            "kind": kind,
            "name": "FAKE property",
            **fields,
        }

    async def put(
        self,
        object_id: UUID,
        body: dict[str, object],
        *,
        headers: dict[str, str] | None = None,
        key: str | None = None,
    ) -> httpx.Response:
        return await self.client.put(
            f"{self.base}/{object_id}",
            json=body,
            headers={**(headers or self.headers), "Idempotency-Key": key or str(uuid7())},
        )

    def member(self, role: str, location: UUID | None) -> dict[str, str]:
        user = seed_user(self.owner_conn, f"property-{role}-{uuid7()}")
        add_membership(
            self.owner_conn,
            tenant_id=self.tenant,
            user_id=user.user_id,
            role=role,
            location_id=location,
        )
        return self.idp.bearer(user.subject, email=user.email)

    async def counterparty(self) -> str:
        party_id = str(uuid7())
        res = await self.client.put(
            f"/v1/businesses/{self.tenant}/counterparties/{party_id}",
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "kind": "organization",
                "display_name": "FAKE owner or manager",
                "roles": ["partner"],
            },
            headers={**self.headers, "Idempotency-Key": str(uuid7())},
        )
        assert res.is_success, res.text
        return party_id


@pytest.fixture
def catalog(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> Catalog:
    return Catalog(
        client, world, idp, owner_conn, idp.bearer(manager_a.subject, email=manager_a.email)
    )


@pytest.fixture
async def enabled(
    catalog: Catalog, manager_a: FakeUser, monkeypatch: pytest.MonkeyPatch
) -> Catalog:
    current = modules.MODULES_BY_ID.get("property")
    if current is not None:
        monkeypatch.setitem(
            modules.MODULES_BY_ID,
            "property",
            current.model_copy(
                update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
            ),
        )
    config = Config(catalog.client, catalog.idp)
    await config.profile(manager_a, catalog.tenant, 0, [22])
    requested = ["booking_resources", "counterparties"]
    if current is not None:
        requested.append("property")
    await config.publish(manager_a, catalog.tenant, 0, requested)
    return catalog


async def test_unaccepted_module_refuses_writes(catalog: Catalog) -> None:
    response = await catalog.put(uuid7(), catalog.body())
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "MODULE_NOT_READY"


async def test_catalog_enforces_hierarchy_company_and_location(enabled: Catalog) -> None:
    parcel, building, unit = uuid7(), uuid7(), uuid7()
    saved = await enabled.put(parcel, enabled.body())
    assert saved.status_code == 200, saved.text

    saved = await enabled.put(building, enabled.body("building", parent_id=str(parcel)))
    assert saved.status_code == 200, saved.text
    response = await enabled.put(unit, enabled.body("unit", parent_id=str(parcel)))
    assert response.status_code == 422, response.text
    response = await enabled.put(unit, enabled.body("unit", parent_id=str(building)))
    assert response.status_code == 200, response.text
    other, _ = seed_other_branch(enabled.owner_conn, enabled.world.a)
    response = await enabled.put(
        uuid7(), enabled.body("unit", parent_id=str(building), location_id=str(other))
    )
    assert response.status_code == 422, response.text
    response = await enabled.put(
        uuid7(), enabled.body(location_id=str(enabled.world.b.location_id))
    )
    assert response.status_code == 422, response.text


async def test_versions_keep_owner_manager_and_replay_history(enabled: Catalog) -> None:
    owner, manager, replacement = [await enabled.counterparty() for _ in range(3)]
    object_id = uuid7()
    body = enabled.body(owner_id=owner, manager_id=manager)
    first = await enabled.put(object_id, body, key="first-catalog-command")
    assert first.status_code == 200, first.text
    changed = await enabled.put(
        object_id, enabled.body(expected_revision=1, owner_id=replacement, manager_id=manager)
    )
    assert changed.status_code == 200, changed.text
    replay = await enabled.put(object_id, body, key="first-catalog-command")
    assert replay.json() == first.json()
    history = await enabled.client.get(
        f"{enabled.base}/{object_id}/history", headers=enabled.headers
    )
    assert history.is_success, history.text
    assert [(r["owner_id"], r["manager_id"]) for r in history.json()["items"]] == [
        (owner, manager),
        (replacement, manager),
    ]
    stale = await enabled.put(object_id, body)
    assert stale.status_code == 409, stale.text
    foreign_party = await enabled.put(uuid7(), enabled.body(owner_id=str(uuid7())))
    assert foreign_party.status_code == 422, foreign_party.text


async def test_branch_reads_its_catalog_only_and_cannot_read_history_or_write(
    enabled: Catalog, manager_b: FakeUser, app_pool: RuntimePool
) -> None:
    other, _ = seed_other_branch(enabled.owner_conn, enabled.world.a)
    visible, hidden = uuid7(), uuid7()
    for object_id, body in (
        (visible, enabled.body()),
        (hidden, enabled.body(location_id=str(other))),
    ):
        result = await enabled.put(object_id, body)
        assert result.is_success, result.text
    branch_manager = enabled.member("manager", enabled.world.a.location_id)
    response = await enabled.client.get(enabled.base, headers=branch_manager)
    assert response.is_success, response.text
    assert [item["object_id"] for item in response.json()["items"]] == [str(visible)]
    assert "owner_id" not in response.json()["items"][0]
    response = await enabled.client.get(f"{enabled.base}/{hidden}", headers=branch_manager)
    assert response.status_code == 404, response.text
    response = await enabled.client.get(f"{enabled.base}/{visible}/history", headers=branch_manager)
    assert response.status_code == 403, response.text
    response = await enabled.put(uuid7(), enabled.body(), headers=branch_manager)
    assert response.status_code == 403, response.text
    response = await enabled.client.get(
        enabled.base, headers=enabled.idp.bearer(manager_b.subject, email=manager_b.email)
    )
    assert response.status_code == 403, response.text

    async with tenant_transaction(app_pool, enabled.tenant) as conn:
        await conn.execute(
            "select set_config('gba.location_id', %s, true)", (str(enabled.world.a.location_id),)
        )
        rows = await (await conn.execute("select id from gba.property_objects")).fetchall()
        assert rows == [(visible,)]
        assert await (await conn.execute("select * from gba.property_parties")).fetchall() == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.property_objects (tenant_id, id, location_id, kind) "
                    "values (%s, %s, %s, 'parcel')",
                    (enabled.tenant, uuid7(), enabled.world.a.location_id),
                )


async def test_competing_owner_revisions_commit_once(enabled: Catalog) -> None:
    object_id = uuid7()
    first, second = [await enabled.counterparty() for _ in range(2)]
    saved = await enabled.put(object_id, enabled.body(owner_id=first))
    assert saved.is_success, saved.text
    outcomes = await asyncio.gather(
        enabled.put(
            object_id, enabled.body(expected_revision=1, name="FAKE first", owner_id=second)
        ),
        enabled.put(
            object_id, enabled.body(expected_revision=1, name="FAKE second", owner_id=second)
        ),
    )
    assert sorted(outcome.status_code for outcome in outcomes) == [200, 409]
    rejected = next(outcome for outcome in outcomes if outcome.status_code == 409)
    assert rejected.json()["error"]["code"] == "PROPERTY_REVISION_CONFLICT"
    history = await enabled.client.get(
        f"{enabled.base}/{object_id}/history", headers=enabled.headers
    )
    assert [(item["revision"], item["owner_id"]) for item in history.json()["items"]] == [
        (1, first),
        (2, second),
    ]
