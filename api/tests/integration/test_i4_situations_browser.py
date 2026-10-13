"""Workforce screens in the situations the acceptance record listed as untested.

A browser clock far from UTC, lists longer than one page, a server fault or an
unreadable answer to a command, a lost answer to the privacy setting, a clock change
inside a shift, more than twenty versions or requests and a company that never enabled
the module. Actual OIDC/PKCE, screens
and PostgreSQL on desktop and mobile; the module is enabled by a real publication.
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

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_i4_browser import _SignedIn
from tests.integration.test_management_browser import _browser_env, _management_app, _provider
from tests.support.fake_idp import FakeIdp

# name -> (display label, role, branch); the browser test names people by the label.
CAST = {
    "owner": ("i4s-owner", "owner", "all"),
    "ada": ("i4s-ada", "artist", "home"),
    "ben": ("i4s-ben", "artist", "home"),
}
ACTORS = {"desktop": "ada", "mobile": "ben"}
PAGED = 12
VERSIONS = 21
REQUESTS = 21


def _clock_change(zone: ZoneInfo, after: datetime) -> tuple[datetime, str, str]:
    """The next day the location's clocks change: its date, the kind and a bad time."""
    day = after.replace(hour=12, minute=0, second=0, microsecond=0)
    for _ in range(400):
        following = day + timedelta(days=1)
        before, later = day.utcoffset(), following.replace(fold=0).utcoffset()
        assert before is not None
        assert later is not None
        if before != later:
            # Clocks go back: an hour occurs twice. Clocks go forward: an hour is missing.
            return (following, "fold", "01:30") if later < before else (following, "gap", "02:30")
        day = following
    raise AssertionError(f"No clock change within 400 days in {zone.key}")


def test_i4_situations_in_a_real_browser(
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: I4 browser situations require GBA_REQUIRE_BROWSER=1")
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
    # The second company never selects the workforce module.
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
    now = datetime.now(local)
    today = now.date()
    # Four weeks of own shifts start here; the paged week and the fault day lie beyond.
    first = today + timedelta(days=30)
    paged = {"desktop": today + timedelta(days=100), "mobile": today + timedelta(days=140)}
    change, kind, bad_time = _clock_change(local, now)

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
        GBA_I4S_BUSINESS=str(tenant),
        GBA_I4S_OTHER_BUSINESS=str(world.b.tenant_id),
        GBA_I4S_LOCATION=str(home),
        GBA_I4S_ZONE=local.key,
        GBA_I4S_FIRST=first.isoformat(),
        GBA_I4S_PAGED_DESKTOP=paged["desktop"].isoformat(),
        GBA_I4S_PAGED_MOBILE=paged["mobile"].isoformat(),
        GBA_I4S_PAGED_COUNT=str(PAGED),
        GBA_I4S_FAULT_DAY=(today + timedelta(days=40)).isoformat(),
        GBA_I4S_CLOCK_DAY=change.date().isoformat(),
        GBA_I4S_CLOCK_KIND=kind,
        GBA_I4S_CLOCK_BAD_TIME=bad_time,
        GBA_I4S_VERSIONED_DAY=(today + timedelta(days=60)).isoformat(),
    )
    owner = people["owner"]
    headers = idp.bearer(owner.subject, email=owner.email, iss=issuer)
    root = f"{origin}/v1/businesses/{tenant}"
    with live_server(provider, idp_port), live_server(app, app_port):

        def request(
            method: str, suffix: str, body: dict[str, object], who: dict[str, str] = headers
        ) -> httpx.Response:
            result = httpx.request(
                method,
                f"{root}/{suffix}",
                json=body,
                headers={**who, "Idempotency-Key": str(uuid7())},
                timeout=15,
            )
            assert result.status_code == 200, result.text
            return result

        def shift(position: str, day: datetime, opens: time, closes: time, who: str | None) -> str:
            moment = datetime.combine(day, opens, tzinfo=local)
            created = uuid7()
            request(
                "PUT",
                f"workforce/shifts/{created}",
                {
                    "schema_version": 1,
                    "expected_revision": 0,
                    "location_id": str(home),
                    "position": position,
                    "starts_at": moment.isoformat(),
                    "ends_at": datetime.combine(day, closes, tzinfo=local).isoformat(),
                    "status": "published",
                    "staff_profile_id": who,
                },
            )
            return str(created)

        request("PUT", "profile", {"expected_revision": 0, "industry_ids": [1]})
        saved = request(
            "PUT",
            "configuration/draft",
            {
                "expected_version": 0,
                "profile_revision": 1,
                "module_ids": ["booking_resources", "workforce"],
            },
        ).json()
        for step, revision in (("validate", 1), ("publish", 2)):
            request(
                "POST",
                f"configuration/versions/{saved['version']}/{step}",
                {"expected_revision": revision},
            )
        profiles: dict[str, str] = {}
        for name in CAST:
            created = request(
                "PUT",
                f"workforce/staff/{uuid7()}",
                {
                    "schema_version": 1,
                    "membership_id": str(memberships[people[name].user_id]),
                    "location_id": str(home),
                },
            )
            profiles[name] = created.json()["profile_id"]
        for project, actor in ACTORS.items():
            tag, mine = f"FAKE {project}", profiles[actor]
            # Around the four weeks: the evening before, the first and last day, the day after.
            for label, offset, opens, closes in (
                ("before", -1, time(20), time(22)),
                ("first", 0, time(8), time(10)),
                ("last", 27, time(20), time(22)),
                ("after", 28, time(8), time(10)),
            ):
                at = datetime.combine(first + timedelta(days=offset), time(0))
                shift(f"{tag} {label}", at, opens, closes, mine)
            # More open shifts than one small page holds.
            for index in range(PAGED):
                at = datetime.combine(paged[project] + timedelta(days=1), time(0))
                shift(f"{tag} page {index + 1:02d}", at, time(6 + index), time(7 + index), None)
            # One draft corrected twenty times: twenty-one versions.
            versioned = uuid7()
            drafted = datetime.combine(today + timedelta(days=60), time(9), tzinfo=local)
            for revision in range(VERSIONS):
                request(
                    "PUT",
                    f"workforce/shifts/{versioned}",
                    {
                        "schema_version": 1,
                        "expected_revision": revision,
                        "location_id": str(home),
                        "position": f"{tag} versioned",
                        "starts_at": drafted.isoformat(),
                        "ends_at": (drafted + timedelta(minutes=60 + revision)).isoformat(),
                        "status": "draft",
                        "staff_profile_id": None,
                    },
                )
            # More requests than the screen reads shift details for, all for open shifts
            # far outside the four weeks shown.
            person = people[actor]
            bearer = idp.bearer(person.subject, email=person.email, iss=issuer)
            far = 200 if project == "desktop" else 300
            for index in range(REQUESTS):
                at = datetime.combine(today + timedelta(days=far + index), time(0))
                wanted = shift(f"{tag} wanted {index + 1:02d}", at, time(9), time(10), None)
                request(
                    "PUT",
                    f"workforce/changes/{uuid7()}",
                    {
                        "schema_version": 1,
                        "kind": "pickup",
                        "shift_id": wanted,
                        "expected_shift_revision": 1,
                        "target_profile_id": mine,
                        "other_shift_id": None,
                        "expected_other_shift_revision": None,
                    },
                    bearer,
                )

        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm
            [npm, "run", "test:management:workforce:situations"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)  # noqa: T201 - actual browser evidence in pytest -s

    def rows(query: str) -> list[tuple[object, ...]]:
        return owner_conn.execute(query).fetchall()

    with owner_tenant_transaction(owner_conn, tenant):
        # A lost answer and its recovery left one version per change, never two.
        assert rows(
            "select location_id,revision,colleague_shifts_visible "
            "from gba.work_location_setting_versions order by revision"
        ) == [(home, 1, False), (home, 2, True), (home, 3, False), (home, 4, True)]
        latest = (
            "select v.position, v.ends_at - v.starts_at from gba.work_shift_versions v "
            "where v.revision = (select max(revision) from gba.work_shift_versions "
            "where tenant_id=v.tenant_id and shift_id=v.shift_id) and v.position like %s "
            "order by v.position"
        )
        # A fault after the server recorded the command leaves one shift, a fault before none.
        faults = owner_conn.execute(latest, ("FAKE % fault %",)).fetchall()
        assert [position for position, _ in faults] == [
            "FAKE desktop fault 500",
            "FAKE desktop fault unreadable",
            "FAKE mobile fault 500",
            "FAKE mobile fault unreadable",
        ]
        # The night of the clock change is one hour longer or shorter than eight hours.
        night = timedelta(hours=9 if kind == "fold" else 7)
        assert owner_conn.execute(latest, ("FAKE % clocks",)).fetchall() == [
            ("FAKE desktop clocks", night),
            ("FAKE mobile clocks", night),
        ]
        # Twenty-one versions of one draft per project, and twenty-one requests each.
        assert rows(
            "select count(*) from gba.work_shift_versions where position like 'FAKE % versioned'"
        ) == [(2 * VERSIONS,)]
        assert rows("select count(*) from gba.shift_change_requests") == [(2 * REQUESTS,)]
        # A wall-clock time the change makes ambiguous or impossible saved nothing.
        assert owner_conn.execute(latest, ("FAKE % impossible",)).fetchall() == []
    with owner_tenant_transaction(owner_conn, world.b.tenant_id):
        for table in ("work_shifts", "staff_profiles", "time_entries", "shift_change_requests"):
            assert rows(f"select count(*) from gba.{table}") == [(0,)], table
