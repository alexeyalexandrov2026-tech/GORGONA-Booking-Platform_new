"""PROPERTY-01 (5c/6 UI): maintenance, contractor portal and move-out in a real browser.

Actual OIDC/PKCE, Chromium (desktop and mobile), FastAPI and PostgreSQL 18.
Only a fixture stands in for package acceptance (the registry stays implemented).
"""

import json
import os
import shutil
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote
from uuid import uuid7
from zoneinfo import ZoneInfo

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
from tests.integration.test_agreements import draft
from tests.integration.test_counterparties import card
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp
from tests.unit.test_file_validation import pdf, png

PROJECTS = ("desktop", "mobile")
ENABLED = ["booking_resources", "counterparties", "documents", "property"]


def test_property_maintenance_and_move_out_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: property maintenance browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/property/index.html").exists(), "build web first"
    assert (web / "out/property/contractor/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "property",
        modules.MODULES_BY_ID["property"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )

    tenant_a, home = world.a.tenant_id, world.a.location_id
    tenant_b = world.b.tenant_id
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {
        "owner": seed_user(owner_conn, "prop-maint-owner", issuer=issuer),
        "branch": seed_user(owner_conn, "prop-maint-branch", issuer=issuer),
        "b_owner": seed_user(owner_conn, "prop-maint-b-owner", issuer=issuer),
        "contractor": seed_user(owner_conn, "prop-maint-contractor", issuer=issuer),
    }
    add_membership(owner_conn, tenant_id=tenant_a, user_id=people["owner"].user_id, role="owner")
    add_membership(
        owner_conn,
        tenant_id=tenant_a,
        user_id=people["branch"].user_id,
        role="manager",
        location_id=home,
    )
    add_membership(owner_conn, tenant_id=tenant_b, user_id=people["b_owner"].user_id, role="owner")
    add_membership(
        owner_conn, tenant_id=tenant_b, user_id=people["contractor"].user_id, role="manager"
    )

    idp = FakeIdp()
    signed_in = _SignedIn(people)
    provider, verifier = _provider(issuer, origin, idp, cast(FakeUser, signed_in))

    @provider.post("/fixture/user/{name}")
    async def switch(name: str) -> dict[str, str]:
        if name not in people:
            raise HTTPException(404, "Unknown FAKE person")
        signed_in.name = name
        return {"user": name}

    app = _management_app(test_database, verifier, issuer, web)
    env = _browser_env(origin, issuer)
    owner = people["owner"]
    b_owner = people["b_owner"]
    headers_a = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    headers_b = idp.bearer(b_owner.subject, email=b_owner.email, iss=issuer)
    business_a = f"/v1/businesses/{tenant_a}"
    business_b = f"/v1/businesses/{tenant_b}"

    with live_server(provider, idp_port), live_server(app, app_port):

        def call(
            method: str,
            path: str,
            body: object = None,
            *,
            auth: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            result = httpx.request(
                method,
                f"{origin}{path}",
                json=body,
                headers={**(auth or headers_a), "Idempotency-Key": str(uuid7())},
                timeout=15,
            )
            assert result.status_code == 200, result.text
            answer: dict[str, Any] = result.json()
            return answer

        call("PUT", f"{business_a}/profile", {"expected_revision": 0, "industry_ids": [22]})
        version = call(
            "PUT",
            f"{business_a}/configuration/draft",
            {"expected_version": 0, "profile_revision": 1, "module_ids": ENABLED},
        )["version"]
        for step, revision in (("validate", 1), ("publish", 2)):
            call(
                "POST",
                f"{business_a}/configuration/versions/{version}/{step}",
                {"expected_revision": revision},
            )

        tenant_party = str(uuid7())
        call(
            "PUT",
            f"{business_a}/counterparties/{tenant_party}",
            card(display_name="FAKE Tenant", roles=["partner"]),
        )
        contractor_party = str(uuid7())
        call(
            "PUT",
            f"{business_a}/counterparties/{contractor_party}",
            card(display_name="FAKE Plumbing Contractor", roles=["supplier"]),
        )

        grant_id = str(uuid7())
        call(
            "PUT",
            f"{business_a}/delegations/{grant_id}",
            {
                "schema_version": 1,
                "servicer_business_id": str(tenant_b),
                "permissions": ["property.contractor_work"],
                "location_id": str(home),
                "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            },
        )
        call(
            "POST",
            f"{business_b}/delegations/{grant_id}/accept",
            {
                "schema_version": 1,
                "expected_revision": 1,
                "delegate_user_ids": [str(people["contractor"].user_id)],
            },
            auth=headers_b,
        )

        def upload(name: str, data: bytes, media: str) -> str:
            file_id = str(uuid7())
            response = httpx.put(
                f"{origin}{business_a}/document-files/{file_id}",
                content=data,
                headers={
                    **headers_a,
                    "Idempotency-Key": str(uuid7()),
                    "Content-Type": media,
                    "X-File-Name": quote(name),
                },
                timeout=30,
            )
            assert response.status_code == 200, response.text
            return file_id

        def make_document(title: str, category: str, file_id: str) -> str:
            document_id = str(uuid7())
            call(
                "PUT",
                f"{business_a}/documents/{document_id}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "title": title,
                    "category": category,
                    "valid_from": None,
                    "valid_until": None,
                    "archived": False,
                    "file_id": file_id,
                },
            )
            return document_id

        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        projects: dict[str, dict[str, str]] = {}
        unit_ids: dict[str, str] = {}

        for project_name in PROJECTS:
            building_id = str(uuid7())
            call(
                "PUT",
                f"{business_a}/property/objects/{building_id}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(home),
                    "kind": "building",
                    "name": f"FAKE maint building {project_name}",
                    "parent_id": None,
                },
            )
            unit_id = str(uuid7())
            unit_name = f"FAKE maint unit {project_name}"
            call(
                "PUT",
                f"{business_a}/property/objects/{unit_id}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(home),
                    "kind": "unit",
                    "name": unit_name,
                    "parent_id": building_id,
                },
            )
            unit_ids[project_name] = unit_id

            lease_doc = make_document(
                f"FAKE maint lease {project_name}",
                "agreement",
                upload(f"FAKE Maint Lease {project_name}.pdf", pdf(), "application/pdf"),
            )
            agreement_id = str(uuid7())
            call(
                "PUT",
                f"{business_a}/agreements/{agreement_id}",
                draft(
                    tenant_party,
                    title=f"FAKE maint contract {project_name}",
                    number=f"FAKE-M-{project_name}",
                    summary="FAKE lease for move-out test",
                ),
            )
            call(
                "POST",
                f"{business_a}/agreements/{agreement_id}/agree",
                {
                    "schema_version": 1,
                    "expected_revision": 1,
                    "signed_on": "2026-10-01",
                    "attestation": "signed_outside_platform",
                    "document": {"document_id": lease_doc, "revision": 1},
                },
            )
            lease_id = str(uuid7())
            call(
                "PUT",
                f"{business_a}/property/leases/{lease_id}",
                {
                    "schema_version": 1,
                    "object_id": unit_id,
                    "agreement_id": agreement_id,
                    "agreement_revision": 2,
                },
            )
            in_report_title = f"FAKE move-in report {project_name}"
            in_report = make_document(
                in_report_title,
                "report",
                upload(f"FAKE MoveIn Report {project_name}.pdf", pdf(), "application/pdf"),
            )
            in_photo = make_document(
                f"FAKE move-in photo {project_name}",
                "other",
                upload(f"FAKE MoveIn Photo {project_name}.png", png(), "image/png"),
            )
            call(
                "PUT",
                f"{business_a}/property/leases/{lease_id}/move-in",
                {
                    "schema_version": 1,
                    "term_revision": 1,
                    "moved_in_on": today,
                    "report": {"document_id": in_report, "revision": 1},
                    "photos": [{"document_id": in_photo, "revision": 1}],
                },
            )

            out_report_title = f"FAKE move-out report {project_name}"
            make_document(
                out_report_title,
                "report",
                upload(f"FAKE MoveOut Report {project_name}.pdf", pdf(), "application/pdf"),
            )
            out_photo_title = f"FAKE move-out photo {project_name}"
            make_document(
                out_photo_title,
                "other",
                upload(f"FAKE MoveOut Photo {project_name}.png", png(), "image/png"),
            )

            unbound_id = str(uuid7())
            unbound_title = f"FAKE unbound request {project_name}"
            call(
                "PUT",
                f"{business_a}/property/maintenance/{unbound_id}",
                {
                    "schema_version": 1,
                    "object_id": unit_id,
                    "lease_id": None,
                    "category": "electrical",
                    "priority": "routine",
                    "title": unbound_title,
                    "description": "FAKE light fixture replacement",
                },
            )

            projects[project_name] = {
                "unit_name": unit_name,
                "move_in_report_title": in_report_title,
                "move_out_report_title": out_report_title,
                "move_out_photo_title": out_photo_title,
                "unbound_request_id": unbound_id,
                "unbound_request_title": unbound_title,
            }

        env["GBA_PROPERTY_MAINT_FIXTURE"] = json.dumps(
            {
                "business_id": str(tenant_a),
                "company_b_id": str(tenant_b),
                "grant_id": grant_id,
                "move_out_on": today,
                "projects": projects,
            }
        )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:property-maintenance"],
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

    with owner_tenant_transaction(owner_conn, tenant_a):
        for project_name in PROJECTS:
            unit_id = unit_ids[project_name]
            move_out = owner_conn.execute(
                "select m.moved_out_on, m.condition_summary, m.note, "
                "(select count(*) from gba.property_move_out_photos p "
                " where p.tenant_id = m.tenant_id and p.lease_id = m.lease_id) "
                "from gba.property_move_outs m "
                "join gba.property_leases l on l.tenant_id = m.tenant_id and l.id = m.lease_id "
                "where l.object_id = %s",
                (unit_id,),
            ).fetchone()
            assert move_out == (
                date.fromisoformat(today),
                "damage_noted",
                "FAKE scuffed wall near entry",
                1,
            ), project_name

            req = owner_conn.execute(
                "select id, state, revision, approved_limit_minor, currency "
                "from gba.property_maintenance_requests "
                "where object_id = %s and title = %s",
                (unit_id, f"FAKE sink leak {project_name}"),
            ).fetchone()
            assert req is not None, project_name
            req_id = req[0]
            assert tuple(req[1:]) == ("completed", 4, 35000, "USD"), project_name

            events = owner_conn.execute(
                "select revision, action from gba.property_maintenance_events "
                "where request_id = %s order by revision",
                (req_id,),
            ).fetchall()
            assert [tuple(row) for row in events] == [
                (2, "approve"),
                (3, "assign"),
                (4, "complete"),
            ], project_name

            link = owner_conn.execute(
                "select company_id from gba.property_maintenance_contractor_links "
                "where request_id = %s order by revision desc limit 1",
                (req_id,),
            ).fetchone()
            assert link == (tenant_b,), project_name

            updates = owner_conn.execute(
                "select number, kind, note from gba.property_maintenance_contractor_updates "
                "where request_id = %s order by number",
                (req_id,),
            ).fetchall()
            assert [tuple(row) for row in updates] == [
                (1, "in_progress", "FAKE shut off valve and replaced trap")
            ], project_name
