"""Documents through real OIDC/PKCE, Chromium, API and PostgreSQL (FAKE fixture data)."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.module_support import verified_modules
from tests.integration.seed import seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp
from tests.unit.test_file_validation import pdf


def test_real_document_browser_oidc_pkce_and_database(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    tmp_path: Path,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: document browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/documents/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, f"FAKE-document-browser-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    idp = FakeIdp()
    provider, verifier = _provider(issuer, origin, idp, owner)
    app = _management_app(test_database, verifier, issuer, web)
    sample = tmp_path / "FAKE Agreement.pdf"
    sample.write_bytes(pdf())
    env = _browser_env(origin, issuer)
    env.update(
        GBA_DOC_BUSINESS=str(world.a.tenant_id),
        GBA_DOC_SAMPLE_PDF=str(sample),
        GBA_DOC_SAMPLE_SHA256=hashlib.sha256(sample.read_bytes()).hexdigest(),
    )
    headers = {**idp.bearer(owner.subject, email=owner.email, iss=issuer)}
    with (
        live_server(provider, idp_port),
        live_server(app, app_port),
    ):

        def request(method: str, suffix: str, body: dict[str, object]) -> dict[str, object]:
            result = httpx.request(
                method,
                f"{origin}/v1/businesses/{world.a.tenant_id}/{suffix}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=10,
            )
            assert result.status_code == 200, result.text
            data: dict[str, object] = result.json()
            return data

        request("PUT", "profile", {"expected_revision": 0, "industry_ids": [1, 6, 24]})
        # Test-only registry override; the publication itself is the real command path.
        with verified_modules("documents"):
            request(
                "PUT",
                "configuration/draft",
                {
                    "expected_version": 0,
                    "profile_revision": 1,
                    "module_ids": ["booking_resources", "counterparties", "documents"],
                },
            )
            request("POST", "configuration/versions/1/validate", {"expected_revision": 1})
            request("POST", "configuration/versions/1/publish", {"expected_revision": 2})
        request(
            "PUT",
            f"counterparties/{uuid7()}",
            card(display_name="FAKE Document Partner", email=None, phone=None),
        )
        result = subprocess.run(  # noqa: S603 - fixed repository test script
            [npm, "run", "test:management:documents"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - browser evidence in pytest -s
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        assert owner_conn.execute("select count(*) from gba.documents").fetchone() == (1,)
        assert owner_conn.execute(
            "select revision, title, file_id is not null from gba.document_versions "
            "order by revision"
        ).fetchall() == [
            (1, "FAKE Supply agreement", True),
            (2, "FAKE Supply agreement v2", False),
            (3, "FAKE Supply agreement v3", False),
        ]
        assert owner_conn.execute(
            "select count(*), min(sha256), min(file_name) from gba.document_files"
        ).fetchone() == (1, env["GBA_DOC_SAMPLE_SHA256"], "FAKE Agreement.pdf")
        assert owner_conn.execute(
            "select action from gba.document_counterparty_links order by sequence"
        ).fetchall() == [("linked",), ("unlinked",)]
        audits = owner_conn.execute(
            "select action, details from gba.audit_events "
            "where action like 'document%%' order by id"
        ).fetchall()
        actions = [row[0] for row in audits]
        assert actions.count("document_file.uploaded") == 1
        assert actions.count("document.saved") == 3
        assert actions.count("document_file.downloaded") == 2
        receipts = owner_conn.execute(
            "select response_body from gba.idempotency_keys "
            "where operation like 'business.document%%'"
        ).fetchall()
        assert len(receipts) == 6
        for text in (json.dumps([row[1] for row in audits]), json.dumps(receipts)):
            assert "FAKE Supply" not in text
            assert "FAKE Agreement" not in text
            assert "FAKE Document Partner" not in text
