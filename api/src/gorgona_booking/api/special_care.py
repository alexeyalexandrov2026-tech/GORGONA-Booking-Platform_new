"""HTTP routes for SPECIAL-02 (0146): consent-gated Healthcare, Veterinary & Social Care."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import special_care as sc
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/care", tags=["clinical_care"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.CARE_READ,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        allow_location_scope=True,
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/subjects", response_model=sc.CareSubjectList)
async def get_subjects(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> sc.CareSubjectList:
    async with _access(request, principal, business_id) as access:
        return await sc.list_subjects(access.conn, business_id)


@router.get("/consents", response_model=sc.CareConsentList)
async def get_consents(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> sc.CareConsentList:
    async with _access(request, principal, business_id) as access:
        return await sc.list_consents(access.conn, business_id)


@router.put("/subjects/{subject_id}", response_model=sc.CareSubjectView)
async def put_subject(
    business_id: UUID,
    subject_id: UUID,
    body: sc.CareSubjectInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sc.CareSubjectView:
    async with _access(request, principal, business_id, Permission.CARE_MANAGE) as access:
        return await sc.save_subject(
            access.conn,
            business_id,
            subject_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.put("/consents/{consent_id}", response_model=sc.CareConsentView)
async def put_consent(
    business_id: UUID,
    consent_id: UUID,
    body: sc.CareConsentInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sc.CareConsentView:
    async with _access(request, principal, business_id, Permission.CARE_MANAGE) as access:
        return await sc.save_consent(
            access.conn,
            business_id,
            consent_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.put("/plans/{plan_id}", response_model=sc.CarePlanView)
async def put_plan(
    business_id: UUID,
    plan_id: UUID,
    body: sc.CarePlanInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sc.CarePlanView:
    async with _access(request, principal, business_id, Permission.CARE_WORK) as access:
        return await sc.save_plan(
            access.conn,
            business_id,
            plan_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/encounters", response_model=sc.CareEncounterList)
async def get_encounters(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    subject_id: UUID | None = None,
) -> sc.CareEncounterList:
    async with _access(request, principal, business_id) as access:
        return await sc.list_encounters(access.conn, business_id, subject_id=subject_id)


@router.put("/encounters/{encounter_id}", response_model=sc.CareEncounterView)
async def put_encounter(
    business_id: UUID,
    encounter_id: UUID,
    body: sc.CareEncounterInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sc.CareEncounterView:
    async with _access(request, principal, business_id, Permission.CARE_WORK) as access:
        return await sc.record_encounter(
            access.conn,
            business_id,
            encounter_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )
