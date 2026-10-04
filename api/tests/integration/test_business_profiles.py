import asyncio
from collections.abc import AsyncIterator
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.api.app import create_app
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.business.catalog import BusinessFormat
from gorgona_booking.business.contracts import ProfileInput
from gorgona_booking.business.service import save_profile
from gorgona_booking.config import Settings
from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.db.provisioning import (
    add_membership,
    grant_platform_admin,
    owner_tenant_transaction,
)
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
    user = seed_user(owner_conn, f"business-manager-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=user.user_id, role="manager")
    return user


async def test_profile_replays_once_keeps_history_and_conflicts(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    business_id = world.a.tenant_id
    path = f"/v1/businesses/{business_id}"
    headers = idp.bearer(manager.subject, email=manager.email)
    original = await client.get(path, headers=headers)
    assert original.status_code == 200
    assert original.json()["business_id"] == str(business_id)
    assert original.json()["profile"] is None
    catalog = await client.get(f"{path}/industry-catalog", headers=headers)
    assert catalog.status_code == 200
    assert len(catalog.json()["industries"]) == 39
    payload = {"expected_revision": 0, "industry_ids": [1, 24], "business_formats": ["b2b"]}
    key_headers = {**headers, "Idempotency-Key": str(uuid7())}
    first = await client.put(f"{path}/profile", json=payload, headers=key_headers)
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "draft"
    assert first.json()["revision"] == 1
    replay = await client.put(f"{path}/profile", json=payload, headers=key_headers)
    assert replay.json() == first.json()
    changed = await client.put(
        f"{path}/profile", json={**payload, "industry_ids": [2]}, headers=key_headers
    )
    assert changed.status_code == 422
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    stale = await client.put(
        f"{path}/profile", json=payload, headers={**headers, "Idempotency-Key": str(uuid7())}
    )
    assert stale.status_code == 409
    second = await client.put(
        f"{path}/profile",
        json={**payload, "expected_revision": 1, "industry_ids": [2, 19]},
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert second.status_code == 200
    assert second.json()["revision"] == 2
    async with tenant_transaction(app_pool, business_id) as conn:
        rows = await (
            await conn.execute(
                "select revision, industry_id from gba.business_profile_industries "
                "order by revision, industry_id"
            )
        ).fetchall()
        assert rows == [(1, 1), (1, 24), (2, 2), (2, 19)]
        audits = await (
            await conn.execute(
                "select details from gba.audit_events where action = 'business_profile.created'"
            )
        ).fetchall()
        assert len(audits) == 2
        assert audits[0][0]["industry_ids"] in ([1, 24], [2, 19])


async def test_concurrent_saves_have_one_winner(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
) -> None:
    path = f"/v1/businesses/{world.a.tenant_id}/profile"
    headers = idp.bearer(manager.subject, email=manager.email)
    results = await asyncio.gather(
        *(
            client.put(
                path,
                json={"expected_revision": 0, "industry_ids": [industry]},
                headers={**headers, "Idempotency-Key": str(uuid7())},
            )
            for industry in (1, 24)
        )
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    key = str(uuid7())
    retry_results = await asyncio.gather(
        *(
            client.put(
                path,
                json={"expected_revision": 1, "industry_ids": [19, 23]},
                headers={**headers, "Idempotency-Key": key},
            )
            for _ in range(2)
        )
    )
    assert [r.status_code for r in retry_results] == [200, 200]
    assert retry_results[0].json() == retry_results[1].json()


async def test_aborted_transaction_rolls_back_profile_selections_audit_and_command(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    principal = Principal(manager.user_id, "FAKE rollback manager", frozenset())
    body = ProfileInput(
        expected_revision=0, industry_ids=(1, 24), business_formats=(BusinessFormat.B2B,)
    )
    key = str(uuid7())

    async def abort_after_save() -> None:
        async with authorized_tenant(
            app_pool,
            principal,
            world.a.tenant_id,
            Permission.BUSINESS_MANAGE,
            exclusive="business-profile",
        ) as access:
            await save_profile(
                access.conn,
                business_id=world.a.tenant_id,
                user_id=manager.user_id,
                actor=principal.actor,
                key=key,
                body=body,
            )
            raise RuntimeError("FAKE transaction failure")

    with pytest.raises(RuntimeError, match="FAKE transaction failure"):
        await abort_after_save()
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select count(*) from gba.business_profile_versions "
                "union all select count(*) from gba.business_profile_industries "
                "union all select count(*) from gba.business_profile_formats "
                "union all select count(*) from gba.idempotency_keys "
                "union all select count(*) from gba.audit_events "
                "where action = 'business_profile.created'"
            )
        ).fetchall()
        assert rows == [(0,)] * 5
    response = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/profile",
        json=body.model_dump(mode="json"),
        headers={**idp.bearer(manager.subject, email=manager.email), "Idempotency-Key": key},
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1


async def test_tenant_isolation_scoped_access_and_revoke(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    headers = idp.bearer(manager.subject, email=manager.email)
    path = f"/v1/businesses/{world.a.tenant_id}"
    payload = {"expected_revision": 0, "industry_ids": [1]}
    response = await client.put(
        f"{path}/profile", json=payload, headers={**headers, "Idempotency-Key": str(uuid7())}
    )
    assert response.status_code == 200
    for suffix in ("", "/industry-catalog"):
        assert (
            await client.get(f"/v1/businesses/{world.b.tenant_id}{suffix}", headers=headers)
        ).status_code == 403
    async with unscoped_transaction(app_pool) as conn:
        assert (
            await (await conn.execute("select * from gba.business_profile_versions")).fetchall()
            == []
        )
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        assert (
            await (await conn.execute("select * from gba.business_profile_industries")).fetchall()
            == []
        )
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = %s where user_id = %s",
            (world.a.location_id, manager.user_id),
        )
    for route in (path, f"{path}/industry-catalog"):
        assert (await client.get(route, headers=headers)).status_code == 403
    assert (
        await client.get(f"/v1/salons/{world.a.tenant_id}/bookings", headers=headers)
    ).status_code == 200
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set location_id = null, status = 'revoked' where user_id = %s",
            (manager.user_id,),
        )
    assert (await client.get(path, headers=headers)).status_code == 403


async def test_platform_grant_has_audited_fallback_without_expanding_scoped_membership(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    grant_platform_admin(owner_conn, user_id=manager.user_id, granted_by="test")
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.memberships set role = 'artist', location_id = %s where user_id = %s",
            (world.a.location_id, manager.user_id),
        )
    headers = idp.bearer(manager.subject, email=manager.email)
    path = f"/v1/businesses/{world.a.tenant_id}"
    response = await client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    write = await client.put(
        f"{path}/profile",
        json={"expected_revision": 0, "industry_ids": [1]},
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert write.status_code == 403
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        row = await (
            await conn.execute(
                "select details from gba.audit_events where action = 'platform.tenant_access'"
            )
        ).fetchone()
        assert row is not None
        assert row[0]["permission"] == "business.read"


async def test_readonly_role_and_snapshot_database_guards(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    path = f"/v1/businesses/{world.a.tenant_id}"
    headers = idp.bearer(manager.subject, email=manager.email)
    assert (
        await client.put(
            f"{path}/profile",
            json={"expected_revision": 0, "industry_ids": [1]},
            headers={**headers, "Idempotency-Key": str(uuid7())},
        )
    ).status_code == 200
    reader = seed_user(owner_conn, f"business-reader-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=reader.user_id, role="artist")
    auth = idp.bearer(reader.subject, email=reader.email)
    assert (await client.get(path, headers=auth)).status_code == 200
    assert (
        await client.put(
            f"{path}/profile",
            json={"expected_revision": 1, "industry_ids": [2]},
            headers={**auth, "Idempotency-Key": str(uuid7())},
        )
    ).status_code == 403
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.business_profile_industries values (%s, 1, 2)",
                (world.a.tenant_id,),
            )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.business_profile_versions "
                "(tenant_id, revision, catalog_version, created_by, created_transaction) "
                "values (%s, 2, 1, %s, pg_current_xact_id())",
                (world.a.tenant_id, manager.user_id),
            )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
            await conn.execute(
                "update gba.business_profile_versions set custom_activity_name = 'changed'"
            )
