"""O-09 customer proposal through OIDC, Chromium, the API and PostgreSQL."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_o1_construction_estimates import accepted, client, idp, line, manager_a
from tests.integration.test_o5_construction_billing import Billing, billing
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "billing", "client", "idp", "manager_a", "owner_a", "owner_b", "parties"]


@pytest.mark.anyio
async def test_customer_accepts_proposal_from_browser_link(
    billing: Billing,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: O-09 browser requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread((web / "out/construction/customer/index.html").is_file), (
        "build web first"
    )
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    customer = seed_user(owner_conn, "o9-customer", issuer=issuer)
    c = billing.c
    add_membership(
        owner_conn, tenant_id=c.world.b.tenant_id, user_id=customer.user_id, role="owner"
    )
    terms = {
        "permissions": ["construction.customer_answer"],
        "location_id": str(c.world.a.location_id),
    }
    revoked = await parties.active_grant(owner_a, owner_b, [customer], **terms)
    result = await parties.act(owner_a, billing.tenant, revoked, "revoke", 2)
    assert result.status_code == 200, result.text
    grant = await parties.active_grant(owner_a, owner_b, [customer], **terms)
    fixtures = {}
    for device in ("desktop", "mobile"):
        project = uuid7()
        assert (await c.project(project)).status_code == 200
        assert (await c.estimate(project, [line("FAKE customer scope")])).status_code == 200
        assert (await c.propose(project, 1)).status_code == 200
        linked = await c.send(
            "PUT",
            f"/projects/{project}/customer-company",
            {
                "expected_revision": 0,
                "expected_customer_generation": 1,
                "company_id": str(c.world.b.tenant_id),
            },
        )
        assert linked.status_code == 200, linked.text
        fixtures[device] = {
            "business": str(billing.tenant),
            "project": str(project),
            "grant": str(grant),
            "revoked": str(revoked),
        }

    provider, verifier = _provider(issuer, origin, FakeIdp(), customer)
    app = _management_app(test_database, verifier, issuer, web)
    env = {**_browser_env(origin, issuer), "GBA_CUSTOMER_PROPOSALS": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        browser = await asyncio.to_thread(
            subprocess.run,
            [
                npm,
                "exec",
                "--",
                "playwright",
                "test",
                "tests/construction-customer-proposal.spec.ts",
                "--max-failures=1",
            ],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        assert browser.returncode == 0, browser.stdout + browser.stderr
        print(browser.stdout)  # noqa: T201 - browser evidence in CI output

    with owner_tenant_transaction(owner_conn, billing.tenant):
        for fixture in fixtures.values():
            rows = owner_conn.execute(
                "select signatory, note, customer_grant_id, recorded_by "
                "from gba.construction_contracts where project_id=%s",
                (fixture["project"],),
            ).fetchall()
            assert rows == [
                ("FAKE signing delegate", "FAKE scope reviewed", grant, customer.user_id)
            ]
