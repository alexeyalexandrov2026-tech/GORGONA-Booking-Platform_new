"""Transport API (ADR-0028..0030); a carrier's dispatcher acts within its grant (ADR-0031)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request
from pydantic import AwareDatetime

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import transport as service
from gorgona_booking.business import transport_assignments as fleet
from gorgona_booking.business import transport_brokerage as brokerage
from gorgona_booking.business import transport_carrier_companies as carriers
from gorgona_booking.business import transport_carrier_pay as carrier_pay
from gorgona_booking.business import transport_clearance as clearance
from gorgona_booking.business import transport_events as events
from gorgona_booking.business import transport_money as money
from gorgona_booking.business import transport_rate_confirmations as confirmations
from gorgona_booking.business import transport_tenders as tenders
from gorgona_booking.business.transport import (
    OrderInput,
    OrderList,
    OrderView,
    TripInput,
    TripList,
    TripView,
)
from gorgona_booking.business.transport_assignments import (
    AssignmentInput,
    DriverInput,
    DriverList,
    DriverView,
    EndInput,
    VehicleInput,
    VehicleList,
    VehicleView,
)
from gorgona_booking.business.transport_brokerage import (
    AuthorityInput,
    AuthorityView,
    CarrierProfileInput,
    CarrierProfileView,
    EligibilityView,
)
from gorgona_booking.business.transport_clearance import (
    ClearanceView,
    DutyInput,
    DutyView,
    PingInput,
    PingView,
    ProfileInput,
    ProfileView,
)
from gorgona_booking.business.transport_events import EventInput
from gorgona_booking.business.transport_money import (
    AccrueInput,
    ComponentInput,
    ComponentView,
    OrderInvoiceInput,
    OrderInvoiceView,
    PayView,
    RateInput,
    RateView,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import (
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/transport", tags=["transport"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.TRANSPORT_READ,
    *,
    allow_delegation: bool = True,
) -> AsyncIterator[TenantAccess]:
    # ADR-0031: a carrier's dispatcher acts through its grant; fleet registration never does.
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=True,
        allow_delegation=allow_delegation,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/orders")
async def get_orders(
    business_id: UUID, request: Request, principal: CurrentPrincipal, after: UUID | None = None
) -> OrderList:
    async with _access(request, principal, business_id) as access:
        return await service.list_orders(access.conn, after)


@router.get("/orders/{order_id}")
async def get_order(
    business_id: UUID, order_id: UUID, request: Request, principal: CurrentPrincipal
) -> OrderView:
    async with _access(request, principal, business_id) as access:
        view = await service.load_order(access.conn, order_id)
        if view is None:
            raise NotFoundError("Order not found", order_id=str(order_id))
        return view


@router.put("/orders/{order_id}")
async def put_order(
    business_id: UUID,
    order_id: UUID,
    body: OrderInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> OrderView:
    """ADR-0028 decision 3: the whole order and its loads, with the expected revision."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_PLAN) as access:
        return await service.save_order(
            access.conn,
            business_id,
            order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/trips")
async def get_trips(
    business_id: UUID, request: Request, principal: CurrentPrincipal, after: UUID | None = None
) -> TripList:
    async with _access(request, principal, business_id) as access:
        return await service.list_trips(access.conn, after)


@router.get("/trips/{trip_id}")
async def get_trip(
    business_id: UUID, trip_id: UUID, request: Request, principal: CurrentPrincipal
) -> TripView:
    async with _access(request, principal, business_id) as access:
        view = await service.load_trip(access.conn, trip_id)
        if view is None:
            raise NotFoundError("Trip not found", trip_id=str(trip_id))
        return view


@router.put("/trips/{trip_id}")
async def put_trip(
    business_id: UUID,
    trip_id: UUID,
    body: TripInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> TripView:
    """ADR-0028 decision 4: the whole planned trip, its stops and legs, with its revision."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_PLAN) as access:
        return await service.save_trip(
            access.conn,
            business_id,
            trip_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/drivers")
async def get_drivers(
    business_id: UUID, request: Request, principal: CurrentPrincipal, after: UUID | None = None
) -> DriverList:
    async with _access(request, principal, business_id) as access:
        return await fleet.list_drivers(access.conn, after)


@router.get("/drivers/{driver_id}")
async def get_driver(
    business_id: UUID, driver_id: UUID, request: Request, principal: CurrentPrincipal
) -> DriverView:
    async with _access(request, principal, business_id) as access:
        view = await fleet.load_driver(access.conn, driver_id)
        if view is None:
            raise NotFoundError("Driver not found", driver_id=str(driver_id))
        return view


@router.put("/drivers/{driver_id}")
async def put_driver(
    business_id: UUID,
    driver_id: UUID,
    body: DriverInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DriverView:
    """ADR-0029 decision 1: a driver with its own lane in its branch."""
    async with _access(
        request, principal, business_id, Permission.TRANSPORT_MANAGE, allow_delegation=False
    ) as access:
        access.require_location(body.location_id)
        return await fleet.save_driver(
            access.conn,
            business_id,
            driver_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/vehicles")
async def get_vehicles(
    business_id: UUID, request: Request, principal: CurrentPrincipal, after: UUID | None = None
) -> VehicleList:
    async with _access(request, principal, business_id) as access:
        return await fleet.list_vehicles(access.conn, after)


@router.get("/vehicles/{vehicle_id}")
async def get_vehicle(
    business_id: UUID, vehicle_id: UUID, request: Request, principal: CurrentPrincipal
) -> VehicleView:
    async with _access(request, principal, business_id) as access:
        view = await fleet.load_vehicle(access.conn, vehicle_id)
        if view is None:
            raise NotFoundError("Vehicle not found", vehicle_id=str(vehicle_id))
        return view


@router.put("/vehicles/{vehicle_id}")
async def put_vehicle(
    business_id: UUID,
    vehicle_id: UUID,
    body: VehicleInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> VehicleView:
    """ADR-0029 decision 1: a truck or trailer with its own lane in its branch."""
    async with _access(
        request, principal, business_id, Permission.TRANSPORT_MANAGE, allow_delegation=False
    ) as access:
        access.require_location(body.location_id)
        return await fleet.save_vehicle(
            access.conn,
            business_id,
            vehicle_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.put("/trips/{trip_id}/assignments/{assignment_id}")
async def put_assignment(
    business_id: UUID,
    trip_id: UUID,
    assignment_id: UUID,
    body: AssignmentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> TripView:
    """ADR-0029 decisions 3-5: assign, or replace the open period of a role, all or none."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_ASSIGN) as access:
        return await fleet.assign(
            access.conn,
            business_id,
            trip_id,
            assignment_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/trips/{trip_id}/assignments/{assignment_id}/end")
async def end_assignment(
    business_id: UUID,
    trip_id: UUID,
    assignment_id: UUID,
    body: EndInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> TripView:
    """ADR-0029 decision 4: end an open period; the rest of its hold is released."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_ASSIGN) as access:
        return await fleet.end_assignment(
            access.conn,
            business_id,
            trip_id,
            assignment_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/trips/{trip_id}/events")
async def post_event(
    business_id: UUID,
    trip_id: UUID,
    body: EventInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> TripView:
    """ADR-0030: a stop event as an idempotent fact; partial delivery per leg."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_EVENTS) as access:
        return await events.record_event(
            access.conn,
            business_id,
            trip_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
            servicer=_servicer(access),
        )


@router.get("/hos-profile")
async def get_hos_profile(
    business_id: UUID, request: Request, principal: CurrentPrincipal
) -> ProfileView:
    async with _access(request, principal, business_id) as access:
        view = await clearance.load_profile(access.conn)
        if view is None:
            raise NotFoundError("No hours-of-service profile")
        return view


@router.put("/hos-profile")
async def put_hos_profile(
    business_id: UUID,
    body: ProfileInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ProfileView:
    """ADR-0032 decision 1: the business's rule profile, replaced with its revision."""
    async with _access(
        request, principal, business_id, Permission.TRANSPORT_MANAGE, allow_delegation=False
    ) as access:
        return await clearance.save_profile(
            access.conn,
            business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/drivers/{driver_id}/duty-records")
async def post_duty_record(
    business_id: UUID,
    driver_id: UUID,
    body: DutyInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DutyView:
    """ADR-0032 decision 2: a driver's duty status over an interval, as an idempotent fact."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_EVENTS) as access:
        return await clearance.record_duty(
            access.conn,
            business_id,
            driver_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/vehicles/{vehicle_id}/pings")
async def post_ping(
    business_id: UUID,
    vehicle_id: UUID,
    body: PingInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> PingView:
    """ADR-0032 decision 2: a vehicle's telematics observation, as an idempotent fact."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_EVENTS) as access:
        return await clearance.record_ping(
            access.conn,
            business_id,
            vehicle_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/trips/{trip_id}/clearance")
async def get_clearance(
    business_id: UUID,
    trip_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    at: Annotated[AwareDatetime | None, Query()] = None,
) -> ClearanceView:
    """ADR-0032 decisions 3-4: computed for a moment; never cleared on stale or unknown data."""
    async with _access(request, principal, business_id) as access:
        return await clearance.clearance(access.conn, trip_id, at or datetime.now(UTC))


# M7a (ADR-0033): money is a company-wide finance task, never a delegate's; invoice and accrual
# take the ledger lock like L4 and L5.


@asynccontextmanager
async def _finance(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission,
    *,
    ledger: bool = False,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        exclusive="ledger" if ledger else None,
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/orders/{order_id}/rate")
async def get_rate(
    business_id: UUID, order_id: UUID, request: Request, principal: CurrentPrincipal
) -> RateView:
    async with _finance(request, principal, business_id, Permission.FINANCE_READ) as access:
        view = await money.load_rate(access.conn, order_id)
        if view is None:
            raise NotFoundError("Order not found", order_id=str(order_id))
        return view


@router.put("/orders/{order_id}/rate")
async def put_rate(
    business_id: UUID,
    order_id: UUID,
    body: RateInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> RateView:
    """ADR-0033 decision 1: a new version of the agreed rate, frozen once invoiced."""
    async with _finance(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await money.save_rate(
            access.conn,
            business_id,
            order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/orders/{order_id}/invoice")
async def get_order_invoice(
    business_id: UUID, order_id: UUID, request: Request, principal: CurrentPrincipal
) -> OrderInvoiceView:
    async with _finance(request, principal, business_id, Permission.FINANCE_READ) as access:
        view = await money.load_order_invoice(access.conn, business_id, order_id)
        if view is None:
            raise NotFoundError("Invoice not found", order_id=str(order_id))
        return view


@router.post("/orders/{order_id}/invoice")
async def post_order_invoice(
    business_id: UUID,
    order_id: UUID,
    body: OrderInvoiceInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> OrderInvoiceView:
    """ADR-0033 decision 2: the order's one FIN-03 receivable draft, once nothing is open."""
    async with _finance(
        request, principal, business_id, Permission.FINANCE_MANAGE, ledger=True
    ) as access:
        return await money.invoice_order(
            access.conn,
            business_id,
            order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/trips/{trip_id}/pay")
async def get_pay(
    business_id: UUID, trip_id: UUID, request: Request, principal: CurrentPrincipal
) -> PayView:
    async with _finance(request, principal, business_id, Permission.FINANCE_READ) as access:
        view = await money.load_pay(access.conn, business_id, trip_id)
        if view is None:
            raise NotFoundError("Trip not found", trip_id=str(trip_id))
        return view


@router.put("/trips/{trip_id}/pay/{component_id}")
async def put_pay_component(
    business_id: UUID,
    trip_id: UUID,
    component_id: UUID,
    body: ComponentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ComponentView:
    """ADR-0033 decision 3: a stable source of one obligation, registered once."""
    async with _finance(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await money.save_component(
            access.conn,
            business_id,
            trip_id,
            component_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/trips/{trip_id}/pay/{component_id}/accrue")
async def post_pay_accrual(
    business_id: UUID,
    trip_id: UUID,
    component_id: UUID,
    body: AccrueInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ComponentView:
    """ADR-0033 decision 4: the component's one FIN-03 payable accrual on a closed trip."""
    async with _finance(
        request, principal, business_id, Permission.FINANCE_MANAGE, ledger=True
    ) as access:
        return await money.accrue_component(
            access.conn,
            business_id,
            trip_id,
            component_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


# N1 (ADR-0034): broker authority and carrier profiles; owners and managers with transport.broker,
# company-wide, never a delegate.


@asynccontextmanager
async def _broker(
    request: Request, principal: CurrentPrincipal, business_id: UUID
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.TRANSPORT_BROKER,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/broker-authority")
async def get_broker_authority(
    business_id: UUID, request: Request, principal: CurrentPrincipal
) -> AuthorityView:
    async with _broker(request, principal, business_id) as access:
        return await brokerage.load_authority(access.conn)


@router.put("/broker-authority")
async def put_broker_authority(
    business_id: UUID,
    body: AuthorityInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> AuthorityView:
    """ADR-0034 decision 1: a new version of the business's broker authority."""
    async with _broker(request, principal, business_id) as access:
        return await brokerage.save_authority(
            access.conn,
            business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/broker-authority/eligibility")
async def get_broker_eligibility(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    on: Annotated[date, Query()],
) -> EligibilityView:
    """ADR-0034 decision 3: computed for a date, never stored."""
    async with _broker(request, principal, business_id) as access:
        view = await brokerage.load_authority(access.conn)
        return brokerage.authority_eligibility(view, on)


def _servicer(access: TenantAccess) -> UUID | None:
    """N4: the servicing company of a delegated request, None for the business's own staff."""
    return None if access.delegation is None else access.delegation.servicer_business_id


@asynccontextmanager
async def _carrier(
    request: Request, principal: CurrentPrincipal, business_id: UUID
) -> AsyncIterator[tuple[TenantAccess, UUID]]:
    """N4: a carrier company's delegate under a grant with transport.tender; never a role."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_TENDER) as access:
        servicer = _servicer(access)
        if servicer is None:
            raise PermissionDeniedError("Only the carrier's company answers here")
        yield access, servicer


@router.get("/tenders/{tender_id}/accrual")
async def get_tender_accrual(
    business_id: UUID, tender_id: UUID, request: Request, principal: CurrentPrincipal
) -> carrier_pay.CarrierPayView:
    async with _broker(request, principal, business_id) as access:
        view = await carrier_pay.load_pay(access.conn, business_id, tender_id)
        if view is None:
            raise NotFoundError("Accrual not found", tender_id=str(tender_id))
        return view


@router.post("/tenders/{tender_id}/accrual")
async def post_tender_accrual(
    business_id: UUID,
    tender_id: UUID,
    body: carrier_pay.CarrierPayInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> carrier_pay.CarrierPayView:
    """N5: the carrier's one FIN-03 payable for an accepted tender with closed legs."""
    async with _broker(request, principal, business_id) as access:
        return await carrier_pay.accrue(
            access.conn,
            business_id,
            tender_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/orders/{order_id}/margin")
async def get_order_margin(
    business_id: UUID, order_id: UUID, request: Request, principal: CurrentPrincipal
) -> carrier_pay.MarginView:
    """N5: revenue less the order's own carrier pay; derived, never stored."""
    async with _broker(request, principal, business_id) as access:
        view = await carrier_pay.load_margin(access.conn, business_id, order_id)
        if view is None:
            raise NotFoundError("Order not found", order_id=str(order_id))
        return view


@router.get("/carriers/{counterparty_id}/company")
async def get_carrier_company(
    business_id: UUID, counterparty_id: UUID, request: Request, principal: CurrentPrincipal
) -> carriers.LinkView:
    async with _broker(request, principal, business_id) as access:
        view = await carriers.load_link(access.conn, counterparty_id)
        if view is None:
            raise NotFoundError("Carrier not found", counterparty_id=str(counterparty_id))
        return view


@router.put("/carriers/{counterparty_id}/company")
async def put_carrier_company(
    business_id: UUID,
    counterparty_id: UUID,
    body: carriers.LinkInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> carriers.LinkView:
    """N4: link a carrier to its own company on the platform, or unlink it."""
    async with _broker(request, principal, business_id) as access:
        view = await carriers.save_link(
            access.conn,
            business_id,
            counterparty_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
        if view is None:
            raise NotFoundError("Carrier not found", counterparty_id=str(counterparty_id))
        return view


@router.post("/tenders/{tender_id}/carrier-answers")
async def post_tender_carrier_answer(
    business_id: UUID,
    tender_id: UUID,
    body: tenders.CarrierAnswerInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> tenders.TenderView:
    """N4: the carrier answers its tender in its own company, through its grant."""
    async with _carrier(request, principal, business_id) as (access, servicer):
        view = await tenders.answer_tender(
            access.conn,
            business_id,
            tender_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
            servicer=servicer,
        )
        if view is None:
            raise NotFoundError("Tender not found", tender_id=str(tender_id))
        return view


@router.post("/tenders/{tender_id}/rate-confirmation/{revision}/carrier-answers")
async def post_rate_confirmation_carrier_answer(
    business_id: UUID,
    tender_id: UUID,
    revision: Annotated[int, Path(ge=1, le=2_147_483_647)],
    body: confirmations.CarrierConfirmationAnswerInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> confirmations.RateConfirmationView:
    """N4: the carrier answers one version in its own company, through its grant."""
    async with _carrier(request, principal, business_id) as (access, servicer):
        view = await confirmations.answer(
            access.conn,
            business_id,
            tender_id,
            revision,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
            servicer=servicer,
        )
        if view is None:
            raise NotFoundError("Rate confirmation not found", tender_id=str(tender_id))
        return view


@router.get("/carriers/{counterparty_id}/profile")
async def get_carrier_profile(
    business_id: UUID, counterparty_id: UUID, request: Request, principal: CurrentPrincipal
) -> CarrierProfileView:
    async with _broker(request, principal, business_id) as access:
        view = await brokerage.load_profile(access.conn, counterparty_id)
        if view is None:
            raise NotFoundError("Carrier not found", counterparty_id=str(counterparty_id))
        return view


@router.put("/carriers/{counterparty_id}/profile")
async def put_carrier_profile(
    business_id: UUID,
    counterparty_id: UUID,
    body: CarrierProfileInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CarrierProfileView:
    """ADR-0034 decision 2: a new version of a carrier's profile."""
    async with _broker(request, principal, business_id) as access:
        view = await brokerage.save_profile(
            access.conn,
            business_id,
            counterparty_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
        if view is None:
            raise NotFoundError("Carrier not found", counterparty_id=str(counterparty_id))
        return view


@router.get("/carriers/{counterparty_id}/eligibility")
async def get_carrier_eligibility(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    on: Annotated[date, Query()],
) -> EligibilityView:
    """ADR-0034 decision 3: computed for a date; every failing condition is named."""
    async with _broker(request, principal, business_id) as access:
        view = await brokerage.load_profile(access.conn, counterparty_id)
        if view is None:
            raise NotFoundError("Carrier not found", counterparty_id=str(counterparty_id))
        return brokerage.carrier_eligibility(view, on)


# N2: tenders of trip legs to other carriers; transport.broker, company-wide.


@router.get("/trips/{trip_id}/tenders")
async def get_trip_tenders(
    business_id: UUID, trip_id: UUID, request: Request, principal: CurrentPrincipal
) -> tenders.TenderListView:
    async with _broker(request, principal, business_id) as access:
        view = await tenders.list_tenders(access.conn, trip_id)
        if view is None:
            raise NotFoundError("Trip not found", trip_id=str(trip_id))
        return view


@router.get("/tenders/{tender_id}")
async def get_tender(
    business_id: UUID, tender_id: UUID, request: Request, principal: CurrentPrincipal
) -> tenders.TenderView:
    async with _broker(request, principal, business_id) as access:
        view = await tenders.load_tender(access.conn, tender_id)
        if view is None:
            raise NotFoundError("Tender not found", tender_id=str(tender_id))
        return view


@router.put("/tenders/{tender_id}")
async def put_tender(
    business_id: UUID,
    tender_id: UUID,
    body: tenders.TenderInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> tenders.TenderView:
    """N2: offer some legs of a trip to one carrier for a carrier rate."""
    async with _broker(request, principal, business_id) as access:
        return await tenders.save_tender(
            access.conn,
            business_id,
            tender_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/tenders/{tender_id}/answers")
async def post_tender_answer(
    business_id: UUID,
    tender_id: UUID,
    body: tenders.AnswerInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> tenders.TenderView:
    """N2: the carrier's answer or the broker's withdrawal, with its source."""
    async with _broker(request, principal, business_id) as access:
        view = await tenders.answer_tender(
            access.conn,
            business_id,
            tender_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
        if view is None:
            raise NotFoundError("Tender not found", tender_id=str(tender_id))
        return view


# N3: rate confirmations of accepted tenders; transport.broker, company-wide.


@router.get("/tenders/{tender_id}/rate-confirmation")
async def get_rate_confirmation(
    business_id: UUID, tender_id: UUID, request: Request, principal: CurrentPrincipal
) -> confirmations.RateConfirmationView:
    async with _broker(request, principal, business_id) as access:
        view = await confirmations.load_confirmation(access.conn, tender_id)
        if view is None:
            raise NotFoundError("Rate confirmation not found", tender_id=str(tender_id))
        return view


@router.put("/tenders/{tender_id}/rate-confirmation")
async def put_rate_confirmation(
    business_id: UUID,
    tender_id: UUID,
    body: confirmations.ProposalInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> confirmations.RateConfirmationView:
    """N3: propose a new version; it is in force once the carrier agrees."""
    async with _broker(request, principal, business_id) as access:
        view = await confirmations.propose(
            access.conn,
            business_id,
            tender_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
        if view is None:
            raise NotFoundError("Tender not found", tender_id=str(tender_id))
        return view


@router.post("/tenders/{tender_id}/rate-confirmation/{revision}/answers")
async def post_rate_confirmation_answer(
    business_id: UUID,
    tender_id: UUID,
    revision: Annotated[int, Path(ge=1, le=2_147_483_647)],
    body: confirmations.ConfirmationAnswerInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> confirmations.RateConfirmationView:
    """N3: the carrier agrees to or declines one version, with its source."""
    async with _broker(request, principal, business_id) as access:
        view = await confirmations.answer(
            access.conn,
            business_id,
            tender_id,
            revision,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
        if view is None:
            raise NotFoundError("Rate confirmation not found", revision=revision)
        return view
