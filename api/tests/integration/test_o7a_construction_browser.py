"""O7a: the construction screens in a real browser (desktop and mobile; FAKE data only).

docs/plan/PACKAGE_O7A_DESIGN_2026-11-02.md. Actual OIDC/PKCE, Chromium and PostgreSQL. The business,
its modules and the customer are seeded through the routes; the browser creates the project, two
estimate versions (the second after a lost answer), the proposal, the customer's acceptance and an
approved change order, and the database is read back.
"""

import os
import shutil
import subprocess
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
from tests.integration.test_o1_construction_estimates import ENABLED, accepted
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted"]
PROJECTS = ("desktop", "mobile")


def test_construction_screens_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    accepted: None,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: O7a browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/construction/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "o7a-owner", issuer=issuer)}
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
        call(
            "PUT",
            f"{business}/counterparties/{uuid7()}",
            card(display_name="FAKE Homeowner", roles=["customer"]),
        )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:construction"],
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
                "select id, time_zone, currency, location_id, created_by "
                "from gba.construction_projects where number = %s",
                (f"FAKE-CP-{project}",),
            ).fetchone()
            assert head is not None, project
            project_id = head[0]
            assert head[1:] == ("America/Chicago", "USD", world.a.location_id, owner.user_id)
            # Two versions: the lost answer was saved once; the second is the proposal.
            versions = owner_conn.execute(
                "select version, note, proposed_by from gba.construction_estimate_versions "
                "where project_id = %s order by version",
                (project_id,),
            ).fetchall()
            assert versions == [(1, "FAKE scope", None), (2, "FAKE scope", owner.user_id)]
            lines = owner_conn.execute(
                "select position, kind, quantity, unit_cost_minor, unit_price_minor "
                "from gba.construction_estimate_lines where project_id = %s and version = 2 "
                "order by position",
                (project_id,),
            ).fetchall()
            assert lines == [
                (1, "material", Decimal("12.0000"), 1500, 2500),
                (2, "labor", Decimal("8.0000"), 4000, 6500),
            ]
            contract = owner_conn.execute(
                "select version, signatory, source, recorded_by "
                "from gba.construction_contracts where project_id = %s",
                (project_id,),
            ).fetchall()
            assert contract == [(2, "FAKE Homeowner", "paper", owner.user_id)]
            change = owner_conn.execute(
                "select l.position, l.action, l.contract_position, l.quantity, "
                "l.unit_price_minor, o.days_delta "
                "from gba.construction_change_order_lines l "
                "join gba.construction_change_orders o on o.tenant_id = l.tenant_id "
                "and o.project_id = l.project_id and o.number = l.number "
                "where l.project_id = %s order by l.number, l.position",
                (project_id,),
            ).fetchall()
            assert change == [
                (1, "add", None, Decimal("2.0000"), 5000, 2),
                (2, "remove", 1, Decimal("2.0000"), None, 2),
            ]
            decision = owner_conn.execute(
                "select number, decision, source, decided_by "
                "from gba.construction_change_order_decisions where project_id = %s",
                (project_id,),
            ).fetchall()
            assert decision == [(1, "approved", "email", owner.user_id)]
