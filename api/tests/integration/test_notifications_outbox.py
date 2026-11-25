"""PG18 integration tests for Email/SMS outbox, retries, dead-lettering, and RLS."""

from __future__ import annotations

from uuid import UUID, uuid7

import httpx
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.notifications.service import list_outbox
from tests.integration import test_management_api as shared
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


async def test_notifications_outbox_email_sms_retry_dead_letter_and_rls(
    client: httpx.AsyncClient, idp: FakeIdp, app_pool: RuntimePool
) -> None:
    # Self-service create Tenant A and Tenant B
    hdr_a = idp.bearer(f"notif-owner-a-{uuid7()}", email="ownera@example.test", name="Owner A")
    hdr_b = idp.bearer(f"notif-owner-b-{uuid7()}", email="ownerb@example.test", name="Owner B")

    res_a = await client.post(
        "/v1/onboarding/businesses",
        json={
            "business_name": "FAKE Notify Co A",
            "slug": f"fake-notif-a-{uuid7().hex[:8]}",
            "location_name": "Austin",
            "timezone": "America/Chicago",
            "industry_ids": [1],
            "business_formats": ["b2c"],
        },
        headers={**hdr_a, "Idempotency-Key": str(uuid7())},
    )
    assert res_a.status_code == 201, res_a.text
    bid_a = res_a.json()["business_id"]

    res_b = await client.post(
        "/v1/onboarding/businesses",
        json={
            "business_name": "FAKE Notify Co B",
            "slug": f"fake-notif-b-{uuid7().hex[:8]}",
            "location_name": "Boston",
            "timezone": "America/New_York",
            "industry_ids": [2],
            "business_formats": ["b2c"],
        },
        headers={**hdr_b, "Idempotency-Key": str(uuid7())},
    )
    assert res_b.status_code == 201, res_b.text
    bid_b = res_b.json()["business_id"]

    # 1. Readiness diagnostics report sandbox mode truthfully
    ready = await client.get(f"/v1/businesses/{bid_a}/notifications/readiness", headers=hdr_a)
    assert ready.status_code == 200, ready.text
    assert ready.json()["channels"]["email"]["mode"] == "sandbox"
    assert ready.json()["channels"]["sms"]["mode"] == "sandbox"
    assert "booking_confirmation" in ready.json()["templates"]

    # 2. Enqueue & dispatch Email (idempotent)
    email_req = {
        "channel": "email",
        "template_code": "booking_confirmation",
        "recipient": "client@example.com",
        "variables": {
            "business_name": "FAKE Notify Co A",
            "reference": "BK-900",
            "starts_at": "2026-12-05 14:00",
        },
        "idempotency_key": f"email-bk-{uuid7().hex[:8]}",
        "dispatch_now": True,
    }
    sent_email = await client.post(
        f"/v1/businesses/{bid_a}/notifications/enqueue", json=email_req, headers=hdr_a
    )
    assert sent_email.status_code == 201, sent_email.text
    email_data = sent_email.json()
    assert email_data["status"] == "sent"
    assert email_data["provider_name"] == "sandbox"
    assert email_data["recipient_masked"] == "c***@example.com"
    assert "client@example.com" not in sent_email.text

    replay = await client.post(
        f"/v1/businesses/{bid_a}/notifications/enqueue", json=email_req, headers=hdr_a
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == email_data["id"]

    # 3. Enqueue & dispatch SMS (E.164 validated & masked)
    sent_sms = await client.post(
        f"/v1/businesses/{bid_a}/notifications/enqueue",
        json={
            "channel": "sms",
            "template_code": "booking_reminder",
            "recipient": "+14155559876",
            "variables": {
                "business_name": "FAKE Notify Co A",
                "reference": "BK-900",
                "starts_at": "2026-12-05 14:00",
            },
            "idempotency_key": f"sms-bk-{uuid7().hex[:8]}",
            "dispatch_now": True,
        },
        headers=hdr_a,
    )
    assert sent_sms.status_code == 201, sent_sms.text
    assert sent_sms.json()["status"] == "sent"
    assert sent_sms.json()["recipient_masked"] == "+14***9876"

    # 4. Transient failures retry and dead-letter on 3rd attempt
    flaky = await client.post(
        f"/v1/businesses/{bid_a}/notifications/enqueue",
        json={
            "channel": "email",
            "template_code": "invoice_issued",
            "recipient": "retry@fail.invalid",
            "variables": {
                "business_name": "FAKE Notify Co A",
                "reference": "INV-1",
                "amount": "$120.00",
            },
            "idempotency_key": f"email-retry-{uuid7().hex[:8]}",
            "dispatch_now": True,
        },
        headers=hdr_a,
    )
    assert flaky.status_code == 201
    assert flaky.json()["status"] == "failed"
    assert flaky.json()["attempt_count"] == 1
    nid = flaky.json()["id"]

    r2 = await client.post(
        f"/v1/businesses/{bid_a}/notifications/{nid}/dispatch",
        json={"recipient": "retry@fail.invalid"},
        headers=hdr_a,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "failed"
    assert r2.json()["attempt_count"] == 2

    r3 = await client.post(
        f"/v1/businesses/{bid_a}/notifications/{nid}/dispatch",
        json={"recipient": "retry@fail.invalid"},
        headers=hdr_a,
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "dead_lettered"
    assert r3.json()["attempt_count"] == 3

    # 5. Cross-tenant HTTP & DB RLS isolation
    forbid = await client.get(f"/v1/businesses/{bid_a}/notifications/outbox", headers=hdr_b)
    assert forbid.status_code == 403

    async with tenant_transaction(app_pool, UUID(bid_b)) as conn_b:
        assert await list_outbox(conn_b, tenant_id=UUID(bid_b)) == []
