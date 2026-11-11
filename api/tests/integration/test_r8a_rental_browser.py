"""R8a: the rental screens in a real browser (desktop and mobile; FAKE data only).

docs/plan/PACKAGE_R8A_DESIGN_2026-11-09.md. Actual OIDC/PKCE, Chromium and PostgreSQL. The business,
its modules and the customer are seeded through the routes; the browser creates a class and a unit,
reads availability, books, assigns the unit and cancels a second booking, and the database is read
back.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast
from uuid import uuid7

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
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_r1_rental_catalog import ENABLED, accepted
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted"]
PROJECTS = ("desktop", "mobile")


def test_rental_screens_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    accepted: None,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: R8a browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/rental/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "r8a-owner", issuer=issuer)}
    add_membership(owner_conn, tenant_id=tenant, user_id=people["owner"].user_id, role="owner")
    idp = FakeIdp()
    signed_in = _SignedIn(people)
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    owner = people["owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    business = f"/v1/businesses/{tenant}"
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

        call("PUT", f"{business}/profile", {"expected_revision": 0, "industry_ids": [23]})
        version = call(
            "PUT",
            f"{business}/configuration/draft",
            {"expected_version": 0, "profile_revision": 1, "module_ids": ENABLED},
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
            card(display_name="FAKE Renter", roles=["customer"]),
        )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:rental"],
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
            head = owner_conn.execute(
                "select id, name, meter_kind, created_by from gba.rental_classes where code = %s",
                (f"FAKE-{project.upper()}",),
            ).fetchone()
            assert head is not None, project
            car = head[0]
            assert head[1:] == (f"FAKE van {project}", "odometer", owner.user_id)
            unit = owner_conn.execute(
                "select id, location_id, state from gba.rental_units "
                "where class_id = %s and identifier = %s",
                (car, f"FAKE-U-{project}"),
            ).fetchone()
            assert unit is not None, project
            assert unit[1:] == (world.a.location_id, "active")
            booked = owner_conn.execute(
                "select b.note, c.reason, (select count(*) from gba.rental_assignments a "
                "where a.booking_id = b.id and a.unit_id = %s) "
                "from gba.rental_bookings b left join gba.rental_booking_cancellations c "
                "on c.tenant_id = b.tenant_id and c.booking_id = b.id "
                "where b.class_id = %s order by b.starts_at",
                (unit[0], car),
            ).fetchall()
            assert booked == [
                (f"FAKE note {project}", None, 1),
                (None, f"FAKE plans changed {project}", 0),
            ], project
