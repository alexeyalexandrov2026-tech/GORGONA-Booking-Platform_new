"""O7b: the budget, commitments, schedule, daily reports and progress screens in a real browser.

docs/plan/PACKAGE_O7B_DESIGN_2026-11-02.md (desktop and mobile; FAKE data only). Actual OIDC/PKCE,
Chromium and PostgreSQL. A contracted project per browser is seeded through the routes; the browser
commits, schedules, reports and measures, and the database is read back.
"""

import os
import shutil
import subprocess
from datetime import date
from decimal import Decimal
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
from tests.integration.test_o1_construction_estimates import ENABLED, accepted, line
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted"]
PROJECTS = ("desktop", "mobile")


def test_construction_execution_screens_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    accepted: None,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: O7b browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/construction/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "o7b-owner", issuer=issuer)}
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

        call("PUT", f"{business}/profile", {"expected_revision": 0, "industry_ids": [19]})
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
        customer = uuid7()
        for party, name, roles in (
            (customer, "FAKE Homeowner", ["customer"]),
            (uuid7(), "FAKE Electric Co", ["contractor"]),
            (uuid7(), "FAKE Lumber", ["supplier"]),
        ):
            call("PUT", f"{business}/counterparties/{party}", card(display_name=name, roles=roles))
        base = f"{business}/construction/projects"
        for project in PROJECTS:
            project_id = uuid7()
            call(
                "PUT",
                f"{base}/{project_id}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "number": f"FAKE-CP-O7B-{project}",
                    "name": f"FAKE kitchen remodel {project}",
                    "customer_id": str(customer),
                    "location_id": str(world.a.location_id),
                    "site_address": "FAKE 1 Main St, Springfield",
                    "time_zone": "America/Chicago",
                    "currency": "USD",
                },
            )
            lines = [
                line("FAKE drywall"),
                line(
                    "FAKE wiring",
                    quantity="8",
                    cost=4000,
                    price=6500,
                    kind="labor",
                    phase="Electrical",
                    unit="hour",
                ),
            ]
            call(
                "POST",
                f"{base}/{project_id}/estimates",
                {"schema_version": 1, "based_on": 0, "note": "FAKE scope", "lines": lines},
            )
            call("POST", f"{base}/{project_id}/estimates/1/proposal", {"schema_version": 1})
            call(
                "POST",
                f"{base}/{project_id}/contract",
                {
                    "schema_version": 1,
                    "version": 1,
                    "signatory": "FAKE Homeowner",
                    "source": "paper",
                },
            )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:construction-execution"],
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
            found = owner_conn.execute(
                "select id from gba.construction_projects where number = %s",
                (f"FAKE-CP-O7B-{project}",),
            ).fetchone()
            assert found is not None, project
            project_id = found[0]
            # The subcontract and its revision above the budget line (32000).
            versions = owner_conn.execute(
                "select v.revision, v.state, l.change_order, l.budget_position, l.amount_minor "
                "from gba.construction_commitment_versions v "
                "join gba.construction_commitment_lines l on l.tenant_id = v.tenant_id "
                "and l.project_id = v.project_id and l.number = v.number "
                "and l.revision = v.revision where v.project_id = %s order by v.revision",
                (project_id,),
            ).fetchall()
            assert versions == [(1, "open", None, 2, 30000), (2, "open", None, 2, 34000)]
            kind = owner_conn.execute(
                "select kind, created_by from gba.construction_commitments where project_id = %s",
                (project_id,),
            ).fetchall()
            assert kind == [("subcontract", owner.user_id)]
            phases = owner_conn.execute(
                "select phase, planned_start, planned_finish from gba.construction_schedule_phases "
                "where project_id = %s and revision = 1 order by planned_start",
                (project_id,),
            ).fetchall()
            assert phases == [
                ("Framing", date(2031, 6, 2), date(2031, 6, 5)),
                ("Electrical", date(2031, 6, 6), date(2031, 6, 9)),
            ]
            depends = owner_conn.execute(
                "select phase, depends_on from gba.construction_schedule_dependencies "
                "where project_id = %s",
                (project_id,),
            ).fetchall()
            assert depends == [("Electrical", "Framing")]
            report = owner_conn.execute(
                "select r.report_date, r.revision, r.weather, c.label, c.headcount "
                "from gba.construction_daily_reports r join gba.construction_daily_report_crew c "
                "on c.tenant_id = r.tenant_id and c.project_id = r.project_id "
                "and c.report_date = r.report_date and c.revision = r.revision "
                "where r.project_id = %s",
                (project_id,),
            ).fetchall()
            assert report == [(date(2026, 10, 1), 1, "FAKE sunny", "FAKE framers", 3)]
            # The lost answer recorded the measurement once.
            measured = owner_conn.execute(
                "select change_order, budget_position, measured_on, quantity_to_date "
                "from gba.construction_progress_measurements where project_id = %s",
                (project_id,),
            ).fetchall()
            assert measured == [(None, 1, date(2026, 10, 1), Decimal("4.0000"))]
