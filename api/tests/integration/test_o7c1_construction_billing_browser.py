"""O7c1 pay applications in Chromium against PostgreSQL and the real API."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast
from uuid import uuid7

import psycopg
import pytest
from fastapi import HTTPException

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_o2_construction_contract import accept
from tests.integration.test_o4a_construction_execution import TWO_LINES, ago, measure
from tests.integration.test_o5_construction_billing import (
    Billing,
    accepted,
    billing,
    client,
    idp,
    manager_a,
)
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "billing", "client", "idp", "manager_a"]


@pytest.mark.anyio
async def test_construction_pay_application_in_real_browser(
    billing: Billing, owner_conn: psycopg.Connection, test_database: ProvisionedDatabase
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: O7c1 browser requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread((web / "out/construction/index.html").is_file), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    fixtures = {}
    for target, currency in (("desktop", "USD"), ("mobile", "JPY")):
        project = uuid7()
        saved = await billing.c.project(project, currency=currency)
        assert saved.status_code == 200, saved.text
        assert (await billing.c.estimate(project, TWO_LINES)).status_code == 200
        assert (await billing.c.propose(project, 1)).status_code == 200
        assert (await accept(billing.c, project, 1)).status_code == 200
        response = await measure(billing.c, project, 1, "4", ago(10))
        assert response.status_code == 200, response.text
        fixtures[target] = {
            "project": str(project),
            "project_number": f"FAKE-CP-{project.hex[-8:]}",
            "document_number": f"FAKE-PA-{project.hex[-8:]}",
            "period": ago(8),
            "book": str(billing.book),
            "receivable": str(billing.chart["1200"]),
            "revenue": str(billing.chart["4100"]),
            "retainage": str(billing.retainage),
            "currency": currency,
        }

    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, "o7c1-owner", issuer=issuer)
    add_membership(owner_conn, tenant_id=billing.tenant, user_id=owner.user_id, role="owner")
    branch = seed_user(owner_conn, "o7c1-branch", issuer=issuer)
    add_membership(
        owner_conn,
        tenant_id=billing.tenant,
        user_id=branch.user_id,
        role="manager",
        location_id=billing.c.world.a.location_id,
    )
    people = {"owner": owner, "branch": branch}
    signed_in = _SignedIn(people)
    provider, verifier = _provider(issuer, origin, FakeIdp(), cast(FakeUser, signed_in))

    @provider.post("/fixture/user/{name}")
    async def switch_person(name: str) -> None:
        if name not in people:
            raise HTTPException(404, "Unknown FAKE person")
        signed_in.name = name

    app = _management_app(test_database, verifier, issuer, web)
    env = {**_browser_env(origin, issuer), "GBA_PAY_APPLICATION_FIXTURES": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        result = await asyncio.to_thread(
            subprocess.run,
            [
                npm,
                "exec",
                "--",
                "playwright",
                "test",
                "tests/construction-billing.spec.ts",
                "--max-failures=1",
            ],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - browser results in CI output

    with owner_tenant_transaction(owner_conn, billing.tenant):
        for fixture in fixtures.values():
            rows = owner_conn.execute(
                "select number, rate_revision, rate_bp, this_period_minor, "
                "retained_minor, due_minor, invoice_document_id <> retainage_document_id "
                "from gba.construction_pay_applications where project_id = %s order by number",
                (fixture["project"],),
            ).fetchall()
            assert rows == [(1, 1, 1000, 10000, 1000, 9000, True)]
