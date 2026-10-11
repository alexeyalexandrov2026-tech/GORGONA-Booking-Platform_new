"""Actual OIDC/PKCE, workforce screens and PostgreSQL on desktop and mobile.

The workforce module is not accepted. The closed path runs against the registry as
it is; only this fixture then opens readiness for the enabled and switched-off paths.
Several FAKE people sign in through the same loopback provider, one at a time.
"""

import os
import shutil
import subprocess
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid7
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
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp

# name -> (display label, role, branch); the browser test names people by the label.
CAST = {
    "owner": ("i4-owner", "owner", "all"),
    "manager": ("i4-manager", "manager", "home"),
    "ada": ("i4-ada", "artist", "home"),
    "ben": ("i4-ben", "artist", "home"),
    "cy": ("i4-cy", "artist", "away"),
    "newdesktop": ("i4-new-desktop", "front_desk", "home"),
    "newmobile": ("i4-new-mobile", "front_desk", "home"),
}
ACTORS = {"desktop": "ada", "mobile": "ben"}


class _SignedIn:
    """The FAKE person the fixture provider authenticates next; the browser switches it."""

    def __init__(self, people: dict[str, FakeUser]) -> None:
        self.people = people
        self.name = "owner"

    @property
    def subject(self) -> str:
        return self.people[self.name].subject

    @property
    def email(self) -> str:
        return self.people[self.name].email


def test_i4_real_browser_closed_then_enabled_then_switched_off(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: I4 browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    for screen in ("schedule", "my-shifts", "timesheets"):
        assert (web / "out" / screen / "index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    seed_customer_setup(owner_conn, world)
    tenant, home = world.a.tenant_id, world.a.location_id
    away, _ = seed_other_branch(owner_conn, world.a)
    branches = {"all": None, "home": home, "away": away}
    app_port, idp_port = free_port(), free_port()
    origin, issuer = f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{idp_port}"
    people: dict[str, FakeUser] = {}
    for name, (label, role, branch) in CAST.items():
        people[name] = seed_user(owner_conn, label, issuer=issuer)
        add_membership(
            owner_conn,
            tenant_id=tenant,
            user_id=people[name].user_id,
            role=role,
            location_id=branches[branch],
        )
    # A second company for the owner: a saved reference must not follow them there.
    add_membership(
        owner_conn, tenant_id=world.b.tenant_id, user_id=people["owner"].user_id, role="manager"
    )
    with owner_tenant_transaction(owner_conn, tenant):
        memberships: dict[UUID, UUID] = dict(
            owner_conn.execute(
                "select user_id, id from gba.memberships where tenant_id=%s", (tenant,)
            ).fetchall()
        )
        zone = owner_conn.execute(
            "select timezone from gba.locations where id=%s", (home,)
        ).fetchone()
    assert zone is not None
    local = ZoneInfo(zone[0])
    today = datetime.now(local).date()
    first = today + timedelta(days=3)
    days = {"desktop": first, "mobile": first + timedelta(days=3)}

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
    env.update(
        GBA_I4_BUSINESS=str(tenant),
        GBA_I4_OTHER_BUSINESS=str(world.b.tenant_id),
        GBA_I4_LOCATION=str(home),
        GBA_I4_DAY=first.isoformat(),
        GBA_I4_PAST=(today - timedelta(days=30)).isoformat(),
    )
    owner = people["owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    root = f"{origin}/v1/businesses/{tenant}"
    with live_server(provider, idp_port), live_server(app, app_port):

        def request(method: str, suffix: str, body: dict[str, object]) -> httpx.Response:
            result = httpx.request(
                method,
                f"{root}/{suffix}",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid7())},
                timeout=15,
            )
            assert result.status_code == 200, result.text
            return result

        def publish(version: int, selected: list[str]) -> None:
            saved = request(
                "PUT",
                "configuration/draft",
                {"expected_version": version, "profile_revision": 1, "module_ids": selected},
            ).json()
            for step, revision in (("validate", 1), ("publish", 2)):
                request(
                    "POST",
                    f"configuration/versions/{saved['version']}/{step}",
                    {"expected_revision": revision},
                )

        def browser(phase: str) -> None:
            result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
                [npm, "run", "test:management:workforce"],
                cwd=web,
                env={**env, "GBA_I4_PHASE": phase},
                capture_output=True,
                text=True,
                timeout=1200,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s

        request("PUT", "profile", {"expected_revision": 0, "industry_ids": [1]})
        publish(0, ["booking_resources"])
        # The registry is used as it is: workforce is not accepted and stays closed.
        browser("closed")
        current = modules.MODULES_BY_ID["workforce"]
        monkeypatch.setitem(
            modules.MODULES_BY_ID,
            "workforce",
            current.model_copy(
                update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
            ),
        )
        publish(1, ["booking_resources", "workforce"])
        profiles: dict[str, str] = {}
        for name, place in (("owner", home), ("ada", home), ("ben", home), ("cy", away)):
            created = request(
                "PUT",
                f"workforce/staff/{uuid7()}",
                {
                    "schema_version": 1,
                    "membership_id": str(memberships[people[name].user_id]),
                    "location_id": str(place),
                },
            )
            profiles[name] = created.json()["profile_id"]
        # Shifts the employee later swaps, has declined and withdraws; the rest is made
        # through the screens.
        for project, start in days.items():
            for position, opens, closes in (("swap", 9, 12), ("extra", 13, 16), ("spare", 17, 19)):
                moment = datetime.combine(start + timedelta(days=1), time(opens), tzinfo=local)
                request(
                    "PUT",
                    f"workforce/shifts/{uuid7()}",
                    {
                        "schema_version": 1,
                        "expected_revision": 0,
                        "location_id": str(home),
                        "position": f"FAKE {project} {position}",
                        "starts_at": moment.isoformat(),
                        "ends_at": moment.replace(hour=closes).isoformat(),
                        "status": "published",
                        "staff_profile_id": profiles[ACTORS[project]],
                    },
                )
        browser("enabled")
        # The company turns the module off: history stays, an open record can be closed.
        publish(2, ["booking_resources"])
        browser("off")

    def count(query: str) -> int:
        row = owner_conn.execute(query).fetchone()
        assert row is not None
        return int(row[0])

    with owner_tenant_transaction(owner_conn, tenant):
        # Per project: the employee's seven-version record and a second one closed while
        # the module was off, and the owner's self-approved record.
        assert count("select count(*) from gba.time_entries") == 6
        assert count("select count(*) from gba.time_entry_revisions where action='clock_out'") == 6
        assert (
            count(
                "select count(*) from gba.time_entry_revisions "
                "where action='approve' and self_approved"
            )
            == 2
        )
        assert count("select count(*) from gba.time_entry_revisions where action='decline'") == 2
        states: dict[str, int] = dict(
            owner_conn.execute(
                "select e.status, count(*) from gba.shift_change_requests r join lateral "
                "(select status from gba.shift_change_events where tenant_id=r.tenant_id "
                "and request_id=r.id order by revision desc limit 1) e on true group by e.status"
            ).fetchall()
        )
        # A lost answer and its recovery left one handover, never two.
        assert states == {"approved": 6, "declined": 2, "withdrawn": 2}
        assert (
            count(
                "select count(*) from gba.audit_events where action='workforce.command_cancelled'"
            )
            == 2
        )
        assert count("select count(*) from gba.staff_profiles") == 6
        assert count("select count(*) from gba.work_skills") == 2
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        assert count("select count(*) from gba.time_entries") == 0
