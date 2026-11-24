"""Self-service business onboarding API routes (authenticated via verified OIDC token)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict

from gorgona_booking.api.deps import get_verified_token, runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.verifier import VerifiedToken
from gorgona_booking.business.onboarding_presets import IndustryPresetView, all_industry_presets
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


class OnboardingPresetsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    industries: tuple[IndustryPresetView, ...]


@router.get("/presets", response_model=OnboardingPresetsResponse)
async def list_onboarding_presets() -> OnboardingPresetsResponse:
    return OnboardingPresetsResponse(industries=all_industry_presets())


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
