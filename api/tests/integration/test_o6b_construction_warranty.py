"""O6b: construction warranty claims, repair cost and the reconciliation view (package O; FAKE).

docs/plan/PACKAGE_O6B_DESIGN_2026-11-02.md: a claim is raised only inside the warranty period the
final acceptance records; its state moves by insert-only events; its repair cost is an O3b cost link
assigned to it, so each fact still counts once; the reconciliation view derives contract, cost,
billing, retainage and FIN-03 settlement and their differences (O-05).
"""

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
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_o1_construction_estimates import (
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
)
from tests.integration.test_o3b_construction_costs import _party, from_payable
from tests.integration.test_o4a_construction_execution import (
    LOCK,
    TWO_LINES,
    ago,
    measure,
    signed_at,
)
from tests.integration.test_o5_construction_billing import (
    CONTRACT,
    Billing,
    billing,
    issue,
    pay,
    rate,
)
from tests.integration.test_o6a_construction_acceptance import accept_final, later, release
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "billing", "client", "idp", "manager_a", "manager_b"]
TABLES = (
    "construction_warranty_claims",
    "construction_warranty_claim_events",
    "construction_warranty_repairs",
)
NONE = (0, 0, 0)
HELD = CONTRACT // 10  # 10 % of 31007, rounded down


async def finished(b: Billing, warranty: str | None = None, retainage: bool = True) -> UUID:
    """A project measured in full, billed in full and finally accepted 8 days ago."""
    project = await signed_at(b.c, TWO_LINES)
    if retainage:
        assert (await rate(b, project, 0, 1000)).status_code == 200
    assert (await measure(b.c, project, 1, "10", ago(10))).status_code == 200
    assert (await measure(b.c, project, 2, "3.3333", ago(10))).status_code == 200
    assert (await pay(b, project, ago(9))).status_code == 200
    final = await accept_final(b, project, ago(8), warranty=warranty or later(365))
    assert final.status_code == 200, final.text
    return project


async def claim(
    b: Billing,
    project: UUID,
    on: str,
    headers: dict[str, str] | None = None,
    key: str | None = None,
    **changes: Any,
) -> httpx.Response:
    body = {
        "title": "FAKE cracked tile",
        "description": "FAKE two tiles cracked by the sink",
        "phase": "Finishes",
        "location": "FAKE kitchen",
        "reported_by": "FAKE Pat Homeowner",
        "raised_on": on,
        **changes,
    }
    return await b.c.send("POST", f"/projects/{project}/warranty-claims", body, headers, key)


async def move_claim(
    b: Billing,
    project: UUID,
    number: int,
    expected: int,
    state: str,
    note: str | None = None,
    headers: dict[str, str] | None = None,
    key: str | None = None,
) -> httpx.Response:
    body = {"expected_sequence": expected, "state": state, "note": note}
    return await b.c.send(
        "POST", f"/projects/{project}/warranty-claims/{number}/events", body, headers, key
    )


async def repair(
    b: Billing,
    project: UUID,
    number: int,
    link: int,
    headers: dict[str, str] | None = None,
    key: str | None = None,
) -> httpx.Response:
    body = {"cost_link": link}
    return await b.c.send(
        "POST", f"/projects/{project}/warranty-claims/{number}/repairs", body, headers, key
    )


async def cost(b: Billing, project: UUID, amount: str, position: int = 2) -> int:
    """An issued payable accrual of one line, linked to a budget line (O3b): the link's number."""
    supplier = await _party(b.c, f"FAKE Tiler {uuid7().hex[-6:]}", ["supplier"])
    document, line_id = uuid7(), uuid7()
    body = {
        "schema_version": 1,
        "expected_revision": 0,
        "direction": "payable",
        "counterparty_id": str(supplier),
        "counterparty_revision": 1,
        "currency": "USD",
        "invoice_date": ago(5),
        "control_account_id": str(b.chart["2000"]),
        "title": "FAKE tile repair",
        "number": f"FAKE-{document.hex[-8:]}",
        "lines": [
            {
                "line_id": str(line_id),
                "counter_account_id": str(b.chart["5000"]),
                "description": "FAKE tiles and labour",
                "amount": amount,
            }
        ],
    }
    saved = await b.c.client.put(
        f"{b.documents}/accruals/{document}",
        json=body,
        headers={**b.c.headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    issued = await issue(b, "accruals", str(document), ago(5))
    assert issued.status_code == 200, issued.text
    fact = from_payable(b.book, document, line_id)
    body = {"change_order": None, "position": position, **fact}
    linked = await b.c.send("POST", f"/projects/{project}/costs", body)
    assert linked.status_code == 200, linked.text
    return int(linked.json()["number"])


async def reverse_cost(b: Billing, project: UUID, number: int) -> None:
    body = {"reason": "FAKE booked twice"}
    answer = await b.c.send("POST", f"/projects/{project}/costs/{number}/reversal", body)
    assert answer.status_code == 200, answer.text


async def relink(b: Billing, project: UUID, number: int) -> int:
    """The fact of a reversed link, linked again (O3b): the new link's number."""
    old = (await b.c.get(f"/projects/{project}/costs/{number}")).json()
    fact = from_payable(UUID(old["book_id"]), UUID(old["document_id"]), UUID(old["line_id"]))
    body = {"change_order": None, "position": old["position"], **fact}
    linked = await b.c.send("POST", f"/projects/{project}/costs", body)
    assert linked.status_code == 200, linked.text
    return int(linked.json()["number"])


def repairs(view: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [(r["cost_link"], r["amount_minor"], r["reversed"]) for r in view["repairs"]]


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    query = "select " + ", ".join(f"(select count(*) from gba.{table})" for table in TABLES)
    async with tenant_transaction(pool, tenant) as conn:
        found = await (await conn.execute(query)).fetchone()
    assert found is not None
    return tuple(int(n) for n in found)


async def _refused_by(pool: RuntimePool, tenant: UUID, statement: str, project: UUID) -> str:
    """The constraint the database names when it refuses this statement."""
    with pytest.raises(psycopg.errors.CheckViolation) as refused:
        async with tenant_transaction(pool, tenant) as conn:
            await conn.execute(statement, (project,))
    return str(refused.value.diag.constraint_name)


# O6b-01 -----------------------------------------------------------------------------


async def test_claims_are_raised_only_inside_the_warranty(
    billing: Billing, app_pool: RuntimePool
) -> None:
    b = billing
    bare = uuid7()
    assert (await b.c.project(bare)).status_code == 200
    for early in (
        await claim(b, bare, ago(1)),
        await b.c.get(f"/projects/{bare}/warranty-claims"),
    ):
        assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    unaccepted = await signed_at(b.c, TWO_LINES)
    none = await claim(b, unaccepted, ago(1))
    assert error(none) == (409, "CONSTRUCTION_NO_WARRANTY"), none.text
    project = await finished(b)
    wrongs: tuple[dict[str, Any], ...] = (
        {"title": "FAKE\ncracked"},
        {"title": ""},
        {"reported_by": ""},
        {"location": "FAKE\tkitchen"},
    )
    for wrong in wrongs:
        refused = await claim(b, project, ago(1), **wrong)
        assert error(refused) == (422, "INVALID_REQUEST"), (wrong, refused.text)
    before = await claim(b, project, ago(9))
    assert error(before) == (422, "CONSTRUCTION_OUTSIDE_WARRANTY"), before.text
    ahead = await claim(b, project, later(2))
    assert error(ahead) == (422, "CONSTRUCTION_FUTURE_DATE"), ahead.text
    unknown = await claim(b, project, ago(1), phase="Roof")
    assert error(unknown) == (422, "INVALID_REFERENCE"), unknown.text
    staff = b.c.member("front_desk", None)
    denied = await claim(b, project, ago(1), headers=staff)
    assert denied.status_code == 403, denied.text
    ended = await finished(b, warranty=ago(2))
    late = await claim(b, ended, ago(1))
    assert error(late) == (422, "CONSTRUCTION_OUTSIDE_WARRANTY"), late.text
    assert await _counts(app_pool, b.tenant) == NONE
    key = str(uuid7())
    first = await claim(b, project, ago(8), key=key)
    assert first.status_code == 200, first.text
    view = first.json()
    assert (
        view["number"],
        view["title"],
        view["description"],
        view["phase"],
        view["location"],
        view["reported_by"],
        view["raised_on"],
        view["state"],
        view["events"],
        view["repairs"],
        view["repair_minor"],
    ) == (
        1,
        "FAKE cracked tile",
        "FAKE two tiles cracked by the sink",
        "Finishes",
        "FAKE kitchen",
        "FAKE Pat Homeowner",
        ago(8),
        "open",
        [],
        [],
        0,
    )
    again = await claim(b, project, ago(8), key=key)
    assert (again.status_code, again.json()) == (200, view)
    whole = await claim(b, project, ago(1), phase=None, title="FAKE door sticks")
    assert whole.status_code == 200, whole.text
    assert (whole.json()["number"], whole.json()["phase"]) == (2, None)
    assert (await b.c.get(f"/projects/{project}/warranty-claims/1")).json() == view
    missing = await b.c.get(f"/projects/{project}/warranty-claims/9")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    listed = (await b.c.get(f"/projects/{project}/warranty-claims")).json()
    assert (listed["warranty_starts_on"], listed["warranty_ends_on"]) == (ago(8), later(365))
    assert [(i["number"], i["state"]) for i in listed["items"]] == [(1, "open"), (2, "open")]
    assert await _counts(app_pool, b.tenant) == (2, 0, 0)


# O6b-02 -----------------------------------------------------------------------------


async def test_claims_move_open_repaired_closed_or_rejected(billing: Billing) -> None:
    b = billing
    project = await finished(b)
    assert (await claim(b, project, ago(2))).status_code == 200
    assert (await claim(b, project, ago(1))).status_code == 200
    skipped = await move_claim(b, project, 1, 0, "closed")
    assert error(skipped) == (409, "CONSTRUCTION_CLAIM_TRANSITION"), skipped.text
    for state in ("open", "rejected"):
        bare = await move_claim(b, project, 1, 0, state)
        assert error(bare) == (422, "INVALID_REQUEST"), (state, bare.text)
    key = str(uuid7())
    repaired = await move_claim(b, project, 1, 0, "repaired", key=key)
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["state"] == "repaired"
    again = await move_claim(b, project, 1, 0, "repaired", key=key)
    assert (again.status_code, again.json()) == (200, repaired.json())
    stale = await move_claim(b, project, 1, 0, "closed")
    assert error(stale) == (409, "CONSTRUCTION_REVISION_CONFLICT"), stale.text
    reopened = await move_claim(b, project, 1, 1, "open", note="FAKE crack came back")
    assert reopened.status_code == 200, reopened.text
    assert (await move_claim(b, project, 1, 2, "repaired")).status_code == 200
    closed = await move_claim(b, project, 1, 3, "closed")
    assert closed.status_code == 200, closed.text
    assert [(e["sequence"], e["state"], e["note"]) for e in closed.json()["events"]] == [
        (1, "repaired", None),
        (2, "open", "FAKE crack came back"),
        (3, "repaired", None),
        (4, "closed", None),
    ]
    for state in ("open", "repaired", "rejected"):
        final = await move_claim(b, project, 1, 4, state, note="FAKE again")
        assert error(final) == (409, "CONSTRUCTION_CLAIM_TRANSITION"), (state, final.text)
    rejected = await move_claim(b, project, 2, 0, "rejected", note="FAKE wear, not a defect")
    assert rejected.status_code == 200, rejected.text
    for state in ("repaired", "open", "closed"):
        final = await move_claim(b, project, 2, 1, state, note="FAKE again")
        assert error(final) == (409, "CONSTRUCTION_CLAIM_TRANSITION"), (state, final.text)
    missing = await move_claim(b, project, 9, 0, "repaired")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    listed = (await b.c.get(f"/projects/{project}/warranty-claims")).json()
    assert [(i["number"], i["state"]) for i in listed["items"]] == [(1, "closed"), (2, "rejected")]


# O6b-03 -----------------------------------------------------------------------------


async def test_repair_cost_is_an_assigned_cost_link(billing: Billing) -> None:
    b = billing
    project = await finished(b)
    assert (await claim(b, project, ago(2))).status_code == 200
    assert (await claim(b, project, ago(1))).status_code == 200
    first = await cost(b, project, "40.00")
    key = str(uuid7())
    assigned = await repair(b, project, 1, first, key=key)
    assert assigned.status_code == 200, assigned.text
    assert repairs(assigned.json()) == [(first, 4000, False)]
    assert assigned.json()["repair_minor"] == 4000
    again = await repair(b, project, 1, first, key=key)
    assert (again.status_code, again.json()) == (200, assigned.json())
    twice = await repair(b, project, 2, first)
    assert error(twice) == (409, "CONSTRUCTION_REPAIR_ASSIGNED"), twice.text
    unknown = await repair(b, project, 1, 99)
    assert error(unknown) == (404, "NOT_FOUND"), unknown.text
    second = await cost(b, project, "10.00")
    await reverse_cost(b, project, second)
    reversed_link = await repair(b, project, 1, second)
    assert error(reversed_link) == (409, "CONSTRUCTION_COST_REVERSED"), reversed_link.text
    third = await cost(b, project, "5.00", position=1)
    not_ours = await move_claim(b, project, 2, 0, "rejected", note="FAKE not ours")
    assert not_ours.status_code == 200, not_ours.text
    rejected = await repair(b, project, 2, third)
    assert error(rejected) == (409, "CONSTRUCTION_CLAIM_CLOSED"), rejected.text
    staff = b.c.member("front_desk", None)
    denied = await repair(b, project, 1, third, headers=staff)
    assert denied.status_code == 403, denied.text
    # A link reversed after its assignment stops counting; its fact may be linked and assigned anew.
    await reverse_cost(b, project, first)
    view = (await b.c.get(f"/projects/{project}/warranty-claims/1")).json()
    assert (repairs(view), view["repair_minor"]) == ([(first, 4000, True)], 0)
    fourth = await relink(b, project, first)
    assert (await repair(b, project, 1, fourth)).status_code == 200
    assert (await repair(b, project, 1, third)).status_code == 200
    # A repaired claim takes cost too; a closed one does not.
    assert (await move_claim(b, project, 1, 0, "repaired")).status_code == 200
    fifth = await cost(b, project, "2.50")
    assert (await repair(b, project, 1, fifth)).status_code == 200
    assert (await move_claim(b, project, 1, 1, "closed")).status_code == 200
    sixth = await cost(b, project, "1.00")
    closed = await repair(b, project, 1, sixth)
    assert error(closed) == (409, "CONSTRUCTION_CLAIM_CLOSED"), closed.text
    view = (await b.c.get(f"/projects/{project}/warranty-claims/1")).json()
    assert view["repair_minor"] == 4000 + 500 + 250
    assert repairs(view) == [
        (first, 4000, True),
        (fourth, 4000, False),
        (third, 500, False),
        (fifth, 250, False),
    ]
    # Each fact counts once: actual cost holds the relinked fact once beside the others.
    budget = (await b.c.get(f"/projects/{project}/budget")).json()
    assert budget["actual_minor"] == 4000 + 500 + 250 + 100


# O6b-04 -----------------------------------------------------------------------------


async def test_reconciliation_derives_every_figure_and_difference(billing: Billing) -> None:
    b = billing
    bare = uuid7()
    assert (await b.c.project(bare)).status_code == 200
    none = await b.c.get(f"/projects/{bare}/reconciliation")
    assert error(none) == (409, "CONSTRUCTION_NO_CONTRACT"), none.text
    fresh = await signed_at(b.c, TWO_LINES)
    empty = (await b.c.get(f"/projects/{fresh}/reconciliation")).json()
    assert (
        empty["contract_minor"],
        empty["completed_minor"],
        empty["billed_minor"],
        empty["actual_minor"],
        empty["unissued_documents"],
        empty["contract_minus_billed_minor"],
    ) == (CONTRACT, 0, 0, 0, 0, CONTRACT)
    project = await finished(b)
    general = await cost(b, project, "40.00", position=1)
    fixed = await cost(b, project, "25.00")
    assert general != fixed
    assert (await claim(b, project, ago(1))).status_code == 200
    assert (await repair(b, project, 1, fixed)).status_code == 200
    budget = (await b.c.get(f"/projects/{project}/budget")).json()
    application = (await b.c.get(f"/projects/{project}/pay-applications/1")).json()
    drafted = (await b.c.get(f"/projects/{project}/reconciliation")).json()
    assert drafted["unissued_documents"] == 2
    for route, document in (
        ("invoices", application["invoice"]["document_id"]),
        ("accruals", application["retainage"]["document_id"]),
    ):
        assert (await issue(b, route, document, ago(8))).status_code == 200, route
    assert (await release(b, project, 1, ago(7))).status_code == 200
    view = (await b.c.get(f"/projects/{project}/reconciliation")).json()
    figures = {
        "currency": "USD",
        "contract_minor": CONTRACT,
        "completed_minor": CONTRACT,
        "budget_minor": budget["budget_minor"],
        "committed_minor": budget["committed_minor"],
        "actual_minor": 6500,
        "warranty_repair_minor": 2500,
        "billed_minor": CONTRACT,
        "retained_minor": HELD,
        "due_minor": CONTRACT - HELD,
        "released_minor": HELD,
        "held_minor": 0,
        "due_paid_minor": 0,
        "due_credited_minor": 0,
        "retainage_paid_minor": 0,
        "retainage_credited_minor": 0,
        "unissued_documents": 0,
        "contract_minus_billed_minor": 0,
        "completed_minus_billed_minor": 0,
        "billed_minus_settled_minor": CONTRACT,
        "retainage_settled_before_release_minor": 0,
        "budget_minus_actual_minor": budget["budget_minor"] - 6500,
        "contract_minus_actual_minor": CONTRACT - 6500,
        "claims": {"open": 1, "repaired": 0, "closed": 0, "rejected": 0},
    }
    assert {k: view[k] for k in figures} == figures
    assert view["project_id"] == str(project)
    staff = b.c.member("front_desk", None)
    denied = await b.c.get(f"/projects/{project}/reconciliation", headers=staff)
    assert denied.status_code == 403, denied.text


# O6b-05 -----------------------------------------------------------------------------


async def test_two_racing_moves_of_a_claim_leave_one(
    billing: Billing, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    b = billing
    project = await finished(b, retainage=False)
    assert (await claim(b, project, ago(1))).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        b.tenant,
        LOCK,
        project,
        [
            move_claim(b, project, 1, 0, "repaired"),
            move_claim(b, project, 1, 0, "rejected", note="FAKE not a defect"),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_REVISION_CONFLICT"), lost.text
    (won,) = [a for a in answers if a.status_code == 200]
    view = (await b.c.get(f"/projects/{project}/warranty-claims/1")).json()
    assert view["state"] == won.json()["state"]
    assert len(view["events"]) == 1
    assert await _counts(app_pool, b.tenant) == (1, 1, 0)


# O6b-06: the database itself ---------------------------------------------------------


async def test_sql_keeps_claims_events_and_repairs_whole(
    billing: Billing, app_pool: RuntimePool
) -> None:
    b = billing
    tenant = b.tenant
    project = await finished(b, retainage=False)
    claim_sql = (
        "insert into gba.construction_warranty_claims (tenant_id, project_id, number, title, "
        "phase, reported_by, raised_on, created_by) select tenant_id, project_id, {number}, "
        "'FAKE crack', {phase}, 'FAKE Pat', date '{on}', recorded_by "
        "from gba.construction_acceptances where project_id = %s and number = 1"
    )
    event_sql = (
        "insert into gba.construction_warranty_claim_events (tenant_id, project_id, claim, "
        "sequence, state, note, created_by) select tenant_id, project_id, 1, {sequence}, "
        "'{state}', {note}, created_by from gba.construction_warranty_claims "
        "where project_id = %s and number = 1"
    )
    repair_sql = (
        "insert into gba.construction_warranty_repairs (tenant_id, project_id, cost_link, claim, "
        "created_by) select tenant_id, project_id, {link}, {claim}, created_by "
        "from gba.construction_warranty_claims where project_id = %s and number = 1"
    )

    def claim_row(number: int, on: str = ago(1), phase: str = "null") -> str:
        return claim_sql.format(number=number, on=on, phase=phase)

    def event_row(sequence: int, state: str, note: str = "null") -> str:
        return event_sql.format(sequence=sequence, state=state, note=note)

    for statement, constraint in (
        (claim_row(5), "construction_warranty_claims_sequence_check"),
        (claim_row(1, on=later(2)), "construction_warranty_claims_date_check"),
        (claim_row(1, on=ago(9)), "construction_warranty_claims_warranty_check"),
        (claim_row(1, phase="'Roof'"), "construction_warranty_claims_phase_check"),
    ):
        assert await _refused_by(app_pool, tenant, statement, project) == constraint, constraint
    # Without the final acceptance there is no warranty to claim under.
    unaccepted = await signed_at(b.c, TWO_LINES)
    assert (await measure(b.c, unaccepted, 1, "10", ago(5))).status_code == 200
    forged = (
        "insert into gba.construction_warranty_claims (tenant_id, project_id, number, title, "
        "reported_by, raised_on, created_by) select tenant_id, project_id, 1, 'FAKE crack', "
        f"'FAKE Pat', date '{ago(1)}', created_by from gba.construction_progress_measurements "
        "where project_id = %s and number = 1"
    )
    unwarranted = await _refused_by(app_pool, tenant, forged, unaccepted)
    assert unwarranted == "construction_warranty_claims_warranty_check"
    assert (await claim(b, project, ago(1))).status_code == 200
    for statement, constraint in (
        (event_row(2, "repaired"), "construction_warranty_claim_events_sequence_check"),
        (event_row(1, "closed"), "construction_warranty_claim_events_transition_check"),
        (event_row(1, "rejected"), "construction_warranty_claim_events_note_check"),
    ):
        assert await _refused_by(app_pool, tenant, statement, project) == constraint, constraint
    first = await cost(b, project, "40.00")
    second = await cost(b, project, "10.00")
    await reverse_cost(b, project, second)
    for statement, constraint in (
        (repair_sql.format(link=second, claim=1), "construction_warranty_repairs_link_check"),
        (repair_sql.format(link=99, claim=1), "construction_warranty_repairs_link_check"),
        (repair_sql.format(link=first, claim=7), "construction_warranty_repairs_claim_check"),
    ):
        assert await _refused_by(app_pool, tenant, statement, project) == constraint, constraint
    assert (await repair(b, project, 1, first)).status_code == 200
    with pytest.raises(psycopg.errors.UniqueViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(repair_sql.format(link=first, claim=1), (project,))
    assert (await move_claim(b, project, 1, 0, "repaired")).status_code == 200
    assert (await move_claim(b, project, 1, 1, "closed")).status_code == 200
    third = await cost(b, project, "1.00")
    closed = await _refused_by(app_pool, tenant, repair_sql.format(link=third, claim=1), project)
    assert closed == "construction_warranty_repairs_claim_check"
    for table in TABLES:
        for statement in (
            f"update gba.{table} set tenant_id = tenant_id",
            f"delete from gba.{table}",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with tenant_transaction(app_pool, tenant) as conn:
                    await conn.execute(statement)
    assert await _counts(app_pool, tenant) == (1, 2, 1)


# O6b-06 -----------------------------------------------------------------------------


async def test_without_the_module_claims_are_refused_and_scope_holds(
    billing: Billing,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    b = billing
    c = b.c
    world: BookingWorld = c.world
    project = await finished(b, retainage=False)
    assert (await claim(b, project, ago(1))).status_code == 200
    link = await cost(b, project, "4.00")
    # A manager of another branch does not see the project's claims or reconciliation.
    away, _ = seed_other_branch(c.owner_conn, world.a)
    elsewhere = c.member("manager", away)
    for path in ("warranty-claims", "warranty-claims/1", "reconciliation"):
        hidden = await c.get(f"/projects/{project}/{path}", headers=elsewhere)
        assert error(hidden) == (404, "NOT_FOUND"), (path, hidden.text)
    hidden_write = await claim(b, project, ago(1), headers=elsewhere)
    assert error(hidden_write) == (404, "NOT_FOUND"), hidden_write.text
    # Another company sees nothing.
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await c.get(f"/projects/{project}/warranty-claims", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == NONE
    # Turned off: writes are refused and write nothing; reads continue.
    before = await _counts(app_pool, c.tenant)
    assert before == (1, 0, 0)
    await Config(c.client, idp).publish(
        manager_a, c.tenant, 1, ["booking_resources", "counterparties"]
    )
    for answer in (
        await claim(b, project, ago(1)),
        await move_claim(b, project, 1, 0, "repaired"),
        await repair(b, project, 1, link),
    ):
        assert error(answer) == (409, "MODULE_DISABLED"), answer.text
    assert await _counts(app_pool, c.tenant) == before
    for path in ("warranty-claims", "warranty-claims/1", "reconciliation"):
        read = await c.get(f"/projects/{project}/{path}")
        assert read.status_code == 200, (path, read.text)
