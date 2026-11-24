"""An owner prepares customer links through the actual project and delegation screens."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast
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
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_o1_construction_estimates import accepted, client, idp, line, manager_a
from tests.integration.test_o5_construction_billing import Billing, billing
from tests.integration.test_o6a_construction_acceptance import later
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "billing", "client", "idp", "manager_a"]


@pytest.mark.anyio
async def test_operator_links_customer_and_issues_construction_access_in_browser(
    billing: Billing, owner_conn: psycopg.Connection, test_database: ProvisionedDatabase
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: customer access browser requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread((web / "out/construction/index.html").is_file), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, "o9-access-owner", issuer=issuer)
    customer = seed_user(owner_conn, "o9-access-customer", issuer=issuer)
    add_membership(owner_conn, tenant_id=billing.tenant, user_id=owner.user_id, role="owner")
    c = billing.c
    fixtures = {}
    companies: set[UUID] = set()
    for device in ("desktop", "mobile"):
        company = provision_tenant(
            owner_conn, slug=f"fake-access-{uuid7().hex}", display_name=f"FAKE customer {device}"
        )
        add_membership(owner_conn, tenant_id=company, user_id=customer.user_id, role="owner")
        project = uuid7()
        assert (await c.project(project)).status_code == 200
        assert (await c.estimate(project, [line("FAKE operator scope")])).status_code == 200
        assert (await c.propose(project, 1)).status_code == 200
        companies.add(company)
        fixtures[device] = {
            "business": str(billing.tenant),
            "company": str(company),
            "project": str(project),
            "number": f"FAKE-CP-{project.hex[-8:]}",
            "location": str(c.world.a.location_id),
            "expires": later(7),
        }
    live_idp = FakeIdp()
    signed_in = _SignedIn({"owner": owner, "customer": customer})
    provider, verifier = _provider(issuer, origin, live_idp, cast(FakeUser, signed_in))
    app = _management_app(test_database, verifier, issuer, web)

    @provider.post("/browser/user/{person}")
    async def switch_user(person: str) -> dict[str, bool]:
        if person not in signed_in.people:
            raise HTTPException(404)
        signed_in.name = person
        return {"selected": True}

    @provider.post("/browser/revoke/{company_id}")
    async def revoke(company_id: UUID) -> dict[str, bool]:
        if company_id not in companies:
            raise HTTPException(404)
        headers = live_idp.bearer(owner.subject, email=owner.email, iss=issuer)
        headers["Idempotency-Key"] = str(uuid7())
        async with httpx.AsyncClient(base_url=origin, headers=headers) as requests:
            listed = await requests.get(f"/v1/businesses/{billing.tenant}/delegations")
            assert listed.status_code == 200, listed.text
            active = [
                grant
                for grant in listed.json()["items"]
                if grant["servicer_business_id"] == str(company_id) and grant["status"] == "active"
            ]
            assert len(active) == 1
            grant = active[0]
            revoked = await requests.post(
                f"/v1/businesses/{billing.tenant}/delegations/{grant['grant_id']}/revoke",
                json={"expected_revision": grant["revision"]},
            )
        assert revoked.status_code == 200, revoked.text
        return {"revoked": True}

    env = {**_browser_env(origin, issuer), "GBA_CUSTOMER_ACCESS": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        browser = await asyncio.to_thread(
            subprocess.run,
            [
                npm,
                "exec",
                "--",
                "playwright",
                "test",
                "tests/construction-customer-access.spec.ts",
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
        print(browser.stdout)  # noqa: T201 - browser evidence in CI
    with owner_tenant_transaction(owner_conn, billing.tenant):
        for fixture in fixtures.values():
            bindings = owner_conn.execute(
                "select revision, company_id from gba.construction_customer_companies "
                "where project_id=%s",
                (fixture["project"],),
            ).fetchall()
            assert bindings == [(1, UUID(fixture["company"]))]
            rows = owner_conn.execute(
                "select source, customer_company_id, recorded_by from gba.construction_contracts "
                "where project_id=%s",
                (fixture["project"],),
            ).fetchall()
            assert rows == [("platform", UUID(fixture["company"]), customer.user_id)]
            grant = owner_conn.execute(
                "select status, cardinality(permissions) from gba.delegation_grants "
                "where owner_tenant_id=%s and servicer_tenant_id=%s",
                (billing.tenant, fixture["company"]),
            ).fetchall()
            assert grant == [("revoked", 9)]
