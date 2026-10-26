"""M7b: transport money on the order and trip screens in a real browser (FAKE data only).

Actual OIDC/PKCE, Chromium and PostgreSQL. A book, its chart, a customer and payees are seeded
through the routes, with a closed trip per project; the browser sets the rate, creates the customer
invoice, registers pay components and accrues the driver's pay; the result is read back.
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


def test_transport_money_on_the_screens_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    accepted: None,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: M7b browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/transport/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"m7b-owner": seed_user(owner_conn, "m7b-owner", issuer=issuer)}
    add_membership(owner_conn, tenant_id=tenant, user_id=people["m7b-owner"].user_id, role="owner")
    idp = FakeIdp()
    signed_in = _SignedIn(people)
    signed_in.name = "m7b-owner"
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    owner = people["m7b-owner"]
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
            {"expected_revision": 0, "code": "FAKE_HAUL", "legal_name": "FAKE Haulage LLC"},
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

        def label(predicate: Any) -> str:
            account = next(a for a in chart if predicate(a))
            return f"{account['code']} {account['name']}"

        env.update(
            GBA_M7B_BOOK="FAKE Haulage LLC",
            GBA_M7B_RECEIVABLE=label(lambda a: a["code"] == "1200"),
            GBA_M7B_REVENUE=label(lambda a: a["type"] == "revenue"),
            GBA_M7B_EXPENSE=label(lambda a: a["code"] == "6000"),
            GBA_M7B_PAYABLE=label(lambda a: a["code"] == "2200"),
        )
        customer = uuid7()
        call(
            "PUT",
            f"{business}/counterparties/{customer}",
            card(display_name="FAKE Shipper", roles=["customer"]),
        )
        for name in ("FAKE Dispatch Co", *(f"FAKE Driver Pay {p}" for p in PROJECTS)):
            call(
                "PUT",
                f"{business}/counterparties/{uuid7()}",
                card(display_name=name, roles=["supplier"]),
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
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:transport-money"],
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
        for p in PROJECTS:
            invoice = call("GET", f"{business}/transport/orders/{orders[p]}/invoice")
            assert (invoice["rate_revision"], invoice["miles"]) == (1, "412.5"), p
            assert [x["amount"] for x in invoice["invoice"]["lines"]] == ["969.38", "75.00"], p
            assert (invoice["invoice"]["state"], invoice["invoice"]["number"]) == (
                "draft",
                f"FAKE-TI-{p}",
            )
            pay = call("GET", f"{business}/transport/trips/{trips[p]}/pay")["components"]
            assert sorted(c["role"] for c in pay) == ["dispatch_fee", "driver"], p
            driver = next(c for c in pay if c["role"] == "driver")
            fee = next(c for c in pay if c["role"] == "dispatch_fee")
            assert (driver["basis"], driver["rate"]) == ("per_mile", "0.55"), p
            assert (fee["basis"], fee["percent"], fee["base"]) == ("percent", "7.5", "1250.00"), p
            assert driver["accrual"]["accrual"]["total"] == "226.88", p
            assert fee["accrual"] is None, p

    with owner_tenant_transaction(owner_conn, tenant):
        for p in PROJECTS:
            assert owner_conn.execute(
                "select revision, basis, amount::text from gba.transport_order_rates "
                "where order_id = %s",
                (orders[p],),
            ).fetchall() == [(1, "per_mile", "2.350")], p
