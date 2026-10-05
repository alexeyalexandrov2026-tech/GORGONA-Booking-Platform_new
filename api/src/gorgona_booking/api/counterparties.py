"""Company-wide counterparties, manual match decisions and booking links (ADR-0020)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import counterparties as service
from gorgona_booking.business.counterparty_contracts import (
    BookingCandidateList,
    BookingLinkHistory,
    BookingLinkInput,
    BookingLinkResult,
    CounterpartyHistory,
    CounterpartyInput,
    CounterpartyList,
    CounterpartyState,
    CounterpartyView,
    LinkedBookingList,
    MatchCheckInput,
    MatchDecisionInput,
    MatchDecisionList,
    MatchDecisionView,
    MatchList,
)
from gorgona_booking.business.counterparty_matching import (
    booking_candidates,
    check_matches,
    find_duplicates,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["counterparties"])
Limit = Annotated[int, Query(ge=1, le=100)]
Revision = Annotated[int | None, Query(ge=1, le=2_147_483_647)]


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    *,
    write: bool = False,
) -> AsyncIterator[TenantAccess]:
    # No branch, delegation or platform opt-in. Existing authorization checks
    # active membership under its row lock inside this same transaction.
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.COUNTERPARTIES_MANAGE if write else Permission.COUNTERPARTIES_READ,
        request_id=get_request_id(request),
        exclusive="counterparties" if write else None,
    ) as access:
        # Optional modules fail closed if a migration's access boundary or gate
        # is missing or altered, including company-wide sessions.
        await assert_location_scope_ready(access.conn)
        yield access


async def _exists(access: TenantAccess, business: UUID, subject: UUID) -> None:
    if await service.load_counterparty(access.conn, business, subject) is None:
        raise NotFoundError("Counterparty not found")


@router.get("/{business_id}/counterparties")
async def get_counterparties(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    state: CounterpartyState | None = None,
    after: UUID | None = None,
    limit: Limit = 50,
) -> CounterpartyList:
    async with _access(request, principal, business_id) as access:
        return await service.list_counterparties(
            access.conn,
            business_id,
            query=q,
            state=state,
            after=after,
            limit=limit,
        )


@router.post("/{business_id}/counterparties/match-check")
async def post_match_check(
    business_id: UUID,
    body: MatchCheckInput,
    request: Request,
    principal: CurrentPrincipal,
) -> MatchList:
    # Read-only POST keeps personal matching details out of the URL.
    async with _access(request, principal, business_id) as access:
        if body.exclude_id is not None:
            await _exists(access, business_id, body.exclude_id)
        return await check_matches(access.conn, business_id, body)


@router.get("/{business_id}/counterparties/{counterparty_id}")
async def get_counterparty(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> CounterpartyView:
    async with _access(request, principal, business_id) as access:
        result = await service.load_counterparty(
            access.conn,
            business_id,
            counterparty_id,
            revision=revision,
        )
        if result is None:
            raise NotFoundError("Counterparty version not found")
        return result


@router.put("/{business_id}/counterparties/{counterparty_id}")
async def put_counterparty(
    business_id: UUID,
    counterparty_id: UUID,
    body: CounterpartyInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CounterpartyView:
    async with _access(request, principal, business_id, write=True) as access:
        return await service.save_counterparty(
            access.conn,
            business_id=business_id,
            counterparty_id=counterparty_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{business_id}/counterparties/{counterparty_id}/versions")
async def get_versions(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    before: Revision = None,
    limit: Limit = 50,
) -> CounterpartyHistory:
    async with _access(request, principal, business_id) as access:
        return await service.counterparty_history(
            access.conn,
            business_id,
            counterparty_id,
            before=before,
            limit=limit,
        )


@router.get("/{business_id}/counterparties/{counterparty_id}/merged-from")
async def get_merged_from(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> CounterpartyList:
    async with _access(request, principal, business_id) as access:
        return await service.merged_counterparties(
            access.conn,
            business_id,
            counterparty_id,
            after=after,
            limit=limit,
        )


@router.get("/{business_id}/counterparties/{counterparty_id}/duplicates")
async def get_duplicates(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> MatchList:
    async with _access(request, principal, business_id) as access:
        await _exists(access, business_id, counterparty_id)
        return await find_duplicates(access.conn, business_id, counterparty_id)


@router.get("/{business_id}/counterparties/{counterparty_id}/match-decisions")
async def get_match_decisions(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> MatchDecisionList:
    async with _access(request, principal, business_id) as access:
        return await service.list_match_decisions(access.conn, business_id, counterparty_id)


@router.post("/{business_id}/counterparties/{counterparty_id}/match-decisions")
async def post_match_decision(
    business_id: UUID,
    counterparty_id: UUID,
    body: MatchDecisionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> MatchDecisionView:
    async with _access(request, principal, business_id, write=True) as access:
        return await service.decide_match(
            access.conn,
            business_id=business_id,
            counterparty_id=counterparty_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{business_id}/counterparties/{counterparty_id}/booking-candidates")
async def get_booking_candidates(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> BookingCandidateList:
    async with _access(request, principal, business_id) as access:
        await _exists(access, business_id, counterparty_id)
        return await booking_candidates(access.conn, business_id, counterparty_id)


@router.get("/{business_id}/counterparties/{counterparty_id}/bookings")
async def get_linked_bookings(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> LinkedBookingList:
    async with _access(request, principal, business_id) as access:
        return await service.linked_bookings(
            access.conn,
            business_id,
            counterparty_id,
            after=after,
            limit=limit,
        )


@router.get("/{business_id}/counterparties/{counterparty_id}/booking-links")
async def get_booking_link_history(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> BookingLinkHistory:
    async with _access(request, principal, business_id) as access:
        return await service.booking_link_history(
            access.conn,
            business_id,
            counterparty_id,
            after=after,
            limit=limit,
        )


@router.post("/{business_id}/counterparties/{counterparty_id}/booking-links")
async def post_booking_links(
    business_id: UUID,
    counterparty_id: UUID,
    body: BookingLinkInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BookingLinkResult:
    async with _access(request, principal, business_id, write=True) as access:
        return await service.change_booking_links(
            access.conn,
            business_id=business_id,
            counterparty_id=counterparty_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
