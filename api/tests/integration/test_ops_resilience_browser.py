"""OPS-03 browser E2E test: desktop/mobile layout, keyboard nav, 503/409 error recovery."""

import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import seed_user
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp


def test_real_ops03_resilience_mobile_keyboard_and_error_recovery_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: OPS-03 browser suite requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/counterparties/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, f"FAKE-ops03-browser-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    idp = FakeIdp()
    provider, verifier = _provider(issuer, origin, idp, owner)
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    headers = {**idp.bearer(owner.subject, email=owner.email, iss=issuer)}
    with (
        live_server(provider, idp_port),
        live_server(app, app_port),
    ):

        def request(method: str, suffix: str, body: dict[str, object]) -> None:
            result = httpx.request(
                method,
                f"{origin}/v1/businesses/{world.a.tenant_id}/{suffix}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=10,
            )
            assert result.status_code == 200, result.text

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

        result = subprocess.run(  # noqa: S603 - fixed repository test script
            [npm, "run", "test:management:ops"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - browser evidence in pytest -s
