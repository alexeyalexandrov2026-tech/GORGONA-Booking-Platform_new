"""Self-service business onboarding API routes (authenticated via verified OIDC token)."""

import ipaddress
import time
from collections import deque
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
_RATE_LIMIT_MAX_KEYS = 1000
_BLUEPRINT_HITS: dict[str, deque[float]] = {}


def extract_client_ip(request: Request, *, trusted_proxy_hops: int = 1) -> str:
    """Extract client IP without trusting spoofable leftmost X-Forwarded-For values."""
    xff = request.headers.get("x-forwarded-for", "")
    valid_ips: list[str] = []
    for raw in xff.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            valid_ips.append(str(ipaddress.ip_address(token)))
        except ValueError:
            continue
    if len(valid_ips) > trusted_proxy_hops:
        return valid_ips[-(trusted_proxy_hops + 1)]
    if valid_ips:
        return valid_ips[-1]
    return request.client.host if request.client else "unknown"


def enforce_sliding_window_rate_limit(
    store: dict[str, deque[float]],
    *,
    key: str,
    window_seconds: float,
    max_requests: int,
    detail: str,
    now: float | None = None,
) -> None:
    """Bounded in-memory sliding-window rate limiter with stale-key eviction."""
    ts = time.monotonic() if now is None else now
    cutoff = ts - window_seconds

    if len(store) >= _RATE_LIMIT_MAX_KEYS and key not in store:
        stale_keys = [k for k, q in store.items() if not q or q[-1] < cutoff]
        for k in stale_keys:
            store.pop(k, None)
        while len(store) >= _RATE_LIMIT_MAX_KEYS:
            oldest_key = next(iter(store))
            store.pop(oldest_key, None)

    bucket = store.get(key)
    if bucket is None:
        bucket = deque()
        store[key] = bucket
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )
    bucket.append(ts)


def _enforce_blueprint_rate_limit(request: Request) -> None:
    """Protect hosted AI blueprint generation from unauthenticated cost/DoS spikes."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None or settings.environment not in ("staging", "production"):
        return
    client_ip = extract_client_ip(request)
    enforce_sliding_window_rate_limit(
        _BLUEPRINT_HITS,
        key=client_ip,
        window_seconds=_BLUEPRINT_WINDOW_SECONDS,
        max_requests=_BLUEPRINT_MAX_PER_WINDOW,
        detail="Too many AI blueprint requests. Please wait a few minutes and try again.",
    )


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
