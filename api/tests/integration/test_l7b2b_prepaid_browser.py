"""L7b2b: sell a prepaid package on the Prepaid screen and redeem it from the visit desk.

Actual OIDC/PKCE, Chromium and PostgreSQL on desktop and mobile; FAKE data only. The visit invoices
are billed and issued, and the sale invoice issued and settled, through the existing routes
(a fixture route stands in for the finance screens); what the screens did is read back from the
database here.
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
PROJECTS = ("desktop", "mobile")


def test_prepaid_sale_and_redemption_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: L7b2b browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/prepaid/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "l7b2b-owner", issuer=issuer)}
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

    def issue(book: object, document: object) -> dict[str, str]:
        root = f"{business}/financial-documents/books/{book}"
        issued: dict[str, str] = request(
            "POST",
            f"{root}/invoices/{document}/issue",
            {
                "schema_version": 1,
                "expected_revision": 1,
                "entry_date": today,
                "attestation": "confirmed_account_treatment",
            },
        ).json()
        return issued

    def settle(book: object, party: object, owed: str, total: str, reference: str) -> None:
        root = f"{business}/financial-documents/books/{book}"
        settlement = uuid7()
        request(
            "PUT",
            f"{root}/settlements/{settlement}",
            {
                "schema_version": 1,
                "expected_sequence": 0,
                "direction": "receivable",
                "counterparty_id": str(party),
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
                "external_reference": reference,
                "attestation": "manual_attestation",
                "allocations": [{"obligation_id": owed, "amount": total}],
            },
        )

    @provider.post("/fixture/pay-sale/{project}")
    async def pay_sale(project: str) -> dict[str, str]:
        if project not in PROJECTS:
            raise HTTPException(404, "Unknown FAKE project")
        party = state[project]

        def run() -> None:
            listed = request("GET", f"{salon}/prepaid?counterparty_id={party}").json()
            (balance,) = [x for x in listed["items"] if x["sale"]["number"] == f"FAKE-P-{project}"]
            sale = balance["sale"]
            issued = issue(sale["book_id"], sale["document_id"])
            settle(
                sale["book_id"],
                party,
                issued["obligation_id"],
                issued["total"],
                f"FAKE-PAY-P-{project}",
            )

        await asyncio.to_thread(run)
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
            {"expected_revision": 0, "code": "FAKE_PREPAID", "legal_name": "FAKE Prepaid LLC"},
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
        codes = {account["code"]: account["account_id"] for account in chart}
        state["cash"] = codes["1100"]
        for project in PROJECTS:
            party = uuid7()
            request(
                "PUT",
                f"{business}/counterparties/{party}",
                card(display_name=f"FAKE Customer {project}", roles=["customer"]),
            )
            state[project] = party
        visits = asyncio.run(
            _started_visits(test_database.app_dsn, world), loop_factory=asyncio.SelectorEventLoop
        )
        # Each visit is billed to its project's customer and issued, unpaid.
        for project in PROJECTS:
            billed = request(
                "POST",
                f"{salon}/bookings/{visits[project]}/invoice",
                {
                    "book_id": str(book),
                    "counterparty_id": str(state[project]),
                    "control_account_id": codes["1200"],
                    "revenue_account_id": codes["4100"],
                    "invoice_date": today,
                    "number": f"FAKE-V-{project}",
                },
            ).json()
            issue(book, billed["document_id"])
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:prepaid"],
            cwd=web,
            env={
                **env,
                "GBA_L7B2B_DESKTOP_BOOKING": str(visits["desktop"]),
                "GBA_L7B2B_MOBILE_BOOKING": str(visits["mobile"]),
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
        for project in PROJECTS:
            used = owner_conn.execute(
                "select b.used_units, b.used_minor, count(r.booking_id) "
                "from gba.prepaid_balances b left join gba.prepaid_redemptions r "
                "on r.tenant_id = b.tenant_id and r.prepaid_id = b.id "
                "where b.counterparty_id = %s group by b.tenant_id, b.id",
                (cast(UUID, state[project]),),
            ).fetchall()
            assert used == [(1, 5000, 1)]
            redeemed = owner_conn.execute(
                "select booking_id from gba.prepaid_redemptions r join gba.prepaid_balances b "
                "on b.tenant_id = r.tenant_id and b.id = r.prepaid_id where b.counterparty_id = %s",
                (cast(UUID, state[project]),),
            ).fetchall()
            assert redeemed == [(visits[project],)]
