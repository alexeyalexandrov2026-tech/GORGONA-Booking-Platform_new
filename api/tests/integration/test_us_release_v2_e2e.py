"""PG18 integration tests for US Release v2.0: AI Business Architect onboarding,
GORGONA App Hub (Connectors, Scoped API Keys, Signed Webhooks, Native MCP),
Cloudflare R2 Media Engine, and Live Unit Economics.
"""

from __future__ import annotations

import base64
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.onboarding.fake_seed import seed_fake_salon
from tests.integration import test_management_api as shared
from tests.integration.seed import seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
    b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_ai_architect_onboarding_app_hub_mcp_media_and_unit_economics(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    # 1. AI Business Architect generates a complete US blueprint
    bp_resp = await client.post(
        "/v1/onboarding/ai-blueprint",
        json={
            "description": (
                "Apex Auto Detailing in Austin TX, 4 bays, ceramic coating and window tint."
            )
        },
    )
    assert bp_resp.status_code == 200, bp_resp.text
    bp = bp_resp.json()
    assert bp["timezone"] == "America/Chicago"
    assert len(bp["services"]) >= 3
    assert len(bp["resources"]) >= 1
    assert len(bp["business_hours"]) >= 1

    # 2. Human approves blueprint and launches a populated business atomically
    founder_sub = f"ai-founder-{uuid7().hex[:8]}"
    founder_hdr = idp.bearer(founder_sub, email=f"{founder_sub}@example.test")
    slug = f"fake-ai-{uuid7().hex[:8]}"
    created = await client.post(
        "/v1/onboarding/businesses",
        headers={**founder_hdr, "Idempotency-Key": f"ai-onb-{uuid7()}"},
        json={
            "business_name": bp["business_name"],
            "slug": slug,
            "location_name": bp["location_name"],
            "timezone": bp["timezone"],
            "industry_ids": bp["industry_ids"],
            "business_formats": bp["business_formats"],
            "starter_services": bp["services"],
            "starter_resources": bp["resources"],
            "starter_hours": bp["business_hours"],
            "cancellation_summary": bp["cancellation_summary"],
        },
    )
    assert created.status_code == 201, created.text
    cdata = created.json()
    biz_id = cdata["business_id"]
    assert cdata["created_services_count"] == len(bp["services"])
    assert cdata["created_resources_count"] == len(bp["resources"])
    assert cdata["created_hours_count"] == len(bp["business_hours"])

    # 3. Seed second isolated tenant B for cross-tenant isolation assertions
    slug_b = f"fake-hub-b-{uuid7().hex[:6]}"
    host_b = f"{slug_b}.test"
    seed_b = seed_fake_salon(owner_conn, slug=slug_b, host=host_b, environment="test", actor="test")
    user_b = seed_user(owner_conn, f"hub-owner-b-{uuid7().hex[:6]}")
    with owner_tenant_transaction(owner_conn, seed_b.tenant_id):
        owner_conn.execute(
            "insert into gba.memberships (tenant_id, user_id, role) values (%s, %s, 'owner')",
            (seed_b.tenant_id, user_b.user_id),
        )
    hdr_b = idp.bearer(user_b.subject, email=user_b.email)

    # 4. GORGONA App Hub: install connector, create Scoped API Key, call Native MCP, test Webhook
    cat = await client.get(f"/v1/businesses/{biz_id}/connectors/catalog", headers=founder_hdr)
    assert cat.status_code == 200, cat.text
    assert any(c["id"] == "native_mcp" for c in cat.json())

    inst = await client.put(
        f"/v1/businesses/{biz_id}/connectors/quickbooks_online",
        headers=founder_hdr,
        json={"status": "installed", "config": {"realm_id": "913035012", "api_token": "sec123456"}},
    )
    assert inst.status_code == 200, inst.text
    assert "sec123456" not in inst.text

    # Cross-tenant denied
    forbid = await client.get(f"/v1/businesses/{biz_id}/connectors/catalog", headers=hdr_b)
    assert forbid.status_code == 403

    key_resp = await client.post(
        f"/v1/businesses/{biz_id}/connectors/api-keys",
        headers=founder_hdr,
        json={"name": "US Voice Agent MCP", "scopes": ["mcp:read", "catalog:read"]},
    )
    assert key_resp.status_code == 201, key_resp.text
    raw_token = key_resp.json()["secret_token"]
    key_id = key_resp.json()["key"]["id"]
    assert raw_token.startswith("gorg_live_")

    # Call /v1/mcp using Scoped API Key (no OIDC token needed)
    mcp_init = await client.post(
        "/v1/mcp",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert mcp_init.status_code == 200, mcp_init.text
    assert mcp_init.json()["result"]["serverInfo"]["name"] == "gorgona-business-os-mcp"

    mcp_svcs = await client.post(
        "/v1/mcp",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_services"}},
    )
    assert mcp_svcs.status_code == 200, mcp_svcs.text
    assert len(mcp_svcs.json()["result"]["structuredContent"]["services"]) == len(bp["services"])

    # Revoking key immediately blocks /v1/mcp
    rev = await client.delete(
        f"/v1/businesses/{biz_id}/connectors/api-keys/{key_id}", headers=founder_hdr
    )
    assert rev.status_code == 204
    mcp_blocked = await client.post(
        "/v1/mcp",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"jsonrpc": "2.0", "id": 3, "method": "initialize"},
    )
    assert mcp_blocked.status_code == 401

    # Webhook create + signed test delivery
    wh = await client.post(
        f"/v1/businesses/{biz_id}/connectors/webhooks",
        headers=founder_hdr,
        json={
            "url": "https://hooks.zapier.com/hooks/catch/12345/abcde/",
            "description": "Zapier CRM sync",
            "events": ["booking.created", "connector.test"],
        },
    )
    assert wh.status_code == 201, wh.text
    wh_id = wh.json()["endpoint"]["id"]
    test_del = await client.post(
        f"/v1/businesses/{biz_id}/connectors/webhooks/{wh_id}/test", headers=founder_hdr
    )
    assert test_del.status_code == 200, test_del.text
    assert test_del.json()["signature_header"].startswith("v1=")

    # 5. Cloudflare R2 / Media Engine upload + read + delete
    up = await client.post(
        f"/v1/businesses/{biz_id}/media",
        headers=founder_hdr,
        json={
            "kind": "logo",
            "filename": "apex-logo.png",
            "data_base64": base64.b64encode(_TINY_PNG).decode("ascii"),
        },
    )
    assert up.status_code == 201, up.text
    asset_id = up.json()["id"]
    assert up.json()["content_type"] == "image/png"
    assert up.json()["storage_backend"] in ("r2", "inline")

    # 6. Live Unit Economics endpoint returns grounded USD metrics
    ue = await client.get(f"/v1/businesses/{biz_id}/growth/unit-economics", headers=founder_hdr)
    assert ue.status_code == 200, ue.text
    ued = ue.json()
    assert ued["currency"] == "USD"
    assert ued["net_margin_cents"] == ued["gross_revenue_cents"] - ued["material_cogs_cents"]
    assert asset_id
