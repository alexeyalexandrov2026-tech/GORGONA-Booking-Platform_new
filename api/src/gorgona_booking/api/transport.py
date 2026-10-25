"""Transport API (ADR-0028..0030); a carrier's dispatcher acts within its grant (ADR-0031)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import transport as service
from gorgona_booking.business import transport_assignments as fleet
from gorgona_booking.business import transport_clearance as clearance
from gorgona_booking.business import transport_events as events
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
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

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
async def get_orders(business_id: UUID, request: Request, principal: CurrentPrincipal) -> OrderList:
    async with _access(request, principal, business_id) as access:
        return await service.list_orders(access.conn)


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
