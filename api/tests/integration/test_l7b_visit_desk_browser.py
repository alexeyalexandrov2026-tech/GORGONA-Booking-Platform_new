"""L7b1 visit desk: complete a visit with actual quantities and write its materials off.

Actual OIDC/PKCE, Chromium and PostgreSQL on desktop and mobile; FAKE data only. What the screen
did is read back from the database here.
"""

import asyncio
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.booking.models import ReservationRequest
from gorgona_booking.booking.service import BookingService
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import create_runtime_pool
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_materials_browser import RULES
from tests.support.fake_idp import FakeIdp

USED_WRITE_OFFS = (
    "select coalesce(sum(l.quantity), 0) from gba.stock_document_lines l "
    "join gba.stock_documents d on d.tenant_id = l.tenant_id and d.id = l.document_id "
    "where d.kind = 'write_off' and d.reason = 'used'"
)


async def _started_visits(dsn: str, world: BookingWorld) -> dict[str, UUID]:
    pool = create_runtime_pool(dsn, min_size=1, max_size=2)
    await pool.open()
    try:
        start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=3)
        service = BookingService(pool)
        visits: dict[str, UUID] = {}
        for project, artist in (("desktop", world.artist_a1), ("mobile", world.artist_a2)):
            result = await service.create_confirmed_booking(
                world.a.tenant_id,
                ReservationRequest(
                    resource_id=artist, variant_id=world.catalog_a.base_variant_id, starts_at=start
                ),
                actor="test:l7b",
                idempotency_key=None,
            )
            visits[project] = result.booking_id
        return visits
    finally:
        await pool.close()


def test_visit_desk_completion_and_consumption_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: L7b browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/bookings/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    tenant, home = world.a.tenant_id, world.a.location_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "l7b-owner", issuer=issuer)}
    add_membership(owner_conn, tenant_id=tenant, user_id=people["owner"].user_id, role="owner")
    idp = FakeIdp()
    signed_in = _SignedIn(people)
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    owner = people["owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
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

        business = f"/v1/businesses/{tenant}"
        request("PUT", f"{business}/profile", {"expected_revision": 0, "industry_ids": [1]})
        draft = request(
            "PUT",
            f"{business}/configuration/draft",
            {
                "expected_version": 0,
                "profile_revision": 1,
                "module_ids": ["booking_resources", "finance", "inventory"],
            },
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
            {"expected_revision": 0, "code": "FAKE_DESK", "legal_name": "FAKE Visit Desk LLC"},
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
        request(
            "PUT",
            f"{business}/inventory/posting-rules/{book}",
            {
                "expected_revision": 0,
                **{f"{name}_account_id": codes[code] for name, code in RULES.items()},
            },
        )
        dye, shelf = uuid7(), uuid7()
        request(
            "PUT",
            f"{business}/inventory/items/{dye}",
            {
                "expected_revision": 0,
                "code": "FAKE-DYE",
                "name": "FAKE dye",
                "unit": "ml",
                "quantity_scale": 1,
            },
        )
        request(
            "PUT",
            f"{business}/inventory/places/{shelf}",
            {
                "expected_revision": 0,
                "location_id": str(home),
                "code": "FAKE-SHELF",
                "name": "FAKE shelf",
            },
        )
        today = datetime.now(UTC).date().isoformat()
        request(
            "PUT",
            f"{business}/inventory/documents/{uuid7()}",
            {
                "kind": "receipt",
                "reason": "purchase",
                "legal_entity_id": str(entity),
                "place_id": str(shelf),
                "document_date": today,
                "lines": [{"item_id": str(dye), "quantity": "100.0", "amount": "50.00"}],
            },
        )
        salon = f"/v1/salons/{tenant}"
        base = world.catalog_a.base_variant_id
        revision = next(
            s["revision"]
            for s in request("GET", f"{salon}/services").json()
            if s["id"] == str(base)
        )
        request(
            "PUT",
            f"{salon}/services/{base}/materials",
            {"expected_revision": revision, "lines": [{"item_id": str(dye), "quantity": "2.5"}]},
        )
        # psycopg's async mode needs the selector loop on Windows.
        visits = asyncio.run(
            _started_visits(test_database.app_dsn, world), loop_factory=asyncio.SelectorEventLoop
        )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:visit"],
            cwd=web,
            env={
                **env,
                "GBA_L7B_DESKTOP_BOOKING": str(visits["desktop"]),
                "GBA_L7B_MOBILE_BOOKING": str(visits["mobile"]),
            },
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s

    with owner_tenant_transaction(owner_conn, tenant):
        for booking in visits.values():
            completion = owner_conn.execute(
                "select stock_document_id is not null, consumption_posted_at is not null "
                "from gba.visit_completions where booking_id = %s",
                (booking,),
            ).fetchone()
            assert completion == (True, True)
            uses = owner_conn.execute(
                "select item_id, planned, actual from gba.visit_material_uses "
                "where booking_id = %s",
                (booking,),
            ).fetchall()
            assert uses == [(dye, 25, 30)]
        assert owner_conn.execute(USED_WRITE_OFFS).fetchone() == (60,)
