"""Construction API (ADR-0035): projects, estimates, contract, budget, commitments, costs and
execution (schedule, daily reports, completed quantities)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import construction as service
from gorgona_booking.business import construction_budget as budget
from gorgona_booking.business import construction_contracts as contracts
from gorgona_booking.business import construction_costs as costs
from gorgona_booking.business import construction_daily_reports as reports
from gorgona_booking.business import construction_progress as progress
from gorgona_booking.business import construction_quality as quality
from gorgona_booking.business import construction_schedule as schedule
from gorgona_booking.business.construction import (
    EstimateInput,
    EstimateList,
    EstimateView,
    ProjectInput,
    ProjectList,
    ProjectView,
    ProposalInput,
)
from gorgona_booking.business.construction_budget import (
    BudgetView,
    CommitmentInput,
    CommitmentList,
    CommitmentView,
    RevisionInput,
)
from gorgona_booking.business.construction_contracts import (
    ChangeOrderInput,
    ChangeOrderList,
    ChangeOrderView,
    ContractInput,
    ContractView,
    DecisionInput,
)
from gorgona_booking.business.construction_costs import (
    CostLinkInput,
    CostLinkList,
    CostLinkView,
    ReversalInput,
)
from gorgona_booking.business.construction_daily_reports import (
    DailyReportInput,
    DailyReportList,
    DailyReportView,
)
from gorgona_booking.business.construction_progress import (
    MeasurementInput,
    MeasurementList,
    MeasurementView,
    ProgressView,
    SiteDate,
)
from gorgona_booking.business.construction_quality import (
    EventInput,
    InspectionInput,
    InspectionList,
    InspectionView,
    ItemInput,
    ItemKind,
    ItemList,
    ItemState,
    ItemView,
)
from gorgona_booking.business.construction_schedule import ScheduleInput, ScheduleView
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/construction", tags=["construction"])
Version = Annotated[int, Path(ge=1, le=100_000)]
Number = Annotated[int, Path(ge=1, le=100_000)]
CostNumber = Annotated[int, Path(ge=1, le=1_000_000)]
ScheduleRevision = Annotated[int | None, Query(ge=1, le=100_000)]
ReportRevision = Annotated[int | None, Query(ge=1, le=1000)]


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


@router.get("/projects/{project_id}/budget")
async def get_budget(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> BudgetView:
    """O3a decision 1: the contract's cost side per line and phase, with what is committed."""
    async with _access(request, principal, business_id) as access:
        return await budget.load_budget(access.conn, project_id)


@router.get("/projects/{project_id}/commitments")
async def get_commitments(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> CommitmentList:
    async with _access(request, principal, business_id) as access:
        return await budget.list_commitments(access.conn, project_id)


@router.get("/projects/{project_id}/commitments/{number}")
async def get_commitment(
    business_id: UUID,
    project_id: UUID,
    number: Number,
    request: Request,
    principal: CurrentPrincipal,
) -> CommitmentView:
    async with _access(request, principal, business_id) as access:
        view = await budget.load_commitment(access.conn, project_id, number)
        if view is None:
            raise NotFoundError("Commitment not found", project_id=str(project_id), number=number)
        return view


@router.post("/projects/{project_id}/commitments")
async def post_commitment(
    business_id: UUID,
    project_id: UUID,
    body: CommitmentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CommitmentView:
    """O3a decisions 3-4: the next subcontract or supplier order, version 1."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await budget.create(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.put("/projects/{project_id}/commitments/{number}")
async def put_commitment(
    business_id: UUID,
    project_id: UUID,
    number: Number,
    body: RevisionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CommitmentView:
    """O3a decision 4: the next version, on the revision the client read; cancelled is final."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await budget.revise(
            access.conn,
            business_id,
            project_id,
            number,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/projects/{project_id}/costs")
async def get_costs(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> CostLinkList:
    async with _access(request, principal, business_id) as access:
        return await costs.list_links(access.conn, project_id)


@router.get("/projects/{project_id}/costs/{number}")
async def get_cost(
    business_id: UUID,
    project_id: UUID,
    number: CostNumber,
    request: Request,
    principal: CurrentPrincipal,
) -> CostLinkView:
    async with _access(request, principal, business_id) as access:
        view = await costs.load_link(access.conn, project_id, number)
        if view is None:
            raise NotFoundError("Cost link not found", project_id=str(project_id), number=number)
        return view


@router.post("/projects/{project_id}/costs")
async def post_cost(
    business_id: UUID,
    project_id: UUID,
    body: CostLinkInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CostLinkView:
    """O3b decisions 1-3: one fact on one budget line, counted once."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await costs.link(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/projects/{project_id}/costs/{number}/reversal")
async def post_cost_reversal(
    business_id: UUID,
    project_id: UUID,
    number: CostNumber,
    body: ReversalInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CostLinkView:
    """O3b decision 4: a link leaves actual with a reason, once; its fact may be linked again."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await costs.reverse(
            access.conn,
            business_id,
            project_id,
            number,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/projects/{project_id}/schedule")
async def get_schedule(
    business_id: UUID,
    project_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: ScheduleRevision = None,
) -> ScheduleView:
    """O4a decision 4: a version of the schedule (the latest by default) with what it derives."""
    async with _access(request, principal, business_id) as access:
        return await schedule.load_schedule(access.conn, project_id, revision)


@router.put("/projects/{project_id}/schedule")
async def put_schedule(
    business_id: UUID,
    project_id: UUID,
    body: ScheduleInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ScheduleView:
    """O4a decisions 2-3: the next version, on the version the client read."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await schedule.put_schedule(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/projects/{project_id}/daily-reports")
async def get_daily_reports(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> DailyReportList:
    async with _access(request, principal, business_id) as access:
        return await reports.list_reports(access.conn, project_id)


@router.get("/projects/{project_id}/daily-reports/{report_date}")
async def get_daily_report(
    business_id: UUID,
    project_id: UUID,
    report_date: SiteDate,
    request: Request,
    principal: CurrentPrincipal,
    revision: ReportRevision = None,
) -> DailyReportView:
    async with _access(request, principal, business_id) as access:
        view = await reports.load_report(access.conn, project_id, report_date, revision)
        if view is None:
            raise NotFoundError(
                "Daily report not found", project_id=str(project_id), date=str(report_date)
            )
        return view


@router.put("/projects/{project_id}/daily-reports/{report_date}")
async def put_daily_report(
    business_id: UUID,
    project_id: UUID,
    report_date: SiteDate,
    body: DailyReportInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DailyReportView:
    """O4a decision 5: the next revision of the report of a site date."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await reports.put_report(
            access.conn,
            business_id,
            project_id,
            report_date,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/projects/{project_id}/progress")
async def get_progress(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> ProgressView:
    """O4a decision 9: completed per line, phase and total, with values."""
    async with _access(request, principal, business_id) as access:
        return await progress.load_progress(access.conn, project_id)


@router.get("/projects/{project_id}/progress/measurements")
async def get_measurements(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> MeasurementList:
    async with _access(request, principal, business_id) as access:
        return await progress.list_measurements(access.conn, project_id)


@router.post("/projects/{project_id}/progress")
async def post_measurement(
    business_id: UUID,
    project_id: UUID,
    body: MeasurementInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> MeasurementView:
    """O4a decisions 6-7: the quantity completed to date on one budget line."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await progress.record(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/projects/{project_id}/inspections")
async def get_inspections(
    business_id: UUID, project_id: UUID, request: Request, principal: CurrentPrincipal
) -> InspectionList:
    async with _access(request, principal, business_id) as access:
        return await quality.list_inspections(access.conn, project_id)


@router.get("/projects/{project_id}/inspections/{number}")
async def get_inspection(
    business_id: UUID,
    project_id: UUID,
    number: CostNumber,
    request: Request,
    principal: CurrentPrincipal,
) -> InspectionView:
    async with _access(request, principal, business_id) as access:
        view = await quality.load_inspection(access.conn, project_id, number)
        if view is None:
            raise NotFoundError("Inspection not found", project_id=str(project_id), number=number)
        return view


@router.post("/projects/{project_id}/inspections")
async def post_inspection(
    business_id: UUID,
    project_id: UUID,
    body: InspectionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> InspectionView:
    """O4b decision 2: the next inspection of the project."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await quality.record_inspection(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/projects/{project_id}/quality-items")
async def get_quality_items(
    business_id: UUID,
    project_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    kind: ItemKind | None = None,
    state: ItemState | None = None,
    phase: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> ItemList:
    """O4b decision 6: items with their derived state, and the summary per phase and kind."""
    async with _access(request, principal, business_id) as access:
        return await quality.list_items(access.conn, project_id, kind, state, phase)


@router.get("/projects/{project_id}/quality-items/{number}")
async def get_quality_item(
    business_id: UUID,
    project_id: UUID,
    number: CostNumber,
    request: Request,
    principal: CurrentPrincipal,
) -> ItemView:
    async with _access(request, principal, business_id) as access:
        view = await quality.load_item(access.conn, project_id, number)
        if view is None:
            raise NotFoundError("Item not found", project_id=str(project_id), number=number)
        return view


@router.post("/projects/{project_id}/quality-items")
async def post_quality_item(
    business_id: UUID,
    project_id: UUID,
    body: ItemInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ItemView:
    """O4b decisions 3-4: the next defect or punch item, open."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await quality.record_item(
            access.conn,
            business_id,
            project_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/projects/{project_id}/quality-items/{number}/events")
async def post_quality_event(
    business_id: UUID,
    project_id: UUID,
    number: CostNumber,
    body: EventInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ItemView:
    """O4b decision 5: the next move of an item, on the events the client saw."""
    async with _access(request, principal, business_id, Permission.CONSTRUCTION_MANAGE) as access:
        return await quality.move_item(
            access.conn,
            business_id,
            project_id,
            number,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
