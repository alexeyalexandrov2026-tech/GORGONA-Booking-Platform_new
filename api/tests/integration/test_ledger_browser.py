"""Real OIDC/PKCE + Chromium + ledger API + PostgreSQL with the accepted registry."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid7

import httpx
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


def test_real_ledger_browser_oidc_pkce_and_database(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: ledger browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/ledger/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, f"FAKE-ledger-browser-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    idp = FakeIdp()
    provider, verifier = _provider(issuer, origin, idp, owner)
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    with live_server(provider, idp_port), live_server(app, app_port):

        def request(method: str, suffix: str, body: dict[str, object]) -> None:
            response = httpx.request(
                method,
                f"{origin}/v1/businesses/{world.a.tenant_id}/{suffix}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=10,
            )
            assert response.status_code == 200, response.text

        request("PUT", "profile", {"expected_revision": 0, "industry_ids": [1]})
        request(
            "PUT",
            "configuration/draft",
            {
                "expected_version": 0,
                "profile_revision": 1,
                "module_ids": ["booking_resources", "finance"],
            },
        )
        request("POST", "configuration/versions/1/validate", {"expected_revision": 1})
        request("POST", "configuration/versions/1/publish", {"expected_revision": 2})
        for project in ("desktop", "mobile"):
            request(
                "PUT",
                f"legal-entities/{uuid7()}",
                {
                    "expected_revision": 0,
                    "code": f"FAKE_{project.upper()}",
                    "legal_name": f"FAKE {project} Ledger LLC",
                },
            )
        result = subprocess.run(  # noqa: S603 - fixed repository script and located npm
            [npm, "run", "test:management:ledger"],
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
        assert owner_conn.execute("select count(*) from gba.ledger_books").fetchone() == (2,)
        assert owner_conn.execute("select count(*) from gba.journal_entries").fetchone() == (6,)
        assert owner_conn.execute("select count(*) from gba.journal_lines").fetchone() == (12,)
        assert owner_conn.execute(
            "select count(*) from gba.ledger_command_cancellations"
        ).fetchone() == (2,)
        assert owner_conn.execute("select count(*) from gba.ledger_period_events").fetchone() == (
            4,
        )
        audits = owner_conn.execute(
            "select details from gba.audit_events where action like 'ledger.%%'"
        ).fetchall()
        receipts = owner_conn.execute(
            "select response_body from gba.idempotency_keys "
            "where operation like 'business.ledger.%%'"
        ).fetchall()
        assert len(receipts) == 14
        assert "FAKE" not in json.dumps([r[0] for r in audits])
        assert "FAKE" not in json.dumps([r[0] for r in receipts])
