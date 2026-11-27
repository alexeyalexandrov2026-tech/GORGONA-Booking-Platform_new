"""Unit tests for AMARKAL v2.6 Phase 2: AI Actions, Evidence Bridge & Billing."""

from __future__ import annotations

from uuid import uuid7

import pytest

from gorgona_booking.ai_assistant.actions import build_action_proposals
from gorgona_booking.ai_assistant.evidence_bridge import build_evidence_envelope, redact_pii
from gorgona_booking.ai_assistant.service import CopilotContext
from gorgona_booking.payments.reconciliation import (
    AMARKAL_SAAS_PLANS,
    create_saas_subscription_checkout,
)
from gorgona_booking.payments.stripe_service import StripePaymentError, StripeRuntimeConfig

pytestmark = pytest.mark.anyio


def test_pii_redaction_and_evidence_envelope_enforce_nonprod_scope() -> None:
    cleaned = redact_pii("Call me at +1 (512) 555-0199 or boss@acme.com SSN 123-45-6789")
    assert "boss@acme.com" not in cleaned
    assert "555-0199" not in cleaned
    assert "123-45-6789" not in cleaned
    assert "[redacted-email]" in cleaned
    assert "[redacted-ssn]" in cleaned

    tid = uuid7()
    env_test = build_evidence_envelope(
        tenant_id=tid,
        kind="owner_copilot_query",
        summary="Reach john@doe.com",
        metadata={"email": "leak@doe.com", "engine": "cloudflare", "count": 3},
        environment="staging",
    )
    assert env_test["learning_scope"] == "none"
    assert "email" not in env_test["metadata"]
    assert "john@doe.com" not in env_test["summary"]

    env_prod = build_evidence_envelope(
        tenant_id=tid,
        kind="copilot_action_executed",
        summary="Created MCP key",
        environment="production",
    )
    assert env_prod["learning_scope"] == "tenant_only"


def test_build_action_proposals_adapts_to_live_metrics() -> None:
    ctx = CopilotContext(
        business_name="Austin Builders LLC",
        metrics={
            "ai_assistant_enabled": False,
            "active_mcp_keys_count": 0,
        },
        insights=[],
    )
    proposals = build_action_proposals(ctx)
    kinds = [p.kind for p in proposals]
    assert "enable_growth_automation" in kinds
    assert "create_mcp_api_key" in kinds
    assert "create_stripe_payment_link" in kinds
    assert "export_business_snapshot" in kinds


async def test_saas_plans_zero_commission_and_free_starter_guard() -> None:
    assert len(AMARKAL_SAAS_PLANS) == 3
    for plan in AMARKAL_SAAS_PLANS:
        assert plan.transaction_commission_bps == 0
        assert plan.currency == "USD"

    cfg = StripeRuntimeConfig(
        secret_key="sk_test_dummy",
        publishable_key="pk_test_dummy",
        webhook_secret=None,
        paypal_configured=False,
    )
    with pytest.raises(StripePaymentError) as exc:
        await create_saas_subscription_checkout(
            config=cfg,
            tenant_id=uuid7(),
            plan_id="starter",
            customer_email=None,
            success_url="https://www.amarkal-platform.com/integrations/",
            cancel_url="https://www.amarkal-platform.com/integrations/",
        )
    assert exc.value.code == "INVALID_SAAS_PLAN"
