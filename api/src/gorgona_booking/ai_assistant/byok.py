"""Optional Tenant Bring-Your-Own-Key (BYOK) AI Provider client.

Allows an organization to route AMARKAL's grounded AI Copilot and AI Booking Assistant
through their own direct commercial agreement with Anthropic (Claude), Google (Gemini),
or OpenAI — strictly preserving Grounding, Human-in-the-Loop, strict HTTPS host allowlists
(zero SSRF), short DB transactions, and AES-256-GCM encrypted key storage.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import logging
import re
import ssl
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

from psycopg import AsyncConnection

from gorgona_booking.connectors.vault import get_tenant_secret_decrypted

_LOG = logging.getLogger(__name__)

ByokProviderId = Literal["anthropic", "google_gemini", "openai"]
ByokEngineName = Literal["byok_anthropic", "byok_gemini", "byok_openai"]
BYOK_AI_CONNECTOR_ID = "byok_ai_provider"
_MODEL_RE = re.compile(r"^[a-zA-Z0-9._:-]{3,80}$")


@dataclass(frozen=True)
class ByokProviderSpec:
    id: ByokProviderId
    display_name: str
    engine_name: ByokEngineName
    api_host: str
    default_model: str
    suggested_models: tuple[str, ...]
    key_prefix_hint: str


BYOK_AI_PROVIDERS: dict[ByokProviderId, ByokProviderSpec] = {
    "anthropic": ByokProviderSpec(
        id="anthropic",
        display_name="Anthropic (Claude)",
        engine_name="byok_anthropic",
        api_host="api.anthropic.com",
        default_model="claude-sonnet-4-20250514",
        suggested_models=(
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-latest",
            "claude-3-5-haiku-latest",
        ),
        key_prefix_hint="sk-ant-...",
    ),
    "google_gemini": ByokProviderSpec(
        id="google_gemini",
        display_name="Google (Gemini API)",
        engine_name="byok_gemini",
        api_host="generativelanguage.googleapis.com",
        default_model="gemini-2.5-flash",
        suggested_models=(
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
        ),
        key_prefix_hint="AIza...",
    ),
    "openai": ByokProviderSpec(
        id="openai",
        display_name="OpenAI (GPT)",
        engine_name="byok_openai",
        api_host="api.openai.com",
        default_model="gpt-4.1-mini",
        suggested_models=(
            "gpt-4.1-mini",
            "gpt-4.1",
            "gpt-4o-mini",
        ),
        key_prefix_hint="sk-...",
    ),
}


@dataclass(frozen=True)
class TenantByokAiConfig:
    provider: ByokProviderId
    model: str
    api_key: str
    enabled: bool


@dataclass(frozen=True)
class ByokProbeResult:
    ok: bool
    provider: ByokProviderId
    model: str
    http_status: int | None
    latency_ms: int
    message: str


def validate_byok_model(provider: ByokProviderId, model: str | None) -> str:
    spec = BYOK_AI_PROVIDERS[provider]
    clean = (model or "").strip()
    if not clean:
        return spec.default_model
    if not _MODEL_RE.match(clean):
        raise ValueError("Model ID must be 3-80 characters using letters, numbers, ., _, :, or -.")
    return clean


async def load_active_tenant_byok_ai(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    environment: str,
) -> TenantByokAiConfig | None:
    """Load an enabled tenant BYOK AI config inside an existing short DB transaction."""
    try:
        loaded = await get_tenant_secret_decrypted(
            conn,
            tenant_id=tenant_id,
            connector_id=BYOK_AI_CONNECTOR_ID,
            kind="byok_ai_key",
            environment=environment,
        )
    except Exception as exc:
        _LOG.warning("Skipping tenant BYOK AI config load: %s", type(exc).__name__)
        return None
    if loaded is None:
        return None
    api_key, meta = loaded
    if not bool(meta.get("enabled", True)):
        return None
    raw_provider = str(meta.get("provider") or "").strip()
    if raw_provider not in BYOK_AI_PROVIDERS:
        return None
    provider: ByokProviderId = raw_provider
    try:
        model = validate_byok_model(provider, str(meta.get("model") or ""))
    except ValueError:
        model = BYOK_AI_PROVIDERS[provider].default_model
    return TenantByokAiConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        enabled=True,
    )


def _call_anthropic_sync(
    api_key: str,
    model: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    *,
    max_tokens: int = 360,
) -> tuple[int | None, str | None, str | None]:
    body = json.dumps(
        {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0.25,
            "system": system_prompt,
            "messages": [{"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    conn = http.client.HTTPSConnection(
        "api.anthropic.com", 443, timeout=15.0, context=ssl.create_default_context()
    )
    try:
        conn.request(
            "POST",
            "/v1/messages",
            body=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        resp = conn.getresponse()
        raw = resp.read(65536)
        if resp.status != 200:
            return resp.status, None, f"Anthropic API returned HTTP {resp.status}."
        parsed = json.loads(raw.decode("utf-8"))
        blocks = parsed.get("content") or []
        parts = [
            str(b.get("text", ""))
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        text = "".join(parts).strip()
        return resp.status, (text[:1200] if text else None), None
    except Exception as exc:
        return None, None, f"Anthropic request failed ({type(exc).__name__})."
    finally:
        conn.close()


def _call_byok_gemini_sync(
    api_key: str,
    model: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    *,
    max_tokens: int = 360,
) -> tuple[int | None, str | None, str | None]:
    safe_model = quote(model, safe="._-")
    body = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": json.dumps(user_payload, ensure_ascii=False)}],
                }
            ],
            "generationConfig": {"temperature": 0.25, "maxOutputTokens": max_tokens},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    conn = http.client.HTTPSConnection(
        "generativelanguage.googleapis.com",
        443,
        timeout=15.0,
        context=ssl.create_default_context(),
    )
    try:
        conn.request(
            "POST",
            f"/v1beta/models/{safe_model}:generateContent",
            body=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
        )
        resp = conn.getresponse()
        raw = resp.read(65536)
        if resp.status != 200:
            return resp.status, None, f"Google Gemini API returned HTTP {resp.status}."
        parsed = json.loads(raw.decode("utf-8"))
        candidates = parsed.get("candidates") or []
        if not candidates:
            return resp.status, None, "Google Gemini returned no candidates."
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
        return resp.status, (text[:1200] if text else None), None
    except Exception as exc:
        return None, None, f"Google Gemini request failed ({type(exc).__name__})."
    finally:
        conn.close()


def _call_openai_sync(
    api_key: str,
    model: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    *,
    max_tokens: int = 360,
) -> tuple[int | None, str | None, str | None]:
    body = json.dumps(
        {
            "model": model,
            "temperature": 0.25,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    conn = http.client.HTTPSConnection(
        "api.openai.com", 443, timeout=15.0, context=ssl.create_default_context()
    )
    try:
        conn.request(
            "POST",
            "/v1/chat/completions",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp = conn.getresponse()
        raw = resp.read(65536)
        if resp.status != 200:
            return resp.status, None, f"OpenAI API returned HTTP {resp.status}."
        parsed = json.loads(raw.decode("utf-8"))
        choices = parsed.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return resp.status, None, "OpenAI returned no choices."
        msg = choices[0].get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        text = content.strip() if isinstance(content, str) else ""
        return resp.status, (text[:1200] if text else None), None
    except Exception as exc:
        return None, None, f"OpenAI request failed ({type(exc).__name__})."
    finally:
        conn.close()


def call_byok_llm_sync(
    config: TenantByokAiConfig,
    system_prompt: str,
    user_payload: dict[str, Any],
) -> tuple[ByokEngineName, str] | None:
    """Invoke the tenant's BYOK LLM strictly on allowlisted vendor HTTPS hosts."""
    spec = BYOK_AI_PROVIDERS[config.provider]
    if config.provider == "anthropic":
        _, text, err = _call_anthropic_sync(
            config.api_key, config.model, system_prompt, user_payload
        )
    elif config.provider == "google_gemini":
        _, text, err = _call_byok_gemini_sync(
            config.api_key, config.model, system_prompt, user_payload
        )
    else:
        _, text, err = _call_openai_sync(config.api_key, config.model, system_prompt, user_payload)
    if text:
        return (spec.engine_name, text)
    if err:
        _LOG.warning("Tenant BYOK AI (%s) fallback triggered: %s", config.provider, err)
    return None


def _probe_byok_sync(config: TenantByokAiConfig) -> ByokProbeResult:
    start = time.monotonic()
    sys_prompt = "Reply with exactly: OK"
    payload = {"check": "amarkal_byok_connectivity"}
    if config.provider == "anthropic":
        code, text, err = _call_anthropic_sync(
            config.api_key, config.model, sys_prompt, payload, max_tokens=16
        )
    elif config.provider == "google_gemini":
        code, text, err = _call_byok_gemini_sync(
            config.api_key, config.model, sys_prompt, payload, max_tokens=16
        )
    else:
        code, text, err = _call_openai_sync(
            config.api_key, config.model, sys_prompt, payload, max_tokens=16
        )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    if text:
        return ByokProbeResult(
            ok=True,
            provider=config.provider,
            model=config.model,
            http_status=code,
            latency_ms=elapsed_ms,
            message=(
                f"Connected to {BYOK_AI_PROVIDERS[config.provider].display_name} "
                f"({config.model}) in {elapsed_ms} ms."
            ),
        )
    return ByokProbeResult(
        ok=False,
        provider=config.provider,
        model=config.model,
        http_status=code,
        latency_ms=elapsed_ms,
        message=err or "Provider did not return a response.",
    )


async def probe_byok_ai_connection(
    config: TenantByokAiConfig, *, environment: str
) -> ByokProbeResult:
    """Verify tenant BYOK API key outside any DB transaction."""
    if environment not in ("staging", "production"):
        return ByokProbeResult(
            ok=True,
            provider=config.provider,
            model=config.model,
            http_status=None,
            latency_ms=0,
            message=(
                f"Key encrypted and validated locally for "
                f"{BYOK_AI_PROVIDERS[config.provider].display_name} ({config.model}). "
                "Outbound LLM probe runs in staging/production."
            ),
        )
    return await asyncio.to_thread(_probe_byok_sync, config)
