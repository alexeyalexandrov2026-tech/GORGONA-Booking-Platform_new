"""M1: the transport module and the planning model (package M, TMS-01; FAKE data only).

ADR-0028 and docs/plan/PACKAGE_M1_DESIGN_2026-10-23.md: shipment order, load, trip, stop and leg are
separate; one trip carries several loads, a load splits across trips, nothing is over-planned.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_counterparties import card
from tests.integration.test_l8b2_finance_races import race
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = ["client", "idp", "manager_a", "manager_b"]
ENABLED = ["booking_resources", "counterparties", "transport"]


def error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def local(zone: str, hour: int, minute: int = 0) -> str:
    """A time on 2031-06-02 in `zone`, with its offset."""
    return datetime(2031, 6, 2, hour, minute, tzinfo=ZoneInfo(zone)).isoformat()


def load(load_id: UUID, quantity: int, description: str = "FAKE pallets") -> dict[str, Any]:
    return {
        "load_id": str(load_id),
        "description": description,
        "quantity": quantity,
        "unit": "pallet",
        "weight_grams": 500000 * quantity,
    }


def stop(kind: str, place: str, zone: str, start: int, end: int) -> dict[str, Any]:
    return {
        "kind": kind,
        "place": place,
        "time_zone": zone,
        "window_start": local(zone, start),
        "window_end": local(zone, end),
    }


def leg(load_id: UUID, quantity: int, pickup: int, delivery: int) -> dict[str, Any]:
    return {
        "load_id": str(load_id),
        "quantity": quantity,
        "pickup_stop": pickup,
        "delivery_stop": delivery,
    }


CHICAGO, INDIANAPOLIS, NEW_YORK = (
    "America/Chicago",
    "America/Indiana/Indianapolis",
    "America/New_York",
)


@dataclass(frozen=True)
class Transport:
    client: httpx.AsyncClient
    world: BookingWorld
    owner_conn: psycopg.Connection
    headers: dict[str, str]
    customer: UUID

    @property
    def tenant(self) -> UUID:
        return self.world.a.tenant_id

    @property
    def base(self) -> str:
        return f"/v1/businesses/{self.tenant}/transport"

    async def put(
        self, path: str, body: dict[str, Any], headers: dict[str, str] | None = None
    ) -> httpx.Response:
        return await self.client.put(
            self.base + path,
            json={"schema_version": 1, **body},
            headers={**(headers or self.headers), "Idempotency-Key": str(uuid7())},
        )

    async def get(self, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.client.get(self.base + path, headers=headers or self.headers)

    async def order(
        self, order_id: UUID, loads: list[dict[str, Any]], revision: int = 0, **changes: Any
    ) -> httpx.Response:
        return await self.put(
            f"/orders/{order_id}",
            {
                "expected_revision": revision,
                "customer_id": str(self.customer),
                "reference": f"FAKE-SO-{order_id.hex[-8:]}",
                "loads": loads,
                **changes,
            },
        )

    async def trip(
        self,
        trip_id: UUID,
        stops: list[dict[str, Any]],
        legs: list[dict[str, Any]],
        revision: int = 0,
    ) -> httpx.Response:
        return await self.put(
            f"/trips/{trip_id}",
            {
                "expected_revision": revision,
                "location_id": str(self.world.a.location_id),
                "reference": f"FAKE-TR-{trip_id.hex[-8:]}",
                "stops": stops,
                "legs": legs,
            },
        )


@pytest.fixture
def accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only fixtures stand in for the package M acceptance; the registry stays implemented."""
    current = modules.MODULES_BY_ID["transport"]
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "transport",
        current.model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


@pytest.fixture
async def transport(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    accepted: None,
) -> Transport:
    config = Config(client, idp)
    await config.profile(manager_a, world.a.tenant_id, 0, [24])
    await config.publish(manager_a, world.a.tenant_id, 0, ENABLED)
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    customer = uuid7()
    saved = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/counterparties/{customer}",
        json=card(display_name="FAKE Shipper", roles=["customer"]),
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    return Transport(client, world, owner_conn, headers, customer)


# M1-01 ------------------------------------------------------------------------------


async def test_the_module_is_registered_but_cannot_be_enabled(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    catalog = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/module-catalog", headers=headers
    )
    assert catalog.status_code == 200, catalog.text
    (entry,) = [m for m in catalog.json()["modules"] if m["id"] == "transport"]
    assert (entry["readiness"], entry["enableable"]) == ("implemented", False)
    assert entry["depends_on"] == ["counterparties"]
    base = f"/v1/businesses/{world.a.tenant_id}/transport"
    refused = await client.put(
        f"{base}/orders/{uuid7()}",
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "customer_id": str(uuid7()),
            "reference": "FAKE-SO-NOT-READY",
            "loads": [load(uuid7(), 1)],
        },
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert error(refused) == (409, "MODULE_NOT_READY"), refused.text
    for path in ("/orders", "/trips"):
        read = await client.get(base + path, headers=headers)
        assert (read.status_code, read.json()["items"]) == (200, []), read.text


# M1-02 ------------------------------------------------------------------------------


async def test_an_order_with_loads_is_replaced_with_its_revision(transport: Transport) -> None:
    order, first, second = uuid7(), uuid7(), uuid7()
    saved = await transport.order(order, [load(first, 10), load(second, 6, "FAKE crates")])
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert (view["order_id"], view["revision"]) == (str(order), 1)
    assert [(item["load_id"], item["quantity"], item["planned"]) for item in view["loads"]] == [
        (str(first), 10, 0),
        (str(second), 6, 0),
    ]
    changed = await transport.order(
        order, [load(first, 12), load(second, 6, "FAKE crates")], revision=1
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2
    stale = await transport.order(order, [load(first, 12)], revision=1)
    assert error(stale) == (409, "TRANSPORT_REVISION_CONFLICT")
    taken = await transport.order(uuid7(), [load(uuid7(), 1)], reference=view["reference"])
    assert error(taken) == (409, "TRANSPORT_REFERENCE_TAKEN")
    listed = await transport.get("/orders")
    assert [item["order_id"] for item in listed.json()["items"]] == [str(order)]


# M1-03, M1-04 -----------------------------------------------------------------------


async def test_trips_carry_several_loads_and_split_a_load_across_trips(
    transport: Transport,
) -> None:
    first, second = uuid7(), uuid7()
    saved = await transport.order(uuid7(), [load(first, 10), load(second, 6)])
    assert saved.status_code == 200, saved.text
    interstate = [
        stop("pickup", "FAKE dock, Chicago", CHICAGO, 8, 10),
        stop("delivery", "FAKE yard, Indianapolis", INDIANAPOLIS, 14, 16),
        stop("delivery", "FAKE store, New York", NEW_YORK, 9, 12),
    ]
    trip_a = uuid7()
    planned = await transport.trip(trip_a, interstate, [leg(first, 10, 1, 2), leg(second, 4, 1, 3)])
    assert planned.status_code == 200, planned.text
    view = planned.json()
    assert (view["status"], view["revision"]) == ("planned", 1)
    # Times are stored in UTC and keep each stop's own time zone.
    stops = view["stops"]
    assert [s["time_zone"] for s in stops] == [CHICAGO, INDIANAPOLIS, NEW_YORK]
    for given, kept in zip(interstate, stops, strict=True):
        assert datetime.fromisoformat(kept["window_start"]) == datetime.fromisoformat(
            given["window_start"]
        )
        assert kept["window_start"].endswith("Z") or kept["window_start"].endswith("+00:00")
    trip_b = uuid7()
    rest = await transport.trip(
        trip_b,
        [
            stop("pickup", "FAKE dock, Chicago", CHICAGO, 11, 12),
            stop("delivery", "FAKE store, New York", NEW_YORK, 13, 15),
        ],
        [leg(second, 2, 1, 2)],
    )
    assert rest.status_code == 200, rest.text
    over = await transport.trip(
        uuid7(),
        [
            stop("pickup", "FAKE dock, Chicago", CHICAGO, 12, 13),
            stop("delivery", "FAKE store, New York", NEW_YORK, 15, 16),
        ],
        [leg(second, 1, 1, 2)],
    )
    assert error(over) == (409, "TRANSPORT_LOAD_OVERPLANNED")
    order = (await transport.get("/orders")).json()["items"][0]
    assert [(item["quantity"], item["planned"]) for item in order["loads"]] == [(10, 10), (6, 6)]
    # The trip is replaced whole with its revision: moving 1 crate back frees it.
    smaller = await transport.trip(
        trip_b,
        [
            stop("pickup", "FAKE dock, Chicago", CHICAGO, 11, 12),
            stop("delivery", "FAKE store, New York", NEW_YORK, 13, 15),
        ],
        [leg(second, 1, 1, 2)],
        revision=1,
    )
    assert smaller.status_code == 200, smaller.text
    assert smaller.json()["revision"] == 2
    trips = await transport.get("/trips")
    assert sorted(item["trip_id"] for item in trips.json()["items"]) == sorted(
        [str(trip_a), str(trip_b)]
    )


async def test_a_leg_goes_from_a_pickup_to_a_later_delivery(transport: Transport) -> None:
    item = uuid7()
    assert (await transport.order(uuid7(), [load(item, 5)])).status_code == 200
    stops = [
        stop("pickup", "FAKE dock", CHICAGO, 8, 9),
        stop("delivery", "FAKE store", NEW_YORK, 12, 13),
    ]
    for legs in ([leg(item, 1, 2, 1)], [leg(item, 1, 2, 2)], [leg(item, 1, 1, 3)]):
        refused = await transport.trip(uuid7(), stops, legs)
        assert error(refused) == (422, "TRANSPORT_LEG_INVALID"), refused.text
    unknown_zone = [{**stops[0], "time_zone": "Mars/Olympus"}, stops[1]]
    assert (await transport.trip(uuid7(), unknown_zone, [leg(item, 1, 1, 2)])).status_code == 422
    backwards = [{**stops[0], "window_start": local(CHICAGO, 10)}, stops[1]]
    assert (await transport.trip(uuid7(), backwards, [leg(item, 1, 1, 2)])).status_code == 422
    unknown_load = await transport.trip(uuid7(), stops, [leg(uuid7(), 1, 1, 2)])
    assert error(unknown_load) == (422, "INVALID_REFERENCE")


# M1-05 ------------------------------------------------------------------------------


async def test_a_planned_load_cannot_be_removed_or_shrunk_below_its_plan(
    transport: Transport,
) -> None:
    order, first, second = uuid7(), uuid7(), uuid7()
    assert (await transport.order(order, [load(first, 10), load(second, 6)])).status_code == 200
    planned = await transport.trip(
        uuid7(),
        [
            stop("pickup", "FAKE dock", CHICAGO, 8, 9),
            stop("delivery", "FAKE store", NEW_YORK, 12, 13),
        ],
        [leg(second, 6, 1, 2)],
    )
    assert planned.status_code == 200, planned.text
    removed = await transport.order(order, [load(first, 10)], revision=1)
    assert error(removed) == (409, "TRANSPORT_LOAD_PLANNED")
    shrunk = await transport.order(order, [load(first, 10), load(second, 5)], revision=1)
    assert error(shrunk) == (409, "TRANSPORT_LOAD_PLANNED")
    kept = await transport.order(order, [load(first, 3), load(second, 6)], revision=1)
    assert kept.status_code == 200, kept.text


# M1-06 ------------------------------------------------------------------------------


async def test_two_racing_plans_of_one_load_leave_its_quantity(
    transport: Transport, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    item = uuid7()
    assert (await transport.order(uuid7(), [load(item, 4)])).status_code == 200
    stops = [
        stop("pickup", "FAKE dock", CHICAGO, 8, 9),
        stop("delivery", "FAKE store", NEW_YORK, 12, 13),
    ]
    answers = await race(
        app_pool,
        test_database,
        transport.tenant,
        "select 1 from gba.transport_loads where id = %s for update",
        item,
        [
            transport.trip(uuid7(), stops, [leg(item, 4, 1, 2)]),
            transport.trip(uuid7(), stops, [leg(item, 4, 1, 2)]),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (refused,) = [a for a in answers if a.status_code == 409]
    assert error(refused) == (409, "TRANSPORT_LOAD_OVERPLANNED")
    async with tenant_transaction(app_pool, transport.tenant) as conn:
        row = await (
            await conn.execute(
                "select coalesce(sum(quantity), 0) from gba.transport_legs where load_id = %s",
                (item,),
            )
        ).fetchone()
    assert row == (4,)


# M1-07 ------------------------------------------------------------------------------


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (
            await conn.execute(
                "select (select count(*) from gba.transport_orders), "
                "(select count(*) from gba.transport_loads), "
                "(select count(*) from gba.transport_trips), "
                "(select count(*) from gba.transport_stops), "
                "(select count(*) from gba.transport_legs)"
            )
        ).fetchone()
    assert row is not None
    return tuple(int(n) for n in row)


async def test_without_the_module_writes_are_refused_and_scope_holds(
    transport: Transport,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    item = uuid7()
    assert (await transport.order(uuid7(), [load(item, 2)])).status_code == 200
    stops = [
        stop("pickup", "FAKE dock", CHICAGO, 8, 9),
        stop("delivery", "FAKE store", NEW_YORK, 12, 13),
    ]
    assert (await transport.trip(uuid7(), stops, [leg(item, 2, 1, 2)])).status_code == 200
    tenant = transport.tenant
    before = await _counts(app_pool, tenant)
    assert before == (1, 1, 1, 2, 1)
    for statement in (
        "delete from gba.transport_orders",
        "delete from gba.transport_loads",
        "delete from gba.transport_trips",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    assert await _counts(app_pool, transport.world.b.tenant_id) == (0, 0, 0, 0, 0)
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await transport.get("/orders", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    # Turned off: writes are refused and write nothing; reads continue.
    await Config(transport.client, idp).publish(
        manager_a, tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await transport.order(uuid7(), [load(uuid7(), 1)])
    assert error(off) == (409, "MODULE_DISABLED")
    assert await _counts(app_pool, tenant) == before
    read = await transport.get("/trips")
    assert read.status_code == 200, read.text
    assert len(read.json()["items"]) == 1
