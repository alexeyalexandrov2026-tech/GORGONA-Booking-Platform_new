"""Privacy-safe evidence bridge from `api/` to the isolated `ai/` learning plane (GCP Pub/Sub).

Invariants:
- Direct contact fields (emails, phones, payment card numbers, SSNs) are ALWAYS redacted.
- Non-production environments (`local`, `test`, `ci`, `staging`) mark `learning_scope = 'none'`.
- Publishing runs strictly outside PostgreSQL transactions and fails open (never blocks user APIs).
"""

from __future__ import annotations

import asyncio
import base64
import http.client
import json
import logging
import os
import re
import time
import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

_LOG = logging.getLogger(__name__)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

_TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0.0}


def redact_pii(text: str) -> str:
    """NFKC-normalize and strip emails, phone numbers, card numbers, and SSNs."""
    clean = unicodedata.normalize("NFKC", text)
    clean = _EMAIL_RE.sub("[redacted-email]", clean)
    clean = _SSN_RE.sub("[redacted-ssn]", clean)
    clean = _CARD_RE.sub("[redacted-number]", clean)
    clean = _PHONE_RE.sub("[redacted-phone]", clean)
    return clean.strip()[:1000]


def build_evidence_envelope(
    *,
    tenant_id: UUID,
    kind: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    """Construct a tenant-scoped, PII-redacted evidence envelope for `gorgona-ai-intake`."""
    env = (environment or os.environ.get("GBA_ENV", "local")).strip().lower()
    learning_scope = "tenant_only" if env == "production" else "none"
    safe_meta: dict[str, str | int | float | bool] = {}
    for k, v in (metadata or {}).items():
        key = str(k).strip().lower()
        if any(bad in key for bad in ("email", "phone", "secret", "token", "password", "card")):
            continue
        if isinstance(v, (bool, int, float)):
            safe_meta[key] = v
        elif isinstance(v, str):
            safe_meta[key] = redact_pii(v)[:200]
    return {
        "schema_version": 1,
        "evidence_id": str(uuid7()),
        "tenant_id": str(tenant_id),
        "environment": env,
        "learning_scope": learning_scope,
        "kind": kind,
        "summary": redact_pii(summary),
        "metadata": safe_meta,
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def _gcp_metadata_token() -> str | None:
    static = os.environ.get("GBA_AI_PUBSUB_ACCESS_TOKEN", "").strip()
    if static:
        return static
    now = time.monotonic()
    if _TOKEN_CACHE["token"] and now < float(_TOKEN_CACHE["expires_at"]):
        return str(_TOKEN_CACHE["token"])
    conn = http.client.HTTPConnection("metadata.google.internal", 80, timeout=3.0)
    try:
        conn.request(
            "GET",
            "/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
        )
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            return None
        payload = json.loads(raw.decode("utf-8"))
        token = str(payload["access_token"])
        expires_in = float(payload.get("expires_in", 300))
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expires_at"] = now + max(30.0, expires_in - 60.0)
        return token
    except Exception:
        return None
    finally:
        conn.close()


def _publish_pubsub_sync(envelope: dict[str, Any]) -> bool:
    topic = os.environ.get("GBA_AI_PUBSUB_TOPIC", "").strip()
    if not topic:
        return False
    token = _gcp_metadata_token()
    if not token:
        return False
    encoded = base64.b64encode(json.dumps(envelope, ensure_ascii=False).encode("utf-8")).decode(
        "ascii"
    )
    body = json.dumps({"messages": [{"data": encoded}]}).encode("utf-8")
    conn = http.client.HTTPSConnection("pubsub.googleapis.com", 443, timeout=5.0)
    try:
        conn.request(
            "POST",
            f"/v1/{topic}:publish",
            body=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        resp.read()
        return 200 <= resp.status < 300
    except Exception as exc:
        _LOG.debug("Pub/Sub evidence publish skipped: %s", type(exc).__name__)
        return False
    finally:
        conn.close()


async def emit_evidence_nonblocking(
    *,
    tenant_id: UUID,
    kind: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Publish redacted evidence to `ai/` Pub/Sub outside DB transactions (no-op if unset)."""
    if not os.environ.get("GBA_AI_PUBSUB_TOPIC", "").strip():
        return False
    envelope = build_evidence_envelope(
        tenant_id=tenant_id,
        kind=kind,
        summary=summary,
        metadata=metadata,
    )
    return await asyncio.to_thread(_publish_pubsub_sync, envelope)
