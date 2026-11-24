"""Customer change answers in Chromium with OIDC, PostgreSQL and live grant revocation."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from fastapi import HTTPException

from gorgona_booking.db.provisioning import (
    add_membership,
    owner_tenant_transaction,
    provision_tenant,
)
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_o1_construction_estimates import accepted, client, idp, manager_a
from tests.integration.test_o2_construction_contract import add, change, remove, signed
from tests.integration.test_o5_construction_billing import Billing, billing
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "billing", "client", "idp", "manager_a", "owner_a", "owner_b", "parties"]


@pytest.mark.anyio
async def test_customer_answers_change_orders_in_browser(
    billing: Billing,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: O-09 change browser requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread((web / "out/construction/customer/change/index.html").is_file), (
        "build web first"
    )
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    customer = seed_user(owner_conn, "o9-change-customer", issuer=issuer)
    approver = seed_user(owner_conn, "o9-change-owner", issuer=issuer)
    c = billing.c
    add_membership(owner_conn, tenant_id=billing.tenant, user_id=approver.user_id, role="owner")
    fixtures = {}
    grants: set[UUID] = set()
    for device in ("desktop", "mobile"):
        company = provision_tenant(
            owner_conn, slug=f"fake-o9-{device}-{uuid7().hex}", display_name="FAKE customer company"
        )
        for user in (customer, owner_b):
            add_membership(owner_conn, tenant_id=company, user_id=user.user_id, role="owner")
        project = await signed(c)
        linked = await c.send(
            "PUT",
            f"/projects/{project}/customer-company",
            {
                "expected_revision": 0,
                "expected_customer_generation": 1,
                "company_id": str(company),
            },
        )
        assert linked.status_code == 200, linked.text
        for _ in range(3):
            made = await change(
                c,
                project,
                [remove(1, "2"), add("FAKE added scope", quantity="1", price=7500)],
                days=-2,
            )
            assert made.status_code == 200, made.text
        grant = uuid7()
        issued = await parties.issue(
            owner_a,
            grant,
            terms={
                "servicer_business_id": str(company),
                "permissions": ["construction.customer_answer"],
                "location_id": str(c.world.a.location_id),
            },
        )
        assert issued.status_code == 200, issued.text
        selected = await parties.act(owner_b, company, grant, "accept", 1, [customer])
        assert selected.status_code == 200, selected.text
        grants.add(grant)
        fixtures[device] = {
            "business": str(billing.tenant),
            "project": str(project),
            "grant": str(grant),
        }
    live_idp = FakeIdp()
    provider, verifier = _provider(issuer, origin, live_idp, customer)
    app = _management_app(test_database, verifier, issuer, web)

    # This test-only provider endpoint invokes the real owner API after the page loaded.
    @provider.post("/browser/revoke/{grant_id}")
    async def revoke(grant_id: UUID) -> dict[str, bool]:
        if grant_id not in grants:
            raise HTTPException(404)
        headers = live_idp.bearer(approver.subject, email=approver.email, iss=issuer)
        headers["Idempotency-Key"] = str(uuid7())
        async with httpx.AsyncClient(base_url=origin, headers=headers) as requests:
            response = await requests.post(
                f"/v1/businesses/{billing.tenant}/delegations/{grant_id}/revoke",
                json={"expected_revision": 2},
            )
        assert response.status_code == 200, response.text
        return {"revoked": True}

    env = {**_browser_env(origin, issuer), "GBA_CUSTOMER_CHANGES": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        browser = await asyncio.to_thread(
            subprocess.run,
            [
                npm,
                "exec",
                "--",
                "playwright",
                "test",
                "tests/construction-customer-change.spec.ts",
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
        print(browser.stdout)  # noqa: T201 - real browser verification in CI
    with owner_tenant_transaction(owner_conn, billing.tenant):
        for fixture in fixtures.values():
            rows = owner_conn.execute(
                "select number, decision, note, customer_grant_id, decided_by "
                "from gba.construction_change_order_decisions where project_id=%s order by number",
                (fixture["project"],),
            ).fetchall()
            grant_id = UUID(fixture["grant"])
            assert rows == [
                (1, "approved", "FAKE reviewed scope", grant_id, customer.user_id),
                (2, "rejected", "FAKE out of scope", grant_id, customer.user_id),
            ]
