"""M5: hours-of-service profiles, telematics freshness and trip clearance (TMS-03; FAKE data only).

ADR-0032 and docs/plan/PACKAGE_M5_DESIGN_2026-10-24.md: clearance is computed from versioned rule
profiles and insert-only facts; stale or unknown data never gives a positive clearance.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser
from tests.integration.test_m1_transport_planning import Transport, accepted, error, transport
from tests.integration.test_m2_transport_assignments import assign, at, planned
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "transport"]

US = {
    "code": "US_PROPERTY_70_8",
    "max_driving_minutes": 660,
    "max_window_minutes": 840,
    "reset_minutes": 600,
    "cycle_minutes": 4200,
    "cycle_days": 8,
    "max_data_age_minutes": 15,
}
NOW = at(10)
H = timedelta(hours=1)
M = timedelta(minutes=1)


async def profile(t: Transport, revision: int = 0, **rules: Any) -> httpx.Response:
    return await t.put("/hos-profile", {"expected_revision": revision, **US, **rules})


async def lane(t: Transport, path: str, body: dict[str, Any]) -> UUID:
    saved = await t.put(f"{path}/{uuid7()}", {"location_id": str(t.world.a.location_id), **body})
    assert saved.status_code == 200, saved.text
    view = saved.json()
    return UUID(view["driver_id" if path == "/drivers" else "vehicle_id"])


async def duty(
    t: Transport,
    driver: UUID,
    status: str,
    start: datetime,
    end: datetime,
    record: str | None = None,
) -> httpx.Response:
    return await t.client.post(
        f"{t.base}/drivers/{driver}/duty-records",
        json={
            "schema_version": 1,
            "source": "eld.fake",
            "source_record_id": record or f"FAKE-{uuid7()}",
            "status": status,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
        },
        headers={**t.headers, "Idempotency-Key": str(uuid7())},
    )


async def ping(
    t: Transport, vehicle: UUID, observed: datetime, record: str | None = None
) -> httpx.Response:
    return await t.client.post(
        f"{t.base}/vehicles/{vehicle}/pings",
        json={
            "schema_version": 1,
            "source": "telematics.fake",
            "source_record_id": record or f"FAKE-{uuid7()}",
            "observed_at": observed.isoformat(),
        },
        headers={**t.headers, "Idempotency-Key": str(uuid7())},
    )


async def history(t: Transport, driver: UUID, blocks: list[tuple[str, datetime, datetime]]) -> None:
    for status, start, end in blocks:
        recorded = await duty(t, driver, status, start, end)
        assert recorded.status_code == 200, recorded.text


def legal(now: datetime) -> list[tuple[str, datetime, datetime]]:
    """Eight days off duty, then an hour on duty and almost two hours of driving."""
    return [
        ("off_duty", now - 8 * 24 * H - H, now - 3 * H),
        ("on_duty", now - 3 * H, now - 2 * H),
        ("driving", now - 2 * H, now - 5 * M),
    ]


async def clearance(t: Transport, trip: UUID, moment: datetime = NOW) -> dict[str, Any]:
    read = await t.client.get(
        f"{t.base}/trips/{trip}/clearance", params={"at": moment.isoformat()}, headers=t.headers
    )
    assert read.status_code == 200, read.text
    view: dict[str, Any] = read.json()
    return view


def roles(view: dict[str, Any]) -> dict[str, tuple[str, list[str]]]:
    return {item["role"]: (item["status"], item["reasons"]) for item in view["roles"]}


_unit = iter(range(100, 1000))


async def crewed(t: Transport) -> tuple[UUID, UUID, UUID]:
    """A planned trip (08:00-17:00 Chicago) with a registered and assigned driver and truck."""
    trip, _ = await planned(t)
    number = next(_unit)
    driver = await lane(t, "/drivers", {"display_name": f"FAKE Driver {number}"})
    truck = await lane(t, "/vehicles", {"kind": "truck", "unit_number": f"FAKE-T{number}"})
    driver_lane = UUID((await t.get(f"/drivers/{driver}")).json()["resource_id"])
    truck_lane = UUID((await t.get(f"/vehicles/{truck}")).json()["resource_id"])
    assert (await assign(t, trip, "driver", driver_lane)).status_code == 200
    assert (await assign(t, trip, "truck", truck_lane)).status_code == 200
    return trip, driver, truck


# M5-01 ------------------------------------------------------------------------------


async def test_a_profile_is_replaced_with_its_revision(
    transport: Transport, app_pool: RuntimePool
) -> None:
    t = transport
    assert (await t.get("/hos-profile")).status_code == 404
    first = await profile(t)
    assert first.status_code == 200, first.text
    assert (first.json()["revision"], first.json()["max_driving_minutes"]) == (1, 660)
    second = await profile(t, 1, max_driving_minutes=600)
    assert (second.json()["revision"], second.json()["max_driving_minutes"]) == (2, 600)
    stale = await profile(t, 1)
    assert error(stale) == (409, "TRANSPORT_REVISION_CONFLICT"), stale.text
    current = await t.get("/hos-profile")
    assert current.json()["revision"] == 2
    async with tenant_transaction(app_pool, t.tenant) as conn:
        row = await (
            await conn.execute("select count(*) from gba.transport_hos_profiles")
        ).fetchone()
    assert row == (2,)


# M5-02 ------------------------------------------------------------------------------


async def test_fresh_complete_data_within_the_limits_clears_the_trip(transport: Transport) -> None:
    t = transport
    trip, driver, truck = await crewed(t)
    assert (await profile(t)).status_code == 200
    await history(t, driver, legal(NOW))
    assert (await ping(t, truck, NOW - 2 * M)).status_code == 200
    view = await clearance(t, trip)
    assert view["status"] == "cleared", view
    assert roles(view) == {"driver": ("cleared", []), "truck": ("cleared", [])}
    assert view["profile"] == {"code": "US_PROPERTY_70_8", "revision": 1}


# M5-03 ------------------------------------------------------------------------------


async def test_stale_or_unknown_data_never_clears(transport: Transport) -> None:
    t = transport
    trip, driver, truck = await crewed(t)
    # No profile yet: nothing can be judged.
    early = await clearance(t, trip)
    assert early["status"] == "unknown"
    assert roles(early)["driver"] == ("unknown", ["no_hos_profile"])
    assert (await profile(t)).status_code == 200
    view = await clearance(t, trip)
    assert (view["status"], roles(view)) == (
        "unknown",
        {"driver": ("unknown", ["no_duty_data"]), "truck": ("unknown", ["no_telematics"])},
    )
    # Records that stop 30 minutes ago and a ping 20 minutes old are stale.
    await history(
        t,
        driver,
        [("off_duty", NOW - 8 * 24 * H - H, NOW - 2 * H), ("driving", NOW - 2 * H, NOW - 30 * M)],
    )
    assert (await ping(t, truck, NOW - 20 * M)).status_code == 200
    stale = await clearance(t, trip)
    assert (stale["status"], roles(stale)) == (
        "unknown",
        {"driver": ("unknown", ["stale_duty_data"]), "truck": ("unknown", ["stale_telematics"])},
    )
    # A gap in the cycle is unknown even when the latest record is fresh.
    assert (await duty(t, driver, "driving", NOW - 20 * M, NOW - 5 * M)).status_code == 200
    assert (await ping(t, truck, NOW - M)).status_code == 200
    gapped = await clearance(t, trip)
    assert roles(gapped)["driver"] == ("unknown", ["incomplete_duty_data"])
    assert roles(gapped)["truck"] == ("cleared", [])
    assert gapped["status"] == "unknown"
    # An unassigned driver and truck never clear either.
    lonely, _ = await planned(t)
    alone = await clearance(t, lonely)
    assert roles(alone) == {
        "driver": ("unknown", ["unassigned"]),
        "truck": ("unknown", ["unassigned"]),
    }


# M5-04 ------------------------------------------------------------------------------


def _cycle_breaker() -> list[tuple[str, datetime, datetime]]:
    """Eight days of 14 hours on duty and 10 hours off, then a reset and under an hour driving."""
    blocks: list[tuple[str, datetime, datetime]] = []
    for day in range(8, 0, -1):
        base = NOW - day * 24 * H
        blocks.append(("on_duty", base - 10 * H, base + 4 * H))
        blocks.append(("off_duty", base + 4 * H, base + 14 * H))
    return [*blocks, ("off_duty", NOW - 10 * H, NOW - H), ("driving", NOW - H, NOW - 5 * M)]


async def test_an_exceeded_limit_does_not_clear(transport: Transport) -> None:
    t = transport
    assert (await profile(t)).status_code == 200
    cases: list[tuple[str, list[tuple[str, datetime, datetime]]]] = [
        (
            "driving_limit",
            [("off_duty", NOW - 9 * 24 * H, NOW - 12 * H), ("driving", NOW - 12 * H, NOW - 5 * M)],
        ),
        (
            "window_limit",
            [
                ("off_duty", NOW - 9 * 24 * H, NOW - 15 * H),
                ("on_duty", NOW - 15 * H, NOW - H),
                ("driving", NOW - H, NOW - 5 * M),
            ],
        ),
        ("cycle_limit", _cycle_breaker()),
    ]
    for reason, blocks in cases:
        trip, driver, truck = await crewed(t)
        await history(t, driver, blocks)
        assert (await ping(t, truck, NOW - M)).status_code == 200
        view = await clearance(t, trip)
        assert (view["status"], roles(view)["driver"]) == (
            "not_cleared",
            ("not_cleared", [reason]),
        ), reason


# M5-05 ------------------------------------------------------------------------------


async def test_a_repeated_fact_changes_nothing(transport: Transport, app_pool: RuntimePool) -> None:
    t = transport
    driver = await lane(t, "/drivers", {"display_name": "FAKE Driver One"})
    truck = await lane(t, "/vehicles", {"kind": "truck", "unit_number": "FAKE-T1"})
    first = await duty(t, driver, "driving", NOW - 2 * H, NOW - H, record="FAKE-ELD-1")
    assert first.status_code == 200, first.text
    again = await duty(t, driver, "driving", NOW - 2 * H, NOW - H, record="FAKE-ELD-1")
    assert (again.status_code, again.json()) == (200, first.json())
    other = await duty(t, driver, "on_duty", NOW - 2 * H, NOW - H, record="FAKE-ELD-1")
    assert error(other) == (409, "TRANSPORT_FACT_CONFLICT"), other.text
    overlap = await duty(t, driver, "on_duty", NOW - 90 * M, NOW - 30 * M)
    assert error(overlap) == (409, "TRANSPORT_DUTY_OVERLAP"), overlap.text
    backwards = await duty(t, driver, "on_duty", NOW - 30 * M, NOW - 40 * M)
    assert backwards.status_code == 422, backwards.text
    seen = await ping(t, truck, NOW - M, record="FAKE-GPS-1")
    assert seen.status_code == 200, seen.text
    assert (await ping(t, truck, NOW - M, record="FAKE-GPS-1")).json() == seen.json()
    moved = await ping(t, truck, NOW, record="FAKE-GPS-1")
    assert error(moved) == (409, "TRANSPORT_FACT_CONFLICT"), moved.text
    async with tenant_transaction(app_pool, t.tenant) as conn:
        row = await (
            await conn.execute(
                "select (select count(*) from gba.transport_duty_records), "
                "(select count(*) from gba.transport_telematics_pings)"
            )
        ).fetchone()
    assert row == (1, 1)


# M5-06 ------------------------------------------------------------------------------


async def _counts(pool: RuntimePool, tenant: UUID, location: UUID | None = None) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        if location is not None:
            await conn.execute(
                "select pg_catalog.set_config('gba.location_id', %s, true)", (str(location),)
            )
        row = await (
            await conn.execute(
                "select (select count(*) from gba.transport_hos_profiles), "
                "(select count(*) from gba.transport_duty_records), "
                "(select count(*) from gba.transport_telematics_pings)"
            )
        ).fetchone()
    assert row is not None
    return tuple(int(n) for n in row)


async def test_without_the_module_facts_are_refused_and_scope_holds(
    transport: Transport,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    t = transport
    assert (await profile(t)).status_code == 200
    driver = await lane(t, "/drivers", {"display_name": "FAKE Driver One"})
    truck = await lane(t, "/vehicles", {"kind": "truck", "unit_number": "FAKE-T1"})
    assert (await duty(t, driver, "driving", NOW - 2 * H, NOW - H)).status_code == 200
    assert (await ping(t, truck, NOW - M)).status_code == 200
    before = await _counts(app_pool, t.tenant)
    assert before == (1, 1, 1)
    for statement in (
        "update gba.transport_hos_profiles set cycle_days = 7",
        "delete from gba.transport_hos_profiles",
        "update gba.transport_duty_records set status = 'off_duty'",
        "delete from gba.transport_duty_records",
        "update gba.transport_telematics_pings set observed_at = now()",
        "delete from gba.transport_telematics_pings",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, t.tenant) as conn:
                await conn.execute(statement)
    # Profiles are company-wide; duty records and pings follow their driver's and vehicle's branch.
    assert (await _counts(app_pool, t.tenant, location=uuid7()))[1:] == (0, 0)
    assert await _counts(app_pool, t.world.b.tenant_id) == (0, 0, 0)
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    assert (await t.get("/hos-profile", headers=other)).status_code in (403, 404)
    await Config(t.client, idp).publish(
        manager_a, t.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await duty(t, driver, "on_duty", NOW - H, NOW - 30 * M)
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    assert error(await ping(t, truck, NOW)) == (409, "MODULE_DISABLED")
    assert error(await profile(t, 1)) == (409, "MODULE_DISABLED")
    assert await _counts(app_pool, t.tenant) == before
