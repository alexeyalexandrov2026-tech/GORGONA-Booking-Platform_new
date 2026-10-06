"""Contracts through real OIDC/PKCE, Chromium, API and PostgreSQL (FAKE fixture data)."""

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
from tests.integration.test_counterparties import card
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp


def test_real_agreement_browser_oidc_pkce_and_database(
    world: BookingWorld, owner_conn: psycopg.Connection, test_database: ProvisionedDatabase
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: contract browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/counterparties/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, f"FAKE-agreement-browser-{uuid7()}", issuer=issuer)
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
        request(
            "PUT",
            f"counterparties/{uuid7()}",
            card(display_name="FAKE Contract Partner", email=None, phone=None),
        )
        result = subprocess.run(  # noqa: S603 - fixed repository test script
            [npm, "run", "test:management:agreements"],
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
        assert owner_conn.execute("select count(*) from gba.agreements").fetchone() == (1,)
        assert owner_conn.execute(
            "select revision, state, title, attestation is not null "
            "from gba.agreement_versions order by revision"
        ).fetchall() == [
            (1, "draft", "FAKE Service contract", False),
            (2, "agreed", "FAKE Service contract", True),
            (3, "draft", "FAKE Service contract v2", False),
            (4, "agreed", "FAKE Service contract v2", True),
            (5, "draft", "FAKE Service contract v3", False),
            (6, "terminated", "FAKE Service contract v2", True),
        ]
        # The termination ends agreed version 4 from a future date (set by the browser).
        ended = owner_conn.execute(
            "select terminates_revision, terminated_on > signed_on "
            "from gba.agreement_versions where state = 'terminated'"
        ).fetchone()
        assert ended == (4, True)
        audits = owner_conn.execute(
            "select action, details from gba.audit_events "
            "where action like 'agreement.%%' order by id"
        ).fetchall()
        assert [row[0] for row in audits] == [
            "agreement.drafted",
            "agreement.agreed",
            "agreement.drafted",
            "agreement.agreed",
            "agreement.drafted",
            "agreement.terminated",
        ]
        assert audits[-1][1]["terminates_revision"] == 4
        assert audits[-1][1]["abandoned_draft_revision"] == 5
        receipts = owner_conn.execute(
            "select response_body from gba.idempotency_keys "
            "where operation like 'business.agreement.%%'"
        ).fetchall()
        assert len(receipts) == 6
        assert "FAKE" not in json.dumps([row[1] for row in audits])
        assert "FAKE" not in json.dumps([row[0] for row in receipts])
