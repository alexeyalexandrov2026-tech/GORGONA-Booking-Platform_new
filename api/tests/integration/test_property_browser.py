"""PROPERTY-01: the internal catalog screen in a real browser (desktop and mobile; FAKE data only).

docs/plan/PACKAGE_PROPERTY01_SCREEN_DESIGN_2026-11-15.md. Actual OIDC/PKCE, Chromium and
PostgreSQL. Only a fixture stands in for the package acceptance (the registry stays implemented).
The business, its modules and parties are seeded through the routes; the browser builds the
catalog, keeps and clears parties and meets a stale revision as a company-wide owner, then reads as
a branch manager and as the manager of an empty branch. The database is read back.
"""

import json
import os
import shutil
import subprocess
from datetime import date, datetime
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
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_agreements import draft
from tests.integration.test_counterparties import card
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp
from tests.unit.test_file_validation import pdf, png

PROJECTS = ("desktop", "mobile")
ENABLED = ["booking_resources", "counterparties", "documents", "property"]


def test_property_catalog_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: property browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/property/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "property",
        modules.MODULES_BY_ID["property"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )
    tenant, home = world.a.tenant_id, world.a.location_id
    hidden_branch, _ = seed_other_branch(owner_conn, world.a)
    empty_branch, _ = seed_other_branch(owner_conn, world.a)
    assert len({home, hidden_branch, empty_branch}) == 3
    with owner_tenant_transaction(owner_conn, tenant):
        found = owner_conn.execute("select name from gba.locations where id = %s", (home,))
        branch_name = cast(tuple[str], found.fetchone())[0]
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people = {
        "owner": seed_user(owner_conn, "property-owner", issuer=issuer),
        "branch": seed_user(owner_conn, "property-branch", issuer=issuer),
        "empty": seed_user(owner_conn, "property-empty", issuer=issuer),
    }
    for name, role, location in (
        ("owner", "owner", None),
        ("branch", "manager", home),
        ("empty", "manager", empty_branch),
    ):
        add_membership(
            owner_conn,
            tenant_id=tenant,
            user_id=people[name].user_id,
            role=role,
            location_id=location,
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
    env = {**_browser_env(origin, issuer), "GBA_PROPERTY_BRANCH": branch_name}
    owner = people["owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    business = f"/v1/businesses/{tenant}"
    party: dict[str, str] = {}
    with live_server(provider, idp_port), live_server(app, app_port):

        def call(method: str, path: str, body: object = None) -> dict[str, Any]:
            result = httpx.request(
                method,
                f"{origin}{path}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=15,
            )
            assert result.status_code == 200, result.text
            answer: dict[str, Any] = result.json()
            return answer

        call("PUT", f"{business}/profile", {"expected_revision": 0, "industry_ids": [22]})
        version = call(
            "PUT",
            f"{business}/configuration/draft",
            {"expected_version": 0, "profile_revision": 1, "module_ids": ENABLED},
        )["version"]
        for step, revision in (("validate", 1), ("publish", 2)):
            call(
                "POST",
                f"{business}/configuration/versions/{version}/{step}",
                {"expected_revision": revision},
            )
        for role in ("Owner", "Manager"):
            party[role] = str(uuid7())
            call(
                "PUT",
                f"{business}/counterparties/{party[role]}",
                card(display_name=f"FAKE {role}", roles=["partner"]),
            )
        call(
            "PUT",
            f"{business}/property/objects/{uuid7()}",
            {
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(hidden_branch),
                "kind": "parcel",
                "name": "FAKE hidden parcel",
            },
        )

        tenant_party = str(uuid7())
        call(
            "PUT",
            f"{business}/counterparties/{tenant_party}",
            card(display_name="FAKE Tenant", roles=["partner"]),
        )
        other_party = str(uuid7())
        call(
            "PUT",
            f"{business}/counterparties/{other_party}",
            card(display_name="FAKE Other tenant", roles=["partner"]),
        )

        def upload(name: str, data: bytes, media: str) -> str:
            file_id = str(uuid7())
            response = httpx.put(
                f"{origin}{business}/document-files/{file_id}",
                content=data,
                headers={
                    **headers,
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
            saved = call(
                "PUT",
                f"{business}/documents/{document_id}",
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
            assert saved["document_id"] == document_id
            return document_id

        def make_contract(title: str, document_id: str, party: str, number: str) -> str:
            subject = str(uuid7())
            call(
                "PUT",
                f"{business}/agreements/{subject}",
                draft(party, title=title, number=number, summary="FAKE lease term"),
            )
            agreed = call(
                "POST",
                f"{business}/agreements/{subject}/agree",
                {
                    "schema_version": 1,
                    "expected_revision": 1,
                    "signed_on": "2026-10-01",
                    "attestation": "signed_outside_platform",
                    "document": {"document_id": document_id, "revision": 1},
                },
            )
            assert agreed["revision"] == 2, agreed
            return subject

        projects: dict[str, dict[str, str]] = {}
        for project_name in PROJECTS:
            lease_document = make_document(
                f"FAKE lease file {project_name}",
                "agreement",
                upload(f"FAKE Lease {project_name}.pdf", pdf(), "application/pdf"),
            )
            overlap_document = make_document(
                f"FAKE overlap file {project_name}",
                "agreement",
                upload(f"FAKE Overlap {project_name}.pdf", pdf(), "application/pdf"),
            )
            extension_document = make_document(
                f"FAKE extension file {project_name}",
                "agreement",
                upload(f"FAKE Extension {project_name}.pdf", pdf(), "application/pdf"),
            )
            make_document(
                f"FAKE condition report {project_name}",
                "report",
                upload(f"FAKE Report {project_name}.pdf", pdf(), "application/pdf"),
            )
            make_document(
                f"FAKE condition photo {project_name}",
                "other",
                upload(f"FAKE Photo {project_name}.png", png(), "image/png"),
            )
            projects[project_name] = {
                "lease_title": f"FAKE unit lease {project_name}",
                "agreement_id": make_contract(
                    f"FAKE unit lease {project_name}",
                    lease_document,
                    tenant_party,
                    f"FAKE-{project_name}-L",
                ),
                "overlap_title": f"FAKE overlapping lease {project_name}",
                "report_title": f"FAKE condition report {project_name}",
                "photo_title": f"FAKE condition photo {project_name}",
                "extension_document_id": extension_document,
            }
            make_contract(
                f"FAKE overlapping lease {project_name}",
                overlap_document,
                tenant_party,
                f"FAKE-{project_name}-O",
            )
        decoy_document = make_document(
            "FAKE decoy file",
            "agreement",
            upload("FAKE Decoy lease.pdf", pdf(), "application/pdf"),
        )
        decoy_agreement = make_contract(
            "FAKE decoy lease", decoy_document, other_party, "FAKE-DECOY"
        )
        building_id = str(uuid7())
        call(
            "PUT",
            f"{business}/property/objects/{building_id}",
            {
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(home),
                "kind": "building",
                "name": "FAKE other building",
                "parent_id": None,
            },
        )
        other_unit = str(uuid7())
        call(
            "PUT",
            f"{business}/property/objects/{other_unit}",
            {
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(home),
                "kind": "unit",
                "name": "FAKE other unit",
                "parent_id": building_id,
            },
        )
        call(
            "PUT",
            f"{business}/property/leases/{uuid7()}",
            {
                "schema_version": 1,
                "object_id": other_unit,
                "agreement_id": decoy_agreement,
                "agreement_revision": 2,
            },
        )
        move_in_day = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        env["GBA_PROPERTY_FIXTURE"] = json.dumps(
            {
                "business_id": str(tenant),
                "counterparty_id": tenant_party,
                "counterparty": "FAKE Tenant",
                "move_in_on": move_in_day,
                "release_on": move_in_day,
                "decoy_title": "FAKE decoy lease",
                "projects": projects,
            }
        )
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:property"],
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

    owner_id, manager_id = party["Owner"], party["Manager"]

    def latest(name: str) -> tuple[Any, ...]:
        row = owner_conn.execute(
            "select v.object_id, v.kind, v.location_id, v.parent_id from "
            "gba.property_revisions v where v.name = %s and v.revision = "
            "(select max(revision) from gba.property_revisions r "
            "where r.object_id = v.object_id)",
            (name,),
        ).fetchone()
        assert row is not None, name
        return tuple(row)

    with owner_tenant_transaction(owner_conn, tenant):
        for project in PROJECTS:
            parcel = latest(f"FAKE parcel {project}")
            building = latest(f"FAKE building {project}")
            unit = latest(f"FAKE unit {project}")
            assert parcel[1:] == ("parcel", home, None)
            assert building[1:] == ("building", home, parcel[0])
            assert unit[1:] == ("unit", home, building[0])
            revisions = owner_conn.execute(
                "select v.revision, v.name, p.owner_id::text, p.manager_id::text, p.recorded_by "
                "from gba.property_revisions v join gba.property_parties p "
                "using (tenant_id, object_id, revision) where v.object_id = %s "
                "order by v.revision",
                (unit[0],),
            ).fetchall()
            name = f"FAKE unit {project}"
            assert [tuple(r) for r in revisions] == [
                (1, name, owner_id, manager_id, owner.user_id),
                (2, f"{name} renamed", owner_id, manager_id, owner.user_id),
                (3, f"{name} renamed", owner_id, None, owner.user_id),
                (4, f"{name} final", owner_id, None, owner.user_id),
                (5, name, owner_id, None, owner.user_id),
            ], project
            listing = owner_conn.execute(
                "select headline, state, monthly_rent, currency "
                "from gba.property_listing_revisions where object_id = %s",
                (unit[0],),
            ).fetchall()
            assert listing == [(f"FAKE listing {project}", "published", 125050, "USD")]
            showings = owner_conn.execute(
                "select s.prospect_id, s.host_resource_id, count(a.id) "
                "from gba.property_showings s join gba.property_showing_cancellations c "
                "on (s.tenant_id, s.id) = (c.tenant_id, c.showing_id) "
                "join gba.resource_allocations a on a.tenant_id = s.tenant_id "
                "and a.source_kind = 'property_showing' and a.source_id = s.id "
                "where s.object_id = %s and a.state = 'released' "
                "group by s.prospect_id, s.host_resource_id",
                (unit[0],),
            ).fetchall()
            assert len(showings) == 1, project
            assert str(showings[0][0]) == owner_id
            assert showings[0][1] in (world.artist_a1, world.artist_a2)
            assert showings[0][2] == 2
            stale = owner_conn.execute(
                "select count(*) from gba.property_revisions where name = %s",
                (f"{name} stale",),
            ).fetchone()
            assert stale == (0,), project

            lease_row = owner_conn.execute(
                "select v.title, l.starts_on, l.ends_on, l.term_revision, l.occupied_through, "
                "m.moved_in_on, m.term_revision, "
                "(select count(*) from gba.property_move_in_photos p "
                "where p.tenant_id = l.tenant_id and p.lease_id = l.id) "
                "from gba.property_leases l "
                "join gba.agreement_versions v on v.tenant_id = l.tenant_id "
                "and v.agreement_id = l.agreement_id and v.revision = l.agreement_revision "
                "left join gba.property_move_ins m "
                "on m.tenant_id = l.tenant_id and m.lease_id = l.id "
                "where l.object_id = %s",
                (unit[0],),
            ).fetchone()
            assert lease_row == (
                f"FAKE unit lease {project}",
                date(2026, 1, 1),
                date(2026, 12, 31),
                3,
                date.fromisoformat(move_in_day),
                date.fromisoformat(move_in_day),
                2,
                1,
            ), project
            events = owner_conn.execute(
                "select e.revision, e.action from gba.property_lease_term_events e "
                "join gba.property_leases l on l.tenant_id = e.tenant_id and l.id = e.lease_id "
                "where l.object_id = %s order by e.revision",
                (unit[0],),
            ).fetchall()
            assert [tuple(row) for row in events] == [(2, "extend"), (3, "release")], project
            overlap = owner_conn.execute(
                "select count(*) from gba.property_leases l "
                "join gba.agreement_versions v on v.tenant_id = l.tenant_id "
                "and v.agreement_id = l.agreement_id and v.revision = l.agreement_revision "
                "where v.title = %s",
                (f"FAKE overlapping lease {project}",),
            ).fetchone()
            assert overlap == (0,), project
