"""Resource reservations through real OIDC/PKCE, Chromium, API and PostgreSQL (FAKE data)."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import seed_user
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp


def test_real_reservation_browser_oidc_pkce_and_database(
    world: BookingWorld, owner_conn: psycopg.Connection, test_database: ProvisionedDatabase
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: reservation browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/reservations/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, f"FAKE-reservation-browser-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    idp = FakeIdp()
    provider, verifier = _provider(issuer, origin, idp, owner)
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    with live_server(provider, idp_port), live_server(app, app_port):
        result = subprocess.run(  # noqa: S603 - fixed repository test script
            [npm, "run", "test:management:reservations"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - browser evidence in pytest -s
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        assert owner_conn.execute(
            "select status, purpose from gba.resource_reservations"
        ).fetchall() == [("cancelled", "FAKE team training")]
        assert owner_conn.execute(
            "select resource_id, state from gba.resource_allocations "
            "where source_kind = 'reservation' order by resource_id"
        ).fetchall() == sorted([(world.artist_a1, "released"), (world.artist_a2, "released")])
        audits = owner_conn.execute(
            "select action, details from gba.audit_events "
            "where action like 'resource_reservation.%%' order by occurred_at"
        ).fetchall()
        assert [row[0] for row in audits] == [
            "resource_reservation.created",
            "resource_reservation.cancelled",
        ]
        assert "FAKE" not in json.dumps([row[1] for row in audits])
        receipts = owner_conn.execute(
            "select response_body from gba.idempotency_keys "
            "where operation like 'business.reservation.%%'"
        ).fetchall()
        assert len(receipts) == 2
