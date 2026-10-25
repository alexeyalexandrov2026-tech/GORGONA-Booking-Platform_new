"""M6a-01: trips, drivers and vehicles are listed completely in pages of 50 (FAKE data only)."""

from typing import Any
from uuid import uuid7

import pytest

from tests.integration import test_management_api as shared
from tests.integration.test_m1_transport_planning import Transport, accepted, leg, load, transport
from tests.integration.test_m2_transport_assignments import span_stops

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
__all__ = ["accepted", "client", "idp", "manager_a", "transport"]


async def every(t: Transport, path: str, key: str) -> list[str]:
    """Read a list to its end through its cursor; every page holds at most 50 items."""
    seen: list[str] = []
    after: str | None = None
    while True:
        page = await t.get(path + (f"?after={after}" if after else ""))
        assert page.status_code == 200, page.text
        body: dict[str, Any] = page.json()
        assert len(body["items"]) <= 50
        seen += [item[key] for item in body["items"]]
        after = body["next_cursor"]
        if after is None:
            return seen


async def test_trips_drivers_and_vehicles_are_listed_completely(transport: Transport) -> None:
    t = transport
    item = uuid7()
    assert (await t.order(uuid7(), [load(item, 1000)])).status_code == 200
    trips = []
    for _ in range(53):
        trip = uuid7()
        made = await t.trip(trip, span_stops(8, 17), [leg(item, 1, 1, 2)])
        assert made.status_code == 200, made.text
        trips.append(str(trip))
    drivers, vehicles = [], []
    for number in range(52):
        saved = await t.put(
            f"/drivers/{uuid7()}",
            {"location_id": str(t.world.a.location_id), "display_name": f"FAKE Driver {number}"},
        )
        assert saved.status_code == 200, saved.text
        drivers.append(saved.json()["driver_id"])
        saved = await t.put(
            f"/vehicles/{uuid7()}",
            {
                "location_id": str(t.world.a.location_id),
                "kind": "truck",
                "unit_number": f"FAKE-T{number}",
            },
        )
        assert saved.status_code == 200, saved.text
        vehicles.append(saved.json()["vehicle_id"])
    first = (await t.get("/trips")).json()
    assert (len(first["items"]), first["next_cursor"]) == (50, first["items"][-1]["trip_id"])
    assert await every(t, "/trips", "trip_id") == sorted(trips)
    assert await every(t, "/drivers", "driver_id") == sorted(drivers)
    assert await every(t, "/vehicles", "vehicle_id") == sorted(vehicles)
    # A cursor names the last item seen; nothing after the last one.
    last = (await t.get(f"/trips?after={sorted(trips)[-1]}")).json()
    assert (last["items"], last["next_cursor"]) == ([], None)
    assert (await t.get("/trips?after=not-a-cursor")).status_code == 422
