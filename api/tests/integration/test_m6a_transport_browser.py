"""M6a: the dispatch board and the trip page in a real browser (desktop and mobile; FAKE data only).

Actual OIDC/PKCE, Chromium and PostgreSQL. The trips, crews, hours-of-service profile and FAKE
duty records and pings are seeded through the routes; what the screens did is read back from the
database.
"""

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_m1_transport_planning import accepted, leg, load, stop
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted"]
MODULES = ["booking_resources", "counterparties", "transport"]
PROJECTS = ("desktop", "mobile")
STOPS = [
    stop("pickup", "FAKE dock, Chicago", "America/Chicago", 8, 10),
    stop("delivery", "FAKE yard, Indianapolis", "America/Indiana/Indianapolis", 14, 16),
    stop("delivery", "FAKE store, New York", "America/New_York", 20, 23),
]
DELIVERED = (
    "select q.leg_position, q.quantity from gba.transport_event_quantities q "
    "join gba.transport_stop_events e "
    "on e.tenant_id = q.tenant_id and e.id = q.event_id "
    "where e.trip_id = %s and e.kind = 'delivered'"
)


def test_dispatch_board_and_trip_page_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    accepted: None,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: M6a browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/transport/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "m6a-owner", issuer=issuer)}
    add_membership(owner_conn, tenant_id=tenant, user_id=people["owner"].user_id, role="owner")
    idp = FakeIdp()
    signed_in = _SignedIn(people)
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    owner = people["owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    business = f"/v1/businesses/{tenant}"
    trips: dict[str, UUID] = {}
    with live_server(provider, idp_port), live_server(app, app_port):

        def call(method: str, path: str, body: object = None) -> dict[str, Any]:
            result = httpx.request(
                method,
                f"{origin}{path}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=15,
            )
            assert result.status_code == 200, result.text
            answer: dict[str, Any] = result.json()
            return answer

        call("PUT", f"{business}/profile", {"expected_revision": 0, "industry_ids": [24]})
        version = call(
            "PUT",
            f"{business}/configuration/draft",
            {"expected_version": 0, "profile_revision": 1, "module_ids": MODULES},
        )["version"]
        for step, revision in (("validate", 1), ("publish", 2)):
            call(
                "POST",
                f"{business}/configuration/versions/{version}/{step}",
                {"expected_revision": revision},
            )
        customer = uuid7()
        call(
            "PUT",
            f"{business}/counterparties/{customer}",
            card(display_name="FAKE Shipper", roles=["customer"]),
        )
        call(
            "PUT",
            f"{business}/transport/hos-profile",
            {
                "schema_version": 1,
                "expected_revision": 0,
                "code": "US_PROPERTY_70_8",
                "max_driving_minutes": 660,
                "max_window_minutes": 840,
                "reset_minutes": 600,
                "cycle_minutes": 4200,
                "cycle_days": 8,
                # The browser asks for clearance now; a day keeps the seeded facts fresh.
                "max_data_age_minutes": 1440,
            },
        )
        now = datetime.now(UTC)
        location = str(world.a.location_id)
        for project in PROJECTS:
            pallets, crates = uuid7(), uuid7()
            call(
                "PUT",
                f"{business}/transport/orders/{uuid7()}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "customer_id": str(customer),
                    "reference": f"FAKE-SO-{project}",
                    "loads": [load(pallets, 10), load(crates, 6, "FAKE crates")],
                },
            )
            trips[project] = uuid7()
            call(
                "PUT",
                f"{business}/transport/trips/{trips[project]}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": location,
                    "reference": f"FAKE-TR-{project}",
                    "stops": STOPS,
                    "legs": [leg(pallets, 10, 1, 2), leg(crates, 6, 1, 3)],
                },
            )
            driver = uuid7()
            call(
                "PUT",
                f"{business}/transport/drivers/{driver}",
                {
                    "schema_version": 1,
                    "location_id": location,
                    "display_name": f"FAKE Driver {project}",
                },
            )
            for number in (1, 2):
                vehicle = uuid7()
                call(
                    "PUT",
                    f"{business}/transport/vehicles/{vehicle}",
                    {
                        "schema_version": 1,
                        "location_id": location,
                        "kind": "truck",
                        "unit_number": f"FAKE-T-{project}-{number}",
                    },
                )
                call(
                    "POST",
                    f"{business}/transport/vehicles/{vehicle}/pings",
                    {
                        "schema_version": 1,
                        "source": "telematics.fake",
                        "source_record_id": f"FAKE-{uuid7()}",
                        "observed_at": (now - timedelta(minutes=1)).isoformat(),
                    },
                )
            if project == "desktop":
                for status, start, end in (
                    ("off_duty", now - timedelta(days=8, hours=1), now - timedelta(hours=3)),
                    ("on_duty", now - timedelta(hours=3), now - timedelta(hours=2)),
                    ("driving", now - timedelta(hours=2), now + timedelta(hours=2)),
                ):
                    call(
                        "POST",
                        f"{business}/transport/drivers/{driver}/duty-records",
                        {
                            "schema_version": 1,
                            "source": "eld.fake",
                            "source_record_id": f"FAKE-{uuid7()}",
                            "status": status,
                            "starts_at": start.isoformat(),
                            "ends_at": end.isoformat(),
                        },
                    )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:transport"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
        snapshots = "".join(
            f"\n--- {path.parent.name}\n" + path.read_text(encoding="utf-8")
            for path in sorted((web / "test-results").glob("*/error-context.md"))
        )
        assert result.returncode == 0, result.stdout + result.stderr + snapshots
        print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s

    with owner_tenant_transaction(owner_conn, tenant):
        for project in PROJECTS:
            trip = trips[project]
            events = owner_conn.execute(
                "select kind, source, recorded_by from gba.transport_stop_events "
                "where trip_id = %s order by kind",
                (trip,),
            ).fetchall()
            assert events == [
                ("arrived", "dispatcher", owner.user_id),
                ("delivered", "dispatcher", owner.user_id),
                ("loaded", "dispatcher", owner.user_id),
            ], project
            assert owner_conn.execute(DELIVERED, (trip,)).fetchall() == [(1, 7)], project
            crew = owner_conn.execute(
                "select a.role, a.replaces is not null, e.ends_at "
                "from gba.transport_assignments a left join gba.transport_assignment_ends e "
                "on e.tenant_id = a.tenant_id and e.assignment_id = a.id "
                "where a.trip_id = %s order by a.created_at",
                (trip,),
            ).fetchall()
            noon = datetime(2031, 6, 2, 17, tzinfo=UTC)  # 12:00 in Chicago (CDT)
            assert crew == [("driver", False, None), ("truck", False, noon), ("truck", True, None)]
