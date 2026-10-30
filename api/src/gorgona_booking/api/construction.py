"""Construction API (ADR-0035): projects and estimate versions; nothing is delegated in O1."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import construction as service
from gorgona_booking.business import construction_contracts as contracts
from gorgona_booking.business.construction import (
    EstimateInput,
    EstimateList,
    EstimateView,
    ProjectInput,
    ProjectList,
    ProjectView,
    ProposalInput,
)
from gorgona_booking.business.construction_contracts import (
    ChangeOrderInput,
    ChangeOrderList,
    ChangeOrderView,
    ContractInput,
    ContractView,
    DecisionInput,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/construction", tags=["construction"])
Version = Annotated[int, Path(ge=1, le=100_000)]
Number = Annotated[int, Path(ge=1, le=100_000)]


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.CONSTRUCTION_READ,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=True,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/projects")
async def get_projects(
    business_id: UUID, request: Request, principal: CurrentPrincipal, after: UUID | None = None
) -> ProjectList:
    async with _access(request, principal, business_id) as access:
        return await service.list_projects(access.conn, after)


@router.get("/projects/{project_id}")
async def get_project(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> ProjectView:
    async with _access(request, principal, business_id) as access:
        view = await service.load_project(access.conn, project_id)
        if view is None:
            raise NotFoundError("Project not found", project_id=str(project_id))
        return view


@router.put("/projects/{project_id}")
async def put_project(
    business_id: UUID,
    project_id: UUID,
    body: ProjectInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ProjectView:
    """ADR-0035 decision 3: the whole project, with the expected revision."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await service.save_project(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/projects/{project_id}/estimates")
async def get_estimates(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> EstimateList:
    async with _access(request, principal, business_id) as access:
        return await service.list_estimates(access.conn, project_id)


@router.get("/projects/{project_id}/estimates/{version}")
async def get_estimate(
    business_id: UUID,
    project_id: UUID,
    version: Version,
    request: Request,
    principal: CurrentPrincipal,
) -> EstimateView:
    async with _access(request, principal, business_id) as access:
        view = await service.load_estimate(access.conn, project_id, version)
        if view is None:
            raise NotFoundError("Estimate not found", project_id=str(project_id), version=version)
        return view


@router.post("/projects/{project_id}/estimates")
async def post_estimate(
    business_id: UUID,
    project_id: UUID,
    body: EstimateInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> EstimateView:
    """ADR-0035 decision 4: the next insert-only version, on the latest one the client read."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await service.save_estimate(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/projects/{project_id}/estimates/{version}/proposal")
async def post_proposal(
    business_id: UUID,
    project_id: UUID,
    version: Version,
    body: ProposalInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> EstimateView:
    """ADR-0035 decision 6: the latest version is stamped as the proposal, once."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await service.propose(
            access.conn,
            business_id,
            project_id,
            version,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/projects/{project_id}/contract")
async def get_contract(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> ContractView:
    async with _access(request, principal, business_id) as access:
        view = await contracts.load_contract(access.conn, project_id)
        if view is None:
            raise NotFoundError("Contract not found", project_id=str(project_id))
        return view


@router.post("/projects/{project_id}/contract")
async def post_contract(
    business_id: UUID,
    project_id: UUID,
    body: ContractInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ContractView:
    """O2 decision 1: the customer's acceptance of the latest proposal, the original contract."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_APPROVE) as access:
        return await contracts.accept(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/projects/{project_id}/change-orders")
async def get_change_orders(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> ChangeOrderList:
    async with _access(request, principal, business_id) as access:
        return await contracts.list_change_orders(access.conn, project_id)


@router.get("/projects/{project_id}/change-orders/{number}")
async def get_change_order(
    business_id: UUID,
    project_id: UUID,
    number: Number,
    request: Request,
    principal: CurrentPrincipal,
) -> ChangeOrderView:
    async with _access(request, principal, business_id) as access:
        view = await contracts.load_change_order(access.conn, project_id, number)
        if view is None:
            raise NotFoundError("Change order not found", project_id=str(project_id), number=number)
        return view


@router.post("/projects/{project_id}/change-orders")
async def post_change_order(
    business_id: UUID,
    project_id: UUID,
    body: ChangeOrderInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ChangeOrderView:
    """O2 decision 3: the next change order, proposed."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await contracts.propose_change(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/projects/{project_id}/change-orders/{number}/decision")
async def post_change_order_decision(
    business_id: UUID,
    project_id: UUID,
    number: Number,
    body: DecisionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ChangeOrderView:
    """O2 decision 4: the customer's answer needs `construction.approve`; a withdrawal `manage`."""
    permission = (
        Permission.CONSTRUCTION_MANAGE
        if body.decision == "withdrawn"
        else Permission.CONSTRUCTION_APPROVE
    )
    async with _access(request, principal, business_id, permission) as access:
        return await contracts.decide(
            access.conn,
            business_id,
            project_id,
            number,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
