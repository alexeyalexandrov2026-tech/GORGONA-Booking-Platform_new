"""Real PostgreSQL 18 integration tests for Self-Service Business Onboarding."""

from uuid import uuid7

import httpx
import pytest
from psycopg import errors

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_management_api as shared
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


async def test_unlinked_oidc_user_registers_multi_industry_business_end_to_end(
    client: httpx.AsyncClient, idp: FakeIdp, app_pool: RuntimePool
) -> None:
    sub = f"self-service-founder-{uuid7()}"
    headers = idp.bearer(sub, email="founder@example.test", name="FAKE Self-Service Founder")

    # 1. Before onboarding: /v1/me rejects unlinked user, /v1/onboarding/status shows linked=False
    me_before = await client.get("/v1/me", headers=headers)
    assert me_before.status_code == 403
    status_before = await client.get("/v1/onboarding/status", headers=headers)
    assert status_before.status_code == 200, status_before.text
    assert status_before.json()["linked"] is False
    assert status_before.json()["can_create_business"] is True

    # 2. Presets cover all 39 industries
    presets = await client.get("/v1/onboarding/presets")
    assert presets.status_code == 200
    assert len(presets.json()["industries"]) == 39

    # 3. Register new multi-industry company without any admin involvement
    slug = f"fake-ss-{uuid7().hex[:10]}"
    key = str(uuid7())
    payload = {
        "business_name": "FAKE Self-Service Multi-Industry Co",
        "slug": slug,
        "location_name": "Austin HQ",
        "timezone": "America/Chicago",
        "industry_ids": [1, 19, 38],
        "business_formats": ["b2c", "b2b"],
    }
    created = await client.post(
        "/v1/onboarding/businesses",
        json=payload,
        headers={**headers, "Idempotency-Key": key},
    )
    assert created.status_code == 201, created.text
    data = created.json()
    bid = data["business_id"]
    assert data["slug"] == slug
    assert data["role"] == "owner"
    assert data["profile_revision"] == 1
    assert data["configuration_version"] == 1
    assert data["industry_ids"] == [1, 19, 38]
    assert "organization" in data["effective_module_ids"]
    assert "booking_resources" in data["effective_module_ids"]
    assert "finance_documents" in data["effective_module_ids"]

    # 4. Idempotent replay returns exact same business; reused key with different body returns 422
    replay = await client.post(
        "/v1/onboarding/businesses",
        json=payload,
        headers={**headers, "Idempotency-Key": key},
    )
    assert replay.status_code == 201
    assert replay.json() == data

    reused = await client.post(
        "/v1/onboarding/businesses",
        json={**payload, "business_name": "Different Name"},
        headers={**headers, "Idempotency-Key": key},
    )
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    # 5. Duplicate slug rejected cleanly with 409
    dup_slug = await client.post(
        "/v1/onboarding/businesses",
        json=payload,
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert dup_slug.status_code == 409

    # 6. Founder immediately gets a working owner cabinet
    me_after = await client.get("/v1/me", headers=headers)
    assert me_after.status_code == 200, me_after.text
    assert me_after.json()["memberships"][0]["salon_id"] == bid
    assert me_after.json()["memberships"][0]["role"] == "owner"

    overview = await client.get(f"/v1/salons/{bid}/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    cfg = await client.get(f"/v1/businesses/{bid}/configuration", headers=headers)
    assert cfg.status_code == 200
    assert cfg.json()["baseline"] is False
    assert cfg.json()["published"]["version"] == 1
    cp = await client.get(f"/v1/businesses/{bid}/counterparties", headers=headers)
    assert cp.status_code == 200

    # 7. Security invariant preserved: unguarded INSERT into gba.tenants fails with 42501
    rogue_id = uuid7()
    with pytest.raises(errors.InsufficientPrivilege):
        async with tenant_transaction(app_pool, rogue_id) as conn:
            await conn.execute(
                "insert into gba.tenants (id, slug, display_name) values (%s, 'rogue-ss', 'x')",
                (rogue_id,),
            )

    # 8. Cross-tenant isolation: another self-service founder cannot read the first business
    other_headers = idp.bearer(f"other-founder-{uuid7()}", email="other@example.test", name="Other")
    other_created = await client.post(
        "/v1/onboarding/businesses",
        json={
            "business_name": "FAKE Other Company",
            "slug": f"fake-other-{uuid7().hex[:10]}",
            "location_name": "NYC",
            "timezone": "America/New_York",
            "industry_ids": [12],
            "business_formats": ["b2c"],
        },
        headers={**other_headers, "Idempotency-Key": str(uuid7())},
    )
    assert other_created.status_code == 201
    forbidden = await client.get(f"/v1/businesses/{bid}/configuration", headers=other_headers)
    assert forbidden.status_code == 403
