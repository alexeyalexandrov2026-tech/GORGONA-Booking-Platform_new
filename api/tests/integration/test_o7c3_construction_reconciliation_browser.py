"""O7c3 construction reconciliation with actual FIN-03 postings in a disposable database."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_invoice_issue import InvoiceWorld
from tests.integration.test_ledger import LedgerWorld
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_o4a_construction_execution import ago
from tests.integration.test_o5_construction_billing import (
    Billing,
    accepted,
    billing,
    client,
    idp,
    issue,
    manager_a,
)
from tests.integration.test_o6b_construction_warranty import claim, cost, finished, repair
from tests.integration.test_settlements import SettlementWorld
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "billing", "client", "idp", "manager_a"]


async def post_receipt(payments: PaymentWorld, obligation: UUID, amount: str) -> None:
    settlement = await payments.settlements.reserved(obligation, amount)
    date = ago(7)
    posted = await payments.confirm(
        settlement,
        3,
        [(obligation, amount)],
        amount,
        f"FAKE-BUILD-{uuid7().hex[-12:]}",
        changes={"actual_external_date": date, "entry_date": date},
    )
    assert posted.status_code == 200, posted.text


@pytest.mark.anyio
async def test_project_reconciliation_with_real_browser_and_paid_documents(
    billing: Billing,
    manager_a: FakeUser,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: O7c3 browser requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread((web / "out/construction/index.html").is_file), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    b = billing
    control, revenue = b.chart["1200"], b.chart["4100"]
    ledger = LedgerWorld(b.c.client, b.tenant, b.book, manager_a, b.c.headers, (control, revenue))
    payments = PaymentWorld(
        SettlementWorld(InvoiceWorld(ledger, b.c.customer, control, revenue)), b.chart["1100"]
    )
    fixtures = {}
    for target in ("desktop", "mobile"):
        project = await finished(b)
        await cost(b, project, "40.00", position=1)
        assigned = await cost(b, project, "25.00")
        response = await claim(b, project, ago(1))
        assert response.status_code == 200, response.text
        response = await repair(b, project, 1, assigned)
        assert response.status_code == 200, response.text
        application = (await b.c.get(f"/projects/{project}/pay-applications/1")).json()
        for kind, route, amount in (
            ("invoice", "invoices", "100.00"),
            ("retainage", "accruals", "15.00"),
        ):
            issued = await issue(b, route, application[kind]["document_id"], ago(8))
            assert issued.status_code == 200, issued.text
            await post_receipt(payments, UUID(issued.json()["obligation_id"]), amount)
        fixtures[target] = {
            "project": str(project),
            "project_number": f"FAKE-CP-{project.hex[-8:]}",
            "release_date": ago(6),
        }

    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, "o7c3-owner", issuer=issuer)
    add_membership(owner_conn, tenant_id=b.tenant, user_id=owner.user_id, role="owner")
    provider, verifier = _provider(
        issuer, origin, FakeIdp(), cast(FakeUser, _SignedIn({"owner": owner}))
    )
    app = _management_app(test_database, verifier, issuer, web)
    env = {**_browser_env(origin, issuer), "GBA_RECONCILIATION_FIXTURES": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        result = await asyncio.to_thread(
            subprocess.run,
            [
                npm,
                "exec",
                "--",
                "playwright",
                "test",
                "tests/construction-reconciliation.spec.ts",
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

    with owner_tenant_transaction(owner_conn, b.tenant):
        for fixture in fixtures.values():
            rows = owner_conn.execute(
                "select amount_minor from gba.construction_retainage_releases where project_id=%s",
                (fixture["project"],),
            ).fetchall()
            assert rows == [(3100,)]
