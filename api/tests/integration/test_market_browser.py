"""MARKET-01 Slice 3: real-browser desktop + mobile E2E for /marketplace/ proving strict
published_fields allow-list projection, zero-GORGONA-commission marketplaces with revocable
seller connections, isolated multi-seller basket split into FIN-03 invoices, partial refund
credit notes, and direct PostgreSQL 18 read-back.
"""

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
from tests.integration.test_counterparties import card
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp

PROJECTS = ("desktop", "mobile")
ENABLED = [
    "counterparties",
    "finance",
    "finance_documents",
    "storefronts",
]


def test_market_ui_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: market browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/marketplace/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None

    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "storefronts",
        modules.MODULES_BY_ID["storefronts"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )

    tenant_a = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {
        "owner": seed_user(owner_conn, "mkt-ui-owner", issuer=issuer),
    }
    add_membership(owner_conn, tenant_id=tenant_a, user_id=people["owner"].user_id, role="owner")

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
            # 1. Select profile & publish counterparties + finance_documents + storefronts
            prof = http.put(
                f"{business}/profile",
                headers={**headers, "Idempotency-Key": f"mkt-ui-prof-{uuid7()}"},
                json={"expected_revision": 0, "industry_ids": [25]},
            )
            assert prof.status_code == 200, prof.text
            draft_res = http.put(
                f"{business}/configuration/draft",
                headers={**headers, "Idempotency-Key": f"mkt-ui-cfg-{uuid7()}"},
                json={"expected_version": 0, "profile_revision": 1, "module_ids": ENABLED},
            )
            assert draft_res.status_code == 200, draft_res.text
            version = draft_res.json()["version"]
            for step, rev in (("validate", 1), ("publish", 2)):
                st = http.post(
                    f"{business}/configuration/versions/{version}/{step}",
                    headers={**headers, "Idempotency-Key": f"mkt-ui-{step}-{uuid7()}"},
                    json={"expected_revision": rev},
                )
                assert st.status_code == 200, st.text

            # 2. Seed buyer & seller counterparties + two distinct seller legal entities & books
            for cname in ("Marketplace Buyer Corp", "Independent Seller Studio"):
                cid = uuid7()
                assert (
                    http.put(
                        f"{business}/counterparties/{cid}",
                        headers={**headers, "Idempotency-Key": f"mkt-ui-cp-{cid}"},
                        json=card(display_name=cname, roles=["customer", "supplier"]),
                    ).status_code
                    == 200
                )
            for code, lname in (
                ("MKT_SELLER_A", "Seller Alpha LLC"),
                ("MKT_SELLER_B", "Seller Beta LLC"),
            ):
                eid, bid = uuid7(), uuid7()
                assert (
                    http.put(
                        f"{business}/legal-entities/{eid}",
                        headers={**headers, "Idempotency-Key": f"mkt-ui-le-{eid}"},
                        json={"expected_revision": 0, "code": code, "legal_name": lname},
                    ).status_code
                    == 200
                )
                assert (
                    http.put(
                        f"{business}/ledger/books/{bid}",
                        headers={**headers, "Idempotency-Key": f"mkt-ui-bk-{bid}"},
                        json={
                            "schema_version": 1,
                            "expected_revision": 0,
                            "legal_entity_id": str(eid),
                            "base_currency": "USD",
                            "fiscal_year_start_month": 1,
                            "accounting_start": date(2026, 1, 1).isoformat(),
                        },
                    ).status_code
                    == 200
                )

        cmd = [
            npm,
            "exec",
            "--",
            "playwright",
            "test",
            "tests/market.spec.ts",
            *(f"--project={project}" for project in PROJECTS),
        ]
        result = subprocess.run(  # noqa: S603
            cmd,
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    # 3. Direct PostgreSQL 18 read-back for both desktop & mobile runs
    with owner_tenant_transaction(owner_conn, tenant_a) as tx:
        for low in ("desktop", "mobile"):
            mp_row = tx.execute(
                "select gorgona_commission_bps, operator_fee_bps from gba.marketplaces "
                "where tenant_id = %s and slug = %s",
                (tenant_a, f"hub-{low}"),
            ).fetchone()
            assert mp_row == (0, 300)

            conn_row = tx.execute(
                "select status, revoked_at is not null from gba.marketplace_seller_connections "
                "where tenant_id = %s and seller_storefront_slug = %s",
                (tenant_a, f"studio-{low}"),
            ).fetchone()
            assert conn_row == ("revoked", True)

            ord_rows = tx.execute(
                "select s.slug, o.total_minor, o.refunded_minor, o.status, "
                "o.invoice_document_id, o.credit_note_document_id is not null, "
                "o.legal_entity_id, o.book_id "
                "from gba.market_orders o "
                "join gba.market_storefronts s "
                "on s.tenant_id = o.tenant_id and s.id = o.storefront_id "
                "where o.tenant_id = %s and s.slug in (%s, %s) order by s.slug",
                (tenant_a, f"alpha-{low}", f"beta-{low}"),
            ).fetchall()
            assert len(ord_rows) == 2
            alpha_ord, beta_ord = ord_rows[0], ord_rows[1]
            assert alpha_ord[1] == 40000
            assert beta_ord[1] == 15000
            assert alpha_ord[4] != beta_ord[4]  # distinct FIN-03 invoices
            assert alpha_ord[6] != beta_ord[6]  # distinct legal entities
            assert alpha_ord[7] != beta_ord[7]  # distinct ledger books
            # Exactly one of the 2 orders was partially refunded for $100.00
            refunded_flags = [(r[2], r[3], r[5]) for r in ord_rows]
            assert (10000, "partially_refunded", True) in refunded_flags

            fee_rows = tx.execute(
                "select f.gorgona_commission_minor, f.operator_fee_minor "
                "from gba.market_operator_fees f "
                "join gba.marketplaces m on m.tenant_id = f.tenant_id and m.id = f.marketplace_id "
                "where f.tenant_id = %s and m.slug = %s order by f.operator_fee_minor",
                (tenant_a, f"hub-{low}"),
            ).fetchall()
            assert fee_rows == [(0, 450), (0, 1200)]
