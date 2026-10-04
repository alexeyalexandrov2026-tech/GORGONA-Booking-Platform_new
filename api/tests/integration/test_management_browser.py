"""Real OIDC code/PKCE + Chromium + management API + disposable PostgreSQL.

The identity provider is explicitly FAKE and exists only in this test fixture.
Its discovery, authorize, token, JWKS and logout requests are real loopback HTTP.
No login callback, token or management API response is mocked in the browser.
"""

import base64
import hashlib
import hmac
import os
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode
from uuid import uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import SecretStr

from gorgona_booking.api.app import create_app
from gorgona_booking.auth.verifier import OidcJwtVerifier, StaticJwksKeySource
from gorgona_booking.config import Settings
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import customer_day, seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.support.fake_idp import FAKE_AUDIENCE, FakeIdp

CLIENT_ID = "gba-browser-test"
GUEST = "FAKE Management Browser Guest"


@dataclass(frozen=True, slots=True)
class AuthorizationCode:
    challenge: str
    nonce: str
    invalid_nonce: bool


def _provider(
    issuer: str, app_origin: str, idp: FakeIdp, user: FakeUser
) -> tuple[FastAPI, OidcJwtVerifier]:
    provider = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    provider.add_middleware(
        CORSMiddleware,
        allow_origins=[app_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    verifier = OidcJwtVerifier(
        issuer=issuer,
        audience=FAKE_AUDIENCE,
        key_source=StaticJwksKeySource(idp.jwks),
        leeway_seconds=0,
    )
    redirect_uri = f"{app_origin}/auth/callback/"
    codes: dict[str, AuthorizationCode] = {}

    @provider.get("/.well-known/openid-configuration")
    async def discovery() -> dict[str, object]:
        return {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/authorize",
            "token_endpoint": f"{issuer}/token",
            "jwks_uri": f"{issuer}/jwks",
            "userinfo_endpoint": f"{issuer}/userinfo",
            "end_session_endpoint": f"{issuer}/logout",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }

    @provider.get("/jwks")
    async def jwks() -> dict[str, object]:
        return idp.jwks

    @provider.get("/authorize")
    async def authorize(request: Request) -> RedirectResponse:
        query = request.query_params
        if (
            query.get("client_id") != CLIENT_ID
            or query.get("redirect_uri") != redirect_uri
            or query.get("response_type") != "code"
            or query.get("code_challenge_method") != "S256"
            or not query.get("code_challenge")
            or not query.get("state")
        ):
            raise HTTPException(400, "Invalid authorization request")
        code = secrets.token_urlsafe(32)
        codes[code] = AuthorizationCode(
            query["code_challenge"],
            query.get("nonce", ""),
            query.get("invalid_nonce") == "1",
        )
        return RedirectResponse(
            f"{redirect_uri}?{urlencode({'code': code, 'state': query['state']})}", status_code=302
        )

    @provider.post("/token")
    async def token(request: Request) -> JSONResponse:
        body = await request.body()
        if len(body) > 8192:
            raise HTTPException(400, "Invalid token request")
        values = parse_qs(body.decode("utf-8"))

        def value(name: str) -> str:
            entries = values.get(name, [])
            return entries[0] if len(entries) == 1 else ""

        record = codes.pop(value("code"), None)
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(value("code_verifier").encode("ascii")).digest()
            )
            .rstrip(b"=")
            .decode("ascii")
        )
        if (
            value("grant_type") != "authorization_code"
            or value("client_id") != CLIENT_ID
            or value("redirect_uri") != redirect_uri
            or record is None
            or not hmac.compare_digest(record.challenge, challenge)
        ):
            raise HTTPException(400, "Invalid code or PKCE verifier")
        access_token = idp.token(
            user.subject,
            email=user.email,
            iss=issuer,
            name="FAKE Management Browser Manager",
        )
        id_token = idp.token(
            user.subject,
            email=user.email,
            iss=issuer,
            name="FAKE Management Browser Manager",
            aud=CLIENT_ID,
            nonce="invalid-nonce" if record.invalid_nonce else record.nonce,
        )
        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": id_token,
                "scope": "openid profile email",
            },
            headers={"Cache-Control": "no-store"},
        )

    @provider.get("/userinfo")
    async def userinfo(request: Request) -> dict[str, object]:
        scheme, _, credential = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(401, "Authentication required")
        verified = await verifier.verify(credential)
        return {
            "sub": verified.subject,
            "email": user.email,
            "email_verified": True,
            "name": "FAKE Management Browser Manager",
        }

    @provider.get("/logout")
    async def logout(request: Request) -> RedirectResponse:
        destination = request.query_params.get("post_logout_redirect_uri", "")
        if destination not in (f"{app_origin}/", f"{app_origin}/overview/"):
            raise HTTPException(400, "Invalid logout redirect")
        return RedirectResponse(destination, status_code=302)

    return provider, verifier


def _management_app(
    test_database: ProvisionedDatabase, verifier: OidcJwtVerifier, issuer: str, web: Path
) -> FastAPI:
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
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=web / "out", html=True), name="management-test-web")
    return app


def _browser_env(app_origin: str, issuer: str) -> dict[str, str]:
    blocked_keys = ("DSN", "DATABASE_URL", "SECRET", "PASSWORD", "TOKEN")
    env = {
        k: v for k, v in os.environ.items() if not any(part in k.upper() for part in blocked_keys)
    }
    env.update(
        GBA_MGMT_BROWSER_URL=app_origin,
        GBA_MGMT_BROWSER_DAY=customer_day(),
        GBA_TEST_OIDC_ISSUER=issuer,
    )
    return env


@pytest.mark.parametrize("location_limited", [False, True])
def test_real_management_browser_oidc_pkce_and_database(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    location_limited: bool,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: management browser verification requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out" / "auth" / "callback" / "index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    private_location, private_resource = seed_other_branch(owner_conn, world.a)
    app_port, idp_port = free_port(), free_port()
    app_origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    user = seed_user(owner_conn, f"browser-manager-{uuid7()}", issuer=issuer)
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=user.user_id,
        role="manager",
        location_id=world.a.location_id if location_limited else None,
    )
    owner = seed_user(owner_conn, f"browser-owner-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    idp = FakeIdp()
    provider, verifier = _provider(issuer, app_origin, idp, user)
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(app_origin, issuer)
    env.update(
        GBA_PRIVATE_LOCATION=str(private_location),
        GBA_PRIVATE_RESOURCE=str(private_resource),
    )
    with live_server(provider, idp_port), live_server(app, app_port):
        if location_limited:
            private = httpx.post(
                f"{app_origin}/v1/salons/{world.a.tenant_id}/bookings",
                headers=idp.bearer(owner.subject, email=owner.email, iss=issuer),
                json={
                    "location_id": str(private_location),
                    "resource_id": str(private_resource),
                    "variant_id": str(world.catalog_a.base_variant_id),
                    "starts_at": datetime.fromisoformat(f"{customer_day()}T11:00:00")
                    .replace(tzinfo=ZoneInfo("America/Los_Angeles"))
                    .isoformat(),
                    "customer_name": "FAKE private browser guest",
                    "customer_email": "private-browser@example.test",
                    "customer_phone": "+15551234569",
                },
                timeout=10,
            )
            assert private.status_code == 201, private.text
            env["GBA_PRIVATE_BOOKING"] = private.json()["booking_id"]
        result = subprocess.run(  # noqa: S603 - fixed repository script and located npm executable
            [npm, "run", "test:management:location" if location_limited else "test:management"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - surface browser evidence under pytest -s
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        rows = owner_conn.execute(
            "select b.status, count(*) from gba.bookings b join gba.booking_customers c "
            "on c.tenant_id = b.tenant_id and c.booking_id = b.id "
            "where c.customer_name = %s group by b.status",
            ("FAKE Location Browser Guest" if location_limited else GUEST,),
        ).fetchall()
    assert dict(rows) == {"CANCELLED": 4 if location_limited else 3}, (
        "calendar create -> reschedule -> cancel and overview create -> cancel "
        "persist in PostgreSQL"
    )
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        count = owner_conn.execute("select count(*) from gba.bookings").fetchone()
    assert count is not None
    assert count[0] == 0
    if not location_limited:
        with owner_tenant_transaction(owner_conn, world.a.tenant_id):
            entities = owner_conn.execute(
                "select e.code, max(v.revision), count(*) "
                "from gba.legal_entities e join gba.legal_entity_versions v "
                "on v.tenant_id = e.tenant_id and v.legal_entity_id = e.id "
                "group by e.code order by e.code"
            ).fetchall()
        assert entities == [("FAKE_DESKTOP", 4, 4), ("FAKE_MOBILE", 4, 4)]
        with owner_tenant_transaction(owner_conn, world.a.tenant_id):
            departments = owner_conn.execute(
                "select d.code, v.revision, v.archived, v.location_id is not null, p.code "
                "from gba.departments d join lateral (select * from gba.department_versions "
                "where tenant_id = d.tenant_id and department_id = d.id "
                "order by revision desc limit 1) v on true "
                "left join gba.departments p "
                "on p.tenant_id = v.tenant_id and p.id = v.parent_department_id "
                "order by d.code"
            ).fetchall()
        # Lost response, rejected cycle/archive and stale edit add no versions.
        assert departments == [
            ("FAKE_DESKTOP_OPS", 3, True, False, None),
            ("FAKE_DESKTOP_TEAM", 2, True, True, "FAKE_DESKTOP_OPS"),
            ("FAKE_MOBILE_OPS", 3, True, False, None),
            ("FAKE_MOBILE_TEAM", 2, True, True, "FAKE_MOBILE_OPS"),
        ]
        with owner_tenant_transaction(owner_conn, world.b.tenant_id):
            assert owner_conn.execute("select count(*) from gba.legal_entities").fetchone() == (0,)
            assert owner_conn.execute("select count(*) from gba.departments").fetchone() == (0,)
    if location_limited:
        with owner_tenant_transaction(owner_conn, world.a.tenant_id):
            private_state = owner_conn.execute(
                "select status from gba.bookings where id = %s", (env["GBA_PRIVATE_BOOKING"],)
            ).fetchone()
        assert private_state == ("CONFIRMED",)


def test_real_delegation_browser_oidc_pkce_and_database(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    """The owner of a servicing business accepts a limited offer and books as a delegate."""
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: management browser verification requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out" / "auth" / "callback" / "index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    seed_other_branch(owner_conn, world.a)
    app_port, idp_port = free_port(), free_port()
    app_origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    servicer = seed_user(owner_conn, f"browser-servicer-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.b.tenant_id, user_id=servicer.user_id, role="owner")
    owner = seed_user(owner_conn, f"browser-owner-{uuid7()}", issuer=issuer)
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=owner.user_id, role="owner")
    idp = FakeIdp()
    provider, verifier = _provider(issuer, app_origin, idp, servicer)
    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(app_origin, issuer)
    env.update(
        GBA_DELEGATION_PARTNER=str(world.a.tenant_id),
        GBA_DELEGATION_SERVICER=str(world.b.tenant_id),
    )
    with live_server(provider, idp_port), live_server(app, app_port):
        offer = httpx.put(
            f"{app_origin}/v1/businesses/{world.a.tenant_id}/delegations/{uuid7()}",
            headers={
                **idp.bearer(owner.subject, email=owner.email, iss=issuer),
                "Idempotency-Key": str(uuid7()),
            },
            json={
                "servicer_business_id": str(world.b.tenant_id),
                "permissions": ["booking.read", "booking.write", "catalog.read", "staff.read"],
                "location_id": str(world.a.location_id),
                "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            },
            timeout=10,
        )
        assert offer.status_code == 200, offer.text
        result = subprocess.run(  # noqa: S603 - fixed repository script and located npm executable
            [npm, "run", "test:management:delegation"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - surface browser evidence under pytest -s
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        booked = owner_conn.execute(
            "select b.status, b.location_id from gba.bookings b "
            "join gba.booking_customers c on c.tenant_id = b.tenant_id and c.booking_id = b.id "
            "where c.customer_name = %s",
            ("FAKE Delegated Browser Guest",),
        ).fetchall()
        grants = owner_conn.execute(
            "select g.owner_tenant_id = %s, g.status, g.revoked_by_side, "
            "array(select m.user_id from gba.delegation_grant_members m "
            "where m.owner_tenant_id = g.owner_tenant_id and m.grant_id = g.id) "
            "from gba.delegation_grants g order by g.created_at",
            (world.a.tenant_id,),
        ).fetchall()
        access = owner_conn.execute(
            "select distinct actor from gba.audit_events where action = %s",
            ("delegation.access",),
        ).fetchall()
    # The delegate's booking stays in the owner's company and at the granted location.
    assert booked == [("CANCELLED", world.a.location_id)]
    assert grants == [
        (True, "revoked", "servicer", [servicer.user_id]),
        (False, "revoked", "owner", []),
    ]
    assert access == [(f"user:{servicer.user_id}",)]
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        assert owner_conn.execute("select count(*) from gba.bookings").fetchone() == (0,)
