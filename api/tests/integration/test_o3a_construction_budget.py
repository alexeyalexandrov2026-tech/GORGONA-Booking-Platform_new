"""O3a: the construction budget and commitments (package O, BUILD-01; FAKE data only).

docs/plan/PACKAGE_O3A_DESIGN_2026-10-31.md: the budget is the contract's cost side per line and
phase, derived; commitments are versioned, insert-only, against budget lines; overruns are shown.
"""

from decimal import Decimal
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
from tests.integration.test_counterparties import card
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_o1_construction_estimates import (
    Construction,
    accepted,
    client,
    construction,
    error,
    idp,
    line,
    manager_a,
    manager_b,
)
from tests.integration.test_o2_construction_contract import add, change, decide, remove, signed
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "construction", "idp", "manager_a", "manager_b"]
LOCK = "select 1 from gba.construction_projects where id = %s for update"
# 10 sheets at 15.00 cost (Framing) and 3.3333 m2 of tile at 10.00 cost (Finishes): 150.00 + 33.33.
TWO_LINES = [
    line(),
    line("FAKE tile", quantity="3.3333", cost=1000, price=1800, phase="Finishes", unit="m2"),
]


def budgeted(change_order: int | None, position: int, amount: int) -> dict[str, Any]:
    return {"change_order": change_order, "position": position, "amount_minor": amount}


async def party(c: Construction, name: str, roles: list[str]) -> UUID:
    counterparty = uuid7()
    saved = await c.client.put(
        f"/v1/businesses/{c.tenant}/counterparties/{counterparty}",
        json=card(display_name=name, roles=roles),
        headers={**c.headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    return counterparty


async def commit(
    c: Construction,
    project: UUID,
    kind: str,
    counterparty: UUID,
    lines: list[dict[str, Any]],
    headers: dict[str, str] | None = None,
    key: str | None = None,
    **changes: Any,
) -> httpx.Response:
    body = {
        "kind": kind,
        "counterparty_id": str(counterparty),
        "title": "FAKE framing labour",
        "reference": "FAKE-SC-1",
        "lines": lines,
        **changes,
    }
    return await c.send("POST", f"/projects/{project}/commitments", body, headers, key)


async def revise(
    c: Construction,
    project: UUID,
    number: int,
    revision: int,
    lines: list[dict[str, Any]],
    state: str = "open",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    body = {
        "expected_revision": revision,
        "state": state,
        "title": "FAKE framing labour, revised",
        "note": "FAKE scope agreed on site",
        "lines": lines,
    }
    return await c.send("PUT", f"/projects/{project}/commitments/{number}", body, headers)


def row(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["change_order"],
        item["position"],
        item["phase"],
        Decimal(item["quantity"]),
        item["budget_minor"],
        item["committed_minor"],
        item["uncommitted_minor"],
        item["over_committed"],
    )


def phases(view: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (p["phase"], p["budget_minor"], p["committed_minor"], p["uncommitted_minor"])
        for p in view["phases"]
    ]


def totals(view: dict[str, Any]) -> tuple[int, int, int]:
    return view["budget_minor"], view["committed_minor"], view["uncommitted_minor"]


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        found = await (
            await conn.execute(
                "select (select count(*) from gba.construction_commitments), "
                "(select count(*) from gba.construction_commitment_versions), "
                "(select count(*) from gba.construction_commitment_lines)"
            )
        ).fetchone()
    assert found is not None
    return tuple(int(n) for n in found)


async def _changed(c: Construction) -> UUID:
    """Two contract lines; 1 approved (an outlet added, 1.1111 m2 of tile removed); 2 proposed."""
    project = await signed(c, TWO_LINES)
    outlet = add(
        "FAKE outlet", kind="labor", quantity="2", cost=700, price=1200, phase="Electrical"
    )
    first = await change(c, project, [outlet, remove(2, "1.1111")])
    assert first.status_code == 200, first.text
    assert (await decide(c, project, 1, "approved")).status_code == 200
    skylight = await change(c, project, [add("FAKE skylight", quantity="1", cost=50000)])
    assert skylight.status_code == 200, skylight.text
    return project


# O3a-01, O3a-02 --------------------------------------------------------------------


async def test_the_budget_is_the_contract_cost_after_approved_changes(
    construction: Construction,
) -> None:
    c = construction
    bare = uuid7()
    assert (await c.project(bare)).status_code == 200
    early = await c.get(f"/projects/{bare}/budget")
    assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    nowhere = await c.get(f"/projects/{uuid7()}/budget")
    assert error(nowhere) == (404, "NOT_FOUND"), nowhere.text
    project = await _changed(c)
    assert (await change(c, project, [remove(1, "10")])).status_code == 200
    assert (await decide(c, project, 3, "rejected")).status_code == 200
    read = await c.get(f"/projects/{project}/budget")
    assert read.status_code == 200, read.text
    view = read.json()
    assert (view["project_id"], view["currency"]) == (str(project), "USD")
    # Tile: 3.3333 - 1.1111 = 2.2222 m2; 3333 - 1111 = 2222. The proposed skylight and the
    # rejected removal of the sheets do not count.
    assert [row(item) for item in view["lines"]] == [
        (None, 1, "Framing", Decimal(10), 15000, 0, 15000, False),
        (None, 2, "Finishes", Decimal("2.2222"), 2222, 0, 2222, False),
        (1, 1, "Electrical", Decimal(2), 1400, 0, 1400, False),
    ]
    first = view["lines"][0]
    assert (first["kind"], first["description"], first["unit"], first["unit_cost_minor"]) == (
        "material",
        "FAKE drywall",
        "sheet",
        1500,
    )
    assert phases(view) == [
        ("Framing", 15000, 0, 15000),
        ("Finishes", 2222, 0, 2222),
        ("Electrical", 1400, 0, 1400),
    ]
    contract = (await c.get(f"/projects/{project}/contract")).json()
    assert totals(view) == (18622, 0, 18622)
    assert view["budget_minor"] == contract["current_cost_minor"]
    # All sheets removed by an approved change: the line stays, with nothing left in it.
    assert (await change(c, project, [remove(1, "10")])).status_code == 200
    assert (await decide(c, project, 4, "approved")).status_code == 200
    after = (await c.get(f"/projects/{project}/budget")).json()
    assert row(after["lines"][0]) == (None, 1, "Framing", Decimal(0), 0, 0, 0, False)
    contract = (await c.get(f"/projects/{project}/contract")).json()
    assert after["budget_minor"] == contract["current_cost_minor"] == 3622


# O3a-03 ----------------------------------------------------------------------------


async def test_a_commitment_needs_a_contract_and_a_party_of_its_kind(
    construction: Construction, app_pool: RuntimePool
) -> None:
    c = construction
    crew = await party(c, "FAKE Framing Crew", ["contractor"])
    yard = await party(c, "FAKE Lumber Yard", ["supplier"])
    bare = uuid7()
    assert (await c.project(bare)).status_code == 200
    early = await commit(c, bare, "subcontract", crew, [budgeted(None, 1, 8000)])
    assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    project = await signed(c)
    gone = await party(c, "FAKE Retired Crew", ["contractor"])
    archived = await c.client.put(
        f"/v1/businesses/{c.tenant}/counterparties/{gone}",
        json=card(
            display_name="FAKE Retired Crew",
            roles=["contractor"],
            expected_revision=1,
            archived=True,
        ),
        headers={**c.headers, "Idempotency-Key": str(uuid7())},
    )
    assert archived.status_code == 200, archived.text
    for kind, who in (
        ("subcontract", yard),
        ("purchase_order", crew),
        ("subcontract", c.customer),
        ("subcontract", uuid7()),
        ("subcontract", gone),
    ):
        refused = await commit(c, project, kind, who, [budgeted(None, 1, 8000)])
        assert error(refused) == (422, "INVALID_REFERENCE"), (kind, refused.text)
    loan = await commit(c, project, "loan", crew, [budgeted(None, 1, 8000)])
    assert loan.status_code == 422, loan.text
    assert await _counts(app_pool, c.tenant) == (0, 0, 0)
    key = str(uuid7())
    first = await commit(c, project, "subcontract", crew, [budgeted(None, 1, 8000)], key=key)
    assert first.status_code == 200, first.text
    view = first.json()
    assert (view["number"], view["revision"], view["kind"], view["state"]) == (
        1,
        1,
        "subcontract",
        "open",
    )
    assert (view["counterparty_id"], view["title"], view["reference"], view["note"]) == (
        str(crew),
        "FAKE framing labour",
        "FAKE-SC-1",
        None,
    )
    assert view["lines"] == [budgeted(None, 1, 8000)]
    assert (view["total_minor"], view["currency"]) == (8000, "USD")
    repeat = await commit(c, project, "subcontract", crew, [budgeted(None, 1, 8000)], key=key)
    assert (repeat.status_code, repeat.json()) == (200, view)
    reused = await commit(c, project, "subcontract", crew, [budgeted(None, 1, 9000)], key=key)
    assert error(reused) == (422, "IDEMPOTENCY_KEY_REUSED"), reused.text
    second = await commit(c, project, "purchase_order", yard, [budgeted(None, 1, 3000)])
    assert (second.status_code, second.json()["number"]) == (200, 2), second.text
    listed = await c.get(f"/projects/{project}/commitments")
    assert listed.status_code == 200, listed.text
    assert [
        (i["number"], i["kind"], i["state"], i["total_minor"]) for i in listed.json()["items"]
    ] == [(1, "subcontract", "open", 8000), (2, "purchase_order", "open", 3000)]
    shown = await c.get(f"/projects/{project}/commitments/2")
    assert (shown.status_code, shown.json()) == (200, second.json())
    missing = await c.get(f"/projects/{project}/commitments/9")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    with pytest.raises(psycopg.errors.CheckViolation) as skipped:
        async with tenant_transaction(app_pool, c.tenant) as conn:
            await conn.execute(
                "insert into gba.construction_commitments (tenant_id, project_id, number, kind, "
                "counterparty_id, created_by) select tenant_id, project_id, 9, kind, "
                "counterparty_id, created_by from gba.construction_commitments "
                "where project_id = %s and number = 1",
                (project,),
            )
    assert skipped.value.diag.constraint_name == "construction_commitments_sequence_check"


# O3a-04 ----------------------------------------------------------------------------


async def test_commitment_versions_are_insert_only_and_a_cancellation_is_final(
    construction: Construction, app_pool: RuntimePool
) -> None:
    c = construction
    project = await _changed(c)
    crew = await party(c, "FAKE Framing Crew", ["contractor"])
    made = await commit(c, project, "subcontract", crew, [budgeted(None, 1, 8000)])
    assert made.status_code == 200, made.text
    for stale in (0, 2):
        conflict = await revise(c, project, 1, stale, [budgeted(None, 1, 9000)])
        assert error(conflict) == (409, "CONSTRUCTION_REVISION_CONFLICT"), conflict.text
    revised = await revise(c, project, 1, 1, [budgeted(None, 1, 9000), budgeted(1, 1, 500)])
    assert revised.status_code == 200, revised.text
    view = revised.json()
    assert (view["revision"], view["state"], view["total_minor"]) == (2, "open", 9500)
    assert (view["title"], view["reference"], view["note"]) == (
        "FAKE framing labour, revised",
        None,
        "FAKE scope agreed on site",
    )
    assert view["lines"] == [budgeted(None, 1, 9000), budgeted(1, 1, 500)]
    twice = await revise(c, project, 1, 2, [budgeted(None, 1, 1), budgeted(None, 1, 2)])
    assert twice.status_code == 422, twice.text
    # Unknown line; a line of a proposed change order; a removal line; an unknown change order.
    for change_order, position in ((None, 9), (2, 1), (1, 2), (7, 1)):
        unknown = await revise(c, project, 1, 2, [budgeted(change_order, position, 100)])
        assert error(unknown) == (422, "INVALID_REFERENCE"), (change_order, unknown.text)
    empty = await revise(c, project, 1, 2, [])
    assert empty.status_code == 422, empty.text
    loaded = await revise(c, project, 1, 2, [budgeted(None, 1, 1)], state="cancelled")
    assert loaded.status_code == 422, loaded.text
    cancelled = await revise(c, project, 1, 2, [], state="cancelled")
    assert cancelled.status_code == 200, cancelled.text
    assert (cancelled.json()["revision"], cancelled.json()["state"]) == (3, "cancelled")
    assert (cancelled.json()["lines"], cancelled.json()["total_minor"]) == ([], 0)
    final = await revise(c, project, 1, 3, [budgeted(None, 1, 1)])
    assert error(final) == (409, "CONSTRUCTION_COMMITMENT_CANCELLED"), final.text
    shown = await c.get(f"/projects/{project}/commitments/1")
    assert (shown.status_code, shown.json()) == (200, cancelled.json())
    assert await _counts(app_pool, c.tenant) == (1, 3, 3)
    tenant = c.tenant
    for statement in (
        "update gba.construction_commitments set kind = 'purchase_order'",
        "delete from gba.construction_commitments",
        "update gba.construction_commitment_versions set title = 'FAKE'",
        "delete from gba.construction_commitment_versions",
        "update gba.construction_commitment_lines set amount_minor = 1",
        "delete from gba.construction_commitment_lines",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    with pytest.raises(psycopg.errors.CheckViolation) as reopened:
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "insert into gba.construction_commitment_versions (tenant_id, project_id, number, "
                "revision, state, title, created_by) select tenant_id, project_id, number, 4, "
                "'open', 'FAKE', created_by from gba.construction_commitment_versions "
                "where project_id = %s and number = 1 and revision = 3",
                (project,),
            )
    assert reopened.value.diag.constraint_name == "construction_commitment_versions_cancelled_check"
    other = await commit(c, project, "subcontract", crew, [budgeted(None, 2, 100)])
    assert other.status_code == 200, other.text
    with pytest.raises(psycopg.errors.CheckViolation) as nowhere:
        await _version_with_unknown_line(app_pool, tenant, project)
    assert nowhere.value.diag.constraint_name == "construction_commitment_lines_budget_check"


async def _version_with_unknown_line(pool: RuntimePool, tenant: UUID, project: UUID) -> None:
    """A second version of commitment 2 written by SQL, naming budget line 9 that does not exist."""
    async with tenant_transaction(pool, tenant) as conn:
        await conn.execute(
            "insert into gba.construction_commitment_versions (tenant_id, project_id, number, "
            "revision, state, title, created_by) select tenant_id, project_id, number, 2, "
            "'open', 'FAKE', created_by from gba.construction_commitment_versions "
            "where project_id = %s and number = 2 and revision = 1",
            (project,),
        )
        await conn.execute(
            "insert into gba.construction_commitment_lines (tenant_id, project_id, number, "
            "revision, line_no, change_order, budget_position, amount_minor) "
            "select tenant_id, project_id, number, 2, 1, null, 9, 100 "
            "from gba.construction_commitment_versions "
            "where project_id = %s and number = 2 and revision = 1",
            (project,),
        )


# O3a-05 ----------------------------------------------------------------------------


async def test_committed_is_the_latest_open_versions_and_overruns_are_shown(
    construction: Construction,
) -> None:
    c = construction
    project = await signed(c, TWO_LINES)
    crew = await party(c, "FAKE Framing Crew", ["contractor"])
    yard = await party(c, "FAKE Lumber Yard", ["supplier"])
    assert (await commit(c, project, "subcontract", crew, [budgeted(None, 1, 9000)])).json()[
        "number"
    ] == 1
    assert (await revise(c, project, 1, 1, [budgeted(None, 1, 10000)])).status_code == 200
    lumber = [budgeted(None, 1, 6000), budgeted(None, 2, 4000)]
    over = await commit(c, project, "purchase_order", yard, lumber)
    assert (over.status_code, over.json()["number"]) == (200, 2), over.text
    view = (await c.get(f"/projects/{project}/budget")).json()
    assert [row(item) for item in view["lines"]] == [
        (None, 1, "Framing", Decimal(10), 15000, 16000, -1000, True),
        (None, 2, "Finishes", Decimal("3.3333"), 3333, 4000, -667, True),
    ]
    assert phases(view) == [("Framing", 15000, 16000, -1000), ("Finishes", 3333, 4000, -667)]
    assert [p["over_committed"] for p in view["phases"]] == [True, True]
    assert totals(view) == (18333, 20000, -1667)
    assert (await revise(c, project, 2, 1, [], state="cancelled")).status_code == 200
    view = (await c.get(f"/projects/{project}/budget")).json()
    assert [row(item) for item in view["lines"]] == [
        (None, 1, "Framing", Decimal(10), 15000, 10000, 5000, False),
        (None, 2, "Finishes", Decimal("3.3333"), 3333, 0, 3333, False),
    ]
    assert totals(view) == (18333, 10000, 8333)


# O3a-06 ----------------------------------------------------------------------------


async def test_two_racing_revisions_leave_one_version(
    construction: Construction, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    c = construction
    project = await signed(c)
    crew = await party(c, "FAKE Framing Crew", ["contractor"])
    assert (
        await commit(c, project, "subcontract", crew, [budgeted(None, 1, 8000)])
    ).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        c.tenant,
        LOCK,
        project,
        [
            revise(c, project, 1, 1, [budgeted(None, 1, 9000)]),
            revise(c, project, 1, 1, [budgeted(None, 1, 7000)]),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_REVISION_CONFLICT")
    assert await _counts(app_pool, c.tenant) == (1, 2, 2)


async def test_two_racing_commitments_take_the_next_numbers(
    construction: Construction, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    c = construction
    project = await signed(c)
    crew = await party(c, "FAKE Framing Crew", ["contractor"])
    yard = await party(c, "FAKE Lumber Yard", ["supplier"])
    answers = await race(
        app_pool,
        test_database,
        c.tenant,
        LOCK,
        project,
        [
            commit(c, project, "subcontract", crew, [budgeted(None, 1, 8000)]),
            commit(c, project, "purchase_order", yard, [budgeted(None, 1, 3000)]),
        ],
    )
    assert [a.status_code for a in answers] == [200, 200], [a.text for a in answers]
    assert sorted(a.json()["number"] for a in answers) == [1, 2]
    assert await _counts(app_pool, c.tenant) == (2, 2, 2)


# O3a-07 ----------------------------------------------------------------------------


async def test_without_the_module_commitments_are_refused_and_scope_holds(
    construction: Construction,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    c = construction
    world: BookingWorld = c.world
    project = await signed(c)
    crew = await party(c, "FAKE Framing Crew", ["contractor"])
    assert (
        await commit(c, project, "subcontract", crew, [budgeted(None, 1, 8000)])
    ).status_code == 200
    # Front desk reads nothing it may not and writes no commitment.
    staff = c.member("front_desk", None)
    refused = await commit(c, project, "subcontract", crew, [budgeted(None, 1, 1)], headers=staff)
    assert refused.status_code == 403, refused.text
    unrevised = await revise(c, project, 1, 1, [budgeted(None, 1, 1)], headers=staff)
    assert unrevised.status_code == 403, unrevised.text
    # A manager of another branch does not see the budget or the commitments.
    away, _ = seed_other_branch(c.owner_conn, world.a)
    elsewhere = c.member("manager", away)
    for path in ("budget", "commitments", "commitments/1"):
        hidden = await c.get(f"/projects/{project}/{path}", headers=elsewhere)
        assert error(hidden) == (404, "NOT_FOUND"), (path, hidden.text)
    # Another company sees nothing.
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await c.get(f"/projects/{project}/budget", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == (0, 0, 0)
    # Turned off: writes are refused and write nothing; reads continue.
    before = await _counts(app_pool, c.tenant)
    assert before == (1, 1, 1)
    await Config(c.client, idp).publish(
        manager_a, c.tenant, 1, ["booking_resources", "counterparties"]
    )
    for answer in (
        await commit(c, project, "subcontract", crew, [budgeted(None, 1, 1)]),
        await revise(c, project, 1, 1, [budgeted(None, 1, 1)]),
    ):
        assert error(answer) == (409, "MODULE_DISABLED"), answer.text
    assert await _counts(app_pool, c.tenant) == before
    budget = await c.get(f"/projects/{project}/budget")
    assert (budget.status_code, budget.json()["committed_minor"]) == (200, 8000), budget.text
    listed = await c.get(f"/projects/{project}/commitments")
    assert (listed.status_code, len(listed.json()["items"])) == (200, 1), listed.text
