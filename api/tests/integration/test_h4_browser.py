"""Actual OIDC/PKCE, H financial/admission UI and PostgreSQL on desktop/mobile.

The production H registry is tested closed first. Its positive override is confined
to this disposable fixture; neither source registry nor deployed data is changed.
"""

import os
import shutil
import subprocess
from pathlib import Path
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp


def test_h4_real_browser_and_closed_production_gate(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: H4 browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/finance/index.html").exists(), "build web first"
    assert (web / "out/provider-admission/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, f"FAKE-h4-browser-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    idp = FakeIdp()
    provider, verifier = _provider(issuer, origin, idp, owner)
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    root = f"{origin}/v1/businesses/{world.a.tenant_id}"
    books: list[UUID] = []
    with live_server(provider, idp_port), live_server(app, app_port):

        def request(method: str, suffix: str, body: dict[str, object]) -> httpx.Response:
            result = httpx.request(
                method,
                f"{root}/{suffix}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=15,
            )
            assert result.status_code == 200, result.text
            return result

        def publish(version: int, selected: list[str]) -> None:
            saved = request(
                "PUT",
                "configuration/draft",
                {
                    "expected_version": version,
                    "profile_revision": 1,
                    "module_ids": selected,
                },
            ).json()
            request(
                "POST",
                f"configuration/versions/{saved['version']}/validate",
                {"expected_revision": 1},
            )
            request(
                "POST",
                f"configuration/versions/{saved['version']}/publish",
                {"expected_revision": 2},
            )

        def browser(script: str, phase: str) -> None:
            result = subprocess.run(  # noqa: S603 - fixed repository scripts, located npm
                [npm, "run", script],
                cwd=web,
                env={**env, "GBA_H4_BROWSER_PHASE": phase},
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s

        request("PUT", "profile", {"expected_revision": 0, "industry_ids": [1]})
        publish(0, ["booking_resources", "finance", "counterparties"])
        for project in ("desktop", "mobile"):
            entity, book = uuid7(), uuid7()
            request(
                "PUT",
                f"legal-entities/{entity}",
                {
                    "expected_revision": 0,
                    "code": f"FAKE_{project.upper()}",
                    "legal_name": f"FAKE {project} Finance LLC",
                },
            )
            request(
                "PUT",
                f"ledger/books/{book}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "legal_entity_id": str(entity),
                    "base_currency": "USD",
                    "fiscal_year_start_month": 1,
                    "accounting_start": "2026-01-01",
                },
            )
            books.append(book)
        request("PUT", f"counterparties/{uuid7()}", card(display_name="FAKE Finance Customer"))
        browser("test:management:finance", "closed")
        # Positive workflow testing only; no acceptance/readiness source mutation.
        verified = tuple(
            module.model_copy(
                update={"readiness": Readiness.TECHNICALLY_VERIFIED, "enableable": True}
            )
            if module.id == "finance_documents"
            else module
            for module in modules.MODULES
        )
        monkeypatch.setattr(modules, "MODULES", verified)
        monkeypatch.setattr(modules, "MODULES_BY_ID", {m.id: m for m in verified})
        monkeypatch.setattr(modules, "MODULE_CATALOG", modules.ModuleCatalog(modules=verified))
        publish(1, ["booking_resources", "finance", "counterparties", "finance_documents"])
        browser("test:management:finance", "enabled")
        browser("test:management:admission", "enabled")
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        for book in books:
            for table, expected in (
                ("financial_documents", 3),
                ("external_payments", 2),
                ("journal_entries", 10),
            ):
                row = owner_conn.execute(
                    f"select count(*) from gba.{table} where book_id=%s", (book,)
                ).fetchone()
                assert row is not None
                assert row[0] == expected
        assert owner_conn.execute(
            "select count(*) from gba.provider_admission_requests"
        ).fetchone() == (2,)
