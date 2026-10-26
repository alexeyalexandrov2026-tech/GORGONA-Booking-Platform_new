"""M8: TMS-01 end to end on one trip (package M acceptance; FAKE data only).

Two orders' loads on one interstate trip with three stops; the truck is replaced after loading;
the first delivery is partial (refused and damaged pallets); the rest arrives at the third stop.
The trip keeps its plan, every assignment period and every event: its history.
"""

from uuid import UUID, uuid7

import pytest

from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.test_m1_transport_planning import (
    Transport,
    accepted,
    error,
    leg,
    load,
    transport,
)
from tests.integration.test_m2_transport_assignments import assign, at, driver, periods, vehicle
from tests.integration.test_m3_transport_events import INTERSTATE, event, progress

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
__all__ = ["accepted", "client", "idp", "manager_a", "transport"]
# An event: kind, stop, quantities per leg (leg, quantity), hour in Chicago.
Step = tuple[str, int, tuple[tuple[int, int], ...], int]


async def test_tms_01_an_interstate_trip_keeps_its_history(transport: Transport) -> None:
    t = transport
    pallets, crates = uuid7(), uuid7()
    for item, quantity, name in ((pallets, 10, "FAKE pallets"), (crates, 6, "FAKE crates")):
        saved = await t.order(uuid7(), [load(item, quantity, name)])
        assert saved.status_code == 200, saved.text
    trip = uuid7()
    made = await t.trip(trip, INTERSTATE, [leg(pallets, 10, 1, 2), leg(crates, 6, 1, 3)])
    assert made.status_code == 200, made.text
    person = await driver(t)
    truck1 = await vehicle(t, "truck", "FAKE-T1")
    truck2 = await vehicle(t, "truck", "FAKE-T2")
    first = uuid7()
    assert (await assign(t, trip, "driver", person)).status_code == 200
    assert (await assign(t, trip, "truck", truck1, assignment=first)).status_code == 200
    before: list[Step] = [
        ("arrived", 1, (), 8),
        ("loaded", 1, ((1, 10), (2, 6)), 9),
        ("departed", 1, (), 10),
    ]
    for kind, stop_position, quantities, hour in before:
        done = await event(t, trip, kind, stop_position, quantities=quantities, hour=hour)
        assert done.status_code == 200, done.text
    # The truck breaks down on the road: a second truck takes over at noon.
    replaced = await assign(t, trip, "truck", truck2, starts=12, replaces=first)
    assert replaced.status_code == 200, replaced.text
    after: list[Step] = [
        ("delivered", 2, ((1, 7),), 14),
        ("refused", 2, ((1, 2),), 14),
        ("damaged", 2, ((1, 1),), 14),
        ("delivered", 3, ((2, 6),), 20),
    ]
    for kind, stop_position, quantities, hour in after:
        done = await event(t, trip, kind, stop_position, quantities=quantities, hour=hour)
        assert done.status_code == 200, done.text
    view = (await t.get(f"/trips/{trip}")).json()
    assert view["status"] == "in_transit"
    # Per leg: position, planned, loaded, delivered, refused, damaged.
    assert progress(view) == [(1, 10, 10, 7, 2, 1), (2, 6, 6, 6, 0, 0)]
    trucks = periods(view, "truck")
    assert [(p[0], p[2], p[3]) for p in trucks] == [
        (truck1, at(12), None),
        (truck2, None, first),
    ]
    assert [(p[0], p[2]) for p in periods(view, "driver")] == [(person, None)]
    assert [(e["stop_position"], e["kind"]) for e in view["events"]] == [
        (1, "arrived"),
        (1, "loaded"),
        (1, "departed"),
        (2, "delivered"),
        (2, "refused"),
        (2, "damaged"),
        (3, "delivered"),
    ]
    # The plan is kept once the trip started; the history stays in the database.
    replanned = await t.trip(trip, INTERSTATE, [leg(pallets, 9, 1, 2)], revision=1)
    assert error(replanned) == (409, "TRANSPORT_TRIP_STARTED"), replanned.text
    with owner_tenant_transaction(t.owner_conn, t.tenant):
        ended = t.owner_conn.execute(
            "select e.ends_at from gba.transport_assignment_ends e "
            "join gba.transport_assignments a on a.tenant_id = e.tenant_id "
            "and a.id = e.assignment_id where a.id = %s",
            (first,),
        ).fetchall()
    assert ended == [(at(12),)]
    assert UUID(view["trip_id"]) == trip
