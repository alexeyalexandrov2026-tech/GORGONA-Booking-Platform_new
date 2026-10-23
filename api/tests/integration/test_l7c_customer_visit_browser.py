"""L7c: a guest books a visit of several services on the customer site (package L; FAKE data).

Real Chromium against the exported web, FastAPI and a disposable PostgreSQL 18, desktop and mobile.
The colour (staged FAKE gel: 30 active, 60 processing, 20 finish) is followed by the FAKE style
(30 minutes) that only artist A1 serves; what the site booked is read back from the database here.
"""

import os
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from pydantic import SecretStr

from gorgona_booking.api.app import create_app
from gorgona_booking.config import Settings
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import seed_customer_setup
from tests.integration.live_server import free_port, live_server
from tests.integration.test_l2c_visits import make_visit
from tests.integration.test_l7b_visit_desk_browser import BRANCH_ZONE, zone_today

PROJECTS = ("desktop", "mobile")


def _spans(
    owner_conn: psycopg.Connection, tenant: UUID, booking: UUID
) -> set[tuple[UUID, datetime, datetime]]:
    rows = owner_conn.execute(
        "select resource_id, lower(during), upper(during) from gba.booking_allocations "
        "where tenant_id = %s and booking_id = %s",
        (tenant, booking),
    ).fetchall()
    return {(UUID(str(r[0])), r[1], r[2]) for r in rows}


def test_customer_visit_of_several_services_real_browser(
    world: BookingWorld, owner_conn: psycopg.Connection, test_database: ProvisionedDatabase
) -> None:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: L7c browser requires GBA_REQUIRE_BROWSER=1")
    web = Path(__file__).resolve().parents[3] / "web"
    assert (web / "out/book/index.html").exists(), "build web first"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None
    # Hours and services first, so the style added by make_visit is linked to A1 only.
    seed_customer_setup(owner_conn, world)
    visit = make_visit(owner_conn, world)
    tenant = world.a.tenant_id
    port = free_port()
    host = f"127.0.0.1:{port}"
    with owner_tenant_transaction(owner_conn, tenant):
        owner_conn.execute(
            "insert into gba.tenant_hosts (host, tenant_id) values (%s, %s)", (host, tenant)
        )
    # Two days ahead in the branch's own zone (never UTC), inside the 60-day window.
    day = (
        date.fromisoformat(zone_today(owner_conn, tenant, BRANCH_ZONE, world.a.location_id))
        + timedelta(days=2)
    ).isoformat()
    app = create_app(
        Settings(
            environment="test",
            database_url=SecretStr(test_database.app_dsn),
            customer_web_dir=web / "out",
        )
    )
    env = {k: v for k, v in os.environ.items() if "DSN" not in k and "DATABASE_URL" not in k}
    with live_server(app, port) as origin:
        env.update(GBA_BROWSER_URL=origin, GBA_BROWSER_DAY=day)
        result = subprocess.run(  # noqa: S603 - fixed repository script, located npm executable
            [npm, "run", "test:visit"],
            cwd=web,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout)  # noqa: T201 - surface real browser evidence under pytest -s

    with owner_tenant_transaction(owner_conn, tenant):
        rows = owner_conn.execute(
            "select b.id, b.status, b.starts_at, b.ends_at, b.total_cents, b.quote "
            "from gba.bookings b join gba.booking_customers c "
            "on c.tenant_id = b.tenant_id and c.booking_id = b.id "
            "where b.tenant_id = %s and c.customer_name = 'FAKE Visit Guest' order by b.id",
            (tenant,),
        ).fetchall()
        # One confirmed visit per project; the refused visit wrote nothing.
        assert len(rows) == len(PROJECTS), rows
        for booking, status, starts, ends, total, quote in rows:
            assert status == "CONFIRMED"
            snapshot: dict[str, Any] = quote
            assert snapshot["version"] == 2
            assert [(line["kind"], line["code"]) for line in snapshot["lines"]] == [
                ("variant", "FAKE_GEL"),
                ("variant", "FAKE_STYLE"),
            ]
            assert total == 6500 + 3000
            assert ends - starts == timedelta(minutes=140)
            # The specialist works 30, is free for the 60 of processing, then finishes 20 and
            # does the style 30 in one interval; the chair is held for the colour, the
            # processor for its processing only.
            minute = timedelta(minutes=1)
            assert _spans(owner_conn, tenant, UUID(str(booking))) == {
                (world.artist_a1, starts, starts + 30 * minute),
                (world.artist_a1, starts + 90 * minute, starts + 140 * minute),
                (visit["chair"], starts, starts + 110 * minute),
                (visit["equipment"], starts + 30 * minute, starts + 90 * minute),
            }
        refused = owner_conn.execute(
            "select count(*) from gba.bookings where tenant_id = %s and quote -> 'lines' @> "
            """'[{"code": "FAKE_BASE"}]'::jsonb""",
            (tenant,),
        ).fetchone()
        assert refused == (0,)
