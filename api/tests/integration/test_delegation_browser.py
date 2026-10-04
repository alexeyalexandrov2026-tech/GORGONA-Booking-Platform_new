"""Delegation between businesses through real OIDC/PKCE, Chromium, API and PostgreSQL.

`management`: one person owns business A and business B. In the browser they grant B access
to A, designate a B employee from B and revoke the grant from A.
`workspace`: a designated B employee signs in and books for A within the grant.
The identity provider is the FAKE loopback provider of the management browser harness.
"""

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid7

import httpx
import psycopg
import pytest
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import SecretStr

from gorgona_booking.api.app import create_app
from gorgona_booking.config import Settings
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import customer_day, seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import seed_user
from tests.integration.test_management_browser import CLIENT_ID, _provider
from tests.support.fake_idp import FAKE_AUDIENCE, FakeIdp

PURPOSE = "FAKE browser call centre"
GUEST = "FAKE Delegated Browser Guest"
WRITE = ["booking.read", "booking.write", "catalog.read", "staff.read"]


@pytest.mark.parametrize("scenario", ["management", "workspace"])
def test_real_delegation_browser_flows(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    scenario: str,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: delegation browser verification requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out" / "auth" / "callback" / "index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    app_port, idp_port = free_port(), free_port()
    app_origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner_a = seed_user(owner_conn, f"browser-grantor-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner_a.user_id, role="owner")
    owner_b = (
        owner_a
        if scenario == "management"
        else seed_user(owner_conn, f"browser-serving-owner-{uuid7()}", issuer=issuer)
    )
    add_membership(owner_conn, tenant_id=world.b.tenant_id, user_id=owner_b.user_id, role="owner")
    label = f"browser-dispatcher-{uuid7()}"
    delegate = seed_user(owner_conn, label, issuer=issuer)
    delegate_membership = add_membership(
        owner_conn, tenant_id=world.b.tenant_id, user_id=delegate.user_id, role="front_desk"
    )
    user = owner_a if scenario == "management" else delegate
    idp = FakeIdp()
    provider, verifier = _provider(issuer, app_origin, idp, user)
    app = create_app(
        Settings(environment="test", database_url=SecretStr(test_database.app_dsn)),
        token_verifier=verifier,
    )

    @app.get("/auth-config.json")
    async def auth_config() -> JSONResponse:
        return JSONResponse(
            {
                "authority": issuer,
                "client_id": CLIENT_ID,
                "scope": "openid profile email",
                "resource": FAKE_AUDIENCE,
            },
            headers={"Cache-Control": "no-store"},
        )

    # Test-only runtime route precedes the actual static export; APIs remain unchanged.
    app.mount("/", StaticFiles(directory=web / "out", html=True), name="delegation-test-web")
    blocked_keys = ("DSN", "DATABASE_URL", "SECRET", "PASSWORD", "TOKEN")
    env = {
        k: v for k, v in os.environ.items() if not any(part in k.upper() for part in blocked_keys)
    }
    now = datetime.now(UTC)
    env.update(
        GBA_MGMT_BROWSER_URL=app_origin,
        GBA_MGMT_BROWSER_DAY=customer_day(),
        GBA_TEST_OIDC_ISSUER=issuer,
        GBA_OWNER_BUSINESS=str(world.a.tenant_id),
        GBA_SERVING_BUSINESS=str(world.b.tenant_id),
        GBA_DELEGATE_NAME=f"FAKE user {label}",
        GBA_DELEGATE_OPTION=f"FAKE user {label} (front_desk)",
        GBA_DELEGATE_USER=str(delegate.user_id),
        GBA_DELEGATION_FROM=(now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        GBA_DELEGATION_UNTIL=(now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M"),
    )
    owner_headers = idp.bearer(owner_a.subject, email=owner_a.email, iss=issuer)
    grant_id = uuid7()
    with live_server(provider, idp_port), live_server(app, app_port):
        if scenario == "workspace":
            granted = httpx.put(
                f"{app_origin}/v1/businesses/{world.a.tenant_id}/delegations/{grant_id}",
                headers={**owner_headers, "Idempotency-Key": str(uuid7())},
                json={
                    "expected_revision": 0,
                    "grantee_business_id": str(world.b.tenant_id),
                    "purpose": PURPOSE,
                    "permissions": WRITE,
                    "valid_from": (now - timedelta(hours=1)).isoformat(),
                    "valid_until": (now + timedelta(days=7)).isoformat(),
                },
                timeout=10,
            )
            assert granted.status_code == 200, granted.text
            designated = httpx.put(
                f"{app_origin}/v1/businesses/{world.b.tenant_id}/incoming-delegations/"
                f"{grant_id}/delegates/{delegate_membership}",
                headers={
                    **idp.bearer(owner_b.subject, email=owner_b.email, iss=issuer),
                    "Idempotency-Key": str(uuid7()),
                },
                timeout=10,
            )
            assert designated.status_code == 200, designated.text
        result = subprocess.run(  # noqa: S603 - fixed repository script and located npm executable
            [npm, "run", f"test:delegation:{scenario}"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - surface browser evidence under pytest -s
        if scenario == "workspace":
            revoked = httpx.post(
                f"{app_origin}/v1/businesses/{world.a.tenant_id}/delegations/{grant_id}/revoke",
                headers={**owner_headers, "Idempotency-Key": str(uuid7())},
                json={"expected_revision": 1},
                timeout=10,
            )
            assert revoked.status_code == 200, revoked.text
            after = httpx.get(
                f"{app_origin}/v1/salons/{world.a.tenant_id}/bookings",
                headers=idp.bearer(delegate.subject, email=delegate.email, iss=issuer),
                timeout=10,
            )
            assert after.status_code == 403, after.text

    if scenario == "management":
        with owner_tenant_transaction(owner_conn, world.a.tenant_id):
            grants = owner_conn.execute(
                "select g.grantee_business_id, array_agg(v.state order by v.revision) "
                "from gba.delegation_grants g join gba.delegation_grant_versions v "
                "on v.tenant_id = g.tenant_id and v.grant_id = g.id group by g.tenant_id, g.id"
            ).fetchall()
        # Desktop and mobile each create, then revoke, one grant from A to B.
        assert grants == [(world.b.tenant_id, ["active", "revoked"])] * 2
        with owner_tenant_transaction(owner_conn, world.b.tenant_id):
            designations = owner_conn.execute(
                "select count(*) from gba.delegation_designations "
                "where membership_id = %s and status = 'active'",
                (delegate_membership,),
            ).fetchone()
            # B reads the grants addressed to it but owns none of them.
            visible = owner_conn.execute(
                "select count(*) filter (where grantee_business_id = %s), "
                "count(*) filter (where tenant_id = %s) from gba.delegation_grants",
                (world.b.tenant_id, world.b.tenant_id),
            ).fetchone()
        assert designations == (2,)
        assert visible == (2, 0)
        return

    actor = f"delegate:{delegate.user_id}@{world.b.tenant_id}/grant:{grant_id}"
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        rows = owner_conn.execute(
            "select b.status, b.created_by, count(*) from gba.bookings b "
            "join gba.booking_customers c on c.tenant_id = b.tenant_id and c.booking_id = b.id "
            "where c.customer_name = %s group by b.status, b.created_by",
            (GUEST,),
        ).fetchall()
        actors = owner_conn.execute(
            "select distinct e.actor from gba.booking_events e "
            "join gba.booking_customers c on c.tenant_id = e.tenant_id "
            "and c.booking_id = e.booking_id where c.customer_name = %s",
            (GUEST,),
        ).fetchall()
        audited = owner_conn.execute(
            "select count(*) from gba.audit_events "
            "where action = 'delegation.access' and actor = %s",
            (actor,),
        ).fetchone()
    # Desktop and mobile each create -> reschedule -> cancel: four cancelled bookings in A.
    assert rows == [("CANCELLED", actor, 4)]
    assert actors == [(actor,)]
    assert audited is not None
    assert audited[0] > 0
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        assert owner_conn.execute("select count(*) from gba.bookings").fetchone() == (0,)
