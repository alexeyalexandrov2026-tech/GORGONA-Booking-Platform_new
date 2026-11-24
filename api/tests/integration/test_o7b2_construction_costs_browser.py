"""O7b2 actual cost links in Chromium against the real API and disposable PostgreSQL."""

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
from tests.integration.test_o3b_construction_costs import (
    Costs,
    accepted,
    billed,
    client,
    costs,
    idp,
    manager_a,
    signed_in,
    stocked,
    worked,
    written_off,
)
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "client", "costs", "idp", "manager_a", "stocked"]


@pytest.mark.anyio
async def test_construction_costs_in_real_browser(
    costs: Costs, owner_conn: psycopg.Connection, test_database: ProvisionedDatabase
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: O7b2 browser requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread((web / "out/construction/index.html").is_file), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    fixtures: dict[str, dict[str, str]] = {}
    for browser_project, hour in (("desktop", 9), ("mobile", 12)):
        project = await signed_in(costs.c)
        _, write_off = await written_off(costs)
        book, document, line = await billed(costs)
        entry = await worked(costs, hour)
        fixtures[browser_project] = {
            "number": f"FAKE-CP-{project.hex[-8:]}",
            "project": str(project),
            "stock": str(write_off),
            "book": str(book),
            "payable": str(document),
            "payable_line": str(line),
            "time_entry": str(entry),
        }

    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, "o7b2-owner", issuer=issuer)
    add_membership(owner_conn, tenant_id=costs.tenant, user_id=owner.user_id, role="owner")
    provider, verifier = _provider(
        issuer, origin, FakeIdp(), cast(FakeUser, _SignedIn({"owner": owner}))
    )
    app = _management_app(test_database, verifier, issuer, web)
    env = {**_browser_env(origin, issuer), "GBA_COST_BROWSER_FIXTURES": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        result = await asyncio.to_thread(
            subprocess.run,
            [npm, "exec", "--", "playwright", "test", "tests/construction-costs.spec.ts"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - browser results in CI output

    with owner_tenant_transaction(owner_conn, costs.tenant):
        for fixture in fixtures.values():
            rows = owner_conn.execute(
                "select c.number, c.kind, c.amount_minor, c.stock_document_id::text, "
                "c.document_id::text, c.time_entry_id::text, r.reason "
                "from gba.construction_cost_links c left join gba.construction_cost_reversals r "
                "on (r.tenant_id, r.project_id, r.number) = (c.tenant_id, c.project_id, c.number) "
                "where c.project_id = %s order by c.number",
                (fixture["project"],),
            ).fetchall()
            assert rows == [
                (1, "stock_write_off", 1000, fixture["stock"], None, None, "Wrong budget line"),
                (2, "payable", 4000, None, fixture["payable"], None, None),
                (3, "time_entry", 6000, None, None, fixture["time_entry"], None),
            ]
