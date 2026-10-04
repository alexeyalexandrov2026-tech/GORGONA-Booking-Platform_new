"""Company department workflows use real PostgreSQL, authorization and RLS."""

import asyncio
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.auth.permissions import Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.business.department_contracts import DepartmentInput
from gorgona_booking.business.departments import save_department
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.tenancy.authorization import authorized_tenant
from tests.integration import test_delegations as delegation
from tests.integration import test_legal_entities as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client, idp, manager = shared.client, shared.idp, shared.manager
parties = delegation.parties


def headers(idp: FakeIdp, user: FakeUser, key: str | None = None) -> dict[str, str]:
    return {**idp.bearer(user.subject, email=user.email), "Idempotency-Key": key or str(uuid7())}


def draft(**changes: object) -> dict[str, object]:
    return {"expected_revision": 0, "code": "MAIN", "name": "FAKE Department", **changes}


async def save(
    client: httpx.AsyncClient, base: str, department: UUID, auth: dict[str, str], **changes: object
) -> httpx.Response:
    return await client.put(f"{base}/{department}", headers=auth, json=draft(**changes))


async def test_versions_replay_conflicts_duplicate_reference_and_history(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    base = f"/v1/businesses/{world.a.tenant_id}/departments"
    department = uuid7()
    auth = headers(idp, manager)
    first = await save(client, base, department, auth)
    assert first.status_code == 200, first.text
    assert first.json()["business_id"] == str(world.a.tenant_id)
    assert first.json()["state"] == "draft"
    assert first.json()["revision"] == 1
    assert first.json()["parent_department_id"] is None
    assert (await save(client, base, department, auth)).json() == first.json()
    assert (await save(client, base, uuid7(), auth)).status_code == 422
    second = await save(
        client, base, department, headers(idp, manager), expected_revision=1, name="FAKE Renamed"
    )
    assert second.status_code == 200, second.text
    assert second.json()["revision"] == 2
    old = await client.get(f"{base}/{department}", headers=auth, params={"revision": 1})
    assert old.json() == first.json()
    assert (await save(client, base, department, headers(idp, manager))).status_code == 409
    assert (await save(client, base, uuid7(), headers(idp, manager))).status_code == 409
    another = await save(client, base, uuid7(), headers(idp, manager), code="SECOND")
    assert another.status_code == 200, another.text
    page = (await client.get(base, headers=auth, params={"limit": 1})).json()
    assert [item["code"] for item in page["items"]] == ["MAIN"]
    assert page["next_cursor"] == "MAIN"
    last = (await client.get(base, headers=auth, params={"after": "MAIN", "limit": 1})).json()
    assert [item["code"] for item in last["items"]] == ["SECOND"]
    assert last["next_cursor"] is None
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        for table, expected in (("departments", 2), ("department_versions", 3)):
            row = await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()
            assert row == (expected,)
        audit = await (
            await conn.execute(
                "select actor, details from gba.audit_events where action = 'department.saved'"
            )
        ).fetchall()
        assert len(audit) == 3
        assert all(
            actor == f"user:{manager.user_id}" and "name" not in details for actor, details in audit
        )


async def test_links_are_same_company_and_hierarchy_cannot_cycle(
    client: httpx.AsyncClient, world: BookingWorld, manager: FakeUser, idp: FakeIdp
) -> None:
    base = f"/v1/businesses/{world.a.tenant_id}/departments"
    parent, child = uuid7(), uuid7()
    assert (await save(client, base, parent, headers(idp, manager))).status_code == 200
    result = await save(
        client,
        base,
        child,
        headers(idp, manager),
        code="CHILD",
        parent_department_id=str(parent),
        location_id=str(world.a.location_id),
    )
    assert result.status_code == 200, result.text
    assert result.json()["parent_department_id"] == str(parent)
    for changes in (
        {"parent_department_id": str(child), "expected_revision": 1},
        {"parent_department_id": str(parent), "expected_revision": 1},
        {"location_id": str(world.b.location_id), "expected_revision": 1},
        {"legal_entity_id": str(uuid7()), "expected_revision": 1},
    ):
        rejected = await save(client, base, parent, headers(idp, manager), **changes)
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["error"]["code"] == "INVALID_REFERENCE"
    assert (await client.get(f"{base}/{parent}", headers=headers(idp, manager))).json()[
        "revision"
    ] == 1


async def test_concurrent_reparenting_has_one_winner_without_cycle(
    client: httpx.AsyncClient, world: BookingWorld, manager: FakeUser, idp: FakeIdp
) -> None:
    base = f"/v1/businesses/{world.a.tenant_id}/departments"
    a, b = uuid7(), uuid7()
    for department, code in ((a, "A"), (b, "B")):
        assert (
            await save(client, base, department, headers(idp, manager), code=code)
        ).status_code == 200
    results = await asyncio.gather(
        save(
            client,
            base,
            a,
            headers(idp, manager),
            code="A",
            expected_revision=1,
            parent_department_id=str(b),
        ),
        save(
            client,
            base,
            b,
            headers(idp, manager),
            code="B",
            expected_revision=1,
            parent_department_id=str(a),
        ),
    )
    assert sorted(response.status_code for response in results) == [200, 422]


async def test_legal_entity_link_can_be_set_cleared_and_preserved_in_history(
    client: httpx.AsyncClient, world: BookingWorld, manager: FakeUser, idp: FakeIdp
) -> None:
    department, entity = uuid7(), uuid7()
    auth = headers(idp, manager)
    result = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/legal-entities/{entity}",
        headers=auth,
        json={"expected_revision": 0, "code": "FAKE", "legal_name": "FAKE LLC"},
    )
    assert result.status_code == 200, result.text
    base = f"/v1/businesses/{world.a.tenant_id}/departments"
    first = await save(client, base, department, headers(idp, manager), legal_entity_id=str(entity))
    assert first.status_code == 200, first.text
    assert first.json()["legal_entity_id"] == str(entity)
    second = await save(client, base, department, headers(idp, manager), expected_revision=1)
    assert second.status_code == 200, second.text
    assert second.json()["legal_entity_id"] is None
    old = await client.get(f"{base}/{department}?revision=1", headers=auth)
    assert old.json() == first.json()


async def test_foreign_parent_and_legal_entity_cannot_create_partial_records(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    add_membership(owner_conn, tenant_id=world.b.tenant_id, user_id=manager.user_id, role="manager")
    foreign_parent, foreign_entity = uuid7(), uuid7()
    other = f"/v1/businesses/{world.b.tenant_id}"
    assert (
        await save(client, f"{other}/departments", foreign_parent, headers(idp, manager))
    ).status_code == 200
    legal = await client.put(
        f"{other}/legal-entities/{foreign_entity}",
        headers=headers(idp, manager),
        json={"expected_revision": 0, "code": "FAKE", "legal_name": "FAKE Foreign LLC"},
    )
    assert legal.status_code == 200, legal.text
    base = f"/v1/businesses/{world.a.tenant_id}/departments"
    for reference in ("parent_department_id", "legal_entity_id"):
        foreign = foreign_parent if reference == "parent_department_id" else foreign_entity
        response = await save(
            client, base, uuid7(), headers(idp, manager), **{reference: str(foreign)}
        )
        assert response.status_code == 422, response.text
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        for table in ("departments", "department_versions", "idempotency_keys"):
            assert (await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()) == (
                0,
            )


async def test_company_and_branch_scope_and_revoked_replay(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    department = uuid7()
    auth = headers(idp, manager)
    base = f"/v1/businesses/{world.a.tenant_id}/departments"
    assert (await save(client, base, department, auth)).status_code == 200
    other = f"/v1/businesses/{world.b.tenant_id}/departments"
    assert (await client.get(other, headers=auth)).status_code == 403
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = %s where user_id = %s",
            (world.a.location_id, manager.user_id),
        )
    for path in (base, f"{base}/{department}"):
        assert (await client.get(path, headers=auth)).status_code == 403
    assert (await save(client, base, department, auth)).status_code == 403
    for tenant, scope in ((world.b.tenant_id, None), (world.a.tenant_id, world.a.location_id)):
        async with tenant_transaction(app_pool, tenant) as conn:
            if scope:
                await conn.execute("select set_config('gba.location_id', %s, true)", (str(scope),))
            for table in ("departments", "department_versions"):
                assert (await (await conn.execute(f"select * from gba.{table}")).fetchall()) == []
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute(
                        "insert into gba.departments (tenant_id, id, code, created_by) "
                        "values (%s, %s, 'DENIED', %s)",
                        (world.a.tenant_id, uuid7(), manager.user_id),
                    )
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = null, status = 'revoked' where user_id = %s",
            (manager.user_id,),
        )
    assert (await save(client, base, department, auth)).status_code == 403


async def test_delegated_operational_access_cannot_read_or_write_departments(
    client: httpx.AsyncClient,
    world: BookingWorld,
    parties: delegation.Parties,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    grant = await delegation._delegation(client, idp, world, parties)
    base = f"/v1/businesses/{world.a.tenant_id}/departments"
    assert (await save(client, base, uuid7(), headers(idp, parties.owner_a))).status_code == 200
    auth = headers(idp, parties.delegate)
    assert (await client.get(base, headers=auth)).status_code == 403
    assert (await save(client, base, uuid7(), auth)).status_code == 403
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        await conn.execute("select set_config('gba.delegation_grant_id', %s, true)", (str(grant),))
        for table in ("departments", "department_versions"):
            assert (await (await conn.execute(f"select * from gba.{table}")).fetchall()) == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.departments (tenant_id, id, code, created_by) "
                    "values (%s, %s, 'DENIED', %s)",
                    (world.a.tenant_id, uuid7(), parties.delegate.user_id),
                )


async def test_rollback_removes_identity_version_audit_and_receipt(
    world: BookingWorld, manager: FakeUser, app_pool: RuntimePool
) -> None:
    principal = Principal(manager.user_id, "FAKE department manager", frozenset())

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
                department_id=uuid7(),
                user_id=manager.user_id,
                actor=access.actor,
                key=str(uuid7()),
                body=DepartmentInput(expected_revision=0, code="MAIN", name="FAKE Department"),
            )
            raise RuntimeError("FAKE abort")

    with pytest.raises(RuntimeError, match="FAKE abort"):
        await abort_after_save()
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        for table in ("departments", "department_versions", "idempotency_keys"):
            assert (await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()) == (
                0,
            )
        assert (
            await (
                await conn.execute(
                    "select count(*) from gba.audit_events where action = 'department.saved'"
                )
            ).fetchone()
        ) == (0,)


async def test_database_enforces_immutable_versions_links_and_hierarchy(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    base = f"/v1/businesses/{world.a.tenant_id}/departments"
    a, b = uuid7(), uuid7()
    for department, code, parent in ((a, "A", None), (b, "B", str(a))):
        assert (
            await save(
                client,
                base,
                department,
                headers(idp, manager),
                code=code,
                parent_department_id=parent,
            )
        ).status_code == 200
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        for sql in (
            "update gba.departments set code = 'CHANGED' where id = %s",
            "delete from gba.departments where id = %s",
            "update gba.department_versions set name = 'CHANGED' where department_id = %s",
            "delete from gba.department_versions where department_id = %s",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(sql, (a,))
        for revision, parent_id, location, error in (
            (3, None, None, psycopg.errors.CheckViolation),
            (2, b, None, psycopg.errors.CheckViolation),
            (2, None, world.b.location_id, psycopg.errors.ForeignKeyViolation),
        ):
            with pytest.raises(error), owner_conn.transaction():
                owner_conn.execute(
                    "insert into gba.department_versions "
                    "(tenant_id, department_id, revision, name, "
                    "parent_department_id, location_id, created_by) "
                    "values (%s, %s, %s, 'FAKE', %s, %s, %s)",
                    (world.a.tenant_id, a, revision, parent_id, location, manager.user_id),
                )


@pytest.mark.parametrize("table", ["departments", "department_versions"])
@pytest.mark.parametrize("scope", ["unrestricted", "delegation"])
async def test_scope_policy_damage_fails_readiness(
    client: httpx.AsyncClient, owner_conn: psycopg.Connection, table: str, scope: str
) -> None:
    function = "current_location_id" if scope == "unrestricted" else "current_delegation_grant_id"
    try:
        owner_conn.execute(
            f"alter policy {table}_{scope}_scope on gba.{table} using (true) with check (true)"
        )
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(
            f"alter policy {table}_{scope}_scope on gba.{table} "
            f"using (gba.{function}() is null) with check (gba.{function}() is null)"
        )
    assert (await client.get("/health/ready")).status_code == 200


async def test_stale_repeatable_read_snapshots_cannot_commit_a_hierarchy_cycle(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    base = f"/v1/businesses/{world.a.tenant_id}/departments"
    a, b = uuid7(), uuid7()
    for department, code in ((a, "A"), (b, "B")):
        assert (
            await save(client, base, department, headers(idp, manager), code=code)
        ).status_code == 200
    with psycopg.connect(test_database.owner_dsn, autocommit=True) as other:
        outcomes: list[str | None] = []
        try:
            for conn in (owner_conn, other):
                conn.execute("begin isolation level repeatable read")
                conn.execute(
                    "select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),)
                )
                # Pin both snapshots before either version is inserted/committed.
                conn.execute("select count(*) from gba.department_versions").fetchone()
            for conn, department, parent in ((owner_conn, a, b), (other, b, a)):
                try:
                    conn.execute(
                        "insert into gba.department_versions "
                        "(tenant_id, department_id, revision, name, "
                        "parent_department_id, created_by) "
                        "values (%s, %s, 2, 'FAKE', %s, %s)",
                        (world.a.tenant_id, department, parent, manager.user_id),
                    )
                    conn.execute("commit")
                    outcomes.append("committed")
                except psycopg.errors.CheckViolation as exc:
                    outcomes.append(exc.diag.constraint_name)
                    conn.execute("rollback")
        finally:
            owner_conn.execute("rollback")
            other.execute("rollback")
    assert outcomes == ["department_isolation", "department_isolation"]
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        assert owner_conn.execute(
            "select count(*) from gba.department_versions where revision = 2"
        ).fetchone() == (0,)


async def test_unsupported_snapshot_configuration_rolls_back_command(
    world: BookingWorld, manager: FakeUser, app_pool: RuntimePool
) -> None:
    async def save_in_unsupported_transaction() -> None:
        async with app_pool.connection() as conn, conn.transaction():
            await conn.execute("set transaction isolation level repeatable read")
            await conn.execute(
                "select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),)
            )
            await save_department(
                conn,
                business_id=world.a.tenant_id,
                department_id=uuid7(),
                user_id=manager.user_id,
                actor=f"user:{manager.user_id}",
                key=str(uuid7()),
                body=DepartmentInput(expected_revision=0, code="FAKE", name="FAKE Department"),
            )

    with pytest.raises(DatabaseUnavailableError, match="READ COMMITTED"):
        await save_in_unsupported_transaction()
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        for table in ("departments", "department_versions", "idempotency_keys"):
            assert (await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()) == (
                0,
            )
