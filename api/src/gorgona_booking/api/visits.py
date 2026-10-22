"""L3: recipes, visit completion and material consumption (design PACKAGE_L3_DESIGN)."""

from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import ROLE_PERMISSIONS, Permission
from gorgona_booking.business import visits as service
from gorgona_booking.business.visits import (
    CompletionInput,
    CompletionView,
    ConsumptionInput,
    RecipeReplace,
    RecipeView,
)
from gorgona_booking.db.inventory_guard import assert_inventory_ready
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import PermissionDeniedError, authorized_tenant

router = APIRouter(prefix="/v1/salons/{salon_id}", tags=["visits"])


async def _recipe(
    salon_id: UUID,
    owner: service.RecipeOwner,
    owner_id: UUID,
    body: RecipeReplace,
    request: Request,
    principal: CurrentPrincipal,
) -> RecipeView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.CATALOG_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        return await service.replace_recipe(access.conn, owner, owner_id, body)


@router.put("/services/{variant_id}/materials")
async def put_variant_materials(
    salon_id: UUID,
    variant_id: UUID,
    body: RecipeReplace,
    request: Request,
    principal: CurrentPrincipal,
) -> RecipeView:
    """Decision 16: the whole recipe of a variant, with its expected revision."""
    return await _recipe(salon_id, "variant", variant_id, body, request, principal)


@router.put("/add-ons/{add_on_id}/materials")
async def put_add_on_materials(
    salon_id: UUID,
    add_on_id: UUID,
    body: RecipeReplace,
    request: Request,
    principal: CurrentPrincipal,
) -> RecipeView:
    """Decision 16: the whole recipe of an add-on, with its expected revision."""
    return await _recipe(salon_id, "add_on", add_on_id, body, request, principal)


@router.post("/bookings/{booking_id}/complete")
async def complete_visit(
    salon_id: UUID,
    booking_id: UUID,
    body: CompletionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CompletionView:
    """Decisions 17-18: booking rights of a member and the caller's branch scope.

    Not delegated: delegation stays exactly the booking workspace.
    """
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.BOOKING_WRITE,
        request_id=get_request_id(request),
        allow_location_scope=True,
    ) as access:
        await assert_location_scope_ready(access.conn)
        return await service.complete_visit(
            access.conn,
            salon_id,
            booking_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/bookings/{booking_id}/consumption")
async def post_consumption(
    salon_id: UUID,
    booking_id: UUID,
    body: ConsumptionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CompletionView:
    """Decision 19: the rights of any write-off, under the ledger posting lock."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.INVENTORY_MANAGE,
        request_id=get_request_id(request),
        exclusive="ledger",
    ) as access:
        finance = (
            access.via == "membership"
            and access.location_id is None
            and access.role is not None
            and Permission.FINANCE_MANAGE in ROLE_PERMISSIONS[access.role]
        )
        if not finance:
            raise PermissionDeniedError("Posting a consumption also requires finance access")
        await assert_location_scope_ready(access.conn)
        await assert_inventory_ready(access.conn)
        return await service.post_consumption(
            access.conn,
            salon_id,
            booking_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
