"""Self-service business onboarding API routes (authenticated via verified OIDC token)."""

import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from gorgona_booking.api.deps import get_verified_token, runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.verifier import VerifiedToken
from gorgona_booking.business.onboarding_presets import IndustryPresetView, all_industry_presets
from gorgona_booking.onboarding.ai_architect import (
    AiBlueprintRequest,
    AiBusinessBlueprint,
    generate_business_blueprint,
)
from gorgona_booking.onboarding.self_service import (
    OnboardingStatusView,
    SelfServiceBusinessInput,
    SelfServiceBusinessResult,
    get_onboarding_status,
    register_business,
)

router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])
CallerToken = Annotated[VerifiedToken, Depends(get_verified_token)]
OnboardingKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]
_BLUEPRINT_WINDOW_SECONDS = 300.0
_BLUEPRINT_MAX_PER_WINDOW = 12
_BLUEPRINT_HITS: dict[str, deque[float]] = defaultdict(deque)


def _enforce_blueprint_rate_limit(request: Request) -> None:
    """Protect hosted AI blueprint generation from unauthenticated cost/DoS spikes."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None or settings.environment not in ("staging", "production"):
        return
    xff = request.headers.get("x-forwarded-for", "")
    client_ip = (
        xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
    )
    now = time.monotonic()
    bucket = _BLUEPRINT_HITS[client_ip]
    cutoff = now - _BLUEPRINT_WINDOW_SECONDS
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _BLUEPRINT_MAX_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many AI blueprint requests. Please wait a few minutes and try again.",
        )
    bucket.append(now)


class OnboardingPresetsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    industries: tuple[IndustryPresetView, ...]


@router.get("/presets", response_model=OnboardingPresetsResponse)
async def list_onboarding_presets() -> OnboardingPresetsResponse:
    return OnboardingPresetsResponse(industries=all_industry_presets())


@router.post("/ai-blueprint", response_model=AiBusinessBlueprint)
async def build_ai_business_blueprint(
    body: AiBlueprintRequest,
    request: Request,
) -> AiBusinessBlueprint:
    """Draft a complete US business workspace structure for human review before creation."""
    _enforce_blueprint_rate_limit(request)
    return await generate_business_blueprint(body)


@router.get("/status", response_model=OnboardingStatusView)
async def onboarding_status(request: Request, token: CallerToken) -> OnboardingStatusView:
    return await get_onboarding_status(runtime_pool(request), token)


@router.post("/businesses", response_model=SelfServiceBusinessResult, status_code=201)
async def create_self_service_business(
    body: SelfServiceBusinessInput,
    request: Request,
    token: CallerToken,
    key: OnboardingKey,
) -> SelfServiceBusinessResult:
    return await register_business(
        runtime_pool(request),
        token,
        body=body,
        key=key,
        request_id=get_request_id(request),
    )
