"""REST-01 Slice 5: real-browser desktop + mobile E2E with PostgreSQL 18 read-back."""

import os
import shutil
import subprocess
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
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp

PROJECTS = ("desktop", "mobile")
ENABLED = [
    "booking_resources",
    "counterparties",
    "finance",
    "finance_documents",
    "inventory",
    "workforce",
    "restaurant",
]
DAY = "2026-10-01"


def test_restaurant_ui_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: restaurant browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/restaurant/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None

    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "restaurant",
        modules.MODULES_BY_ID["restaurant"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )

    tenant_a, home = world.a.tenant_id, world.a.location_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {
        "owner": seed_user(owner_conn, "rest-ui-owner", issuer=issuer),
        "front_desk": seed_user(owner_conn, "rest-ui-front", issuer=issuer),
        "kitchen": seed_user(owner_conn, "rest-ui-kitchen", issuer=issuer),
    }
    add_membership(owner_conn, tenant_id=tenant_a, user_id=people["owner"].user_id, role="owner")
    add_membership(
        owner_conn,
        tenant_id=tenant_a,
        user_id=people["front_desk"].user_id,
        role="front_desk",
        location_id=home,
    )
    add_membership(
        owner_conn,
        tenant_id=tenant_a,
        user_id=people["kitchen"].user_id,
        role="artist",
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
    business = f"/v1/businesses/{tenant_a}"

    with live_server(provider, idp_port), live_server(app, app_port):
        with httpx.Client(base_url=origin, timeout=20.0) as http:
            # 1. Select Restaurant industry (ID 2) & publish restaurant + inventory + finance
            prof = http.put(
                f"{business}/profile",
                headers={**headers, "Idempotency-Key": f"rest-ui-prof-{uuid7()}"},
                json={"expected_revision": 0, "industry_ids": [2]},
            )
            assert prof.status_code == 200, prof.text
            draft_res = http.put(
                f"{business}/configuration/draft",
                headers={**headers, "Idempotency-Key": f"rest-ui-cfg-{uuid7()}"},
                json={"expected_version": 0, "profile_revision": 1, "module_ids": ENABLED},
            )
            assert draft_res.status_code == 200, draft_res.text
            version = draft_res.json()["version"]
            for step, rev in (("validate", 1), ("publish", 2)):
                st = http.post(
                    f"{business}/configuration/versions/{version}/{step}",
                    headers={**headers, "Idempotency-Key": f"rest-ui-{step}-{uuid7()}"},
                    json={"expected_revision": rev},
                )
                assert st.status_code == 200, st.text

            # 2. Seed legal entity, ledger book, posting rules, storage place, beef stock (1000g)
            entity_id, book_id, place_id, beef_id = uuid7(), uuid7(), uuid7(), uuid7()
            assert (
                http.put(
                    f"{business}/legal-entities/{entity_id}",
                    headers={**headers, "Idempotency-Key": f"rest-ui-le-{uuid7()}"},
                    json={
                        "expected_revision": 0,
                        "code": "REST_UI_LE",
                        "legal_name": "Restaurant UI LLC",
                    },
                ).status_code
                == 200
            )
            book_res = http.put(
                f"{business}/ledger/books/{book_id}",
                headers={**headers, "Idempotency-Key": f"rest-ui-bk-{uuid7()}"},
                json={
                    "schema_version": 1,
                    "expected_revision": 0,
                    "legal_entity_id": str(entity_id),
                    "base_currency": "USD",
                    "fiscal_year_start_month": 1,
                    "accounting_start": date(2026, 1, 1).isoformat(),
                },
            )
            assert book_res.status_code == 200, book_res.text

            accts_res = http.get(
                f"{business}/ledger/books/{book_id}/accounts?limit=100",
                headers=headers,
            )
            assert accts_res.status_code == 200, accts_res.text
            accts = {a["code"]: a["account_id"] for a in accts_res.json()["items"]}

            assert (
                http.put(
                    f"{business}/inventory/posting-rules/{book_id}",
                    headers={**headers, "Idempotency-Key": f"rest-ui-rl-{uuid7()}"},
                    json={
                        "schema_version": 1,
                        "expected_revision": 0,
                        "inventory_account_id": accts["1300"],
                        "receipt_account_id": accts["1400"],
                        "opening_account_id": accts["3900"],
                        "surplus_account_id": accts["4900"],
                        "consumption_account_id": accts["5000"],
                        "loss_account_id": accts["6900"],
                        "difference_account_id": accts["6900"],
                    },
                ).status_code
                == 200
            )
            assert (
                http.put(
                    f"{business}/inventory/places/{place_id}",
                    headers={**headers, "Idempotency-Key": f"rest-ui-pl-{uuid7()}"},
                    json={
                        "schema_version": 1,
                        "expected_revision": 0,
                        "location_id": str(home),
                        "code": "KITCHEN_UI",
                        "name": "Kitchen Storage",
                        "archived": False,
                    },
                ).status_code
                == 200
            )
            assert (
                http.put(
                    f"{business}/inventory/items/{beef_id}",
                    headers={**headers, "Idempotency-Key": f"rest-ui-bf-{uuid7()}"},
                    json={
                        "schema_version": 1,
                        "expected_revision": 0,
                        "code": "BEEF_UI",
                        "name": "Beef Patty",
                        "unit": "g",
                        "quantity_scale": 0,
                        "archived": False,
                    },
                ).status_code
                == 200
            )
            rcpt = http.put(
                f"{business}/inventory/documents/{uuid7()}",
                headers={**headers, "Idempotency-Key": f"rest-ui-rc-{uuid7()}"},
                json={
                    "schema_version": 1,
                    "kind": "receipt",
                    "reason": "opening_balance",
                    "legal_entity_id": str(entity_id),
                    "place_id": str(place_id),
                    "document_date": DAY,
                    "lines": [{"item_id": str(beef_id), "quantity": "1000", "amount": "20.00"}],
                },
            )
            assert rcpt.status_code == 200, rcpt.text

        for project in PROJECTS:
            proc = subprocess.run(  # noqa: S603
                [
                    npm,
                    "exec",
                    "--",
                    "playwright",
                    "test",
                    "tests/restaurant.spec.ts",
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

    # Verify PostgreSQL 18 read-back across desktop & mobile (2 x 180g = 360g written off)
    with owner_tenant_transaction(owner_conn, tenant_a):
        check_count = owner_conn.execute("select count(*) from gba.restaurant_checks").fetchone()
        ticket_served = owner_conn.execute(
            "select count(*) from gba.restaurant_kitchen_tickets where status = 'served'"
        ).fetchone()
        split_count = owner_conn.execute(
            "select count(*) from gba.restaurant_check_splits where total_minor = 1700"
        ).fetchone()
        cons_count = owner_conn.execute(
            "select count(*) from gba.restaurant_check_consumptions "
            "where stock_document_id is not null"
        ).fetchone()
        beef_bal = owner_conn.execute(
            "select quantity from gba.stock_balances where place_id = %s and item_id = %s",
            (place_id, beef_id),
        ).fetchone()
    assert check_count == (2,)
    assert ticket_served == (2,)
    assert split_count == (2,)
    assert cons_count == (2,)
    assert beef_bal == (640,)
