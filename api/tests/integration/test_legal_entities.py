"""Legal-entity drafts persist in real PostgreSQL under company/branch access controls."""

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.api.app import create_app
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.business.legal_entities import save_legal_entity
from gorgona_booking.business.legal_entity_contracts import LegalEntityInput
from gorgona_booking.config import Settings
from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from gorgona_booking.tenancy.authorization import authorized_tenant
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio


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
    user = seed_user(owner_conn, f"legal-manager-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=user.user_id, role="manager")
    return user


async def test_versions_replay_history_and_cursor_keep_one_identity(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    base = f"/v1/businesses/{world.a.tenant_id}/legal-entities"
    path = f"{base}/{uuid7()}"
    headers = idp.bearer(manager.subject, email=manager.email)
    payload = {"expected_revision": 0, "code": "MAIN", "legal_name": "FAKE Company LLC"}
    command_headers = {**headers, "Idempotency-Key": str(uuid7())}
    empty = await client.get(base, headers=headers)
    assert empty.json()["items"] == []
    first = await client.put(path, json=payload, headers=command_headers)
    assert first.status_code == 200, first.text
    assert first.json()["business_id"] == str(world.a.tenant_id)
    assert first.json()["state"] == "draft"
    assert first.json()["revision"] == 1
    assert (await client.put(path, json=payload, headers=command_headers)).json() == first.json()
    reused = await client.put(f"{base}/{uuid7()}", json=payload, headers=command_headers)
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    changed = await client.put(
        path,
        json={**payload, "expected_revision": 1, "legal_name": "FAKE Renamed Company LLC"},
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2
    assert (await client.get(path, headers=headers)).json() == changed.json()
    assert (await client.get(path, params={"revision": 1}, headers=headers)).json() == first.json()
    assert (await client.get(path, params={"revision": 3}, headers=headers)).status_code == 404
    stale = await client.put(
        path, json=payload, headers={**headers, "Idempotency-Key": str(uuid7())}
    )
    assert stale.status_code == 409
    renamed_code = await client.put(
        path,
        json={**payload, "expected_revision": 2, "code": "OTHER"},
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert renamed_code.status_code == 422
    # Equal legal names do not justify merging independent entity identities.
    another = await client.put(
        f"{base}/{uuid7()}",
        json={**payload, "code": "SECOND"},
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert another.status_code == 200, another.text
    page = (await client.get(base, params={"limit": 1}, headers=headers)).json()
    assert [item["code"] for item in page["items"]] == ["MAIN"]
    assert page["next_cursor"] == "MAIN"
    last = (await client.get(base, params={"after": "MAIN", "limit": 1}, headers=headers)).json()
    assert [item["code"] for item in last["items"]] == ["SECOND"]
    assert last["next_cursor"] is None
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        assert (
            await (await conn.execute("select count(*) from gba.legal_entities")).fetchone()
        ) == (2,)
        assert (await (await conn.execute("select count(*) from gba.tenants")).fetchone()) == (1,)
        audits = await (
            await conn.execute(
                "select details from gba.audit_events where action = 'legal_entity.saved'"
            )
        ).fetchall()
        assert len(audits) == 3
        assert all("legal_name" not in row[0] for row in audits)


async def test_concurrent_create_and_edit_have_one_winner_and_one_receipt(
    client: httpx.AsyncClient, world: BookingWorld, manager: FakeUser, idp: FakeIdp
) -> None:
    path = f"/v1/businesses/{world.a.tenant_id}/legal-entities/{uuid7()}"
    headers = idp.bearer(manager.subject, email=manager.email)
    payload = {"expected_revision": 0, "code": "MAIN", "legal_name": "FAKE Company LLC"}
    created = await asyncio.gather(
        *(
            client.put(path, json=payload, headers={**headers, "Idempotency-Key": str(uuid7())})
            for _ in range(2)
        )
    )
    assert sorted(response.status_code for response in created) == [200, 409]
    edits = await asyncio.gather(
        *(
            client.put(
                path,
                json={**payload, "expected_revision": 1, "legal_name": name},
                headers={**headers, "Idempotency-Key": str(uuid7())},
            )
            for name in ("FAKE First LLC", "FAKE Second LLC")
        )
    )
    assert sorted(response.status_code for response in edits) == [200, 409]
    key = str(uuid7())
    replays = await asyncio.gather(
        *(
            client.put(
                path,
                json={**payload, "expected_revision": 2},
                headers={**headers, "Idempotency-Key": key},
            )
            for _ in range(2)
        )
    )
    assert [response.status_code for response in replays] == [200, 200]
    assert replays[0].json() == replays[1].json()
    assert replays[0].json()["revision"] == 3


async def test_duplicate_reference_cannot_create_a_second_entity(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    base = f"/v1/businesses/{world.a.tenant_id}/legal-entities"
    headers = idp.bearer(manager.subject, email=manager.email)
    results = await asyncio.gather(
        *(
            client.put(
                f"{base}/{uuid7()}",
                json={"expected_revision": 0, "code": "MAIN", "legal_name": "FAKE LLC"},
                headers={**headers, "Idempotency-Key": str(uuid7())},
            )
            for _ in range(2)
        )
    )
    assert sorted(response.status_code for response in results) == [200, 409]
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        for table in ("legal_entities", "legal_entity_versions", "idempotency_keys"):
            # Fixed test-only table names, never supplied by a request.
            row = await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()
            assert row == (1,)


async def test_company_isolation_branch_scope_and_revoked_replay(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    entity_id = uuid7()
    base = f"/v1/businesses/{world.a.tenant_id}/legal-entities"
    path = f"{base}/{entity_id}"
    headers = {**idp.bearer(manager.subject, email=manager.email), "Idempotency-Key": str(uuid7())}
    payload = {"expected_revision": 0, "code": "MAIN", "legal_name": "FAKE LLC"}
    assert (await client.put(path, headers=headers, json=payload)).status_code == 200
    other = f"/v1/businesses/{world.b.tenant_id}/legal-entities"
    assert (await client.get(other, headers=headers)).status_code == 403
    assert (
        await client.put(f"{other}/{entity_id}", headers=headers, json=payload)
    ).status_code == 403
    async with unscoped_transaction(app_pool) as conn:
        assert (await (await conn.execute("select * from gba.legal_entities")).fetchall()) == []
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        assert (
            await (await conn.execute("select * from gba.legal_entity_versions")).fetchall()
        ) == []
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = %s where user_id = %s",
            (world.a.location_id, manager.user_id),
        )
    assert (await client.get(base, headers=headers)).status_code == 403
    assert (await client.get(path, headers=headers)).status_code == 403
    assert (await client.put(path, headers=headers, json=payload)).status_code == 403
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)", (str(world.a.location_id),)
        )
        assert (await (await conn.execute("select * from gba.legal_entities")).fetchall()) == []
        assert (
            await (await conn.execute("select * from gba.legal_entity_versions")).fetchall()
        ) == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.legal_entities (tenant_id, id, code, created_by) "
                    "values (%s, %s, 'BLOCKED', %s)",
                    (world.a.tenant_id, uuid7(), manager.user_id),
                )
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = null, status = 'revoked' where user_id = %s",
            (manager.user_id,),
        )
    assert (await client.put(path, headers=headers, json=payload)).status_code == 403


async def test_rollback_removes_identity_version_audit_and_command(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    entity_id, key = uuid7(), str(uuid7())
    principal = Principal(manager.user_id, "FAKE entity rollback manager", frozenset())
    body = LegalEntityInput(expected_revision=0, code="MAIN", legal_name="FAKE LLC")

    async def abort_after_save() -> None:
        async with authorized_tenant(
            app_pool,
            principal,
            world.a.tenant_id,
            Permission.BUSINESS_MANAGE,
            exclusive="business-structure",
        ) as access:
            await save_legal_entity(
                access.conn,
                business_id=world.a.tenant_id,
                entity_id=entity_id,
                user_id=manager.user_id,
                actor=principal.actor,
                key=key,
                body=body,
            )
            raise RuntimeError("FAKE abort")

    with pytest.raises(RuntimeError, match="FAKE abort"):
        await abort_after_save()
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        for table in ("legal_entities", "legal_entity_versions", "idempotency_keys"):
            row = await (await conn.execute(f"select count(*) from gba.{table}")).fetchone()
            assert row == (0,)
        count = await (
            await conn.execute(
                "select count(*) from gba.audit_events where action = 'legal_entity.saved'"
            )
        ).fetchone()
        assert count == (0,)
    response = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/legal-entities/{entity_id}",
        json=body.model_dump(mode="json"),
        headers={**idp.bearer(manager.subject, email=manager.email), "Idempotency-Key": key},
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1


async def test_saved_identity_and_versions_are_immutable_and_tenant_bound(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    entity_id = uuid7()
    headers = {**idp.bearer(manager.subject, email=manager.email), "Idempotency-Key": str(uuid7())}
    response = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/legal-entities/{entity_id}",
        json={"expected_revision": 0, "code": "MAIN", "legal_name": "FAKE LLC"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        for statement in (
            "update gba.legal_entities set code = 'CHANGED' where id = %s",
            "delete from gba.legal_entities where id = %s",
            "update gba.legal_entity_versions set legal_name = 'CHANGED' "
            "where legal_entity_id = %s",
            "delete from gba.legal_entity_versions where legal_entity_id = %s",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(statement, (entity_id,))
    with (
        owner_tenant_transaction(owner_conn, world.b.tenant_id),
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        owner_conn.transaction(),
    ):
        owner_conn.execute(
            "insert into gba.legal_entity_versions "
            "(tenant_id, legal_entity_id, revision, legal_name, created_by) "
            "values (%s, %s, 1, 'FAKE чужое', %s)",
            (world.b.tenant_id, entity_id, manager.user_id),
        )


async def test_staff_read_does_not_grant_entity_management(
    client: httpx.AsyncClient,
    world: BookingWorld,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    artist = seed_user(owner_conn, f"legal-artist-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=artist.user_id, role="artist")
    base = f"/v1/businesses/{world.a.tenant_id}/legal-entities"
    headers = {**idp.bearer(artist.subject, email=artist.email), "Idempotency-Key": str(uuid7())}
    assert (await client.get(base, headers=headers)).status_code == 200
    assert (
        await client.put(
            f"{base}/{uuid7()}",
            headers=headers,
            json={"expected_revision": 0, "code": "MAIN", "legal_name": "FAKE LLC"},
        )
    ).status_code == 403


@pytest.mark.parametrize("table", ["legal_entities", "legal_entity_versions"])
async def test_entity_scope_policy_damage_fails_readiness(
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
