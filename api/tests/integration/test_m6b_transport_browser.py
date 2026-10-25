"""M6b: planning forms, fleet, a carrier grant and its dispatcher in a real browser (FAKE only).

Actual OIDC/PKCE, Chromium and PostgreSQL. The browser registers the fleet, enters and corrects an
order, plans and corrects a trip, offers a carrier transport actions, accepts for a dispatcher and
works as that dispatcher; what the screens did is read back from the database.
"""

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid7

import httpx
import psycopg
import pytest
from fastapi import HTTPException

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_m1_transport_planning import accepted
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted"]
MODULES = ["booking_resources", "counterparties", "transport"]
PROJECTS = ("desktop", "mobile")


def test_planning_forms_fleet_and_carrier_dispatcher_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    accepted: None,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: M6b browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/transport/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    shipper, carrier = world.a.tenant_id, world.b.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {
        name: seed_user(owner_conn, name, issuer=issuer)
        for name in ("m6b-owner", "m6b-carrier", *(f"m6b-dispatcher-{p}" for p in PROJECTS))
    }
    for tenant, name in ((shipper, "m6b-owner"), (carrier, "m6b-carrier")):
        add_membership(owner_conn, tenant_id=tenant, user_id=people[name].user_id, role="owner")
    for p in PROJECTS:
        user = people[f"m6b-dispatcher-{p}"].user_id
        add_membership(owner_conn, tenant_id=carrier, user_id=user, role="manager")
    with owner_tenant_transaction(owner_conn, shipper):
        row = owner_conn.execute(
            "select name from gba.locations where id = %s", (world.a.location_id,)
        ).fetchone()
    assert row is not None
    idp = FakeIdp()
    signed_in = _SignedIn(people)
    signed_in.name = "m6b-owner"
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))

    @provider.post("/fixture/user/{name}")
    async def switch(name: str) -> dict[str, str]:
        if name not in people:
            raise HTTPException(404, "Unknown FAKE person")
        signed_in.name = name
        return {"user": name}

    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    env.update(
        GBA_M6B_OWNER_BUSINESS=str(shipper),
        GBA_M6B_CARRIER_BUSINESS=str(carrier),
        GBA_M6B_LOCATION_NAME=str(row[0]),
    )
    owner = people["m6b-owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    business = f"/v1/businesses/{shipper}"
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
        call(
            "PUT",
            f"{business}/counterparties/{uuid7()}",
            card(display_name="FAKE Shipper", roles=["customer"]),
        )
        # A supplier is not offered as a customer.
        call(
            "PUT",
            f"{business}/counterparties/{uuid7()}",
            card(display_name="FAKE Supplier", roles=["supplier"]),
        )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:transport-forms"],
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

    chicago = datetime(2031, 6, 2, 13, tzinfo=UTC)  # 08:00 in Chicago (CDT)
    with owner_tenant_transaction(owner_conn, shipper):
        for p in PROJECTS:
            dispatcher = people[f"m6b-dispatcher-{p}"].user_id
            assert owner_conn.execute(
                "select display_name from gba.transport_drivers where display_name like %s",
                (f"FAKE Driver {p}%",),
            ).fetchall() == [(f"FAKE Driver {p}",)]
            assert owner_conn.execute(
                "select kind from gba.transport_vehicles where unit_number = %s",
                (f"FAKE-T-{p}-1",),
            ).fetchall() == [("truck",)]
            order = owner_conn.execute(
                "select o.id, o.revision from gba.transport_orders o where o.reference = %s",
                (f"FAKE-SO-{p}",),
            ).fetchone()
            assert order is not None, p
            assert order[1] == 2, p
            assert owner_conn.execute(
                "select description, quantity, unit from gba.transport_loads "
                "where order_id = %s order by position",
                (order[0],),
            ).fetchall() == [("FAKE pallets", 10, "pallet"), ("FAKE crates", 8, "crate")]
            trip = owner_conn.execute(
                "select id, status from gba.transport_trips where reference = %s",
                (f"FAKE-TR-{p}",),
            ).fetchone()
            assert trip is not None, p
            assert trip[1] == "in_transit", p
            assert owner_conn.execute(
                "select place, time_zone, window_start from gba.transport_stops "
                "where trip_id = %s order by position",
                (trip[0],),
            ).fetchall() == [
                ("FAKE dock, Chicago", "America/Chicago", chicago),
                (
                    "FAKE yard, Indianapolis",
                    "America/Indiana/Indianapolis",
                    datetime(2031, 6, 2, 18, tzinfo=UTC),
                ),
                ("FAKE store 2, New York", "America/New_York", datetime(2031, 6, 3, tzinfo=UTC)),
            ]
            assert owner_conn.execute(
                "select l.quantity, l.pickup_stop, l.delivery_stop from gba.transport_legs l "
                "where l.trip_id = %s order by l.position",
                (trip[0],),
            ).fetchall() == [(10, 1, 2), (8, 1, 3)]
            assert owner_conn.execute(
                "select role, created_by from gba.transport_assignments where trip_id = %s "
                "order by created_at",
                (trip[0],),
            ).fetchall() == [("driver", dispatcher), ("truck", dispatcher)]
            assert owner_conn.execute(
                "select kind, source, recorded_by from gba.transport_stop_events "
                "where trip_id = %s",
                (trip[0],),
            ).fetchall() == [("arrived", "dispatcher", dispatcher)]
            grant = owner_conn.execute(
                "select g.permissions, g.status from gba.delegation_grants g "
                "join gba.delegation_grant_members m on m.owner_tenant_id = g.owner_tenant_id "
                "and m.grant_id = g.id where g.servicer_tenant_id = %s and m.user_id = %s "
                "and m.removed_at is null",
                (carrier, dispatcher),
            ).fetchall()
            assert [(sorted(g[0]), g[1]) for g in grant] == [
                (
                    ["transport.assign", "transport.events", "transport.read"],
                    # The mobile run revoked the desktop grant before offering its own.
                    "revoked" if p == "desktop" else "active",
                )
            ], p
