"""O7c2 acceptance and retainage release through Chromium, the API and PostgreSQL."""

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
from tests.integration.test_o4a_construction_execution import TWO_LINES, ago, measure, signed_at
from tests.integration.test_o5_construction_billing import (
    Billing,
    accepted,
    billing,
    client,
    idp,
    manager_a,
    pay,
    rate,
)
from tests.integration.test_o6a_construction_acceptance import later
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "billing", "client", "idp", "manager_a"]


@pytest.mark.anyio
async def test_acceptance_and_release_in_real_browser(
    billing: Billing, owner_conn: psycopg.Connection, test_database: ProvisionedDatabase
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: O7c2 browser requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread((web / "out/construction/index.html").is_file), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    fixtures = {}
    for target in ("desktop", "mobile"):
        project = await signed_at(billing.c, TWO_LINES)
        for response in (
            await rate(billing, project, 0, 1000),
            await measure(billing.c, project, 1, "10", ago(10)),
            await measure(billing.c, project, 2, "3.3333", ago(10)),
            await pay(billing, project, ago(8)),
        ):
            assert response.status_code == 200, response.text
        fixtures[target] = {
            "project": str(project),
            "project_number": f"FAKE-CP-{project.hex[-8:]}",
            "too_early": ago(11),
            "accept_phase": ago(6),
            "release_phase": ago(5),
            "accept_final": ago(4),
            "release_final": ago(3),
            "warranty_end": later(365),
        }

    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, "o7c2-owner", issuer=issuer)
    add_membership(owner_conn, tenant_id=billing.tenant, user_id=owner.user_id, role="owner")
    provider, verifier = _provider(
        issuer, origin, FakeIdp(), cast(FakeUser, _SignedIn({"owner": owner}))
    )
    app = _management_app(test_database, verifier, issuer, web)
    env = {**_browser_env(origin, issuer), "GBA_ACCEPTANCE_FIXTURES": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        result = await asyncio.to_thread(
            subprocess.run,
            [
                npm,
                "exec",
                "--",
                "playwright",
                "test",
                "tests/construction-acceptance.spec.ts",
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
                "select a.number, a.scope, a.phase, a.accepted_on::text, a.source, "
                "a.warranty_ends_on::text, r.amount_minor, r.released_on::text "
                "from gba.construction_acceptances a "
                "left join gba.construction_retainage_releases r "
                "on (r.tenant_id, r.project_id, r.acceptance) "
                "= (a.tenant_id, a.project_id, a.number) "
                "where a.project_id = %s order by a.number",
                (fixture["project"],),
            ).fetchall()
            assert rows == [
                (
                    1,
                    "phase",
                    "Framing",
                    fixture["accept_phase"],
                    "paper",
                    None,
                    2500,
                    fixture["release_phase"],
                ),
                (
                    2,
                    "final",
                    None,
                    fixture["accept_final"],
                    "email",
                    fixture["warranty_end"],
                    600,
                    fixture["release_final"],
                ),
            ]
