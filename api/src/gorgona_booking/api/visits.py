"""L3-L6: recipes, completion, consumption, billing, commissions and prepaid balances."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import ROLE_PERMISSIONS, Permission
from gorgona_booking.business import commissions, prepaid, visit_billing
from gorgona_booking.business import visits as service
from gorgona_booking.business.commissions import (
    CommissionInput,
    PlanInput,
    PlanView,
    VisitCommissionView,
)
from gorgona_booking.business.prepaid import (
    PrepaidList,
    PrepaidView,
    RedeemInput,
    RedemptionView,
    SaleInput,
)
from gorgona_booking.business.visit_billing import VisitInvoiceInput, VisitInvoiceView
from gorgona_booking.business.visits import (
    CompletionInput,
    CompletionView,
    ConsumptionInput,
    RecipeReplace,
    RecipeView,
)
from gorgona_booking.db.inventory_guard import assert_inventory_ready
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
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


async def _read_recipe(
    salon_id: UUID,
    owner: service.RecipeOwner,
    owner_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> RecipeView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.CATALOG_READ,
        request_id=get_request_id(request),
        allow_location_scope=True,
    ) as access:
        return await service.read_recipe(access.conn, owner, owner_id)


@router.get("/services/{variant_id}/materials")
async def get_variant_materials(
    salon_id: UUID, variant_id: UUID, request: Request, principal: CurrentPrincipal
) -> RecipeView:
    """L7a: the recipe of a variant, read back for the catalog screen."""
    return await _read_recipe(salon_id, "variant", variant_id, request, principal)


@router.get("/add-ons/{add_on_id}/materials")
async def get_add_on_materials(
    salon_id: UUID, add_on_id: UUID, request: Request, principal: CurrentPrincipal
) -> RecipeView:
    """L7a: the recipe of an add-on."""
    return await _read_recipe(salon_id, "add_on", add_on_id, request, principal)


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


@router.get("/bookings/{booking_id}/completion")
async def get_completion(
    salon_id: UUID, booking_id: UUID, request: Request, principal: CurrentPrincipal
) -> CompletionView:
    """L7b1: the completion of a visit for the visit desk; anyone who reads bookings."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.BOOKING_READ,
        request_id=get_request_id(request),
        allow_location_scope=True,
    ) as access:
        await assert_location_scope_ready(access.conn)
        view = await service.load_completion(access.conn, booking_id)
        if view is None:
            raise service.VisitCompletionNotFoundError(
                "This visit is not completed", booking_id=str(booking_id)
            )
        return view


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


@router.post("/bookings/{booking_id}/invoice")
async def bill_visit(
    salon_id: UUID,
    booking_id: UUID,
    body: VisitInvoiceInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> VisitInvoiceView:
    """L4 decisions 22-24 and 27: a company-wide finance member, under the ledger lock."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
        exclusive="ledger",
    ) as access:
        await assert_location_scope_ready(access.conn)
        return await visit_billing.bill_visit(
            access.conn,
            salon_id,
            booking_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/bookings/{booking_id}/invoice")
async def get_visit_invoice(
    salon_id: UUID, booking_id: UUID, request: Request, principal: CurrentPrincipal
) -> VisitInvoiceView:
    """L4 decision 25: the visit's invoice and, once issued, what is paid and what is open."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        view = await visit_billing.load_visit_invoice(access.conn, salon_id, booking_id)
        if view is None:
            raise NotFoundError("This visit has no invoice", booking_id=str(booking_id))
        return view


@router.get("/staff/{resource_id}/commission")
async def get_commission_plan(
    salon_id: UUID, resource_id: UUID, request: Request, principal: CurrentPrincipal
) -> PlanView:
    """L7b2a: a specialist's plan for the Staff screen; finance read access."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        plan = await commissions.load_plan(access.conn, resource_id)
        if plan is None:
            raise commissions.CommissionPlanNotFoundError(
                "This specialist has no commission plan", resource_id=str(resource_id)
            )
        return plan


@router.get("/bookings/{booking_id}/commission")
async def get_visit_commission(
    salon_id: UUID, booking_id: UUID, request: Request, principal: CurrentPrincipal
) -> VisitCommissionView:
    """L7b2a: the commission of a visit for the visit desk; finance read access."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        view = await commissions.load_commission(access.conn, salon_id, booking_id)
        if view is None:
            raise commissions.VisitNotCommissionedError(
                "This visit has no commission", booking_id=str(booking_id)
            )
        return view


@router.put("/staff/{resource_id}/commission")
async def put_commission_plan(
    salon_id: UUID,
    resource_id: UUID,
    body: PlanInput,
    request: Request,
    principal: CurrentPrincipal,
) -> PlanView:
    """L5 decision 28: a specialist's whole plan; finance rights of a company-wide member."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        return await commissions.save_plan(
            access.conn, salon_id, resource_id, principal.user_id, body
        )


@router.post("/bookings/{booking_id}/commission")
async def accrue_commission(
    salon_id: UUID,
    booking_id: UUID,
    body: CommissionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> VisitCommissionView:
    """L5 decisions 29-31: once, after the visit invoice is fully paid, under the ledger lock."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
        exclusive="ledger",
    ) as access:
        await assert_location_scope_ready(access.conn)
        return await commissions.accrue_commission(
            access.conn,
            salon_id,
            booking_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/prepaid")
async def list_prepaid(
    salon_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    counterparty_id: UUID | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
) -> PrepaidList:
    """L7 decision 46: the business's prepaid balances, one page in creation order."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        return await prepaid.list_prepaid(
            access.conn, salon_id, counterparty_id=counterparty_id, after=after, limit=limit
        )


@router.post("/prepaid")
async def sell_prepaid(
    salon_id: UUID,
    body: SaleInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> PrepaidView:
    """L6 decision 34: a package or certificate sold by an invoice line on a liability."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
        exclusive="ledger",
    ) as access:
        await assert_location_scope_ready(access.conn)
        return await prepaid.sell(
            access.conn,
            salon_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/bookings/{booking_id}/redeem")
async def redeem_prepaid(
    salon_id: UUID,
    booking_id: UUID,
    body: RedeemInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> RedemptionView:
    """L6 decisions 36-38: a credit note of the visit invoice, issued at once."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
        exclusive="ledger",
    ) as access:
        await assert_location_scope_ready(access.conn)
        return await prepaid.redeem(
            access.conn,
            salon_id,
            booking_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
