"""Public rate-limited B2B Demo / Founding Partner Pilot request intake (AMARKAL v2.13.0).

Uses the existing live SMTP/Resend transport without adding extra tables or storing PII.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections import deque
from datetime import UTC, datetime
from uuid import uuid7

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.self_service import enforce_sliding_window_rate_limit, extract_client_ip
from gorgona_booking.notifications.transports import resolve_notification_transports

router = APIRouter(tags=["public-demo"])

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_DEMO_RATE_LIMIT_STORE: dict[str, deque[float]] = {}


class DemoLeadRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    full_name: str = Field(min_length=2, max_length=120)
    company_name: str = Field(min_length=2, max_length=160)
    work_email: str = Field(min_length=5, max_length=160)
    industry: str = Field(min_length=2, max_length=120)
    team_size: str = Field(default="10-50", max_length=40)
    notes: str = Field(default="", max_length=1500)
    source_path: str = Field(default="/", max_length=120)
    website: str = Field(default="", max_length=120)  # Honeypot anti-bot field


class DemoLeadResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    received: bool
    reference_id: str
    message: str


@router.post(
    "/v1/public/demo-requests",
    response_model=DemoLeadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_public_demo_request(
    body: DemoLeadRequest,
    request: Request,
) -> DemoLeadResponse:
    # Honeypot trap: bots filling hidden `website` get a silent synthetic ack
    ref_id = f"DEMO-{str(uuid7())[-6:].upper()}"
    if body.website.strip():
        return DemoLeadResponse(
            received=True,
            reference_id=ref_id,
            message="Thank you. Our team will review your request shortly.",
        )

    clean_email = body.work_email.strip().lower()
    if not _EMAIL_RE.match(clean_email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please enter a valid business email address.",
        )

    settings = getattr(request.app.state, "settings", None)
    env_name = settings.environment if settings is not None else "local"
    if env_name in ("staging", "production"):
        client_ip = extract_client_ip(request)
        enforce_sliding_window_rate_limit(
            _DEMO_RATE_LIMIT_STORE,
            key=client_ip,
            window_seconds=900.0,
            max_requests=5,
            detail="Too many demo requests from this network. Please retry in 15 minutes.",
        )

    notify_to = (
        os.environ.get("GBA_DEMO_NOTIFY_EMAIL", "").strip()
        or os.environ.get("GBA_SMTP_SENDER", "").strip()
        or "ops@amarkal-platform.com"
    )
    transports, _ = resolve_notification_transports()
    email_transport = transports["email"]
    subject = f"[AMARKAL B2B Demo] {body.company_name.strip()} ({body.industry.strip()}) — {ref_id}"
    body_text = (
        f"New B2B Demo / Founding Partner Pilot Request ({ref_id})\n"
        f"Timestamp (UTC): {datetime.now(UTC).isoformat()}\n"
        f"Name: {body.full_name.strip()}\n"
        f"Company: {body.company_name.strip()}\n"
        f"Work Email: {clean_email}\n"
        f"Industry: {body.industry.strip()}\n"
        f"Team Size: {body.team_size.strip()}\n"
        f"Source Page: {body.source_path.strip()}\n"
        f"Notes:\n{body.notes.strip() or '(none)'}\n"
    )
    try:
        await asyncio.to_thread(
            email_transport.send,
            channel="email",
            recipient=notify_to,
            subject=subject[:240],
            body=body_text[:2000],
            idempotency_key=f"demo-lead-{ref_id}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not dispatch your request right now. Please try again in a moment.",
        ) from exc

    return DemoLeadResponse(
        received=True,
        reference_id=ref_id,
        message=(
            f"Request {ref_id} received. The AMARKAL Platform team will reach out to "
            f"{clean_email} with a tailored B2B walkthrough."
        ),
    )
