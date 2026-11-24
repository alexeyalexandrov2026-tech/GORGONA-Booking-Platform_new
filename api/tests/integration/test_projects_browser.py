"""PRO-01 Slice 5: real-browser desktop + mobile E2E with ethical-wall proof & PG18 read-back."""

import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import cast
from uuid import uuid7

import httpx
import psycopg
import pytest
from fastapi import HTTPException

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp
from tests.unit.test_file_validation import pdf

PROJECTS = ("desktop", "mobile")
ENABLED = [
    "counterparties",
    "documents",
    "finance",
    "finance_documents",
    "projects",
]


def test_projects_ui_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: projects browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/projects/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None

    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "projects",
        modules.MODULES_BY_ID["projects"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )

    tenant_a = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {
        "owner": seed_user(owner_conn, "pro-ui-owner", issuer=issuer),
        "outsider": seed_user(owner_conn, "pro-ui-outsider", issuer=issuer),
    }
    add_membership(owner_conn, tenant_id=tenant_a, user_id=people["owner"].user_id, role="owner")
    add_membership(
        owner_conn,
        tenant_id=tenant_a,
        user_id=people["outsider"].user_id,
        role="manager",
        location_id=None,
    )

    idp = FakeIdp()
    signed_in = _SignedIn(people)
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))

    @provider.post("/fixture/user/{name}")
    async def switch(name: str) -> dict[str, str]:
        if name not in people:
            raise HTTPException(404, "Unknown FAKE person")
        signed_in.name = name
        return {"user": name}

    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    owner = people["owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    business = f"/v1/businesses/{tenant_a}"

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(pdf())
        sample_pdf_path = tmp_pdf.name
    env["GBA_TEST_SAMPLE_PDF_PATH"] = sample_pdf_path

    try:
        with live_server(provider, idp_port), live_server(app, app_port):
            with httpx.Client(base_url=origin, timeout=20.0) as http:
                # 1. Select Legal services industry (ID 16) & publish projects + finance_documents
                prof = http.put(
                    f"{business}/profile",
                    headers={**headers, "Idempotency-Key": f"pro-ui-prof-{uuid7()}"},
                    json={"expected_revision": 0, "industry_ids": [16]},
                )
                assert prof.status_code == 200, prof.text
                draft_res = http.put(
                    f"{business}/configuration/draft",
                    headers={**headers, "Idempotency-Key": f"pro-ui-cfg-{uuid7()}"},
                    json={"expected_version": 0, "profile_revision": 1, "module_ids": ENABLED},
                )
                assert draft_res.status_code == 200, draft_res.text
                version = draft_res.json()["version"]
                for step, rev in (("validate", 1), ("publish", 2)):
                    st = http.post(
                        f"{business}/configuration/versions/{version}/{step}",
                        headers={**headers, "Idempotency-Key": f"pro-ui-{step}-{uuid7()}"},
                        json={"expected_revision": rev},
                    )
                    assert st.status_code == 200, st.text

                # 2. Seed client counterparty, legal entity, ledger book, AR (1200) & Revenue (4000)
                cp_id, entity_id, book_id = uuid7(), uuid7(), uuid7()
                assert (
                    http.put(
                        f"{business}/counterparties/{cp_id}",
                        headers={**headers, "Idempotency-Key": f"pro-ui-cp-{uuid7()}"},
                        json=card(display_name="Acme Legal Client", roles=["customer"]),
                    ).status_code
                    == 200
                )
                assert (
                    http.put(
                        f"{business}/legal-entities/{entity_id}",
                        headers={**headers, "Idempotency-Key": f"pro-ui-le-{uuid7()}"},
                        json={
                            "expected_revision": 0,
                            "code": "PRO_UI_LE",
                            "legal_name": "Gorgona Law Partners LLP",
                        },
                    ).status_code
                    == 200
                )
                assert (
                    http.put(
                        f"{business}/ledger/books/{book_id}",
                        headers={**headers, "Idempotency-Key": f"pro-ui-bk-{uuid7()}"},
                        json={
                            "schema_version": 1,
                            "expected_revision": 0,
                            "legal_entity_id": str(entity_id),
                            "base_currency": "USD",
                            "fiscal_year_start_month": 1,
                            "accounting_start": date(2026, 1, 1).isoformat(),
                        },
                    ).status_code
                    == 200
                )
                accts = {
                    a["code"]: a["account_id"]
                    for a in http.get(
                        f"{business}/ledger/books/{book_id}/accounts?limit=100",
                        headers=headers,
                    ).json()["items"]
                }
                if "1200" not in accts:
                    assert (
                        http.put(
                            f"{business}/ledger/books/{book_id}/accounts/{uuid7()}",
                            headers={**headers, "Idempotency-Key": f"pro-ui-ar-{uuid7()}"},
                            json={
                                "schema_version": 1,
                                "expected_revision": 0,
                                "code": "1200",
                                "type": "asset",
                                "name": "Accounts Receivable",
                                "archived": False,
                            },
                        ).status_code
                        == 200
                    )
                if "4000" not in accts:
                    assert (
                        http.put(
                            f"{business}/ledger/books/{book_id}/accounts/{uuid7()}",
                            headers={**headers, "Idempotency-Key": f"pro-ui-rev-{uuid7()}"},
                            json={
                                "schema_version": 1,
                                "expected_revision": 0,
                                "code": "4000",
                                "type": "revenue",
                                "name": "Legal Advisory Revenue",
                                "archived": False,
                            },
                        ).status_code
                        == 200
                    )

            for project in PROJECTS:
                proc = subprocess.run(  # noqa: S603
                    [
                        npm,
                        "exec",
                        "--",
                        "playwright",
                        "test",
                        "tests/projects.spec.ts",
                        "--project",
                        project,
                    ],
                    cwd=web,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert proc.returncode == 0, f"{project} failed:\n{proc.stdout}\n{proc.stderr}"
    finally:
        Path(sample_pdf_path).unlink(missing_ok=True)

    # Verify PostgreSQL 18 read-back across desktop & mobile runs
    with owner_tenant_transaction(owner_conn, tenant_a):
        matter_cnt = owner_conn.execute(
            "select count(*) from gba.project_matters "
            "where status = 'active' and access_mode = 'restricted'"
        ).fetchone()
        stage_cnt = owner_conn.execute(
            "select count(*) from gba.project_stages where status = 'accepted'"
        ).fetchone()
        file_cnt = owner_conn.execute("select count(*) from gba.project_matter_files").fetchone()
        te_cnt = owner_conn.execute(
            "select count(*) from gba.project_time_entries where status = 'billed'"
        ).fetchone()
        run_cnt = owner_conn.execute(
            "select count(*) from gba.project_recurring_runs where billing_status = 'billed'"
        ).fetchone()
        inv_cnt = owner_conn.execute(
            "select count(*) from gba.project_matter_invoices where total_minor = 365000"
        ).fetchone()
        exp_cnt = owner_conn.execute("select count(*) from gba.project_exports").fetchone()
    assert matter_cnt == (2,)
    assert stage_cnt == (2,)
    assert file_cnt == (2,)
    assert te_cnt == (2,)
    assert run_cnt == (2,)
    assert inv_cnt == (2,)
    assert exp_cnt == (4,)
