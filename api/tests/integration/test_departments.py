"""Departments persist in real PostgreSQL as one acyclic, company-bound structure."""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.api.app import create_app
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.business.department_contracts import DepartmentInput
from gorgona_booking.business.departments import save_department
from gorgona_booking.config import Settings
from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from gorgona_booking.tenancy.authorization import authorized_tenant
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio


def _body(code: str, name: str, **changes: object) -> dict[str, object]:
    return {
        "expected_revision": 0,
        "code": code,
        "name": name,
        "parent_department_id": None,
        "legal_entity_id": None,
        "location_id": None,
        "archived": False,
        **changes,
    }


@pytest.fixture(scope="module")
def idp() -> FakeIdp:
    return FakeIdp()


@pytest.fixture
async def client(app_pool: RuntimePool, idp: FakeIdp) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(environment="test"), pool=app_pool, token_verifier=idp.verifier())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as http:
        yield http


@pytest.fixture
def manager(world: BookingWorld, owner_conn: psycopg.Connection) -> FakeUser:
    user = seed_user(owner_conn, f"department-manager-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=user.user_id, role="manager")
    return user


class Departments:
    """FAKE manager commands against one company's department routes."""

    def __init__(
        self, client: httpx.AsyncClient, business_id: UUID, user: FakeUser, idp: FakeIdp
    ) -> None:
        self.client = client
        self.base = f"/v1/businesses/{business_id}/departments"
        self.headers = idp.bearer(user.subject, email=user.email)

    async def put(
        self, department_id: UUID, body: dict[str, object], key: str | None = None
    ) -> httpx.Response:
        return await self.client.put(
            f"{self.base}/{department_id}",
            json=body,
            headers={**self.headers, "Idempotency-Key": key or str(uuid7())},
        )

    async def create(self, code: str, **changes: object) -> UUID:
        department_id = uuid7()
        response = await self.put(department_id, {**_body(code, f"FAKE {code}"), **changes})
        assert response.status_code == 200, response.text
        return department_id

    async def change(self, department_id: UUID, **changes: object) -> httpx.Response:
        current = (
            await self.client.get(f"{self.base}/{department_id}", headers=self.headers)
        ).json()
        body = {key: current[key] for key in _body("X", "X") if key != "expected_revision"}
        return await self.put(
            department_id, {**body, "expected_revision": current["revision"], **changes}
        )


async def test_versions_replay_history_and_cursor_keep_one_identity(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    api = Departments(client, world.a.tenant_id, manager, idp)
    path = f"{api.base}/{uuid7()}"
    payload = _body("OPS", "FAKE Operations")
    command_headers = {**api.headers, "Idempotency-Key": str(uuid7())}
    assert (await client.get(api.base, headers=api.headers)).json()["items"] == []
    first = await client.put(path, json=payload, headers=command_headers)
    assert first.status_code == 200, first.text
    assert first.json()["business_id"] == str(world.a.tenant_id)
    assert first.json()["state"] == "draft"
    assert first.json()["revision"] == 1
    assert (await client.put(path, json=payload, headers=command_headers)).json() == first.json()
    reused = await client.put(f"{api.base}/{uuid7()}", json=payload, headers=command_headers)
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    changed = await client.put(
        path,
        json={**payload, "expected_revision": 1, "name": "FAKE Renamed Operations"},
        headers={**api.headers, "Idempotency-Key": str(uuid7())},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2
    assert (await client.get(path, headers=api.headers)).json() == changed.json()
    assert (
        await client.get(path, params={"revision": 1}, headers=api.headers)
    ).json() == first.json()
    assert (await client.get(path, params={"revision": 3}, headers=api.headers)).status_code == 404
    stale = await client.put(
        path, json=payload, headers={**api.headers, "Idempotency-Key": str(uuid7())}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["details"] == {"revision": 2}
    renamed_code = await client.put(
        path,
        json={**payload, "expected_revision": 2, "code": "OTHER"},
        headers={**api.headers, "Idempotency-Key": str(uuid7())},
    )
    assert renamed_code.status_code == 422
    # Equal names do not justify merging independent department identities.
    await api.create("SALES", name="FAKE Renamed Operations")
    page = (await client.get(api.base, params={"limit": 1}, headers=api.headers)).json()
    assert [item["code"] for item in page["items"]] == ["OPS"]
    assert page["next_cursor"] == "OPS"
    last = (
        await client.get(api.base, params={"after": "OPS", "limit": 1}, headers=api.headers)
    ).json()
    assert [item["code"] for item in last["items"]] == ["SALES"]
    assert last["next_cursor"] is None
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        assert (await (await conn.execute("select count(*) from gba.departments")).fetchone()) == (
            2,
        )
        assert (await (await conn.execute("select count(*) from gba.tenants")).fetchone()) == (1,)
        audits = await (
            await conn.execute(
                "select details from gba.audit_events where action = 'department.saved'"
            )
        ).fetchall()
        assert len(audits) == 3
        assert all("name" not in row[0] for row in audits)


async def test_concurrent_create_and_edit_have_one_winner_and_one_receipt(
    client: httpx.AsyncClient, world: BookingWorld, manager: FakeUser, idp: FakeIdp
) -> None:
    api = Departments(client, world.a.tenant_id, manager, idp)
    department_id = uuid7()
    payload = _body("OPS", "FAKE Operations")
    created = await asyncio.gather(*(api.put(department_id, payload) for _ in range(2)))
    assert sorted(response.status_code for response in created) == [200, 409]
    edits = await asyncio.gather(
        *(
            api.put(department_id, {**payload, "expected_revision": 1, "name": name})
            for name in ("FAKE First Operations", "FAKE Second Operations")
        )
    )
    assert sorted(response.status_code for response in edits) == [200, 409]
    key = str(uuid7())
    replays = await asyncio.gather(
        *(api.put(department_id, {**payload, "expected_revision": 2}, key) for _ in range(2))
    )
    assert [response.status_code for response in replays] == [200, 200]
    assert replays[0].json() == replays[1].json()
    assert replays[0].json()["revision"] == 3


async def test_duplicate_reference_cannot_create_a_second_department(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    api = Departments(client, world.a.tenant_id, manager, idp)
    results = await asyncio.gather(
        *(api.put(uuid7(), _body("OPS", "FAKE Operations")) for _ in range(2))
    )
    assert sorted(response.status_code for response in results) == [200, 409]
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        for table in ("departments", "department_versions", "idempotency_keys"):
            # Fixed test-only table names, never supplied by a request.
            row = await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()
            assert row == (1,)


async def test_links_stay_inside_the_company_and_structure_stays_acyclic(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    api = Departments(client, world.a.tenant_id, manager, idp)
    entity_id = uuid7()
    entity = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/legal-entities/{entity_id}",
        json={"expected_revision": 0, "code": "MAIN", "legal_name": "FAKE Company LLC"},
        headers={**api.headers, "Idempotency-Key": str(uuid7())},
    )
    assert entity.status_code == 200, entity.text
    foreign_entity = uuid7()
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        owner_conn.execute(
            "insert into gba.legal_entities (tenant_id, id, code, created_by) "
            "values (%s, %s, 'FOREIGN', %s)",
            (world.b.tenant_id, foreign_entity, manager.user_id),
        )
    ops = await api.create("OPS")
    team = await api.create(
        "TEAM",
        parent_department_id=str(ops),
        legal_entity_id=str(entity_id),
        location_id=str(world.a.location_id),
    )
    sub = await api.create("SUB", parent_department_id=str(team))
    saved = (await client.get(f"{api.base}/{team}", headers=api.headers)).json()
    assert saved["parent_department_id"] == str(ops)
    assert saved["legal_entity_id"] == str(entity_id)
    assert saved["location_id"] == str(world.a.location_id)

    structure = "DEPARTMENT_STRUCTURE_INVALID"
    for department_id, changes, code, field in (
        (ops, {"parent_department_id": str(ops)}, structure, None),
        (ops, {"parent_department_id": str(team)}, structure, None),
        (ops, {"parent_department_id": str(sub)}, structure, None),
        (ops, {"parent_department_id": str(uuid7())}, "INVALID_REFERENCE", "parent_department_id"),
        (ops, {"legal_entity_id": str(foreign_entity)}, "INVALID_REFERENCE", "legal_entity_id"),
        (ops, {"location_id": str(world.b.location_id)}, "INVALID_REFERENCE", "location_id"),
        (ops, {"archived": True}, structure, None),
    ):
        rejected = await api.change(department_id, **changes)
        assert rejected.status_code == 422, (changes, rejected.text)
        assert rejected.json()["error"]["code"] == code
        if field is not None:
            assert rejected.json()["error"]["details"] == {"field": field}

    for department_id in (sub, team, ops):
        archived = await api.change(department_id, archived=True)
        assert archived.status_code == 200, archived.text
    under_archived_parent = await api.change(team, archived=False)
    assert under_archived_parent.json()["error"]["code"] == structure
    moved_to_top = await api.change(sub, parent_department_id=None, archived=False)
    assert moved_to_top.status_code == 200, moved_to_top.text
    new_under_archived = await api.put(
        uuid7(), _body("NEW", "FAKE New", parent_department_id=str(ops))
    )
    assert new_under_archived.json()["error"]["code"] == structure
    kept = await api.put(
        uuid7(), _body("KEPT", "FAKE Kept", parent_department_id=str(ops), archived=True)
    )
    assert kept.status_code == 200, kept.text
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select d.code, max(v.revision) from gba.departments d "
                "join gba.department_versions v "
                "on v.tenant_id = d.tenant_id and v.department_id = d.id "
                "group by d.code order by d.code"
            )
        ).fetchall()
    # Rejected commands left no version; only accepted saves advanced revisions.
    assert rows == [("KEPT", 1), ("OPS", 2), ("SUB", 3), ("TEAM", 2)]


async def test_company_isolation_branch_scope_and_revoked_replay(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    api = Departments(client, world.a.tenant_id, manager, idp)
    department_id = uuid7()
    payload = _body("OPS", "FAKE Operations")
    key = str(uuid7())
    assert (await api.put(department_id, payload, key)).status_code == 200
    other = f"/v1/businesses/{world.b.tenant_id}/departments"
    assert (await client.get(other, headers=api.headers)).status_code == 403
    assert (
        await client.put(
            f"{other}/{department_id}",
            headers={**api.headers, "Idempotency-Key": str(uuid7())},
            json=payload,
        )
    ).status_code == 403
    async with unscoped_transaction(app_pool) as conn:
        assert (await (await conn.execute("select * from gba.departments")).fetchall()) == []
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        assert (
            await (await conn.execute("select * from gba.department_versions")).fetchall()
        ) == []
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = %s where user_id = %s",
            (world.a.location_id, manager.user_id),
        )
    path = f"{api.base}/{department_id}"
    assert (await client.get(api.base, headers=api.headers)).status_code == 403
    assert (await client.get(path, headers=api.headers)).status_code == 403
    # The stored receipt is not reopened for a narrowed grant.
    assert (await api.put(department_id, payload, key)).status_code == 403
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)", (str(world.a.location_id),)
        )
        assert (await (await conn.execute("select * from gba.departments")).fetchall()) == []
        assert (
            await (await conn.execute("select * from gba.department_versions")).fetchall()
        ) == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.departments (tenant_id, id, code, created_by) "
                    "values (%s, %s, 'BLOCKED', %s)",
                    (world.a.tenant_id, uuid7(), manager.user_id),
                )
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = null, status = 'revoked' where user_id = %s",
            (manager.user_id,),
        )
    assert (await api.put(department_id, payload, key)).status_code == 403


async def test_rollback_removes_identity_version_audit_and_command(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    department_id, key = uuid7(), str(uuid7())
    principal = Principal(manager.user_id, "FAKE department rollback manager", frozenset())
    body = DepartmentInput.model_validate(_body("OPS", "FAKE Operations"))

    async def abort_after_save() -> None:
        async with authorized_tenant(
            app_pool,
            principal,
            world.a.tenant_id,
            Permission.BUSINESS_MANAGE,
            exclusive="business-structure",
        ) as access:
            await save_department(
                access.conn,
                business_id=world.a.tenant_id,
                department_id=department_id,
                user_id=manager.user_id,
                actor=principal.actor,
                key=key,
                body=body,
            )
            raise RuntimeError("FAKE abort")

    with pytest.raises(RuntimeError, match="FAKE abort"):
        await abort_after_save()
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        for table in ("departments", "department_versions", "idempotency_keys"):
            row = await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()
            assert row == (0,)
        count = await (
            await conn.execute(
                "select count(*) from gba.audit_events where action = 'department.saved'"
            )
        ).fetchone()
        assert count == (0,)
    response = await Departments(client, world.a.tenant_id, manager, idp).put(
        department_id, body.model_dump(mode="json"), key
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1


async def test_saved_identity_versions_and_links_are_immutable_and_tenant_bound(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    department_id = await Departments(client, world.a.tenant_id, manager, idp).create("OPS")
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        for statement in (
            "update gba.departments set code = 'CHANGED' where id = %s",
            "delete from gba.departments where id = %s",
            "update gba.department_versions set name = 'CHANGED' where department_id = %s",
            "update gba.department_versions set archived = true where department_id = %s",
            "delete from gba.department_versions where department_id = %s",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(statement, (department_id,))
        # Even the owner role cannot link another company's location or a missing parent.
        for column, value in (
            ("location_id", world.b.location_id),
            ("parent_department_id", uuid7()),
            ("legal_entity_id", uuid7()),
        ):
            with pytest.raises(psycopg.errors.ForeignKeyViolation), owner_conn.transaction():
                owner_conn.execute(
                    "insert into gba.department_versions (tenant_id, department_id, revision, "
                    f"name, {column}, archived, created_by) "
                    "values (%s, %s, 2, 'FAKE linked', %s, false, %s)",
                    (world.a.tenant_id, department_id, value, manager.user_id),
                )
        with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
            owner_conn.execute(
                "insert into gba.department_versions (tenant_id, department_id, revision, "
                "name, parent_department_id, archived, created_by) "
                "values (%s, %s, 2, 'FAKE own parent', %s, false, %s)",
                (world.a.tenant_id, department_id, department_id, manager.user_id),
            )
    with (
        owner_tenant_transaction(owner_conn, world.b.tenant_id),
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        owner_conn.transaction(),
    ):
        owner_conn.execute(
            "insert into gba.department_versions "
            "(tenant_id, department_id, revision, name, archived, created_by) "
            "values (%s, %s, 1, 'FAKE чужое', false, %s)",
            (world.b.tenant_id, department_id, manager.user_id),
        )


async def test_staff_read_does_not_grant_department_management(
    client: httpx.AsyncClient,
    world: BookingWorld,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    artist = seed_user(owner_conn, f"department-artist-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=artist.user_id, role="artist")
    api = Departments(client, world.a.tenant_id, artist, idp)
    assert (await client.get(api.base, headers=api.headers)).status_code == 200
    assert (await api.put(uuid7(), _body("OPS", "FAKE Operations"))).status_code == 403


@pytest.mark.parametrize("table", ["departments", "department_versions"])
async def test_department_scope_policy_damage_fails_readiness(
    client: httpx.AsyncClient,
    owner_conn: psycopg.Connection,
    table: str,
) -> None:
    # Fixed test parameters; privileged schema damage is confined to the disposable database.
    try:
        owner_conn.execute(
            f"alter policy {table}_unrestricted_scope on gba.{table} using (true) with check (true)"
        )
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(
            f"alter policy {table}_unrestricted_scope on gba.{table} "
            "using (gba.current_location_id() is null) "
            "with check (gba.current_location_id() is null)"
        )
