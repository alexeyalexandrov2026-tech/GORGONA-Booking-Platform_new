"""PG18 integration tests for Growth Settings, Smart Waitlist, AI Assistant, and Owner Copilot."""

from __future__ import annotations

import datetime as dt
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


async def test_waitlist_growth_settings_assistant_and_copilot_end_to_end(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    slug_a = f"fake-gr-a-{uuid7().hex[:6]}"
    slug_b = f"fake-gr-b-{uuid7().hex[:6]}"
    host_a = f"{slug_a}.test"
    host_b = f"{slug_b}.test"
    seed_a = seed_fake_salon(owner_conn, slug=slug_a, host=host_a, environment="test", actor="test")
    seed_b = seed_fake_salon(owner_conn, slug=slug_b, host=host_b, environment="test", actor="test")

    user_a = seed_user(owner_conn, f"growth-owner-a-{uuid7().hex[:6]}")
    user_b = seed_user(owner_conn, f"growth-owner-b-{uuid7().hex[:6]}")
    with owner_tenant_transaction(owner_conn, seed_a.tenant_id):
        owner_conn.execute(
            "insert into gba.memberships (tenant_id, user_id, role) values (%s, %s, 'owner')",
            (seed_a.tenant_id, user_a.user_id),
        )
    with owner_tenant_transaction(owner_conn, seed_b.tenant_id):
        owner_conn.execute(
            "insert into gba.memberships (tenant_id, user_id, role) values (%s, %s, 'owner')",
            (seed_b.tenant_id, user_b.user_id),
        )
    headers_a = idp.bearer(user_a.subject, email=user_a.email)
    headers_b = idp.bearer(user_b.subject, email=user_b.email)

    boot_a = await client.get("/v1/customer/bootstrap", headers={"Host": host_a})
    assert boot_a.status_code == 200, boot_a.text
    boot_data = boot_a.json()
    location_id = boot_data["locations"][0]["id"]
    variant_id = boot_data["variants"][0]["id"]

    # 1. Customer AI Assistant returns grounded live availability strictly for Host A
    assistant = await client.post(
        "/v1/customer/assistant",
        headers={"Host": host_a},
        json={"message": "Do you have any open time tomorrow?"},
    )
    assert assistant.status_code == 200, assistant.text
    cdata = assistant.json()
    assert cdata["version"] == 1
    assert cdata["engine"] == "grounded"
    assert cdata["business_name"]
    assert isinstance(cdata["recommended_slots"], list)

    # 2. Customer joins Smart Waitlist on Host A (no raw PII stored)
    tomorrow = (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1)).isoformat()
    joined = await client.post(
        "/v1/customer/waitlist",
        headers={"Host": host_a},
        json={
            "location_id": location_id,
            "variant_id": variant_id,
            "preferred_day": tomorrow,
            "preferred_window": "afternoon",
            "customer_name": "FAKE Waitlist Guest",
            "contact_channel": "email",
            "contact_value": "waitlist-guest@example.com",
            "notes": "Flexible after 2pm",
        },
    )
    assert joined.status_code == 201, joined.text
    entry = joined.json()
    assert entry["contact_masked"] == "w***@example.com"
    assert "waitlist-guest@example.com" not in joined.text
    assert entry["status"] == "waiting"

    # Cross-tenant customer waitlist check: Host B cannot register Host A's location/variant
    cross_join = await client.post(
        "/v1/customer/waitlist",
        headers={"Host": host_b},
        json={
            "location_id": location_id,
            "variant_id": variant_id,
            "preferred_day": tomorrow,
            "preferred_window": "any",
            "customer_name": "FAKE Cross Guest",
            "contact_channel": "email",
            "contact_value": "cross@example.com",
        },
    )
    assert cross_join.status_code == 404

    # 3. Owner A updates Growth Settings (Google review link + reminder cadence)
    updated = await client.put(
        f"/v1/businesses/{seed_a.tenant_id}/growth/settings",
        headers=headers_a,
        json={
            "google_review_url": "https://g.page/r/fake-studio-review/review",
            "reminder_hours_before": 12,
            "review_delay_hours": 3,
            "rebooking_days_after": 21,
            "waitlist_auto_offer": True,
            "ai_assistant_enabled": True,
            "ai_assistant_tone": "executive_hospitality",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["google_review_url"] == "https://g.page/r/fake-studio-review/review"
    assert updated.json()["reminder_hours_before"] == 12

    # Owner B cannot read Owner A's waitlist or copilot
    forbid_wl = await client.get(
        f"/v1/businesses/{seed_a.tenant_id}/growth/waitlist",
        headers=headers_b,
    )
    assert forbid_wl.status_code == 403
    forbid_cp = await client.post(
        f"/v1/businesses/{seed_a.tenant_id}/copilot",
        headers=headers_b,
        json={"question": "Summary"},
    )
    assert forbid_cp.status_code == 403

    # 4. Owner A lists waitlist & sees the entry; Copilot detects recoverable waitlist revenue
    wl_list = await client.get(
        f"/v1/businesses/{seed_a.tenant_id}/growth/waitlist",
        headers=headers_a,
    )
    assert wl_list.status_code == 200
    assert any(item["id"] == entry["id"] for item in wl_list.json())

    copilot = await client.post(
        f"/v1/businesses/{seed_a.tenant_id}/copilot",
        headers=headers_a,
        json={"question": "What should I focus on today?"},
    )
    assert copilot.status_code == 200, copilot.text
    cp = copilot.json()
    assert cp["metrics"]["waiting_waitlist_count"] >= 1
    assert cp["metrics"]["google_review_url_configured"] is True
    assert any(i["category"] == "revenue_recovery" for i in cp["insights"])

    # 5. Owner A sends one-click waitlist slot offer via notification outbox
    offered = await client.post(
        f"/v1/businesses/{seed_a.tenant_id}/growth/waitlist/{entry['id']}/offer",
        headers=headers_a,
        json={
            "recipient": "waitlist-guest@example.com",
            "starts_at": f"{tomorrow} 15:00",
            "business_name": "FAKE Studio A",
            "action_url": "https://example.test/book/",
        },
    )
    assert offered.status_code == 200, offered.text
    assert offered.json()["status"] == "offered"
    assert offered.json()["offer_notification_id"] is not None

    # 6. Human control over AI: disabling ai_assistant_enabled blocks customer assistant cleanly
    disable = await client.put(
        f"/v1/businesses/{seed_a.tenant_id}/growth/settings",
        headers=headers_a,
        json={"ai_assistant_enabled": False},
    )
    assert disable.status_code == 200
    blocked = await client.post(
        "/v1/customer/assistant",
        headers={"Host": host_a},
        json={"message": "Any slots tomorrow?"},
    )
    assert blocked.status_code == 403
