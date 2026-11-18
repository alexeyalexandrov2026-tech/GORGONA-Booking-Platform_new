"""R-09 change offer through manager UI, OIDC, Chromium, API and PostgreSQL."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TypedDict, cast
from uuid import UUID

import psycopg
import pytest
from fastapi import HTTPException

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    idp,
    manager_a,
    rental,
)
from tests.integration.test_r2_rental_bookings import at
from tests.integration.test_r3a_rental_assignment import assign
from tests.integration.test_r3b_rental_blocks import block
from tests.integration.test_r4c_rental_extensions import agreed, holds
from tests.support.fake_idp import FakeIdp

__all__ = ["accepted", "client", "idp", "manager_a", "owner_a", "owner_b", "parties", "rental"]


class Fixture(TypedDict):
    business: str
    booking: str
    number: int
    grant: str
    revoked: str


@pytest.mark.anyio
async def test_rental_change_offer_browser(
    rental: Rental,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: rental change offer requires GBA_REQUIRE_BROWSER=1")
    web = (await asyncio.to_thread(Path(__file__).resolve)).parents[3] / "web"
    assert await asyncio.to_thread((web / "out/rental/customer/change/index.html").is_file), (
        "build web first"
    )
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, "r09-change-owner", issuer=issuer)
    customer = seed_user(owner_conn, "r09-change-renter", issuer=issuer)
    add_membership(owner_conn, tenant_id=rental.tenant, user_id=owner.user_id, role="owner")
    company = rental.world.b.tenant_id
    add_membership(owner_conn, tenant_id=company, user_id=customer.user_id, role="owner")
    terms = {
        "permissions": ["rental.customer_answer"],
        "location_id": str(rental.world.a.location_id),
    }
    revoked = await parties.active_grant(owner_a, owner_b, [customer], **terms)
    ended = await parties.act(owner_a, rental.tenant, revoked, "revoke", 2)
    assert ended.status_code == 200, ended.text
    grant = await parties.active_grant(owner_a, owner_b, [customer], **terms)
    fixtures: dict[str, Fixture] = {}
    for device in ("desktop", "mobile"):
        _, (unit, _), _, booking = await agreed(rental, 2)
        assert (await assign(rental, booking, unit)).status_code == 200
        assert (await block(rental, unit, at(4), at(5))).status_code == 200
        linked = await rental.put(
            f"/bookings/{booking}/customer-company",
            {"expected_revision": 0, "company_id": str(company)},
        )
        assert linked.status_code == 200, linked.text
        existing = await rental.get(f"/bookings/{booking}")
        assert existing.status_code == 200, existing.text
        fixtures[device] = {
            "business": str(rental.tenant),
            "booking": booking,
            "number": int(existing.json()["number"]),
            "grant": str(grant),
            "revoked": str(revoked),
        }

    signed_in = _SignedIn({"owner": owner, "customer": customer})
    provider, verifier = _provider(issuer, origin, FakeIdp(), cast(FakeUser, signed_in))
    app = _management_app(test_database, verifier, issuer, web)

    @provider.post("/browser/user/{person}")
    async def switch_user(person: str) -> dict[str, bool]:
        if person not in signed_in.people:
            raise HTTPException(404)
        signed_in.name = person
        return {"selected": True}

    env = {**_browser_env(origin, issuer), "GBA_RENTAL_CHANGE_OFFERS": json.dumps(fixtures)}
    with live_server(provider, idp_port), live_server(app, app_port):
        result = await asyncio.to_thread(
            subprocess.run,
            [
                npm,
                "exec",
                "--",
                "playwright",
                "test",
                "tests/rental-change-offer.spec.ts",
                "--max-failures=1",
            ],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - browser evidence in CI output

    with owner_tenant_transaction(owner_conn, rental.tenant):
        for fixture in fixtures.values():
            changes = owner_conn.execute(
                "select v.version, v.source, v.customer_change_offer_revision, "
                "v.customer_grant_id, v.recorded_by, v.total "
                "from gba.rental_agreement_versions v join gba.rental_agreements a "
                "on (v.tenant_id, v.agreement_id) = (a.tenant_id, a.id) "
                "where a.booking_id = %s and v.version > 1",
                (UUID(fixture["booking"]),),
            ).fetchall()
            assert changes == [(2, "platform", 3, grant, customer.user_id, 17_100)]
    for fixture in fixtures.values():
        assert [row[0] for row in holds(rental, fixture["booking"])] == ["released", "confirmed"]
