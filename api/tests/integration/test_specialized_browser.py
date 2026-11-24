"""SPECIAL-05: real-browser desktop + mobile E2E for unified /specialized/ 4-tab UI covering
hospitality_events, clinical_care (consent redaction), assets (critical safety lock), and
public_civic (four-eyes dual review), plus PostgreSQL 18 read-back.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import cast
from uuid import uuid7

import httpx
import psycopg
import pytest

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
STAGE8_MODULES = (
    "counterparties",
    "hospitality_events",
    "clinical_care",
    "assets",
    "public_civic",
)


def test_specialized_ui_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: specialized browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/specialized/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None

    for mod_id in ("hospitality_events", "clinical_care", "assets", "public_civic"):
        monkeypatch.setitem(
            modules.MODULES_BY_ID,
            mod_id,
            modules.MODULES_BY_ID[mod_id].model_copy(
                update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
            ),
        )

    ta = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    owner = seed_user(owner_conn, "spec-ui-owner", issuer=issuer)
    add_membership(owner_conn, tenant_id=ta, user_id=owner.user_id, role="owner")
    owner_conn.commit()

    idp = FakeIdp()
    signed_in = _SignedIn({"owner": owner})
    signed_in.name = "owner"
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))

    @provider.post("/fixture/user/{name}")
    async def switch(name: str) -> dict[str, str]:
        signed_in.name = name
        return {"user": name}

    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    h = idp.bearer(owner.subject, email=owner.email, iss=issuer)

    with live_server(provider, idp_port), live_server(app, app_port):
        with httpx.Client(base_url=origin, timeout=20.0) as http:
            biz = f"/v1/businesses/{ta}"
            assert (
                http.put(
                    f"{biz}/profile",
                    headers={**h, "Idempotency-Key": f"spec-prof-{uuid7()}"},
                    json={"expected_revision": 0, "industry_ids": [12, 13, 14, 28, 39]},
                ).status_code
                == 200
            )
            dr = http.put(
                f"{biz}/configuration/draft",
                headers={**h, "Idempotency-Key": f"spec-cfg-{uuid7()}"},
                json={
                    "expected_version": 0,
                    "profile_revision": 1,
                    "module_ids": list(STAGE8_MODULES),
                },
            )
            assert dr.status_code == 200, dr.text
            ver = dr.json()["version"]
            for step, rev in (("validate", 1), ("publish", 2)):
                assert (
                    http.post(
                        f"{biz}/configuration/versions/{ver}/{step}",
                        headers={**h, "Idempotency-Key": f"spec-{step}-{uuid7()}"},
                        json={"expected_revision": rev},
                    ).status_code
                    == 200
                )

            # Create counterparty for enrollments, care guardian & civic case applicant
            assert (
                http.put(
                    f"{biz}/counterparties/{uuid7()}",
                    headers={**h, "Idempotency-Key": f"spec-cp-{uuid7()}"},
                    json=card(
                        display_name="Specialized Participant Morgan",
                        roles=["customer"],
                    ),
                ).status_code
                == 200
            )

        cmd = [
            npm,
            "exec",
            "--",
            "playwright",
            "test",
            "tests/specialized.spec.ts",
            *(f"--project={project}" for project in PROJECTS),
        ]
        result = subprocess.run(  # noqa: S603
            cmd,
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    # Direct PostgreSQL 18 read-back for desktop & mobile UI operations
    with owner_tenant_transaction(owner_conn, ta) as tx:
        for tag in ("DESKTOP", "MOBILE"):
            prog = tx.execute(
                "select enrolled_count from gba.special_programs "
                "where tenant_id = %s and code = %s",
                (ta, f"YOGA_{tag}"),
            ).fetchone()
            assert prog == (1,)

            cons = tx.execute(
                "select status, revoked_at is not null from gba.care_consents "
                "where tenant_id = %s and granted_by_name = %s",
                (ta, f"Guardian {tag}"),
            ).fetchone()
            assert cons == ("revoked", True)

            asset = tx.execute(
                "select status from gba.managed_assets where tenant_id = %s and code = %s",
                (ta, f"SUB_{tag}"),
            ).fetchone()
            assert asset == ("out_of_service",)

            cs = tx.execute(
                "select status from gba.civic_cases where tenant_id = %s and case_number = %s",
                (ta, f"CASE_{tag}"),
            ).fetchone()
            assert cs == ("submitted",)
