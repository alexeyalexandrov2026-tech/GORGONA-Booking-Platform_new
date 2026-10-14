"""J5b Stock documents screen: actual OIDC/PKCE, Chromium and PostgreSQL on desktop and
mobile.

Only this test stands in for the STOCK-01 acceptance; the registry stays planned. The owner
and a branch manager sign in through the same loopback provider, one at a time. Each
project has its own materials and places, so the two projects never share a balance.
"""

import json
import os
import shutil
import subprocess
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
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_materials_browser import RULES
from tests.support.fake_idp import FakeIdp


def test_stock_documents_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: J5b browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/stock-documents/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    tenant, home = world.a.tenant_id, world.a.location_id
    away, _ = seed_other_branch(owner_conn, world.a)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {
        "owner": seed_user(owner_conn, "j5b-owner", issuer=issuer),
        "branch": seed_user(owner_conn, "j5b-branch", issuer=issuer),
    }
    add_membership(owner_conn, tenant_id=tenant, user_id=people["owner"].user_id, role="owner")
    add_membership(
        owner_conn,
        tenant_id=tenant,
        user_id=people["branch"].user_id,
        role="manager",
        location_id=home,
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
    root = f"{origin}/v1/businesses/{tenant}"
    current = modules.MODULES_BY_ID["inventory"]
    with (
        pytest.MonkeyPatch.context() as accepted,
        live_server(provider, idp_port),
        live_server(app, app_port),
    ):
        accepted.setitem(
            modules.MODULES_BY_ID,
            "inventory",
            current.model_copy(
                update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
            ),
        )

        def request(method: str, suffix: str, body: object = None) -> httpx.Response:
            result = httpx.request(
                method,
                f"{root}/{suffix}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=15,
            )
            assert result.status_code == 200, result.text
            return result

        request("PUT", "profile", {"expected_revision": 0, "industry_ids": [1]})
        draft = request(
            "PUT",
            "configuration/draft",
            {
                "expected_version": 0,
                "profile_revision": 1,
                "module_ids": ["booking_resources", "finance", "inventory"],
            },
        ).json()
        for step, revision in (("validate", 1), ("publish", 2)):
            request(
                "POST",
                f"configuration/versions/{draft['version']}/{step}",
                {"expected_revision": revision},
            )
        entity, book = uuid7(), uuid7()
        request(
            "PUT",
            f"legal-entities/{entity}",
            {
                "expected_revision": 0,
                "code": "FAKE_STOCK",
                "legal_name": "FAKE stock Materials LLC",
            },
        )
        request(
            "PUT",
            f"ledger/books/{book}",
            {
                "expected_revision": 0,
                "legal_entity_id": str(entity),
                "base_currency": "USD",
                "fiscal_year_start_month": 1,
                "accounting_start": "2026-01-01",
            },
        )
        chart = request("GET", f"ledger/books/{book}/accounts").json()["items"]
        codes = {account["code"]: account["account_id"] for account in chart}
        request(
            "PUT",
            f"inventory/posting-rules/{book}",
            {
                "expected_revision": 0,
                **{f"{name}_account_id": codes[code] for name, code in RULES.items()},
            },
        )
        for project in ("DESKTOP", "MOBILE"):
            for code, unit, scale in ((f"OIL-{project}", "ml", 1), (f"FOIL-{project}", "pcs", 0)):
                request(
                    "PUT",
                    f"inventory/items/{uuid7()}",
                    {
                        "expected_revision": 0,
                        "code": code,
                        "name": f"FAKE {code.lower()}",
                        "unit": unit,
                        "quantity_scale": scale,
                    },
                )
            for code, branch in (
                (f"A-{project}", home),
                (f"B-{project}", home),
                (f"AWAY-{project}", away),
            ):
                request(
                    "PUT",
                    f"inventory/places/{uuid7()}",
                    {
                        "expected_revision": 0,
                        "location_id": str(branch),
                        "code": code,
                        "name": f"FAKE {code.lower()}",
                    },
                )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:stock-documents"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s

    def rows(query: str) -> list[tuple[object, ...]]:
        return owner_conn.execute(query).fetchall()

    with owner_tenant_transaction(owner_conn, tenant):
        # Per project: one receipt (its lost answer settled, never posted twice), one
        # write-off (the refused one and the discarded one left nothing), the owner's
        # transfer to the other branch, one return and the branch manager's transfer.
        kinds = {
            str(kind): int(str(count))
            for kind, count in rows("select kind, count(*) from gba.stock_documents group by kind")
        }
        assert kinds == {"receipt": 2, "write_off": 2, "transfer": 4, "return": 2}
        assert rows("select count(*) from gba.stock_document_lines") == [(12,)]
        # Receipts, write-offs and returns post; transfers move no money.
        assert rows("select count(*) from gba.journal_entries where source_kind='stock'") == [(6,)]
        assert rows(
            "select count(*) from gba.audit_events where action='inventory.command_cancelled'"
        ) == [(2,)]
        branch_transfers = rows(
            "select count(*) from gba.stock_documents where kind='transfer' "
            f"and location_id='{home}' and to_location_id='{home}'"
        )
        assert branch_transfers == [(2,)]
        audits = rows("select details from gba.audit_events where action like 'inventory.%%'")
        receipts = rows(
            "select response_body from gba.idempotency_keys where operation like 'inventory.%%'"
        )
        assert audits
        assert receipts
        # Supplier documents and names stay in the records, never in audit or receipts.
        assert "FAKE" not in json.dumps([row[0] for row in audits])
        assert "FAKE" not in json.dumps([row[0] for row in receipts])
