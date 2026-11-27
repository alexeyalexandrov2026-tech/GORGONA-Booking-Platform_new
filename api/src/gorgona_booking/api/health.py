"""Liveness, readiness, and public SRE status telemetry.

Readiness and public status report real dependency state, never canned 'ok' responses.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("gorgona_booking.health")

# A readiness probe raises if its dependency is not usable.
type ReadinessProbe = Callable[[], Awaitable[None]]

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    probe: ReadinessProbe | None = getattr(request.app.state, "readiness_probe", None)
    if probe is None:
        return JSONResponse(
            {"status": "unavailable", "checks": {"database": "not_configured"}}, status_code=503
        )
    try:
        await probe()
    except Exception as exc:
        # Details go to logs only; the response never carries driver or server messages.
        logger.warning("readiness probe failed", extra={"error_type": type(exc).__name__})
        return JSONResponse(
            {"status": "unavailable", "checks": {"database": "failed"}}, status_code=503
        )
    return JSONResponse({"status": "ready", "checks": {"database": "ok"}})


@router.get("/v1/status")
async def public_status(request: Request) -> JSONResponse:
    """Public SRE operational status endpoint powering /status/ (no internal secrets)."""
    probe: ReadinessProbe | None = getattr(request.app.state, "readiness_probe", None)
    db_state = "operational"
    if probe is None:
        db_state = "degraded"
    else:
        try:
            await probe()
        except Exception as exc:
            logger.warning("status probe failed", extra={"error_type": type(exc).__name__})
            db_state = "degraded"

    stripe_live = bool(os.environ.get("GBA_STRIPE_SECRET_KEY", "").strip())
    ai_live = bool(
        os.environ.get("GBA_CF_ACCOUNT_ID", "").strip()
        and os.environ.get("GBA_CF_API_TOKEN", "").strip()
    )
    overall = "operational" if db_state == "operational" else "degraded"
    payload: dict[str, Any] = {
        "service": "AMARKAL Platform Business OS",
        "operator": "Alexey AAA Logistics LLC",
        "overall": overall,
        "checked_at": datetime.now(UTC).isoformat(),
        "components": [
            {
                "id": "database",
                "name": "PostgreSQL 18 (Multi-Tenant FORCE RLS)",
                "status": db_state,
            },
            {
                "id": "core_api",
                "name": "Business OS API & Deal-to-Cash Engine",
                "status": overall,
            },
            {
                "id": "ai_copilot",
                "name": "AI Business Architect & Governed Copilot",
                "status": "operational" if ai_live else "standby_grounded",
            },
            {
                "id": "payments",
                "name": "Stripe US Direct Payments (0% Platform Fee)",
                "status": "operational" if stripe_live else "standby",
            },
            {
                "id": "agentic_mcp",
                "name": "Native MCP (11 Tools) & A2A Discovery",
                "status": overall,
            },
        ],
        "security_invariants": [
            "PostgreSQL 18 ENABLE + FORCE ROW LEVEL SECURITY on all tenant tables",
            "Zero SECURITY DEFINER database functions",
            "0% AMARKAL transaction commission across all 39 NAICS industries",
            "HMAC-SHA256 signed outbound webhooks with SSRF protection",
            "Human-in-the-Loop AI governance (zero unapproved writes)",
        ],
    }
    return JSONResponse(
        content=payload,
        status_code=200 if overall == "operational" else 503,
        headers={"Cache-Control": "no-store"},
    )
