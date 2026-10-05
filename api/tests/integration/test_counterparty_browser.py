"""Counterparties through real OIDC/PKCE, Chromium, API and PostgreSQL (FAKE fixture data)."""

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import customer_day, seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import seed_user
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp


def test_real_counterparty_browser_oidc_pkce_and_database(
    world: BookingWorld, owner_conn: psycopg.Connection, test_database: ProvisionedDatabase
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: counterparty browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/counterparties/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, f"FAKE-counterparty-browser-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    idp = FakeIdp()
    provider, verifier = _provider(issuer, origin, idp, owner)
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    env["GBA_CP_BUSINESS"] = str(world.a.tenant_id)
    headers = {**idp.bearer(owner.subject, email=owner.email, iss=issuer)}
    with (
        live_server(provider, idp_port),
        live_server(app, app_port),
    ):

        def request(method: str, suffix: str, body: dict[str, object]) -> dict[str, object]:
            result = httpx.request(
                method,
                f"{origin}/v1/businesses/{world.a.tenant_id}/{suffix}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=10,
            )
            assert result.status_code == 200, result.text
            data: dict[str, object] = result.json()
            return data

        request("PUT", "profile", {"expected_revision": 0, "industry_ids": [1, 6, 24]})
        request(
            "PUT",
            "configuration/draft",
            {
                "expected_version": 0,
                "profile_revision": 1,
                "module_ids": ["booking_resources", "counterparties"],
            },
        )
        request("POST", "configuration/versions/1/validate", {"expected_revision": 1})
        request("POST", "configuration/versions/1/publish", {"expected_revision": 2})
        starts = datetime.fromisoformat(f"{customer_day()}T11:00:00").replace(
            tzinfo=ZoneInfo("America/New_York")
        )
        seeded = httpx.post(
            f"{origin}/v1/salons/{world.a.tenant_id}/bookings",
            headers=headers,
            json={
                "location_id": str(world.a.location_id),
                "resource_id": str(world.artist_a1),
                "variant_id": str(world.catalog_a.base_variant_id),
                "starts_at": starts.isoformat(),
                "customer_name": "FAKE Counterparty Browser Guest",
                "customer_email": "fake.counterparty@example.test",
                "customer_phone": "+15550101234",
            },
            timeout=10,
        )
        assert seeded.status_code == 201, seeded.text
        with owner_tenant_transaction(owner_conn, world.a.tenant_id):
            original_booking = owner_conn.execute("select * from gba.booking_customers").fetchall()
        result = subprocess.run(  # noqa: S603 - fixed repository test script
            [npm, "run", "test:management:counterparties"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - browser evidence in pytest -s
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        assert owner_conn.execute("select count(*) from gba.counterparties").fetchone() == (2,)
        assert (
            owner_conn.execute("select * from gba.booking_customers").fetchall() == original_booking
        )
        assert owner_conn.execute(
            "select kind from gba.counterparty_match_decisions order by id"
        ).fetchall() == [("merged",), ("separated",)]
        assert owner_conn.execute(
            "select action from gba.counterparty_booking_links order by sequence"
        ).fetchall() == [("linked",), ("unlinked",)]
        receipts = owner_conn.execute(
            "select response_body from gba.idempotency_keys "
            "where operation like 'business.counterparty.%'"
        ).fetchall()
        assert "example.test" not in json.dumps([row[0] for row in receipts])
