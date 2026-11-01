"""O4a: the construction schedule, daily reports and completed quantities (package O, BUILD-01).

docs/plan/PACKAGE_O4A_DESIGN_2026-11-01.md (FAKE data only): the schedule is a versioned document of
budget phases with planned dates and acyclic dependencies; daily reports are kept per site date with
revisions; completed quantities are cumulative measurements never above the contract; progress is
derived, and a finished project's completed value is the current contract sum.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_counterparties import card
from tests.integration.test_documents import Documents, doc
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_o1_construction_estimates import (
    CHICAGO,
    Construction,
    accepted,
    client,
    error,
    idp,
    line,
    manager_a,
    manager_b,
)
from tests.integration.test_o2_construction_contract import accept, add, change, decide, remove
from tests.integration.test_o3a_construction_budget import party
from tests.support.fake_idp import FakeIdp
from tests.unit.test_file_validation import jpeg, pdf, png

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b"]
LOCK = "select 1 from gba.construction_projects where id = %s for update"
ENABLED = [
    "booking_resources",
    "counterparties",
    "finance",
    "finance_documents",
    "construction",
    "documents",
]
KIRITIMATI = "Pacific/Kiritimati"  # UTC+14
PAGO_PAGO = "Pacific/Pago_Pago"  # UTC-11: its date is always at least one day behind Kiritimati's
# 10 sheets at 25.00 (Framing) and 3.3333 m2 of tile at 18.02 (Finishes). Removing 1.1111 m2 leaves
# 6007 - 2002 = 4005 on the tile line as O2 sums it, while 2.2222 x 18.02 rounds to 4004.
TWO_LINES = [
    line(),
    line("FAKE tile", quantity="3.3333", cost=1000, price=1802, phase="Finishes", unit="m2"),
]
OUTLET = add("FAKE outlet", kind="labor", quantity="2", cost=700, price=1200, phase="Electrical")
TABLES = (
    "construction_schedule_versions",
    "construction_schedule_phases",
    "construction_schedule_dependencies",
    "construction_daily_reports",
    "construction_daily_report_crew",
    "construction_daily_report_photos",
    "construction_progress_measurements",
)
NONE = (0, 0, 0, 0, 0, 0, 0)


def today(zone: str = CHICAGO) -> date:
    return datetime.now(ZoneInfo(zone)).date()


def ago(days: int) -> str:
    """A site date in Chicago some days back, far from any midnight race."""
    return (today() - timedelta(days=days)).isoformat()


@pytest.fixture
async def site(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    accepted: None,
) -> Construction:
    """Construction with documents enabled, so daily reports may carry photos."""
    config = Config(client, idp)
    await config.profile(manager_a, world.a.tenant_id, 0, [19])
    await config.publish(manager_a, world.a.tenant_id, 0, ENABLED)
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    customer = uuid7()
    saved = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/counterparties/{customer}",
        json=card(display_name="FAKE Homeowner", roles=["customer"]),
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    return Construction(client, world, owner_conn, idp, headers, customer)


async def signed_at(
    c: Construction, lines: list[dict[str, Any]] | None = None, zone: str = CHICAGO
) -> UUID:
    """A project in a site time zone whose first estimate version became the contract."""
    project = uuid7()
    saved = await c.project(project, time_zone=zone)
    assert saved.status_code == 200, saved.text
    made = await c.estimate(project, lines or [line()])
    assert made.status_code == 200, made.text
    assert (await c.propose(project, 1)).status_code == 200
    contract = await accept(c, project, 1)
    assert contract.status_code == 200, contract.text
    return project


async def changed(c: Construction) -> UUID:
    """Two contract lines; change 1 approved (outlet added, 1.1111 m2 removed); 2 proposed."""
    project = await signed_at(c, TWO_LINES)
    first = await change(c, project, [OUTLET, remove(2, "1.1111")])
    assert first.status_code == 200, first.text
    assert (await decide(c, project, 1, "approved")).status_code == 200
    roof = add("FAKE skylight", quantity="1", cost=50000, price=70000, phase="Roofing")
    second = await change(c, project, [roof])
    assert second.status_code == 200, second.text
    return project


def phase(name: str, start: str, finish: str, *after: str) -> dict[str, Any]:
    return {
        "phase": name,
        "planned_start": start,
        "planned_finish": finish,
        "depends_on": list(after),
    }


async def plan(
    c: Construction,
    project: UUID,
    revision: int,
    phases: list[dict[str, Any]],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    body = {"expected_revision": revision, "note": "FAKE baseline", "phases": phases}
    return await c.send("PUT", f"/projects/{project}/schedule", body, headers)


async def report(
    c: Construction,
    project: UUID,
    on: str,
    revision: int = 0,
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    body = {
        "expected_revision": revision,
        "weather": "FAKE clear, 12 C",
        "notes": "FAKE framing walls 1-3",
        "crew": [],
        "photos": [],
        **fields,
    }
    return await c.send("PUT", f"/projects/{project}/daily-reports/{on}", body, headers)


async def measure(
    c: Construction,
    project: UUID,
    position: int,
    quantity: str,
    on: str,
    change_order: int | None = None,
    note: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    body = {
        "change_order": change_order,
        "position": position,
        "measured_on": on,
        "quantity_to_date": quantity,
        "note": note,
    }
    return await c.send("POST", f"/projects/{project}/progress", body, headers)


def scheduled(view: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (
            p["phase"],
            p["planned_start"],
            p["planned_finish"],
            p["depends_on"],
            p["conflict"],
            p["critical"],
        )
        for p in view["phases"]
    ]


def progressed(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["change_order"],
        item["position"],
        item["phase"],
        Decimal(item["quantity"]),
        Decimal(item["completed"]),
        Decimal(item["percent"]),
        item["contract_minor"],
        item["completed_minor"],
    )


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    query = "select " + ", ".join(f"(select count(*) from gba.{table})" for table in TABLES)
    async with tenant_transaction(pool, tenant) as conn:
        found = await (await conn.execute(query)).fetchone()
    assert found is not None
    return tuple(int(n) for n in found)


async def _photo(docs: Documents, data: bytes, media: str, name: str) -> dict[str, Any]:
    """A stage-1 document whose first version carries the file."""
    file_id = await docs.stored(data, media=media, name=name)
    subject = uuid7()
    saved = await docs.save(subject, doc(title=name, category="report", file_id=file_id))
    assert saved.status_code == 200, saved.text
    return {"document_id": str(subject), "revision": 1}


async def _together(
    pool: RuntimePool, tenant: UUID, statements: tuple[tuple[str, tuple[Any, ...]], ...]
) -> None:
    async with tenant_transaction(pool, tenant) as conn:
        for statement, params in statements:
            await conn.execute(statement, params)


async def _refused_by(
    pool: RuntimePool, tenant: UUID, *statements: tuple[str, tuple[Any, ...]]
) -> str:
    """The constraint the database names when it refuses these statements in one transaction."""
    with pytest.raises(psycopg.errors.CheckViolation) as refused:
        await _together(pool, tenant, statements)
    return str(refused.value.diag.constraint_name)


# O4a-01 -----------------------------------------------------------------------------


async def test_a_schedule_names_budget_phases_in_versions(
    site: Construction, app_pool: RuntimePool
) -> None:
    c = site
    bare = uuid7()
    assert (await c.project(bare)).status_code == 200
    framing = [phase("Framing", "2026-11-02", "2026-11-10")]
    for early in (await c.get(f"/projects/{bare}/schedule"), await plan(c, bare, 0, framing)):
        assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    nowhere = await c.get(f"/projects/{uuid7()}/schedule")
    assert error(nowhere) == (404, "NOT_FOUND"), nowhere.text
    project = await changed(c)
    empty = (await c.get(f"/projects/{project}/schedule")).json()
    assert (empty["revision"], empty["phases"], empty["unscheduled"]) == (
        0,
        [],
        ["Framing", "Finishes", "Electrical"],
    )
    first = await plan(c, project, 0, framing)
    assert first.status_code == 200, first.text
    assert (first.json()["revision"], first.json()["unscheduled"]) == (
        1,
        ["Finishes", "Electrical"],
    )
    # Only phases of the budget: the phase of a proposed change order is not one yet.
    roofing = await plan(c, project, 1, [phase("Roofing", "2026-11-02", "2026-11-03")])
    assert error(roofing) == (422, "INVALID_REFERENCE"), roofing.text
    for invalid in (
        [phase("Framing", "2026-11-10", "2026-11-02")],
        [phase("Framing", "1999-12-31", "2026-11-02")],
        [
            phase("Framing", "2026-11-02", "2026-11-10"),
            phase("Framing", "2026-11-11", "2026-11-12"),
        ],
        [phase("Framing", "2026-11-02", "2026-11-10", "Finishes")],
    ):
        answer = await plan(c, project, 1, invalid)
        assert error(answer) == (422, "INVALID_REQUEST"), answer.text
    stale = await plan(c, project, 0, [phase("Framing", "2026-11-03", "2026-11-10")])
    assert error(stale) == (409, "CONSTRUCTION_REVISION_CONFLICT"), stale.text
    second = await plan(
        c,
        project,
        1,
        [
            phase("Framing", "2026-11-03", "2026-11-11"),
            phase("Electrical", "2026-11-12", "2026-11-14", "Framing"),
        ],
    )
    assert (second.status_code, second.json()["revision"]) == (200, 2), second.text
    # The latest version counts; the earlier one stays readable.
    latest = (await c.get(f"/projects/{project}/schedule")).json()
    assert scheduled(latest) == [
        ("Framing", "2026-11-03", "2026-11-11", [], False, True),
        ("Electrical", "2026-11-12", "2026-11-14", ["Framing"], False, True),
    ]
    assert (latest["revision"], latest["planned_finish"]) == (2, "2026-11-14")
    earlier = (await c.get(f"/projects/{project}/schedule?revision=1")).json()
    assert scheduled(earlier) == [("Framing", "2026-11-02", "2026-11-10", [], False, True)]
    missing = await c.get(f"/projects/{project}/schedule?revision=3")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    assert await _counts(app_pool, c.tenant) == (2, 3, 1, 0, 0, 0, 0)


async def test_two_racing_schedule_revisions_leave_one(
    site: Construction, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    c = site
    project = await changed(c)
    first = await plan(c, project, 0, [phase("Framing", "2026-11-02", "2026-11-10")])
    assert first.status_code == 200, first.text
    answers = await race(
        app_pool,
        test_database,
        c.tenant,
        LOCK,
        project,
        [
            plan(c, project, 1, [phase("Framing", "2026-11-03", "2026-11-10")]),
            plan(c, project, 1, [phase("Framing", "2026-11-04", "2026-11-10")]),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_REVISION_CONFLICT")
    assert await _counts(app_pool, c.tenant) == (2, 2, 0, 0, 0, 0, 0)


# O4a-02 -----------------------------------------------------------------------------


async def _forged_dependencies(
    pool: RuntimePool, tenant: UUID, project: UUID, edges: list[tuple[str, str]]
) -> str:
    """Version 2 of the schedule written by SQL: version 1's phases and these dependencies."""
    copy = (
        "insert into gba.construction_schedule_versions (tenant_id, project_id, revision, note, "
        "created_by) select tenant_id, project_id, 2, note, created_by "
        "from gba.construction_schedule_versions where project_id = %s and revision = 1",
        (project,),
    )
    phases = (
        "insert into gba.construction_schedule_phases (tenant_id, project_id, revision, phase, "
        "planned_start, planned_finish) select tenant_id, project_id, 2, phase, planned_start, "
        "planned_finish from gba.construction_schedule_phases where project_id = %s "
        "and revision = 1",
        (project,),
    )
    links = [
        (
            "insert into gba.construction_schedule_dependencies (tenant_id, project_id, revision, "
            "phase, depends_on) select tenant_id, project_id, 2, %s, %s "
            "from gba.construction_schedule_versions where project_id = %s and revision = 2",
            (after, before, project),
        )
        for after, before in edges
    ]
    return await _refused_by(pool, tenant, copy, phases, *links)


async def test_dependencies_never_form_a_cycle_and_the_view_derives(
    site: Construction, app_pool: RuntimePool
) -> None:
    c = site
    project = await changed(c)
    selfish = await plan(c, project, 0, [phase("Framing", "2026-11-02", "2026-11-10", "Framing")])
    assert error(selfish) == (422, "INVALID_REQUEST"), selfish.text
    loop = [
        phase("Framing", "2026-11-02", "2026-11-10", "Finishes"),
        phase("Electrical", "2026-11-11", "2026-11-15", "Framing"),
        phase("Finishes", "2026-11-16", "2026-11-20", "Electrical"),
    ]
    cycle = await plan(c, project, 0, loop)
    assert error(cycle) == (422, "CONSTRUCTION_SCHEDULE_CYCLE"), cycle.text
    assert await _counts(app_pool, c.tenant) == NONE
    saved = await plan(
        c,
        project,
        0,
        [
            phase("Framing", "2026-11-02", "2026-11-10"),
            phase("Electrical", "2026-11-11", "2026-11-15", "Framing"),
            phase("Finishes", "2026-11-10", "2026-11-20", "Framing"),
        ],
    )
    assert saved.status_code == 200, saved.text
    view = saved.json()
    # Finishes starts on the day Framing should finish: a conflict, shown and not blocked. The
    # critical chain runs back from the latest finish (Finishes) through Framing.
    assert scheduled(view) == [
        ("Framing", "2026-11-02", "2026-11-10", [], False, True),
        ("Finishes", "2026-11-10", "2026-11-20", ["Framing"], True, True),
        ("Electrical", "2026-11-11", "2026-11-15", ["Framing"], False, False),
    ]
    assert (view["unscheduled"], view["planned_finish"]) == ([], "2026-11-20")
    # The database itself refuses a dependency on itself and the one that closes a cycle.
    itself = await _forged_dependencies(app_pool, c.tenant, project, [("Framing", "Framing")])
    assert itself == "construction_schedule_dependencies_self_check"
    closed = await _forged_dependencies(
        app_pool,
        c.tenant,
        project,
        [("Electrical", "Framing"), ("Finishes", "Electrical"), ("Framing", "Finishes")],
    )
    assert closed == "construction_schedule_dependencies_cycle_check"
    assert await _counts(app_pool, c.tenant) == (1, 3, 2, 0, 0, 0, 0)


# O4a-03 -----------------------------------------------------------------------------


async def test_a_daily_report_per_site_date_with_revisions(
    site: Construction, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    c = site
    bare = uuid7()
    assert (await c.project(bare)).status_code == 200
    early = await report(c, bare, ago(1))
    assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    project = await signed_at(c)
    docs = Documents(c.client, c.tenant, manager_a, idp)
    wall = await _photo(docs, png(), "image/png", "FAKE wall.png")
    beam = await _photo(docs, jpeg(), "image/jpeg", "FAKE beam.jpg")
    permit = await _photo(docs, pdf(), "application/pdf", "FAKE permit.pdf")
    crew = await party(c, "FAKE Framing Crew", ["contractor"])
    day = ago(2)
    first = await report(
        c,
        project,
        day,
        crew=[
            {"label": "FAKE carpenters", "headcount": 4, "counterparty_id": str(crew)},
            {"label": "FAKE labourers", "headcount": 2, "counterparty_id": None},
        ],
        photos=[wall],
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["report_date"], body["revision"], body["weather"], body["notes"]) == (
        day,
        1,
        "FAKE clear, 12 C",
        "FAKE framing walls 1-3",
    )
    assert [(m["label"], m["headcount"], m["counterparty_id"]) for m in body["crew"]] == [
        ("FAKE carpenters", 4, str(crew)),
        ("FAKE labourers", 2, None),
    ]
    assert [(p["document_id"], p["revision"]) for p in body["photos"]] == [(wall["document_id"], 1)]
    stale = await report(c, project, day, 0, notes="FAKE again")
    assert error(stale) == (409, "CONSTRUCTION_REVISION_CONFLICT"), stale.text
    second = await report(
        c,
        project,
        day,
        1,
        weather=None,
        notes="FAKE walls 1-4, rain after 3 pm",
        photos=[wall, beam],
    )
    assert (second.status_code, second.json()["revision"]) == (200, 2), second.text
    latest = (await c.get(f"/projects/{project}/daily-reports/{day}")).json()
    assert (latest["revision"], latest["weather"], latest["crew"], len(latest["photos"])) == (
        2,
        None,
        [],
        2,
    )
    assert (await c.get(f"/projects/{project}/daily-reports/{day}?revision=1")).json() == body
    later = await report(c, project, ago(1))
    assert later.status_code == 200, later.text
    listed = (await c.get(f"/projects/{project}/daily-reports")).json()
    assert [
        (i["report_date"], i["revision"], i["headcount"], i["photo_count"]) for i in listed["items"]
    ] == [(ago(1), 1, 0, 0), (day, 2, 0, 2)]
    # Refused: an empty report, a PDF, an unknown document or version as a photo, an unknown crew.
    empty = await report(c, project, ago(3), weather=None, notes=None)
    assert error(empty) == (422, "INVALID_REQUEST"), empty.text
    for photos in (
        [permit],
        [{"document_id": str(uuid7()), "revision": 1}],
        [{"document_id": wall["document_id"], "revision": 2}],
    ):
        refused = await report(c, project, ago(3), photos=photos)
        assert error(refused) == (422, "INVALID_REFERENCE"), refused.text
    ghost = {"label": "FAKE ghosts", "headcount": 1, "counterparty_id": str(uuid7())}
    stranger = await report(c, project, ago(3), crew=[ghost])
    assert error(stranger) == (422, "INVALID_REFERENCE"), stranger.text
    missing = await c.get(f"/projects/{project}/daily-reports/{ago(3)}")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    assert await _counts(app_pool, c.tenant) == (0, 0, 0, 3, 2, 3, 0)


async def test_a_report_date_is_not_after_today_on_the_site(site: Construction) -> None:
    c = site
    east = await signed_at(c, zone=KIRITIMATI)
    west = await signed_at(c, zone=PAGO_PAGO)
    day = today(KIRITIMATI).isoformat()
    accepted_east = await report(c, east, day)
    assert accepted_east.status_code == 200, accepted_east.text
    ahead = await report(c, west, day)
    assert error(ahead) == (422, "CONSTRUCTION_FUTURE_DATE"), ahead.text
    early = await report(c, west, "1999-12-31")
    assert error(early) == (422, "INVALID_REQUEST"), early.text


# O4a-04 -----------------------------------------------------------------------------


async def test_completed_quantities_are_cumulative_and_capped(
    site: Construction, app_pool: RuntimePool
) -> None:
    c = site
    bare = uuid7()
    assert (await c.project(bare)).status_code == 200
    for early in (
        await measure(c, bare, 1, "1", ago(1)),
        await c.get(f"/projects/{bare}/progress"),
    ):
        assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    project = await changed(c)
    first = await measure(c, project, 1, "4", ago(5))
    assert first.status_code == 200, first.text
    assert (first.json()["number"], Decimal(first.json()["quantity_to_date"])) == (1, Decimal(4))
    assert (await measure(c, project, 1, "6", ago(4))).status_code == 200
    above = await measure(c, project, 1, "10.0001", ago(4))
    assert error(above) == (409, "CONSTRUCTION_ABOVE_CONTRACT"), above.text
    lower = await measure(c, project, 1, "5", ago(3))
    assert error(lower) == (422, "CONSTRUCTION_CORRECTION_NOTE"), lower.text
    fixed = await measure(c, project, 1, "5", ago(3), note="FAKE recount of the sheets")
    assert fixed.status_code == 200, fixed.text
    earlier = await measure(c, project, 1, "7", ago(6))
    assert error(earlier) == (422, "CONSTRUCTION_MEASUREMENT_ORDER"), earlier.text
    same_day = await measure(c, project, 1, "7", ago(3))
    assert same_day.status_code == 200, same_day.text
    ahead = await measure(c, project, 1, "8", (today() + timedelta(days=2)).isoformat())
    assert error(ahead) == (422, "CONSTRUCTION_FUTURE_DATE"), ahead.text
    # The tile line holds 3.3333 - 1.1111 = 2.2222 m2 after the approved removal.
    tile_above = await measure(c, project, 2, "2.2223", ago(2))
    assert error(tile_above) == (409, "CONSTRUCTION_ABOVE_CONTRACT"), tile_above.text
    assert (await measure(c, project, 2, "2.2222", ago(2))).status_code == 200
    # Not lines of the budget: an unknown position and the added line of a proposed change.
    for refused in (
        await measure(c, project, 9, "1", ago(2)),
        await measure(c, project, 1, "1", ago(2), change_order=2),
    ):
        assert error(refused) == (422, "INVALID_REFERENCE"), refused.text
    # The approved outlet is measurable; the skylight once its change is approved.
    assert (await measure(c, project, 1, "2", ago(2), change_order=1)).status_code == 200
    assert (await decide(c, project, 2, "approved")).status_code == 200
    assert (await measure(c, project, 1, "1", ago(2), change_order=2)).status_code == 200
    listed = (await c.get(f"/projects/{project}/progress/measurements")).json()
    assert [
        (m["number"], m["change_order"], m["position"], Decimal(m["quantity_to_date"]), m["note"])
        for m in listed["items"]
    ] == [
        (1, None, 1, Decimal(4), None),
        (2, None, 1, Decimal(6), None),
        (3, None, 1, Decimal(5), "FAKE recount of the sheets"),
        (4, None, 1, Decimal(7), None),
        (5, None, 2, Decimal("2.2222"), None),
        (6, 1, 1, Decimal(2), None),
        (7, 2, 1, Decimal(1), None),
    ]
    assert await _counts(app_pool, c.tenant) == (0, 0, 0, 0, 0, 0, 7)


# O4a-05 -----------------------------------------------------------------------------


async def test_a_removal_never_goes_below_the_work_done(site: Construction) -> None:
    c = site
    project = await signed_at(c, TWO_LINES)
    assert (await measure(c, project, 2, "3", ago(1))).status_code == 200
    too_far = await change(c, project, [remove(2, "1.1111")])
    assert too_far.status_code == 200, too_far.text
    refused = await decide(c, project, 1, "approved")
    assert error(refused) == (409, "CONSTRUCTION_BELOW_COMPLETED"), refused.text
    still = (await c.get(f"/projects/{project}/change-orders/1")).json()
    assert still["state"] == "proposed"
    exact = await change(c, project, [remove(2, "0.3333")])
    assert exact.status_code == 200, exact.text
    assert (await decide(c, project, 2, "approved")).status_code == 200
    view = (await c.get(f"/projects/{project}/progress")).json()
    assert [
        (i["position"], Decimal(i["quantity"]), Decimal(i["completed"])) for i in view["lines"]
    ] == [(1, Decimal(10), Decimal(0)), (2, Decimal(3), Decimal(3))]


async def test_a_measurement_racing_a_removal_leaves_one_outcome(
    site: Construction, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    c = site
    project = await signed_at(c)  # one contract line: 10 sheets
    assert (await measure(c, project, 1, "4", ago(2))).status_code == 200
    assert (await change(c, project, [remove(1, "3")])).status_code == 200
    measured, approved = await race(
        app_pool,
        test_database,
        c.tenant,
        LOCK,
        project,
        [measure(c, project, 1, "9", ago(1)), decide(c, project, 1, "approved")],
    )
    statuses = sorted((measured.status_code, approved.status_code))
    assert statuses == [200, 409], (measured.text, approved.text)
    if measured.status_code == 200:
        assert error(approved) == (409, "CONSTRUCTION_BELOW_COMPLETED"), approved.text
        expected = (Decimal(10), Decimal(9))
    else:
        assert error(measured) == (409, "CONSTRUCTION_ABOVE_CONTRACT"), measured.text
        expected = (Decimal(7), Decimal(4))
    (item,) = (await c.get(f"/projects/{project}/progress")).json()["lines"]
    assert (Decimal(item["quantity"]), Decimal(item["completed"])) == expected


# O4a-06 -----------------------------------------------------------------------------


async def test_progress_per_line_phase_and_total(site: Construction) -> None:
    c = site
    project = await signed_at(c, TWO_LINES)
    first = await change(c, project, [OUTLET, remove(2, "1.1111")])
    assert first.status_code == 200, first.text
    assert (await decide(c, project, 1, "approved")).status_code == 200
    contract = (await c.get(f"/projects/{project}/contract")).json()
    assert contract["current_price_minor"] == 31405  # 25000 + (6007 - 2002) + 2400
    nothing = (await c.get(f"/projects/{project}/progress")).json()
    assert (nothing["contract_minor"], nothing["completed_minor"]) == (31405, 0)
    assert Decimal(nothing["percent"]) == 0
    assert (await measure(c, project, 1, "4", ago(3))).status_code == 200
    assert (await measure(c, project, 2, "1.1111", ago(3))).status_code == 200
    view = (await c.get(f"/projects/{project}/progress")).json()
    assert (view["project_id"], view["currency"]) == (str(project), "USD")
    assert [progressed(item) for item in view["lines"]] == [
        (None, 1, "Framing", Decimal(10), Decimal(4), Decimal("40.00"), 25000, 10000),
        (None, 2, "Finishes", Decimal("2.2222"), Decimal("1.1111"), Decimal("50.00"), 4005, 2002),
        (1, 1, "Electrical", Decimal(2), Decimal(0), Decimal("0.00"), 2400, 0),
    ]
    assert [
        (p["phase"], p["contract_minor"], p["completed_minor"], Decimal(p["percent"]))
        for p in view["phases"]
    ] == [
        ("Framing", 25000, 10000, Decimal("40.00")),
        ("Finishes", 4005, 2002, Decimal("49.98")),
        ("Electrical", 2400, 0, Decimal("0.00")),
    ]
    assert (view["contract_minor"], view["completed_minor"]) == (31405, 12002)
    assert Decimal(view["percent"]) == Decimal("38.21")
    # Finished, the tile line is worth its contract value 4005, not 2.2222 x 18.02 = 4004.
    for position, quantity, change_order in ((1, "10", None), (2, "2.2222", None), (1, "2", 1)):
        done = await measure(c, project, position, quantity, ago(2), change_order=change_order)
        assert done.status_code == 200, done.text
    finished = (await c.get(f"/projects/{project}/progress")).json()
    assert [(i["completed_minor"], Decimal(i["percent"])) for i in finished["lines"]] == [
        (25000, Decimal(100)),
        (4005, Decimal(100)),
        (2400, Decimal(100)),
    ]
    assert (finished["contract_minor"], finished["completed_minor"]) == (31405, 31405)
    assert Decimal(finished["percent"]) == 100
    # The schedule shows each phase's progress by value.
    saved = await plan(c, project, 0, [phase("Framing", "2026-11-02", "2026-11-10")])
    assert saved.status_code == 200, saved.text
    assert [(p["phase"], Decimal(p["percent"])) for p in saved.json()["phases"]] == [
        ("Framing", Decimal(100))
    ]


# O4a-07 -----------------------------------------------------------------------------


async def test_sql_keeps_execution_rows_whole(site: Construction, app_pool: RuntimePool) -> None:
    c = site
    tenant = c.tenant
    project = await signed_at(c, TWO_LINES)
    framing = phase("Framing", "2026-11-02", "2026-11-10")
    saved = await plan(c, project, 0, [framing, phase("Finishes", "2026-11-11", "2026-11-12")])
    assert saved.status_code == 200, saved.text
    gang = {"label": "FAKE crew", "headcount": 1, "counterparty_id": None}
    assert (await report(c, project, ago(1), crew=[gang])).status_code == 200
    assert (await measure(c, project, 2, "3", ago(1))).status_code == 200
    assert (await change(c, project, [remove(2, "1.1111")])).status_code == 200
    for table in TABLES:
        for statement in (
            f"update gba.{table} set tenant_id = tenant_id",
            f"delete from gba.{table}",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with tenant_transaction(app_pool, tenant) as conn:
                    await conn.execute(statement)
    measured = (
        "insert into gba.construction_progress_measurements (tenant_id, project_id, number, "
        "change_order, budget_position, measured_on, quantity_to_date, note, created_by) "
        "select tenant_id, project_id, 2, null, 1, {on}, {quantity}, null, created_by "
        "from gba.construction_progress_measurements where project_id = %s and number = 1"
    )
    cases = {
        "construction_progress_measurements_contract_check": [
            (measured.format(on="measured_on", quantity="10.0001"), (project,))
        ],
        "construction_progress_measurements_date_check": [
            (measured.format(on="current_date + 2", quantity="1"), (project,))
        ],
        "construction_daily_reports_date_check": [
            (
                "insert into gba.construction_daily_reports (tenant_id, project_id, report_date, "
                "revision, weather, notes, created_by) select tenant_id, project_id, "
                "current_date + 2, 1, weather, notes, created_by "
                "from gba.construction_daily_reports where project_id = %s",
                (project,),
            )
        ],
        "construction_daily_report_crew_report_check": [
            (
                "insert into gba.construction_daily_report_crew (tenant_id, project_id, "
                "report_date, revision, position, label, headcount) select tenant_id, project_id, "
                "report_date, revision, 2, 'FAKE late', 1 from gba.construction_daily_reports "
                "where project_id = %s",
                (project,),
            )
        ],
        "construction_schedule_phases_budget_check": [
            (
                "insert into gba.construction_schedule_versions (tenant_id, project_id, revision, "
                "note, created_by) select tenant_id, project_id, 2, note, created_by "
                "from gba.construction_schedule_versions where project_id = %s",
                (project,),
            ),
            (
                "insert into gba.construction_schedule_phases (tenant_id, project_id, revision, "
                "phase, planned_start, planned_finish) select tenant_id, project_id, 2, "
                "'Roofing', planned_start, planned_finish from gba.construction_schedule_phases "
                "where project_id = %s and phase = 'Framing'",
                (project,),
            ),
        ],
        "construction_schedule_phases_version_check": [
            (
                "insert into gba.construction_schedule_phases (tenant_id, project_id, revision, "
                "phase, planned_start, planned_finish) select tenant_id, project_id, 1, "
                "'Framing', planned_start, planned_finish from gba.construction_schedule_phases "
                "where project_id = %s and phase = 'Finishes'",
                (project,),
            )
        ],
        "construction_change_order_decisions_completed_check": [
            (
                "insert into gba.construction_change_order_decisions (tenant_id, project_id, "
                "number, decision, source, decided_by) select tenant_id, project_id, number, "
                "'approved', 'paper', created_by from gba.construction_change_orders "
                "where project_id = %s and number = 1",
                (project,),
            )
        ],
    }
    for constraint, statements in cases.items():
        assert await _refused_by(app_pool, tenant, *statements) == constraint
    assert await _counts(app_pool, tenant) == (1, 2, 0, 1, 1, 0, 1)


async def test_without_the_module_execution_is_refused_and_scope_holds(
    site: Construction,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    c = site
    world: BookingWorld = c.world
    project = await signed_at(c)
    framing = [phase("Framing", "2026-11-02", "2026-11-10")]
    assert (await plan(c, project, 0, framing)).status_code == 200
    assert (await report(c, project, ago(1))).status_code == 200
    assert (await measure(c, project, 1, "2", ago(1))).status_code == 200
    # Front desk writes nothing here.
    staff = c.member("front_desk", None)
    for refused in (
        await plan(c, project, 1, framing, headers=staff),
        await report(c, project, ago(1), 1, headers=staff),
        await measure(c, project, 1, "3", ago(1), headers=staff),
    ):
        assert refused.status_code == 403, refused.text
    # A manager of another branch does not see the project's execution.
    away, _ = seed_other_branch(c.owner_conn, world.a)
    elsewhere = c.member("manager", away)
    for path in (
        "schedule",
        "daily-reports",
        f"daily-reports/{ago(1)}",
        "progress",
        "progress/measurements",
    ):
        hidden = await c.get(f"/projects/{project}/{path}", headers=elsewhere)
        assert error(hidden) == (404, "NOT_FOUND"), (path, hidden.text)
    # Another company sees nothing.
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await c.get(f"/projects/{project}/progress", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == NONE
    # Turned off: writes are refused and write nothing; reads continue.
    before = await _counts(app_pool, c.tenant)
    assert before == (1, 1, 0, 1, 0, 0, 1)
    await Config(c.client, idp).publish(
        manager_a, c.tenant, 1, ["booking_resources", "counterparties"]
    )
    for answer in (
        await plan(c, project, 1, framing),
        await report(c, project, ago(1), 1),
        await measure(c, project, 1, "3", ago(1)),
    ):
        assert error(answer) == (409, "MODULE_DISABLED"), answer.text
    assert await _counts(app_pool, c.tenant) == before
    for path in ("schedule", "daily-reports", "progress", "progress/measurements"):
        read = await c.get(f"/projects/{project}/{path}")
        assert read.status_code == 200, (path, read.text)
