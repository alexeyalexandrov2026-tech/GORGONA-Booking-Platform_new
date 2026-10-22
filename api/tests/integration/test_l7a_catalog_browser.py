"""L7a catalog screen: stages and materials of a service, equipment as a kind (FAKE data only).

Actual OIDC/PKCE, Chromium and PostgreSQL on desktop and mobile; the data the screen shows is read
back from the database here.
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
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp


def test_catalog_stages_materials_and_equipment_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: L7a browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/services/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    tenant = world.a.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {"owner": seed_user(owner_conn, "l7a-owner", issuer=issuer)}
    add_membership(owner_conn, tenant_id=tenant, user_id=people["owner"].user_id, role="owner")
    idp = FakeIdp()
    signed_in = _SignedIn(people)
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))
    variants = {"base": world.catalog_a.base_variant_id, "gel": world.catalog_a.gel_variant_id}

    @provider.post("/fixture/touch/{name}")
    async def touch(name: str) -> dict[str, str]:
        # Another change of the service while the dialog is open: its revision moves.
        with owner_tenant_transaction(owner_conn, tenant):
            owner_conn.execute(
                "update gba.service_variants set updated_at = clock_timestamp() where id = %s",
                (variants[name],),
            )
        return {"touched": name}

    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    owner = people["owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    root = f"{origin}/v1/businesses/{tenant}"
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

        def request(method: str, suffix: str, body: object = None) -> httpx.Response:
            result = httpx.request(
                method,
                f"{root}/{suffix}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=15,
            )
            assert result.status_code == 200, result.text
            return result

        request("PUT", "profile", {"expected_revision": 0, "industry_ids": [1]})
        draft = request(
            "PUT",
            "configuration/draft",
            {
                "expected_version": 0,
                "profile_revision": 1,
                "module_ids": ["booking_resources", "finance", "inventory"],
            },
        ).json()
        for step, revision in (("validate", 1), ("publish", 2)):
            request(
                "POST",
                f"configuration/versions/{draft['version']}/{step}",
                {"expected_revision": revision},
            )
        dye = uuid7()
        request(
            "PUT",
            f"inventory/items/{dye}",
            {
                "expected_revision": 0,
                "code": "FAKE-DYE",
                "name": "FAKE dye",
                "unit": "ml",
                "quantity_scale": 1,
            },
        )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:catalog"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s

    with owner_tenant_transaction(owner_conn, tenant):
        for variant in variants.values():
            stages = owner_conn.execute(
                "select kind, minutes, resources from gba.variant_stages "
                "where variant_id = %s order by position",
                (variant,),
            ).fetchall()
            assert stages == [
                ("active", 30, ["specialist", "chair"]),
                ("processing", 40, ["chair", "equipment"]),
                ("finish", 20, ["specialist", "chair"]),
            ]
            duration = owner_conn.execute(
                "select booking_duration_minutes from gba.service_variants where id = %s",
                (variant,),
            ).fetchone()
            assert duration == (90,)
            assert owner_conn.execute(
                "select item_id, quantity from gba.variant_materials where variant_id = %s",
                (variant,),
            ).fetchall() == [(dye, 25)]
        equipment = owner_conn.execute(
            "select count(*) from gba.resources where kind = 'equipment' "
            "and display_name like 'FAKE processor %%'"
        ).fetchone()
        assert equipment == (2,)
