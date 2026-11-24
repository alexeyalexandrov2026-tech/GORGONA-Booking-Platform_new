"""R8b: rate cards, the agreement and the security in a real browser (desktop, mobile; FAKE data).

docs/plan/PACKAGE_R8B_DESIGN_2026-11-11.md. Actual OIDC/PKCE, Chromium and PostgreSQL. The business,
its modules and the customer are seeded through the routes; the browser adds a rate card, books,
accepts the agreement and records the security, and the database is read back.
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


def test_rental_agreement_screens_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    accepted: None,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: R8b browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/rental/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "r8b-owner", issuer=issuer)}
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
            [npm, "run", "test:management:rental-agreement"],
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
            car = owner_conn.execute(
                "select id from gba.rental_classes where code = %s", (f"FAKE-AG-{project.upper()}",)
            ).fetchone()
            assert car is not None, project
            priced = owner_conn.execute(
                "select version, currency, day_rate, meter_allowance_per_day, excess_rate, "
                "created_by "
                "from gba.rental_rate_cards where class_id = %s",
                (car[0],),
            ).fetchall()
            assert priced == [(1, "USD", 5000, 100, 25, owner.user_id)], project
            agreed = owner_conn.execute(
                "select v.version, v.total, v.source, v.accepted_by "
                "from gba.rental_agreement_versions v "
                "join gba.rental_agreements a on a.tenant_id = v.tenant_id "
                "and a.id = v.agreement_id "
                "join gba.rental_bookings b on b.tenant_id = a.tenant_id and b.id = a.booking_id "
                "where b.class_id = %s",
                (car[0],),
            ).fetchall()
            assert agreed == [(1, 10000, "paper", "FAKE Renter")], project
            secured = owner_conn.execute(
                "select s.amount, s.currency, s.method, e.sequence, e.kind, e.amount, e.reference, "
                "e.basis from gba.rental_securities s join gba.rental_security_events e "
                "on e.tenant_id = s.tenant_id and e.security_id = s.id "
                "join gba.rental_bookings b on b.tenant_id = s.tenant_id and b.id = s.booking_id "
                "where b.class_id = %s order by e.sequence",
                (car[0],),
            ).fetchall()
            scratch = f"FAKE scratch {project}"
            assert secured == [
                (20000, "USD", "card_hold", 1, "held", 20000, f"FAKE-TERM-{project}", None),
                (20000, "USD", "card_hold", 2, "captured", 3000, None, scratch),
            ], project
