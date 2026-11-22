"""ENTERPRISE-01 Slice 3: real-browser desktop + mobile E2E for /enterprise/ proving atomic
SSO employee deprovisioning (immediate 403 loss of access), consent-based consolidated group
reporting without ownership transfer, immediate revocation hiding, and PG18 read-back.
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
from fastapi import HTTPException

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp

PROJECTS = ("desktop", "mobile")
ENABLED = ["analytics"]


def test_enterprise_ui_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: enterprise browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/enterprise/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None

    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "analytics",
        modules.MODULES_BY_ID["analytics"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )

    ta, tb = world.a.tenant_id, world.b.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {
        "owner_a": seed_user(owner_conn, "ent-ui-owner-a", issuer=issuer),
        "emp_desktop": seed_user(owner_conn, "ent-ui-emp-desktop", issuer=issuer),
        "emp_mobile": seed_user(owner_conn, "ent-ui-emp-mobile", issuer=issuer),
        "owner_b": seed_user(owner_conn, "ent-ui-owner-b", issuer=issuer),
    }
    add_membership(owner_conn, tenant_id=ta, user_id=people["owner_a"].user_id, role="owner")
    add_membership(owner_conn, tenant_id=ta, user_id=people["emp_desktop"].user_id, role="manager")
    add_membership(owner_conn, tenant_id=ta, user_id=people["emp_mobile"].user_id, role="manager")
    add_membership(owner_conn, tenant_id=tb, user_id=people["owner_b"].user_id, role="owner")

    idp = FakeIdp()
    signed_in = _SignedIn(people)
    signed_in.name = "owner_a"
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))

    @provider.post("/fixture/user/{name}")
    async def switch(name: str) -> dict[str, str]:
        if name not in people:
            raise HTTPException(404, "Unknown FAKE person")
        signed_in.name = name
        return {"user": name}

    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    ha = idp.bearer(people["owner_a"].subject, email=people["owner_a"].email, iss=issuer)
    hb = idp.bearer(people["owner_b"].subject, email=people["owner_b"].email, iss=issuer)

    with live_server(provider, idp_port), live_server(app, app_port):
        with httpx.Client(base_url=origin, timeout=20.0) as http:
            # 1. Publish analytics module for both Tenant A (organizer) and Tenant B (member)
            for tid, hdrs in ((ta, ha), (tb, hb)):
                biz = f"/v1/businesses/{tid}"
                assert (
                    http.put(
                        f"{biz}/profile",
                        headers={**hdrs, "Idempotency-Key": f"ent-prof-{tid}"},
                        json={"expected_revision": 0, "industry_ids": [25]},
                    ).status_code
                    == 200
                )
                dr = http.put(
                    f"{biz}/configuration/draft",
                    headers={**hdrs, "Idempotency-Key": f"ent-cfg-{tid}"},
                    json={"expected_version": 0, "profile_revision": 1, "module_ids": ENABLED},
                )
                assert dr.status_code == 200, dr.text
                ver = dr.json()["version"]
                for step, rev in (("validate", 1), ("publish", 2)):
                    assert (
                        http.post(
                            f"{biz}/configuration/versions/{ver}/{step}",
                            headers={**hdrs, "Idempotency-Key": f"ent-{step}-{tid}"},
                            json={"expected_revision": rev},
                        ).status_code
                        == 200
                    )

            # 2. Create holding group HOLDING_UI + Tenant B legal entity
            group_id = uuid7()
            assert (
                http.put(
                    f"/v1/businesses/{ta}/groups/{group_id}",
                    headers={**ha, "Idempotency-Key": f"ent-grp-{uuid7()}"},
                    json={
                        "schema_version": 1,
                        "code": "HOLDING_UI",
                        "name": "Gorgona Enterprise Holding",
                    },
                ).status_code
                == 200
            )
            assert (
                http.put(
                    f"/v1/businesses/{ta}/groups/{group_id}/members/{tb}",
                    headers={**ha, "Idempotency-Key": f"ent-inv-{uuid7()}"},
                    json={"schema_version": 1},
                ).status_code
                == 200
            )
            assert (
                http.post(
                    f"/v1/businesses/{tb}/groups/{group_id}/accept",
                    headers={**hb, "Idempotency-Key": f"ent-acc-{uuid7()}"},
                    json={"schema_version": 1, "expected_revision": 1},
                ).status_code
                == 200
            )
            le_b = uuid7()
            assert (
                http.put(
                    f"/v1/businesses/{tb}/legal-entities/{le_b}",
                    headers={**hb, "Idempotency-Key": f"ent-leb-{uuid7()}"},
                    json={
                        "expected_revision": 0,
                        "code": "SUB_B_UI",
                        "legal_name": "Subsidiary B Holdings Inc",
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
            "tests/enterprise.spec.ts",
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

        # 3. Verify BOTH deprovisioned employees IMMEDIATELY receive 403 TENANT_ACCESS_DENIED
        with httpx.Client(base_url=origin, timeout=20.0) as http:
            for emp_key in ("emp_desktop", "emp_mobile"):
                emp = people[emp_key]
                he = idp.bearer(emp.subject, email=emp.email, iss=issuer)
                r = http.get(f"/v1/businesses/{ta}", headers=he)
                assert r.status_code == 403
                assert r.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    # 4. Direct PostgreSQL 18 read-back for both desktop & mobile runs
    with owner_tenant_transaction(owner_conn, ta) as tx:
        for tag in ("DESKTOP", "MOBILE"):
            lnk_row = tx.execute(
                "select status, deprovisioned_at is not null "
                "from gba.enterprise_directory_links "
                "where tenant_id = %s and employee_code = %s",
                (ta, f"EMP_{tag}"),
            ).fetchone()
            assert lnk_row == ("deprovisioned", True)

    with owner_tenant_transaction(owner_conn, tb) as tx:
        grt_row = tx.execute(
            "select status, revoked_at is not null from gba.enterprise_group_report_grants "
            "where tenant_id = %s and group_id = %s",
            (tb, group_id),
        ).fetchone()
        assert grt_row == ("revoked", True)
