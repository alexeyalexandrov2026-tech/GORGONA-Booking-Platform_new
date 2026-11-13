"""R8c: inspections, usage, settlement, charges, refunds and reconciliation in a real browser.

docs/plan/PACKAGE_R8C_DESIGN_2026-11-11.md (desktop, mobile; FAKE data). Actual OIDC/PKCE, Chromium
and PostgreSQL. The business, its modules, a book and the customer are seeded through the
routes; the browser prices and books a car, hands it over and takes it back, settles, charges a
new dent and records an external refund, and the database is read back.
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


def test_rental_settlement_screens_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    accepted: None,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: R8c browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/rental/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "r8c-owner", issuer=issuer)}
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
        entity, book = uuid7(), uuid7()
        call(
            "PUT",
            f"{business}/legal-entities/{entity}",
            {"expected_revision": 0, "code": "FAKE_RENT", "legal_name": "FAKE Rentals LLC"},
        )
        call(
            "PUT",
            f"{business}/ledger/books/{book}",
            {
                "expected_revision": 0,
                "legal_entity_id": str(entity),
                "base_currency": "USD",
                "fiscal_year_start_month": 1,
                "accounting_start": "2026-01-01",
            },
        )
        chart = call("GET", f"{business}/ledger/books/{book}/accounts")["items"]

        def label(code: str) -> str:
            account = next(a for a in chart if a["code"] == code)
            return f"{account['code']} {account['name']}"

        env.update(
            GBA_R8C_BOOK="FAKE Rentals LLC",
            GBA_R8C_RECEIVABLE=label("1200"),
            GBA_R8C_REVENUE=label("4100"),
        )
        call(
            "PUT",
            f"{business}/counterparties/{uuid7()}",
            card(display_name="FAKE Renter", roles=["customer"]),
        )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:rental-settlement"],
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
            booking = owner_conn.execute(
                "select b.id from gba.rental_bookings b join gba.rental_classes c "
                "on c.tenant_id = b.tenant_id and c.id = b.class_id where c.code = %s",
                (f"FAKE-ST-{project.upper()}",),
            ).fetchone()
            assert booking is not None, project
            inspected = owner_conn.execute(
                "select i.kind, i.meter, i.level, m.position, m.area, m.severity, m.new "
                "from gba.rental_inspections i join gba.rental_inspection_marks m "
                "on m.tenant_id = i.tenant_id and m.inspection_id = i.id "
                "where i.booking_id = %s order by i.inspected_at, m.position",
                (booking[0],),
            ).fetchall()
            assert inspected == [
                ("handover", 1000, 80, 1, "FAKE front bumper", "minor", False),
                ("return", 1300, None, 1, "FAKE rear door", "major", True),
            ], project
            settled = owner_conn.execute(
                "select rental_minor, excess_minor, late_minor, total_minor, settled_by "
                "from gba.rental_settlements where booking_id = %s",
                (booking[0],),
            ).fetchall()
            assert settled == [(10000, 2500, 0, 12500, owner.user_id)], project
            charged = owner_conn.execute(
                "select c.number, c.amount_minor, c.reason, m.position "
                "from gba.rental_damage_charges c join gba.rental_damage_charge_marks m "
                "on m.tenant_id = c.tenant_id and m.booking_id = c.booking_id "
                "and m.number = c.number where c.booking_id = %s",
                (booking[0],),
            ).fetchall()
            assert charged == [(1, 8000, f"FAKE dent {project}", 1)], project
            refunded = owner_conn.execute(
                "select number, method, amount_minor, reason, reference "
                "from gba.rental_refunds where booking_id = %s",
                (booking[0],),
            ).fetchall()
            assert refunded == [(1, "external", 1000, "FAKE goodwill", f"FAKE-REF-{project}")], (
                project
            )
