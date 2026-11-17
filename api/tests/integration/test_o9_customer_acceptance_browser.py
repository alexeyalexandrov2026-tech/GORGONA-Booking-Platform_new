"""Customer acceptance reviews and their immutable proof through OIDC and Chromium."""

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
from tests.integration.test_o4a_construction_execution import TWO_LINES, ago, measure, signed_at
from tests.integration.test_o5_construction_billing import Billing, billing, pay
from tests.integration.test_o6a_construction_acceptance import later
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "billing", "client", "idp", "manager_a", "owner_a", "owner_b", "parties"]


@pytest.mark.anyio
async def test_customer_accepts_reviewed_work_in_browser(
    billing: Billing,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: customer acceptance browser requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread(
        (web / "out/construction/customer/acceptance/index.html").is_file
    ), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    customer = seed_user(owner_conn, "o9-work-customer", issuer=issuer)
    owner = seed_user(owner_conn, "o9-work-owner", issuer=issuer)
    add_membership(owner_conn, tenant_id=billing.tenant, user_id=owner.user_id, role="owner")
    c = billing.c
    fixtures = {}
    projects: set[UUID] = set()
    for device in ("desktop", "mobile"):
        company = provision_tenant(
            owner_conn, slug=f"fake-work-{uuid7().hex}", display_name="FAKE customer company"
        )
        for user in (customer, owner_b):
            add_membership(owner_conn, tenant_id=company, user_id=user.user_id, role="owner")
        project = await signed_at(c, TWO_LINES)
        for position, quantity in ((1, "10"), (2, "3.3333")):
            assert (await measure(c, project, position, quantity, ago(10))).status_code == 200
        assert (await pay(billing, project, ago(8))).status_code == 200
        linked = await c.send(
            "PUT",
            f"/projects/{project}/customer-company",
            {"expected_revision": 0, "expected_customer_generation": 1, "company_id": str(company)},
        )
        assert linked.status_code == 200, linked.text
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
        projects.add(project)
        fixtures[device] = {
            "business": str(billing.tenant),
            "project": str(project),
            "grant": str(grant),
            "warranty": later(365),
            "invalid_warranty": later(365 * 11),
        }
    live_idp = FakeIdp()
    provider, verifier = _provider(issuer, origin, live_idp, customer)
    app = _management_app(test_database, verifier, issuer, web)

    @provider.post("/browser/revise/{project_id}")
    async def revise(project_id: UUID) -> dict[str, bool]:
        if project_id not in projects:
            raise HTTPException(404)
        headers = live_idp.bearer(owner.subject, email=owner.email, iss=issuer)
        headers["Idempotency-Key"] = str(uuid7())
        async with httpx.AsyncClient(base_url=origin, headers=headers) as requests:
            response = await requests.post(
                f"/v1/businesses/{billing.tenant}/construction/projects/{project_id}/progress",
                json={
                    "schema_version": 1,
                    "change_order": None,
                    "position": 1,
                    "measured_on": ago(7),
                    "quantity_to_date": "10",
                    "note": None,
                },
            )
        assert response.status_code == 200, response.text
        return {"updated": True}

    env = {**_browser_env(origin, issuer), "GBA_CUSTOMER_WORK": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        browser = await asyncio.to_thread(
            subprocess.run,
            [
                npm,
                "exec",
                "--",
                "playwright",
                "test",
                "tests/construction-customer-acceptance.spec.ts",
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
        print(browser.stdout)  # noqa: T201 - real browser checks in CI
    with owner_tenant_transaction(owner_conn, billing.tenant):
        for fixture in fixtures.values():
            rows = owner_conn.execute(
                "select scope, phase, signatory, source, warranty_ends_on::text, "
                "customer_grant_id, recorded_by, length(customer_review_hash) "
                "from gba.construction_acceptances where project_id=%s order by number",
                (fixture["project"],),
            ).fetchall()
            proof = (UUID(fixture["grant"]), customer.user_id, 64)
            assert rows == [
                ("phase", "Framing", "FAKE work delegate", "platform", None, *proof),
                ("final", None, "FAKE work delegate", "platform", fixture["warranty"], *proof),
            ]
