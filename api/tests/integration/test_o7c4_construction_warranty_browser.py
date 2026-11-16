"""O7c4 warranty claims and repair cost through Chromium, the API and PostgreSQL."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_o4a_construction_execution import ago
from tests.integration.test_o5_construction_billing import (
    Billing,
    accepted,
    billing,
    client,
    idp,
    manager_a,
)
from tests.integration.test_o6b_construction_warranty import cost, finished
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "billing", "client", "idp", "manager_a"]


@pytest.mark.anyio
async def test_warranty_claim_in_real_browser(
    billing: Billing, owner_conn: psycopg.Connection, test_database: ProvisionedDatabase
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: O7c4 browser requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread((web / "out/construction/index.html").is_file), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    fixtures = {}
    for target in ("desktop", "mobile"):
        project = await finished(billing)
        linked = await cost(billing, project, "25.00")
        fixtures[target] = {
            "project": str(project),
            "project_number": f"FAKE-CP-{project.hex[-8:]}",
            "link": str(linked),
            "reported": ago(1),
        }

    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, "o7c4-owner", issuer=issuer)
    add_membership(owner_conn, tenant_id=billing.tenant, user_id=owner.user_id, role="owner")
    provider, verifier = _provider(
        issuer, origin, FakeIdp(), cast(FakeUser, _SignedIn({"owner": owner}))
    )
    app = _management_app(test_database, verifier, issuer, web)
    env = {**_browser_env(origin, issuer), "GBA_WARRANTY_FIXTURES": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        result = await asyncio.to_thread(
            subprocess.run,
            [
                npm,
                "exec",
                "--",
                "playwright",
                "test",
                "tests/construction-warranty.spec.ts",
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
            project_id = fixture["project"]
            claims = owner_conn.execute(
                "select number, phase, raised_on::text from gba.construction_warranty_claims "
                "where project_id=%s",
                (project_id,),
            ).fetchall()
            assert claims == [(1, "Finishes", fixture["reported"])]
            events = owner_conn.execute(
                "select sequence, state from gba.construction_warranty_claim_events "
                "where project_id=%s order by sequence",
                (project_id,),
            ).fetchall()
            assert events == [(1, "repaired"), (2, "open"), (3, "repaired"), (4, "closed")]
            repairs = owner_conn.execute(
                "select a.cost_link, r.reason from gba.construction_warranty_repairs a "
                "join gba.construction_cost_reversals r "
                "on (a.tenant_id, a.project_id, a.cost_link) "
                "= (r.tenant_id, r.project_id, r.number) "
                "where a.project_id=%s",
                (project_id,),
            ).fetchall()
            assert repairs == [(int(fixture["link"]), "FAKE corrected ledger fact")]
