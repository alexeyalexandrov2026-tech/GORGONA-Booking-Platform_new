"""L7b2a: bill a visit from its desk and accrue the specialist's commission once it is paid.

Actual OIDC/PKCE, Chromium and PostgreSQL on desktop and mobile; FAKE data only. Issuing the invoice
and recording its payment run through the existing FIN-03 routes (a fixture route stands in for the
finance screens); what the desk did is read back from the database here.
"""

import asyncio
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

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_l7b_visit_desk_browser import BUSINESS_ZONE, _started_visits, zone_today
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp

MODULES = ["booking_resources", "finance", "counterparties", "finance_documents"]


def test_visit_billing_and_commission_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: L7b2 browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/bookings/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "l7b2-owner", issuer=issuer)}
    add_membership(owner_conn, tenant_id=tenant, user_id=people["owner"].user_id, role="owner")
    idp = FakeIdp()
    signed_in = _SignedIn(people)
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    owner = people["owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    business = f"/v1/businesses/{tenant}"
    salon = f"/v1/salons/{tenant}"
    # Ledger dates may not be after today in the business time zone.
    today = zone_today(owner_conn, tenant, BUSINESS_ZONE, tenant)
    state: dict[str, object] = {}

    def request(method: str, path: str, body: object = None) -> httpx.Response:
        result = httpx.request(
            method,
            f"{origin}{path}",
            json=body,
            headers={**headers, "Idempotency-Key": str(uuid7())},
            timeout=15,
        )
        assert result.status_code == 200, result.text
        return result

    @provider.post("/fixture/pay/{project}")
    async def pay(project: str) -> dict[str, str]:
        visits = cast(dict[str, UUID], state["visits"])
        if project not in visits:
            raise HTTPException(404, "Unknown FAKE project")

        def settle() -> None:
            billed = request("GET", f"{salon}/bookings/{visits[project]}/invoice").json()
            root = f"{business}/financial-documents/books/{billed['book_id']}"
            issued = request(
                "POST",
                f"{root}/invoices/{billed['document_id']}/issue",
                {
                    "schema_version": 1,
                    "expected_revision": 1,
                    "entry_date": today,
                    "attestation": "confirmed_account_treatment",
                },
            ).json()
            owed, total = issued["obligation_id"], issued["total"]
            settlement = uuid7()
            request(
                "PUT",
                f"{root}/settlements/{settlement}",
                {
                    "schema_version": 1,
                    "expected_sequence": 0,
                    "direction": "receivable",
                    "counterparty_id": str(state["customer"]),
                    "currency": "USD",
                    "allocations": [{"obligation_id": owed, "amount": total}],
                },
            )
            for action, sequence in (("approve", 1), ("reserve", 2)):
                request(
                    "POST",
                    f"{root}/settlements/{settlement}/{action}",
                    {"schema_version": 1, "expected_sequence": sequence},
                )
            request(
                "POST",
                f"{root}/settlements/{settlement}/confirmations/{uuid7()}",
                {
                    "schema_version": 1,
                    "expected_sequence": 3,
                    "amount": total,
                    "actual_external_date": today,
                    "entry_date": today,
                    "cash_account_id": str(state["cash"]),
                    "source_account_alias": "FAKE main bank account",
                    "external_reference": f"FAKE-PAY-{project}",
                    "attestation": "manual_attestation",
                    "allocations": [{"obligation_id": owed, "amount": total}],
                },
            )

        await asyncio.to_thread(settle)
        return {"paid": project}

    with live_server(provider, idp_port), live_server(app, app_port):
        request("PUT", f"{business}/profile", {"expected_revision": 0, "industry_ids": [1]})
        draft = request(
            "PUT",
            f"{business}/configuration/draft",
            {"expected_version": 0, "profile_revision": 1, "module_ids": MODULES},
        ).json()
        for step, revision in (("validate", 1), ("publish", 2)):
            request(
                "POST",
                f"{business}/configuration/versions/{draft['version']}/{step}",
                {"expected_revision": revision},
            )
        entity, book = uuid7(), uuid7()
        request(
            "PUT",
            f"{business}/legal-entities/{entity}",
            {"expected_revision": 0, "code": "FAKE_BILL", "legal_name": "FAKE Billing LLC"},
        )
        request(
            "PUT",
            f"{business}/ledger/books/{book}",
            {
                "expected_revision": 0,
                "legal_entity_id": str(entity),
                "base_currency": "USD",
                "fiscal_year_start_month": 1,
                "accounting_start": "2026-01-01",
            },
        )
        chart = request("GET", f"{business}/ledger/books/{book}/accounts").json()["items"]
        state["cash"] = next(a["account_id"] for a in chart if a["code"] == "1100")
        parties = {
            "customer": "FAKE Customer",
            **{p: f"FAKE Specialist {p}" for p in ("desktop", "mobile")},
        }
        for key, name in parties.items():
            party = uuid7()
            request(
                "PUT",
                f"{business}/counterparties/{party}",
                card(display_name=name, roles=["customer", "supplier"]),
            )
            state[key] = party
        state["visits"] = asyncio.run(
            _started_visits(test_database.app_dsn, world), loop_factory=asyncio.SelectorEventLoop
        )
        visits = cast(dict[str, UUID], state["visits"])
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:billing"],
            cwd=web,
            env={
                **env,
                "GBA_L7B2_DESKTOP_BOOKING": str(visits["desktop"]),
                "GBA_L7B2_MOBILE_BOOKING": str(visits["mobile"]),
            },
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
        # On failure keep the page snapshot: the next browser test clears web/test-results.
        snapshots = "".join(
            f"\n--- {path.parent.name}\n" + path.read_text(encoding="utf-8")
            for path in sorted((web / "test-results").glob("*/error-context.md"))
        )
        assert result.returncode == 0, result.stdout + result.stderr + snapshots
        print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s

    with owner_tenant_transaction(owner_conn, tenant):
        for booking in visits.values():
            billed = owner_conn.execute(
                "select count(*) from gba.visit_invoices where booking_id = %s", (booking,)
            ).fetchone()
            assert billed == (1,)
            accrued = owner_conn.execute(
                "select sum(l.amount_minor) from gba.visit_commissions c "
                "join gba.financial_document_lines l on l.tenant_id = c.tenant_id "
                "and l.book_id = c.book_id and l.document_id = c.document_id "
                "where c.booking_id = %s",
                (booking,),
            ).fetchone()
            assert accrued == (500,)
        plans = owner_conn.execute(
            "select count(*) from gba.commission_rules "
            "where percent_bp = 1000 and service_id is null"
        ).fetchone()
        assert plans == (2,)
