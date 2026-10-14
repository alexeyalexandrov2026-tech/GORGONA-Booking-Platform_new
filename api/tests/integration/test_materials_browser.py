"""J5 Materials screen: actual OIDC/PKCE, Chromium and PostgreSQL on desktop and mobile.

Only this test stands in for the STOCK-01 acceptance; the registry stays planned. The owner
and a branch manager sign in through the same loopback provider, one at a time.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast
from uuid import UUID, uuid7

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
from tests.support.fake_idp import FakeIdp

# Accounts of the neutral starter chart for the seeded company's materials.
RULES = {
    "inventory": "1300",
    "receipt": "1400",
    "opening": "3900",
    "surplus": "4900",
    "consumption": "5000",
    "loss": "6900",
    "difference": "6900",
}


def test_materials_real_browser_before_and_after_books(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: J5 browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/materials/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    tenant, home = world.a.tenant_id, world.a.location_id
    away, _ = seed_other_branch(owner_conn, world.a)
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {
        "owner": seed_user(owner_conn, "j5-owner", issuer=issuer),
        "branch": seed_user(owner_conn, "j5-branch", issuer=issuer),
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

        def browser(phase: str) -> None:
            result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
                [npm, "run", "test:management:materials"],
                cwd=web,
                env={**env, "GBA_J5_PHASE": phase},
                capture_output=True,
                text=True,
                timeout=1200,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s

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
        entities: dict[str, UUID] = {}
        for name in ("desktop", "mobile", "seed"):
            entities[name] = uuid7()
            request(
                "PUT",
                f"legal-entities/{entities[name]}",
                {
                    "expected_revision": 0,
                    "code": f"FAKE_{name.upper()}",
                    "legal_name": f"FAKE {name} Materials LLC",
                },
            )
        browser("nobook")

        books: dict[str, UUID] = {}
        for name, entity in entities.items():
            books[name] = uuid7()
            request(
                "PUT",
                f"ledger/books/{books[name]}",
                {
                    "expected_revision": 0,
                    "legal_entity_id": str(entity),
                    "base_currency": "USD",
                    "fiscal_year_start_month": 1,
                    "accounting_start": "2026-01-01",
                },
            )
        chart = request("GET", f"ledger/books/{books['seed']}/accounts").json()["items"]
        codes = {account["code"]: account["account_id"] for account in chart}
        request(
            "PUT",
            f"inventory/posting-rules/{books['seed']}",
            {
                "expected_revision": 0,
                **{f"{name}_account_id": codes[code] for name, code in RULES.items()},
            },
        )
        oil = uuid7()
        request(
            "PUT",
            f"inventory/items/{oil}",
            {
                "expected_revision": 0,
                "code": "SEED-OIL",
                "name": "FAKE seed oil",
                "unit": "ml",
                "quantity_scale": 1,
            },
        )
        # The seeded company holds oil in both branches; the branch manager sees one.
        for code, label, branch, quantity, amount in (
            ("SEED-SHELF", "FAKE seed shelf", home, "2.5", "10.00"),
            ("AWAY-SHELF", "FAKE away shelf", away, "1", "4.00"),
        ):
            place = uuid7()
            request(
                "PUT",
                f"inventory/places/{place}",
                {
                    "expected_revision": 0,
                    "location_id": str(branch),
                    "code": code,
                    "name": label,
                },
            )
            request(
                "PUT",
                f"inventory/documents/{uuid7()}",
                {
                    "kind": "receipt",
                    "reason": "purchase",
                    "legal_entity_id": str(entities["seed"]),
                    "place_id": str(place),
                    "document_date": "2026-10-01",
                    "lines": [{"item_id": str(oil), "quantity": quantity, "amount": amount}],
                },
            )
        browser("enabled")

    def count(query: str) -> int:
        row = owner_conn.execute(query).fetchone()
        assert row is not None
        return int(row[0])

    with owner_tenant_transaction(owner_conn, tenant):
        # The seeded oil and one material per project, saved three times: created, its
        # lost answer settled after a reload, and sent again under the same key. The
        # discarded fourth change left no version.
        assert count("select count(*) from gba.stock_items") == 3
        assert count("select count(*) from gba.stock_item_versions") == 7
        assert (
            count("select max(revision) from gba.stock_item_versions where name like '%%three'")
            == 3
        )
        assert count("select count(*) from gba.stock_item_versions where name like '%%four'") == 0
        # Two seeded places, and per project one by the owner and one by the branch manager.
        assert count("select count(*) from gba.stock_places") == 6
        at_home = f"select count(*) from gba.stock_places where location_id='{home}'"
        assert count(f"{at_home} and code like 'BR-%%'") == 2
        assert count("select count(*) from gba.stock_posting_rules") == 3
        assert count("select count(*) from gba.stock_documents") == 2
        assert (
            count(
                "select count(*) from gba.audit_events where action='inventory.command_cancelled'"
            )
            == 2
        )
        audits = owner_conn.execute(
            "select details from gba.audit_events where action like 'inventory.%%'"
        ).fetchall()
        receipts = owner_conn.execute(
            "select response_body from gba.idempotency_keys where operation like 'inventory.%%'"
        ).fetchall()
        assert audits
        assert receipts
        # Names stay in the records themselves, never in audit details or command receipts.
        assert "FAKE" not in json.dumps([row[0] for row in audits])
        assert "FAKE" not in json.dumps([row[0] for row in receipts])
