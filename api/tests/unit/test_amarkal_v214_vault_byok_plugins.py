"""Unit tests for AMARKAL v2.14.0: AES-256-GCM Secret Vault, BYOK AI, M365 OAuth, Custom Plugins."""

from __future__ import annotations

from uuid import uuid7

import pytest

from gorgona_booking.ai_assistant.byok import (
    BYOK_AI_PROVIDERS,
    TenantByokAiConfig,
    probe_byok_ai_connection,
    validate_byok_model,
)
from gorgona_booking.ai_assistant.service import _synthesize_reply_sync
from gorgona_booking.connectors.custom_plugins import (
    PreparedPluginProbe,
    _clean_header_name,
    _clean_slug,
    execute_custom_plugin_probe,
)
from gorgona_booking.connectors.oauth import (
    OAUTH_PROVIDERS,
    build_oauth_authorization_url,
    is_oauth_provider_configured,
)
from gorgona_booking.connectors.service import CONNECTORS_BY_ID
from gorgona_booking.connectors.vault import (
    decrypt_tenant_secret,
    encrypt_tenant_secret,
    mask_secret_hint,
)

pytestmark = pytest.mark.anyio


def test_vault_aes256_gcm_roundtrip_and_cross_tenant_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GBA_VAULT_MASTER_KEY", "test-master-key-for-amarkal-vault-2026-v1")
    tid_a = uuid7()
    tid_b = uuid7()
    plaintext = "sk-ant-api03-example-tenant-secret-value-123456"

    enc = encrypt_tenant_secret(
        plaintext,
        tenant_id=tid_a,
        connector_id="byok_ai_provider",
        kind="byok_ai_key",
        environment="production",
    )
    assert enc.key_hint == "sk-a...56"
    assert plaintext not in enc.ciphertext_b64

    recovered = decrypt_tenant_secret(
        nonce_b64=enc.nonce_b64,
        ciphertext_b64=enc.ciphertext_b64,
        tenant_id=tid_a,
        connector_id="byok_ai_provider",
        kind="byok_ai_key",
        key_version=enc.key_version,
        environment="production",
    )
    assert recovered == plaintext

    # Relocation to another tenant MUST cryptographically fail (DEK + GCM AAD mismatch).
    with pytest.raises(ValueError, match="Unable to decrypt"):
        decrypt_tenant_secret(
            nonce_b64=enc.nonce_b64,
            ciphertext_b64=enc.ciphertext_b64,
            tenant_id=tid_b,
            connector_id="byok_ai_provider",
            kind="byok_ai_key",
            key_version=enc.key_version,
            environment="production",
        )

    # Connector mismatch MUST fail.
    with pytest.raises(ValueError, match="Unable to decrypt"):
        decrypt_tenant_secret(
            nonce_b64=enc.nonce_b64,
            ciphertext_b64=enc.ciphertext_b64,
            tenant_id=tid_a,
            connector_id="microsoft_365",
            kind="byok_ai_key",
            key_version=enc.key_version,
            environment="production",
        )


def test_vault_requires_master_key_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GBA_VAULT_MASTER_KEY", raising=False)
    monkeypatch.delenv("GBA_OAUTH_STATE_SECRET", raising=False)
    monkeypatch.delenv("GBA_EDGE_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="Vault master encryption key"):
        encrypt_tenant_secret(
            "secret-value-12345",
            tenant_id=uuid7(),
            connector_id="byok_ai_provider",
            kind="byok_ai_key",
            environment="production",
        )


def test_mask_secret_hint_hides_short_and_long_values() -> None:
    assert mask_secret_hint("short") == "***"
    assert mask_secret_hint("AIzaSyDummyKey99") == "AIza...99"


def test_microsoft_365_optional_oauth2_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "microsoft_365" in OAUTH_PROVIDERS
    assert "microsoft_365" in CONNECTORS_BY_ID
    assert CONNECTORS_BY_ID["google_calendar"].name == "Google Calendar"

    monkeypatch.delenv("GBA_M365_CLIENT_ID", raising=False)
    monkeypatch.delenv("GBA_M365_CLIENT_SECRET", raising=False)
    assert is_oauth_provider_configured("microsoft_365") is False

    monkeypatch.setenv("GBA_M365_CLIENT_ID", "m365-app-id-123")
    monkeypatch.setenv("GBA_M365_CLIENT_SECRET", "m365-app-secret-456")
    assert is_oauth_provider_configured("microsoft_365") is True
    auth_url = build_oauth_authorization_url(
        connector_id="microsoft_365",
        redirect_uri="https://www.amarkal-platform.com/v1/connectors/oauth/microsoft_365/callback",
        state="signed.m365.state",
    )
    assert auth_url.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?")
    assert "Calendars.ReadWrite" in auth_url
    assert "Mail.Send" in auth_url


async def test_byok_ai_validation_local_probe_and_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert {"anthropic", "google_gemini", "openai"} == set(BYOK_AI_PROVIDERS)
    assert validate_byok_model("anthropic", "") == "claude-sonnet-4-20250514"
    assert validate_byok_model("google_gemini", "gemini-2.5-pro") == "gemini-2.5-pro"
    assert validate_byok_model("openai", "gpt-4.1") == "gpt-4.1"
    with pytest.raises(ValueError, match="Model ID"):
        validate_byok_model("anthropic", "bad model/../../hack")

    cfg = TenantByokAiConfig(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        api_key="sk-ant-test-key-123456",
        enabled=True,
    )
    probe = await probe_byok_ai_connection(cfg, environment="local")
    assert probe.ok is True
    assert "Anthropic (Claude)" in probe.message

    # Verify _synthesize_reply_sync prioritizes BYOK over platform LLM when enabled
    monkeypatch.setattr(
        "gorgona_booking.ai_assistant.service.call_byok_llm_sync",
        lambda config, sys_p, payload: ("byok_anthropic", "Verified grounded Claude reply."),
    )
    res = _synthesize_reply_sync("sys", {"k": "v"}, cfg)
    assert res == ("byok_anthropic", "Verified grounded Claude reply.")


async def test_custom_plugin_validation_and_local_probe() -> None:
    assert _clean_slug("my_erp-bridge_1") == "my_erp-bridge_1"
    with pytest.raises(ValueError, match="slug"):
        _clean_slug("../bad")

    assert _clean_header_name("X-API-Key") == "X-API-Key"
    with pytest.raises(ValueError, match="header"):
        _clean_header_name("Host")
    with pytest.raises(ValueError, match="header"):
        _clean_header_name("Cookie")

    prep = PreparedPluginProbe(
        plugin_id=uuid7(),
        slug="acme_erp",
        display_name="Acme ERP Bridge",
        endpoint_url="https://api.example.com/mcp",
        protocol="mcp_remote",
        auth_header_name="Authorization",
        auth_scheme="Bearer",
        credential="secret-token-1234",
    )
    outcome = await execute_custom_plugin_probe(prep, environment="local")
    assert outcome.ok is True
    assert outcome.status == "local_validated"
