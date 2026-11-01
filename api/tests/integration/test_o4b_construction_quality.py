"""O4b: inspections, defects and the punch list (package O, BUILD-01).

docs/plan/PACKAGE_O4B_DESIGN_2026-11-01.md (FAKE data only): inspections are insert-only checks
with a result and photos; defect and punch items are numbered records whose states move by
insert-only events (open, fixed, closed, void, reopened with a note) under the project lock; state,
overdue and the summary per phase and kind are derived.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_documents import Documents
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_o1_construction_estimates import (
    Construction,
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
)
from tests.integration.test_o3a_construction_budget import party
from tests.integration.test_o4a_construction_execution import (
    KIRITIMATI,
    LOCK,
    PAGO_PAGO,
    TWO_LINES,
    _photo,
    ago,
    signed_at,
    site,
    today,
)
from tests.support.fake_idp import FakeIdp
from tests.unit.test_file_validation import jpeg, pdf, png

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "site"]
TABLES = (
    "construction_inspections",
    "construction_inspection_photos",
    "construction_quality_items",
    "construction_quality_item_events",
    "construction_quality_item_photos",
)
NONE = (0, 0, 0, 0, 0)


async def inspect(
    c: Construction,
    project: UUID,
    on: str,
    result: str = "failed",
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    body = {
        "inspected_on": on,
        "kind": "internal",
        "phase": "Framing",
        "inspector": "FAKE Site Lead",
        "inspector_counterparty_id": None,
        "result": result,
        "notes": "FAKE nail spacing on wall 2",
        "photos": [],
        **fields,
    }
    return await c.send("POST", f"/projects/{project}/inspections", body, headers)


async def raise_item(
    c: Construction,
    project: UUID,
    title: str = "FAKE gap at wall 2",
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    body = {
        "kind": "defect",
        "title": title,
        "description": None,
        "phase": "Framing",
        "location": "FAKE wall 2, north side",
        "severity": "major",
        "raised_on": ago(2),
        "due_on": None,
        "responsible_id": None,
        "inspection": None,
        "photos": [],
        **fields,
    }
    return await c.send("POST", f"/projects/{project}/quality-items", body, headers)


async def move(
    c: Construction,
    project: UUID,
    number: int,
    seen: int,
    state: str,
    note: str | None = None,
    photos: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    body = {"expected_sequence": seen, "state": state, "note": note, "photos": photos or []}
    return await c.send("POST", f"/projects/{project}/quality-items/{number}/events", body, headers)


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    query = "select " + ", ".join(f"(select count(*) from gba.{table})" for table in TABLES)
    async with tenant_transaction(pool, tenant) as conn:
        found = await (await conn.execute(query)).fetchone()
    assert found is not None
    return tuple(int(n) for n in found)


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


def numbers(view: dict[str, Any]) -> list[int]:
    return [item["number"] for item in view["items"]]


# O4b-01 -----------------------------------------------------------------------------


async def test_inspections_are_recorded_and_checked(
    site: Construction, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    c = site
    bare = uuid7()
    assert (await c.project(bare)).status_code == 200
    early = await inspect(c, bare, ago(1))
    assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    project = await signed_at(c, TWO_LINES)
    docs = Documents(c.client, c.tenant, manager_a, idp)
    nails = await _photo(docs, png(), "image/png", "FAKE nails.png")
    permit = await _photo(docs, pdf(), "application/pdf", "FAKE permit.pdf")
    city = await party(c, "FAKE City Building Office", ["contractor"])
    first = await inspect(
        c,
        project,
        ago(2),
        kind="authority",
        inspector="FAKE J. Doe",
        inspector_counterparty_id=str(city),
        photos=[nails],
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert (
        body["number"],
        body["inspected_on"],
        body["kind"],
        body["phase"],
        body["inspector"],
        body["inspector_counterparty_id"],
        body["result"],
        body["notes"],
    ) == (
        1,
        ago(2),
        "authority",
        "Framing",
        "FAKE J. Doe",
        str(city),
        "failed",
        "FAKE nail spacing on wall 2",
    )
    assert [(p["document_id"], p["revision"], p["media_type"]) for p in body["photos"]] == [
        (nails["document_id"], 1, "image/png")
    ]
    second = await inspect(c, project, ago(1), "passed", kind="customer", phase=None, notes=None)
    assert second.status_code == 200, second.text
    assert (second.json()["number"], second.json()["phase"], second.json()["notes"]) == (
        2,
        None,
        None,
    )
    assert (await c.get(f"/projects/{project}/inspections/1")).json() == body
    listed = (await c.get(f"/projects/{project}/inspections")).json()
    assert [
        (i["number"], i["inspected_on"], i["result"], i["phase"], i["photo_count"], i["item_count"])
        for i in listed["items"]
    ] == [(1, ago(2), "failed", "Framing", 1, 0), (2, ago(1), "passed", None, 0, 0)]
    # Refused: a phase outside the budget, a PDF or unknown document, an unknown inspector company.
    for fields in (
        {"phase": "Roofing"},
        {"photos": [permit]},
        {"photos": [{"document_id": str(uuid7()), "revision": 1}]},
        {"inspector_counterparty_id": str(uuid7())},
    ):
        refused = await inspect(c, project, ago(1), **fields)
        assert error(refused) == (422, "INVALID_REFERENCE"), (fields, refused.text)
    ahead = await inspect(c, project, (today() + timedelta(days=2)).isoformat())
    assert error(ahead) == (422, "CONSTRUCTION_FUTURE_DATE"), ahead.text
    malformed: list[dict[str, Any]] = [
        {"inspected_on": "1999-12-31"},
        {"result": "maybe"},
        {"kind": "neighbour"},
    ]
    for fields in malformed:
        invalid = await inspect(c, project, ago(1), **fields)
        assert error(invalid) == (422, "INVALID_REQUEST"), (fields, invalid.text)
    missing = await c.get(f"/projects/{project}/inspections/9")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    assert await _counts(app_pool, c.tenant) == (2, 1, 0, 0, 0)


# O4b-02 -----------------------------------------------------------------------------


async def test_items_are_numbered_with_references_checked(
    site: Construction, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    c = site
    bare = uuid7()
    assert (await c.project(bare)).status_code == 200
    early = await raise_item(c, bare)
    assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    project = await signed_at(c, TWO_LINES)
    assert (await inspect(c, project, ago(3))).status_code == 200
    assert (await inspect(c, project, ago(3), "passed")).status_code == 200
    framer = await party(c, "FAKE Framing Crew", ["contractor"])
    docs = Documents(c.client, c.tenant, manager_a, idp)
    gap = await _photo(docs, jpeg(), "image/jpeg", "FAKE gap.jpg")
    permit = await _photo(docs, pdf(), "application/pdf", "FAKE permit.pdf")
    due = today().isoformat()
    first = await raise_item(
        c, project, responsible_id=str(framer), inspection=1, due_on=due, photos=[gap]
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert (
        body["number"],
        body["kind"],
        body["title"],
        body["description"],
        body["phase"],
        body["location"],
        body["severity"],
        body["raised_on"],
        body["due_on"],
        body["responsible_id"],
        body["inspection"],
        body["state"],
        body["sequence"],
        body["overdue"],
        body["events"],
    ) == (
        1,
        "defect",
        "FAKE gap at wall 2",
        None,
        "Framing",
        "FAKE wall 2, north side",
        "major",
        ago(2),
        due,
        str(framer),
        1,
        "open",
        0,
        False,
        [],
    )
    assert [(p["document_id"], p["media_type"]) for p in body["photos"]] == [
        (gap["document_id"], "image/jpeg")
    ]
    punch = await raise_item(
        c,
        project,
        "FAKE paint touch-up",
        kind="punch",
        phase="Finishes",
        severity="minor",
        location=None,
        description="FAKE hallway, two spots",
    )
    assert (punch.status_code, punch.json()["number"]) == (200, 2), punch.text
    whole = await raise_item(c, project, "FAKE site cleanup", kind="punch", phase=None)
    assert (whole.status_code, whole.json()["phase"]) == (200, None), whole.text
    # A passed inspection raises nothing; unknown references are refused.
    passed = await raise_item(c, project, inspection=2)
    assert error(passed) == (422, "CONSTRUCTION_INSPECTION_PASSED"), passed.text
    for fields in (
        {"inspection": 9},
        {"phase": "Roofing"},
        {"responsible_id": str(uuid7())},
        {"photos": [permit]},
    ):
        refused = await raise_item(c, project, **fields)
        assert error(refused) == (422, "INVALID_REFERENCE"), (fields, refused.text)
    ahead = await raise_item(c, project, raised_on=(today() + timedelta(days=2)).isoformat())
    assert error(ahead) == (422, "CONSTRUCTION_FUTURE_DATE"), ahead.text
    invalid_items: list[dict[str, Any]] = [
        {"due_on": ago(3)},
        {"kind": "snag"},
        {"severity": "huge"},
        {"title": "FAKE two\nlines"},
        {"raised_on": "1999-12-31"},
    ]
    for fields in invalid_items:
        invalid = await raise_item(c, project, **fields)
        assert error(invalid) == (422, "INVALID_REQUEST"), (fields, invalid.text)
    assert (await c.get(f"/projects/{project}/quality-items/1")).json() == body
    missing = await c.get(f"/projects/{project}/quality-items/9")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    found = (await c.get(f"/projects/{project}/inspections")).json()
    assert [(i["number"], i["item_count"]) for i in found["items"]] == [(1, 1), (2, 0)]
    assert await _counts(app_pool, c.tenant) == (2, 0, 3, 0, 1)


# O4b-03 -----------------------------------------------------------------------------


async def test_items_move_through_states_by_events(
    site: Construction, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    c = site
    project = await signed_at(c, TWO_LINES)
    for title in ("FAKE gap at wall 2", "FAKE duplicate of 1", "FAKE loose rail"):
        assert (await raise_item(c, project, title)).status_code == 200
    docs = Documents(c.client, c.tenant, manager_a, idp)
    after = await _photo(docs, png(), "image/png", "FAKE fixed.png")
    fixed = await move(c, project, 1, 0, "fixed", "FAKE re-nailed", [after])
    assert fixed.status_code == 200, fixed.text
    assert (fixed.json()["state"], fixed.json()["sequence"]) == ("fixed", 1)
    (event,) = fixed.json()["events"]
    assert (event["sequence"], event["state"], event["note"]) == (1, "fixed", "FAKE re-nailed")
    assert [p["document_id"] for p in event["photos"]] == [after["document_id"]]
    stale = await move(c, project, 1, 0, "closed")
    assert error(stale) == (409, "CONSTRUCTION_REVISION_CONFLICT"), stale.text
    for state in ("open", "void"):
        bare_note = await move(c, project, 2, 0, state)
        assert error(bare_note) == (422, "INVALID_REQUEST"), (state, bare_note.text)
    reopened = await move(c, project, 1, 1, "open", "FAKE still loose")
    assert (reopened.status_code, reopened.json()["state"]) == (200, "open"), reopened.text
    skipped = await move(c, project, 1, 2, "closed")
    assert error(skipped) == (409, "CONSTRUCTION_ITEM_TRANSITION"), skipped.text
    assert (await move(c, project, 1, 2, "fixed")).status_code == 200
    closed = await move(c, project, 1, 3, "closed", "FAKE verified by the site lead")
    assert (closed.status_code, closed.json()["state"]) == (200, "closed"), closed.text
    for state in ("open", "void", "fixed"):
        final = await move(c, project, 1, 4, state, "FAKE try again")
        assert error(final) == (409, "CONSTRUCTION_ITEM_TRANSITION"), (state, final.text)
    voided = await move(c, project, 2, 0, "void", "FAKE raised twice")
    assert (voided.status_code, voided.json()["state"]) == (200, "void"), voided.text
    gone = await move(c, project, 2, 1, "fixed")
    assert error(gone) == (409, "CONSTRUCTION_ITEM_TRANSITION"), gone.text
    same = await move(c, project, 3, 0, "open", "FAKE again")
    assert error(same) == (409, "CONSTRUCTION_ITEM_TRANSITION"), same.text
    unknown = await move(c, project, 9, 0, "fixed")
    assert error(unknown) == (404, "NOT_FOUND"), unknown.text
    history = (await c.get(f"/projects/{project}/quality-items/1")).json()
    assert [(e["sequence"], e["state"]) for e in history["events"]] == [
        (1, "fixed"),
        (2, "open"),
        (3, "fixed"),
        (4, "closed"),
    ]
    assert (history["state"], history["sequence"]) == ("closed", 4)
    assert await _counts(app_pool, c.tenant) == (0, 0, 3, 5, 1)


# O4b-04 -----------------------------------------------------------------------------


async def test_two_racing_moves_of_one_item_leave_one(
    site: Construction, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    c = site
    project = await signed_at(c, TWO_LINES)
    assert (await raise_item(c, project)).status_code == 200
    assert (await move(c, project, 1, 0, "fixed")).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        c.tenant,
        LOCK,
        project,
        [
            move(c, project, 1, 1, "closed"),
            move(c, project, 1, 1, "open", "FAKE loose again"),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_REVISION_CONFLICT"), lost.text
    (won,) = [a for a in answers if a.status_code == 200]
    view = (await c.get(f"/projects/{project}/quality-items/1")).json()
    assert (view["state"], view["sequence"]) == (won.json()["state"], 2)
    assert await _counts(app_pool, c.tenant) == (0, 0, 1, 2, 0)


# O4b-05 -----------------------------------------------------------------------------


async def test_views_derive_state_overdue_and_summary(site: Construction) -> None:
    c = site
    east = await signed_at(c, TWO_LINES, zone=KIRITIMATI)
    west = await signed_at(c, TWO_LINES, zone=PAGO_PAGO)
    day = today(PAGO_PAGO).isoformat()  # before today in Kiritimati, today in Pago Pago
    for project in (east, west):
        saved = await raise_item(c, project, raised_on=day, due_on=day)
        assert saved.status_code == 200, saved.text
    assert (await c.get(f"/projects/{east}/quality-items/1")).json()["overdue"] is True
    assert (await c.get(f"/projects/{west}/quality-items/1")).json()["overdue"] is False
    later = await raise_item(c, east, "FAKE crooked stud", raised_on=day, due_on=day)
    assert later.status_code == 200, later.text
    assert (await move(c, east, 2, 0, "fixed")).status_code == 200
    punch = await raise_item(c, east, "FAKE grout", kind="punch", phase="Finishes", raised_on=day)
    assert punch.status_code == 200, punch.text
    cleanup = await raise_item(c, east, "FAKE cleanup", kind="punch", phase=None, raised_on=day)
    assert cleanup.status_code == 200, cleanup.text
    assert (await raise_item(c, east, "FAKE twice", raised_on=day)).status_code == 200
    assert (await move(c, east, 5, 0, "void", "FAKE raised twice")).status_code == 200
    listed = (await c.get(f"/projects/{east}/quality-items")).json()
    assert [(i["number"], i["kind"], i["state"], i["overdue"]) for i in listed["items"]] == [
        (1, "defect", "open", True),
        (2, "defect", "fixed", False),
        (3, "punch", "open", False),
        (4, "punch", "open", False),
        (5, "defect", "void", False),
    ]
    assert [
        (s["phase"], s["kind"], s["open"], s["fixed"], s["closed"], s["void"], s["overdue"])
        for s in listed["summary"]
    ] == [
        ("Framing", "defect", 1, 1, 0, 1, 1),
        ("Finishes", "punch", 1, 0, 0, 0, 0),
        (None, "punch", 1, 0, 0, 0, 0),
    ]
    filtered = {
        "state=open": [1, 3, 4],
        "kind=punch": [3, 4],
        "phase=Framing": [1, 2, 5],
        "kind=defect&state=fixed": [2],
    }
    for query, expected in filtered.items():
        view = (await c.get(f"/projects/{east}/quality-items?{query}")).json()
        assert numbers(view) == expected, query
        assert view["summary"] == listed["summary"], query
    wrong = await c.get(f"/projects/{east}/quality-items?state=done")
    assert error(wrong) == (422, "INVALID_REQUEST"), wrong.text


# O4b-03 and O4b-06: the database itself ---------------------------------------------


async def test_sql_keeps_quality_rows_whole(
    site: Construction, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    c = site
    tenant = c.tenant
    project = await signed_at(c, TWO_LINES)
    docs = Documents(c.client, c.tenant, manager_a, idp)
    nails = await _photo(docs, png(), "image/png", "FAKE nails.png")
    assert (await inspect(c, project, ago(2), photos=[nails])).status_code == 200
    assert (await inspect(c, project, ago(2), "passed")).status_code == 200
    assert (await raise_item(c, project, inspection=1)).status_code == 200
    assert (await move(c, project, 1, 0, "fixed")).status_code == 200
    for table in TABLES:
        for statement in (
            f"update gba.{table} set tenant_id = tenant_id",
            f"delete from gba.{table}",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with tenant_transaction(app_pool, tenant) as conn:
                    await conn.execute(statement)
    inspected = (
        "insert into gba.construction_inspections (tenant_id, project_id, number, inspected_on, "
        "kind, phase, inspector, result, created_by) select tenant_id, project_id, {number}, "
        "{on}, kind, {phase}, inspector, result, created_by from gba.construction_inspections "
        "where project_id = %s and number = 1"
    )
    raised = (
        "insert into gba.construction_quality_items (tenant_id, project_id, number, kind, title, "
        "phase, severity, raised_on, due_on, inspection, created_by) select tenant_id, project_id, "
        "2, kind, title, {phase}, severity, {raised}, {due}, {inspection}, created_by "
        "from gba.construction_quality_items where project_id = %s and number = 1"
    )
    moved = (
        "insert into gba.construction_quality_item_events (tenant_id, project_id, item, sequence, "
        "state, note, created_by) select tenant_id, project_id, item, {sequence}, {state}, {note}, "
        "created_by from gba.construction_quality_item_events where project_id = %s and item = 1"
    )
    item = {"phase": "phase", "raised": "raised_on", "due": "due_on", "inspection": "inspection"}
    cases = {
        "construction_inspections_date_check": [
            (inspected.format(number=3, on="current_date + 2", phase="phase"), (project,))
        ],
        "construction_inspections_budget_check": [
            (inspected.format(number=3, on="inspected_on", phase="'Roofing'"), (project,))
        ],
        "construction_inspections_sequence_check": [
            (inspected.format(number=5, on="inspected_on", phase="phase"), (project,))
        ],
        "construction_inspection_photos_record_check": [
            (
                "insert into gba.construction_inspection_photos (tenant_id, project_id, number, "
                "position, document_id, document_revision) select tenant_id, project_id, number, "
                "2, document_id, document_revision from gba.construction_inspection_photos "
                "where project_id = %s",
                (project,),
            )
        ],
        "construction_quality_items_inspection_check": [
            (raised.format(**{**item, "inspection": "2"}), (project,))
        ],
        "construction_quality_items_budget_check": [
            (raised.format(**{**item, "phase": "'Roofing'"}), (project,))
        ],
        "construction_quality_items_date_check": [
            (raised.format(**{**item, "raised": "current_date + 2", "due": "null"}), (project,))
        ],
        "construction_quality_items_due_check": [
            (raised.format(**{**item, "due": "raised_on - 1"}), (project,))
        ],
        "construction_quality_item_events_sequence_check": [
            (moved.format(sequence=3, state="'closed'", note="null"), (project,))
        ],
        "construction_quality_item_events_transition_check": [
            (moved.format(sequence=2, state="'void'", note="'FAKE gone'"), (project,))
        ],
        "construction_quality_item_events_note_check": [
            (moved.format(sequence=2, state="'open'", note="null"), (project,))
        ],
        "construction_quality_item_photos_record_check": [
            (
                "insert into gba.construction_quality_item_photos (tenant_id, project_id, item, "
                "sequence, position, document_id, document_revision) select e.tenant_id, "
                "e.project_id, e.item, e.sequence, 1, p.document_id, p.document_revision "
                "from gba.construction_quality_item_events e join "
                "gba.construction_inspection_photos p on p.project_id = e.project_id "
                "where e.project_id = %s",
                (project,),
            )
        ],
    }
    for constraint, statements in cases.items():
        assert await _refused_by(app_pool, tenant, *statements) == constraint, constraint
    assert await _counts(app_pool, tenant) == (2, 1, 1, 1, 0)


# O4b-06 -----------------------------------------------------------------------------


async def test_without_the_module_quality_is_refused_and_scope_holds(
    site: Construction,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    c = site
    world: BookingWorld = c.world
    project = await signed_at(c)
    assert (await inspect(c, project, ago(1))).status_code == 200
    assert (await raise_item(c, project, inspection=1)).status_code == 200
    assert (await move(c, project, 1, 0, "fixed")).status_code == 200
    # Front desk writes nothing here.
    staff = c.member("front_desk", None)
    for refused in (
        await inspect(c, project, ago(1), headers=staff),
        await raise_item(c, project, headers=staff),
        await move(c, project, 1, 1, "closed", headers=staff),
    ):
        assert refused.status_code == 403, refused.text
    # A manager of another branch does not see the project's inspections or items.
    away, _ = seed_other_branch(c.owner_conn, world.a)
    elsewhere = c.member("manager", away)
    for path in ("inspections", "inspections/1", "quality-items", "quality-items/1"):
        hidden = await c.get(f"/projects/{project}/{path}", headers=elsewhere)
        assert error(hidden) == (404, "NOT_FOUND"), (path, hidden.text)
    hidden_move = await move(c, project, 1, 1, "closed", headers=elsewhere)
    assert error(hidden_move) == (404, "NOT_FOUND"), hidden_move.text
    # Another company sees nothing.
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await c.get(f"/projects/{project}/quality-items", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == NONE
    # Turned off: writes are refused and write nothing; reads continue.
    before = await _counts(app_pool, c.tenant)
    assert before == (1, 0, 1, 1, 0)
    await Config(c.client, idp).publish(
        manager_a, c.tenant, 1, ["booking_resources", "counterparties"]
    )
    for answer in (
        await inspect(c, project, ago(1)),
        await raise_item(c, project),
        await move(c, project, 1, 1, "closed"),
    ):
        assert error(answer) == (409, "MODULE_DISABLED"), answer.text
    assert await _counts(app_pool, c.tenant) == before
    for path in ("inspections", "inspections/1", "quality-items", "quality-items/1"):
        read = await c.get(f"/projects/{project}/{path}")
        assert read.status_code == 200, (path, read.text)
