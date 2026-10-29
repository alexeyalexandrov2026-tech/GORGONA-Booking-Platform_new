"""N6: brokerage on the transport screen in a real browser (FAKE data only).

Actual OIDC/PKCE, Chromium and PostgreSQL. A book, a customer and a carrier per project are seeded
through the routes, with a closed trip and an invoiced order per project; the browser records the
broker authority and the carrier's profile, tenders the leg, records the acceptance, agrees a
changed rate confirmation version, accrues the carrier's pay and reads the margin; the result is
read back.
"""

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_m1_transport_planning import accepted, leg, load, stop
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted"]
MODULES = ["booking_resources", "finance", "counterparties", "finance_documents", "transport"]
PROJECTS = ("desktop", "mobile")


def test_brokerage_on_the_screens_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    accepted: None,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: N6 browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/transport/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"n6-owner": seed_user(owner_conn, "n6-owner", issuer=issuer)}
    add_membership(owner_conn, tenant_id=tenant, user_id=people["n6-owner"].user_id, role="owner")
    idp = FakeIdp()
    signed_in = _SignedIn(people)
    signed_in.name = "n6-owner"
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    owner = people["n6-owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    business = f"/v1/businesses/{tenant}"
    orders: dict[str, UUID] = {}
    trips: dict[str, UUID] = {}
    with live_server(provider, idp_port), live_server(app, app_port):

        def call(method: str, path: str, body: object = None) -> Any:
            result = httpx.request(
                method,
                f"{origin}{path}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=15,
            )
            assert result.status_code == 200, result.text
            return result.json()

        call("PUT", f"{business}/profile", {"expected_revision": 0, "industry_ids": [24]})
        version = call(
            "PUT",
            f"{business}/configuration/draft",
            {"expected_version": 0, "profile_revision": 1, "module_ids": MODULES},
        )["version"]
        for step, revision in (("validate", 1), ("publish", 2)):
            call(
                "POST",
                f"{business}/configuration/versions/{version}/{step}",
                {"expected_revision": revision},
            )
        entity, book = uuid7(), uuid7()
        call(
            "PUT",
            f"{business}/legal-entities/{entity}",
            {"expected_revision": 0, "code": "FAKE_BROKER", "legal_name": "FAKE Brokerage LLC"},
        )
        call(
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
        chart = call("GET", f"{business}/ledger/books/{book}/accounts")["items"]

        def account(predicate: Any) -> dict[str, Any]:
            return cast(dict[str, Any], next(a for a in chart if predicate(a)))

        def label(found: dict[str, Any]) -> str:
            return f"{found['code']} {found['name']}"

        receivable = account(lambda a: a["code"] == "1200")
        revenue = account(lambda a: a["type"] == "revenue")
        env.update(
            GBA_N6_BOOK="FAKE Brokerage LLC",
            GBA_N6_EXPENSE=label(account(lambda a: a["code"] == "6000")),
            GBA_N6_PAYABLE=label(account(lambda a: a["code"] == "2200")),
        )
        customer = uuid7()
        call(
            "PUT",
            f"{business}/counterparties/{customer}",
            card(display_name="FAKE Shipper", roles=["customer"]),
        )
        carriers = {p: uuid7() for p in PROJECTS}
        for p, carrier in carriers.items():
            call(
                "PUT",
                f"{business}/counterparties/{carrier}",
                card(display_name=f"FAKE Carrier {p}", roles=["supplier"]),
            )
        location = str(world.a.location_id)
        stops = [
            stop("pickup", "FAKE dock, Chicago", "America/Chicago", 8, 10),
            stop("delivery", "FAKE yard, Indianapolis", "America/Indiana/Indianapolis", 14, 16),
        ]
        now = datetime.now(UTC)
        for p in PROJECTS:
            pallets = uuid7()
            orders[p], trips[p] = uuid7(), uuid7()
            call(
                "PUT",
                f"{business}/transport/orders/{orders[p]}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "customer_id": str(customer),
                    "reference": f"FAKE-SO-{p}",
                    "loads": [load(pallets, 10)],
                },
            )
            call(
                "PUT",
                f"{business}/transport/trips/{trips[p]}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": location,
                    "reference": f"FAKE-TR-{p}",
                    "stops": stops,
                    "legs": [leg(pallets, 10, 1, 2)],
                },
            )
            for kind, position, hours in (("loaded", 1, 2), ("delivered", 2, 1)):
                call(
                    "POST",
                    f"{business}/transport/trips/{trips[p]}/events",
                    {
                        "schema_version": 1,
                        "source": "dispatcher",
                        "source_event_id": f"FAKE-{uuid7()}",
                        "stop_position": position,
                        "kind": kind,
                        "occurred_at": (now - timedelta(hours=hours)).isoformat(),
                        "note": None,
                        "quantities": [{"leg_position": 1, "quantity": 10}],
                    },
                )
            call(
                "PUT",
                f"{business}/transport/orders/{orders[p]}/rate",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "currency": "USD",
                    "basis": "fixed",
                    "amount": "1500.00",
                },
            )
            call(
                "POST",
                f"{business}/transport/orders/{orders[p]}/invoice",
                {
                    "schema_version": 1,
                    "book_id": str(book),
                    "control_account_id": receivable["account_id"],
                    "revenue_account_id": revenue["account_id"],
                    "invoice_date": now.date().isoformat(),
                    "number": f"FAKE-TI-{p}",
                    "miles": None,
                    "extra_lines": [],
                },
            )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:transport-brokerage"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
        snapshots = "".join(
            f"\n--- {path.parent.name}\n" + path.read_text(encoding="utf-8")
            for path in sorted((web / "test-results").glob("*/error-context.md"))
        )
        assert result.returncode == 0, result.stdout + result.stderr + snapshots
        print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s
        authority = call("GET", f"{business}/transport/broker-authority")
        assert [v["authority_number"] for v in authority["versions"]] == [
            f"MC-FAKE-{p}" for p in PROJECTS
        ]
        for p in PROJECTS:
            profile = call("GET", f"{business}/transport/carriers/{carriers[p]}/profile")
            assert [v["safety_rating"] for v in profile["versions"]] == ["satisfactory"], p
            tenders = call("GET", f"{business}/transport/trips/{trips[p]}/tenders")["items"]
            # The refused offer to the carrier without a profile was never stored.
            assert [(t["state"], t["legs"], t["counterparty_id"]) for t in tenders] == [
                ("accepted", [1], str(carriers[p]))
            ], p
            made = tenders[0]["tender_id"]
            confirmation = call("GET", f"{business}/transport/tenders/{made}/rate-confirmation")
            assert [(v["revision"], v["amount"], v["state"]) for v in confirmation["versions"]] == [
                (1, "900.00", "agreed"),
                (2, "950.00", "agreed"),
            ], p
            assert confirmation["in_force"]["revision"] == 2, p
            pay = call("GET", f"{business}/transport/tenders/{made}/accrual")
            assert (pay["revision"], pay["accrual"]["total"], pay["accrual"]["number"]) == (
                2,
                "950.00",
                f"FAKE-CP-{p}",
            ), p
            margin = call("GET", f"{business}/transport/orders/{orders[p]}/margin")
            assert (margin["revenue"], margin["carrier_cost"], margin["margin"]) == (
                "1500.00",
                "950.00",
                "550.00",
            ), p

    with owner_tenant_transaction(owner_conn, tenant):
        assert owner_conn.execute(
            "select count(*) from gba.transport_tender_accruals"
        ).fetchone() == (2,)
        assert owner_conn.execute("select count(*) from gba.transport_tenders").fetchone() == (2,)
