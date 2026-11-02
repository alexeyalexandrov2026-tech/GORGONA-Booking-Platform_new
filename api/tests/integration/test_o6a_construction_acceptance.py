"""O6a: construction stage and final acceptance, retainage release (package O; FAKE data only).

docs/plan/PACKAGE_O6A_DESIGN_2026-11-02.md: a phase or the whole project is accepted once, only when
its work is finished and no open or fixed item blocks it; the final acceptance needs the contract
billed in full and records the warranty period; accepted work is closed for measurements, approvals
and billing; retainage is released once per acceptance by an amount the server derives (O-08).
"""

from datetime import timedelta
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
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_o1_construction_estimates import (
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
)
from tests.integration.test_o2_construction_contract import add, change, decide, remove
from tests.integration.test_o4a_construction_execution import (
    LOCK,
    TWO_LINES,
    ago,
    measure,
    signed_at,
    today,
)
from tests.integration.test_o4b_construction_quality import move, raise_item
from tests.integration.test_o5_construction_billing import CONTRACT, Billing, billing, pay, rate
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "billing", "client", "idp", "manager_a", "manager_b"]
TABLES = ("construction_acceptances", "construction_retainage_releases")
NONE = (0, 0)


def later(days: int) -> str:
    """A site date in Chicago some days ahead."""
    return (today() + timedelta(days=days)).isoformat()


async def accept_scope(
    b: Billing,
    project: UUID,
    scope: str,
    on: str,
    phase: str | None = None,
    warranty: str | None = None,
    headers: dict[str, str] | None = None,
    key: str | None = None,
    **changes: Any,
) -> httpx.Response:
    body = {
        "scope": scope,
        "phase": phase,
        "accepted_on": on,
        "signatory": "FAKE Pat Homeowner",
        "source": "paper",
        "note": None,
        "warranty_ends_on": warranty,
        **changes,
    }
    return await b.c.send("POST", f"/projects/{project}/acceptances", body, headers, key)


async def accept_phase(
    b: Billing, project: UUID, phase: str, on: str, **kwargs: Any
) -> httpx.Response:
    return await accept_scope(b, project, "phase", on, phase=phase, **kwargs)


async def accept_final(
    b: Billing, project: UUID, on: str, warranty: str | None = None, **kwargs: Any
) -> httpx.Response:
    return await accept_scope(b, project, "final", on, warranty=warranty or later(365), **kwargs)


async def release(
    b: Billing,
    project: UUID,
    number: int,
    on: str,
    headers: dict[str, str] | None = None,
    key: str | None = None,
) -> httpx.Response:
    body = {"released_on": on, "note": "FAKE released by the owner's letter"}
    return await b.c.send(
        "POST", f"/projects/{project}/acceptances/{number}/release", body, headers, key
    )


def phases(view: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (
            item["phase"],
            item["finished"],
            item["open_items"],
            item["billed_in_full"],
            item["retained_minor"],
            item["acceptance"],
            item["released_minor"],
        )
        for item in view["phases"]
    ]


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


# O6a-01 -----------------------------------------------------------------------------


async def test_acceptances_are_recorded_once_per_scope(
    billing: Billing, app_pool: RuntimePool
) -> None:
    b = billing
    bare = uuid7()
    assert (await b.c.project(bare)).status_code == 200
    for early in (
        await accept_phase(b, bare, "Framing", ago(1)),
        await b.c.get(f"/projects/{bare}/acceptances"),
    ):
        assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    project = await signed_at(b.c, TWO_LINES)
    assert (await measure(b.c, project, 1, "10", ago(6))).status_code == 200
    for wrong in (
        {"source": "platform"},
        {"warranty_ends_on": later(365)},
        {"signatory": "FAKE\nPat"},
        {"signatory": ""},
    ):
        refused = await accept_phase(b, project, "Framing", ago(5), **wrong)
        assert error(refused) == (422, "INVALID_REQUEST"), (wrong, refused.text)
    for refused in (
        await accept_scope(b, project, "partial", ago(5), phase="Framing"),
        await accept_scope(b, project, "phase", ago(5)),
    ):
        assert error(refused) == (422, "INVALID_REQUEST"), refused.text
    finals: tuple[dict[str, Any], ...] = ({"phase": "Framing"}, {"warranty_ends_on": None})
    for wrong in finals:
        refused = await accept_final(b, project, ago(5), **wrong)
        assert error(refused) == (422, "INVALID_REQUEST"), (wrong, refused.text)
    unknown = await accept_phase(b, project, "Roof", ago(5))
    assert error(unknown) == (422, "INVALID_REFERENCE"), unknown.text
    ahead = await accept_phase(b, project, "Framing", later(2))
    assert error(ahead) == (422, "CONSTRUCTION_FUTURE_DATE"), ahead.text
    staff = b.c.member("front_desk", None)
    denied = await accept_phase(b, project, "Framing", ago(5), headers=staff)
    assert denied.status_code == 403, denied.text
    assert await _counts(app_pool, b.tenant) == NONE
    key = str(uuid7())
    first = await accept_phase(b, project, "Framing", ago(5), key=key)
    assert first.status_code == 200, first.text
    view = first.json()
    assert (
        view["number"],
        view["scope"],
        view["phase"],
        view["accepted_on"],
        view["signatory"],
        view["source"],
        view["warranty_starts_on"],
        view["warranty_ends_on"],
        view["release"],
    ) == (1, "phase", "Framing", ago(5), "FAKE Pat Homeowner", "paper", None, None, None)
    again = await accept_phase(b, project, "Framing", ago(5), key=key)
    assert (again.status_code, again.json()) == (200, view)
    twice = await accept_phase(b, project, "Framing", ago(4))
    assert error(twice) == (409, "CONSTRUCTION_ACCEPTED"), twice.text
    assert (await b.c.get(f"/projects/{project}/acceptances/1")).json() == view
    missing = await b.c.get(f"/projects/{project}/acceptances/9")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    assert await _counts(app_pool, b.tenant) == (1, 0)


# O6a-02 -----------------------------------------------------------------------------


async def test_only_finished_unblocked_and_billed_work_is_accepted(billing: Billing) -> None:
    b = billing
    project = await signed_at(b.c, TWO_LINES)
    assert (await measure(b.c, project, 1, "9", ago(8))).status_code == 200
    short = await accept_phase(b, project, "Framing", ago(7))
    assert error(short) == (409, "CONSTRUCTION_NOT_COMPLETED"), short.text
    assert (await measure(b.c, project, 1, "10", ago(3))).status_code == 200
    early = await accept_phase(b, project, "Framing", ago(4))
    assert error(early) == (409, "CONSTRUCTION_NOT_COMPLETED"), early.text
    # Open or fixed items of the phase block it; closed ones and items of the whole project do not.
    assert (await raise_item(b.c, project, phase="Framing")).status_code == 200
    blocked = await accept_phase(b, project, "Framing", ago(2))
    assert error(blocked) == (409, "CONSTRUCTION_OPEN_ITEMS"), blocked.text
    assert (await move(b.c, project, 1, 0, "fixed")).status_code == 200
    unverified = await accept_phase(b, project, "Framing", ago(2))
    assert error(unverified) == (409, "CONSTRUCTION_OPEN_ITEMS"), unverified.text
    assert (await move(b.c, project, 1, 1, "closed")).status_code == 200
    assert (await raise_item(b.c, project, "FAKE dust", phase=None)).status_code == 200
    framing = await accept_phase(b, project, "Framing", ago(2))
    assert framing.status_code == 200, framing.text
    # The final acceptance: every line finished, no open item anywhere, the contract billed in full.
    unfinished = await accept_final(b, project, ago(2))
    assert error(unfinished) == (409, "CONSTRUCTION_NOT_COMPLETED"), unfinished.text
    assert (await measure(b.c, project, 2, "3.3333", ago(2))).status_code == 200
    blocked = await accept_final(b, project, ago(2))
    assert error(blocked) == (409, "CONSTRUCTION_OPEN_ITEMS"), blocked.text
    voided = await move(b.c, project, 2, 0, "void", note="FAKE raised in error")
    assert voided.status_code == 200, voided.text
    unbilled = await accept_final(b, project, ago(2))
    assert error(unbilled) == (409, "CONSTRUCTION_NOT_FULLY_BILLED"), unbilled.text
    billed = await pay(b, project, ago(1))
    assert billed.status_code == 200, billed.text
    assert billed.json()["billed_to_date_minor"] == CONTRACT
    for warranty in (ago(1), later(3700)):
        refused = await accept_final(b, project, ago(1), warranty=warranty)
        assert error(refused) == (422, "INVALID_REQUEST"), (warranty, refused.text)
    final = await accept_final(b, project, ago(1), warranty=later(365))
    assert final.status_code == 200, final.text
    assert (
        final.json()["number"],
        final.json()["scope"],
        final.json()["phase"],
        final.json()["warranty_starts_on"],
        final.json()["warranty_ends_on"],
    ) == (2, "final", None, ago(1), later(365))
    for after in (
        await accept_phase(b, project, "Finishes", ago(1)),
        await accept_final(b, project, ago(1)),
    ):
        assert error(after) == (409, "CONSTRUCTION_ACCEPTED"), after.text
    listed = (await b.c.get(f"/projects/{project}/acceptances")).json()
    assert [item["number"] for item in listed["items"]] == [1, 2]
    assert listed["final"] == final.json()
    assert phases(listed) == [
        ("Framing", True, 0, True, 0, 1, None),
        ("Finishes", True, 0, True, 0, None, None),
    ]


# O6a-03 -----------------------------------------------------------------------------


async def test_accepted_work_is_closed(billing: Billing) -> None:
    b = billing
    project = await signed_at(b.c, TWO_LINES)
    assert (await measure(b.c, project, 1, "10", ago(6))).status_code == 200
    assert (await accept_phase(b, project, "Framing", ago(5))).status_code == 200
    closed = await measure(b.c, project, 1, "9", ago(4), note="FAKE recount")
    assert error(closed) == (409, "CONSTRUCTION_ACCEPTED"), closed.text
    assert (await measure(b.c, project, 2, "1", ago(4))).status_code == 200
    # Approvals touching the accepted phase are refused; rejections and withdrawals are not.
    assert (await change(b.c, project, [add()])).status_code == 200
    assert (await change(b.c, project, [remove(1, "1")])).status_code == 200
    for number, other in ((1, "rejected"), (2, "withdrawn")):
        approval = await decide(b.c, project, number, "approved")
        assert error(approval) == (409, "CONSTRUCTION_ACCEPTED"), (number, approval.text)
        assert (await decide(b.c, project, number, other)).status_code == 200
    extra = add("FAKE grout sealing", phase="Finishes", quantity="1", price=900)
    assert (await change(b.c, project, [extra])).status_code == 200
    assert (await decide(b.c, project, 3, "approved")).status_code == 200
    assert (await measure(b.c, project, 2, "3.3333", ago(3))).status_code == 200
    assert (await measure(b.c, project, 1, "1", ago(3), change_order=3)).status_code == 200
    assert (await pay(b, project, ago(2))).status_code == 200
    assert (await accept_final(b, project, ago(1))).status_code == 200
    # After the final acceptance nothing is measured, approved or billed.
    late = await measure(b.c, project, 2, "3.3333", ago(1))
    assert error(late) == (409, "CONSTRUCTION_ACCEPTED"), late.text
    assert (await change(b.c, project, [extra])).status_code == 200
    approval = await decide(b.c, project, 4, "approved")
    assert error(approval) == (409, "CONSTRUCTION_ACCEPTED"), approval.text
    assert (await decide(b.c, project, 4, "rejected")).status_code == 200
    billing_after = await pay(b, project, today().isoformat())
    assert error(billing_after) == (409, "CONSTRUCTION_ACCEPTED"), billing_after.text


# O6a-04 -----------------------------------------------------------------------------


async def test_retainage_is_released_once_per_acceptance(
    billing: Billing, app_pool: RuntimePool
) -> None:
    b = billing
    project = await signed_at(b.c, TWO_LINES)
    assert (await rate(b, project, 0, 1000)).status_code == 200
    assert (await measure(b.c, project, 1, "4", ago(10))).status_code == 200
    assert (await pay(b, project, ago(9))).status_code == 200  # 10000 billed, 1000 held
    assert (await rate(b, project, 1, 500)).status_code == 200
    assert (await measure(b.c, project, 1, "10", ago(8))).status_code == 200
    assert (await measure(b.c, project, 2, "1.1111", ago(8))).status_code == 200
    second = await pay(b, project, ago(7))  # 27002 billed, 17002 x 5% = 850.1: 850 held
    assert second.status_code == 200, second.text
    assert second.json()["retained_minor"] == 850
    assert (await accept_phase(b, project, "Framing", ago(6))).status_code == 200
    unknown = await release(b, project, 9, ago(5))
    assert error(unknown) == (404, "NOT_FOUND"), unknown.text
    before = await release(b, project, 1, ago(7))
    assert error(before) == (422, "CONSTRUCTION_BEFORE_ACCEPTANCE"), before.text
    ahead = await release(b, project, 1, later(2))
    assert error(ahead) == (422, "CONSTRUCTION_FUTURE_DATE"), ahead.text
    staff = b.c.member("front_desk", None)
    denied = await release(b, project, 1, ago(5), headers=staff)
    assert denied.status_code == 403, denied.text
    # Framing holds 10000 x 10% + 15000 x 5% = 1750.
    key = str(uuid7())
    framing = await release(b, project, 1, ago(5), key=key)
    assert framing.status_code == 200, framing.text
    freed = framing.json()["release"]
    assert (freed["released_on"], freed["amount_minor"], freed["note"]) == (
        ago(5),
        1750,
        "FAKE released by the owner's letter",
    )
    again = await release(b, project, 1, ago(5), key=key)
    assert (again.status_code, again.json()) == (200, framing.json())
    twice = await release(b, project, 1, ago(4))
    assert error(twice) == (409, "CONSTRUCTION_RELEASED"), twice.text
    # Finishes is accepted but not billed in full yet.
    assert (await measure(b.c, project, 2, "3.3333", ago(4))).status_code == 200
    assert (await accept_phase(b, project, "Finishes", ago(3))).status_code == 200
    unbilled = await release(b, project, 2, ago(3))
    assert error(unbilled) == (409, "CONSTRUCTION_NOT_FULLY_BILLED"), unbilled.text
    third = await pay(b, project, ago(2))  # 31007 billed, 4005 x 5% = 200.25: 200 held
    assert third.status_code == 200, third.text
    assert third.json()["retained_minor"] == 200
    listed = (await b.c.get(f"/projects/{project}/acceptances")).json()
    assert (listed["retained_minor"], listed["released_minor"], listed["held_minor"]) == (
        2050,
        1750,
        300,
    )
    assert phases(listed) == [
        ("Framing", True, 0, True, 1750, 1, 1750),
        ("Finishes", True, 0, True, 300, 2, None),
    ]
    # The final acceptance releases everything still held; nothing is released after it.
    assert (await accept_final(b, project, ago(1))).status_code == 200
    final = await release(b, project, 3, ago(1))
    assert final.status_code == 200, final.text
    assert final.json()["release"]["amount_minor"] == 300
    after = await release(b, project, 2, ago(1))
    assert error(after) == (409, "CONSTRUCTION_RELEASED"), after.text
    listed = (await b.c.get(f"/projects/{project}/acceptances")).json()
    assert (listed["retained_minor"], listed["released_minor"], listed["held_minor"]) == (
        2050,
        2050,
        0,
    )
    assert [
        (i["number"], i["scope"], i["release"] and i["release"]["amount_minor"])
        for i in listed["items"]
    ] == [(1, "phase", 1750), (2, "phase", None), (3, "final", 300)]
    assert listed["final"]["number"] == 3
    # Without a retainage rate nothing is held, so nothing is released.
    bare = await signed_at(b.c, TWO_LINES)
    assert (await measure(b.c, bare, 1, "10", ago(5))).status_code == 200
    assert (await pay(b, bare, ago(4))).status_code == 200
    assert (await accept_phase(b, bare, "Framing", ago(3))).status_code == 200
    nothing = await release(b, bare, 1, ago(2))
    assert error(nothing) == (409, "CONSTRUCTION_NOTHING_TO_RELEASE"), nothing.text
    assert await _counts(app_pool, b.tenant) == (4, 2)


# O6a-05 -----------------------------------------------------------------------------


async def test_racing_releases_and_acceptances_leave_one(
    billing: Billing, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    b = billing
    project = await signed_at(b.c, TWO_LINES)
    assert (await rate(b, project, 0, 1000)).status_code == 200
    assert (await measure(b.c, project, 1, "10", ago(6))).status_code == 200
    assert (await pay(b, project, ago(5))).status_code == 200
    assert (await accept_phase(b, project, "Framing", ago(4))).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        b.tenant,
        LOCK,
        project,
        [release(b, project, 1, ago(3)), release(b, project, 1, ago(3))],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_RELEASED"), lost.text
    assert await _counts(app_pool, b.tenant) == (1, 1)
    # An acceptance racing a correction of its phase: one of them wins, the other is refused.
    other = await signed_at(b.c, TWO_LINES)
    assert (await measure(b.c, other, 1, "10", ago(6))).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        b.tenant,
        LOCK,
        other,
        [
            accept_phase(b, other, "Framing", ago(1)),
            measure(b.c, other, 1, "9", ago(1), note="FAKE recount"),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    accepted_first = answers[0].status_code == 200
    expected = "CONSTRUCTION_ACCEPTED" if accepted_first else "CONSTRUCTION_NOT_COMPLETED"
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, expected), lost.text
    progress = (await b.c.get(f"/projects/{other}/progress")).json()
    completed = [
        Decimal(line["completed"])
        for line in progress["lines"]
        if (line["change_order"], line["position"]) == (None, 1)
    ]
    assert completed == [Decimal(10 if accepted_first else 9)], progress
    assert await _counts(app_pool, b.tenant) == ((2, 1) if accepted_first else (1, 1))


# O6a-06: the database itself ---------------------------------------------------------


async def test_sql_keeps_acceptances_and_releases_whole(
    billing: Billing, app_pool: RuntimePool
) -> None:
    b = billing
    tenant = b.tenant
    project = await signed_at(b.c, TWO_LINES)
    assert (await rate(b, project, 0, 1000)).status_code == 200
    assert (await measure(b.c, project, 1, "10", ago(10))).status_code == 200
    assert (await measure(b.c, project, 2, "1", ago(10))).status_code == 200
    assert (await pay(b, project, ago(9))).status_code == 200  # 26802 billed, 2680 held
    assert (await raise_item(b.c, project, phase="Framing")).status_code == 200
    accept_sql = (
        "insert into gba.construction_acceptances (tenant_id, project_id, number, scope, phase, "
        "accepted_on, signatory, source, warranty_ends_on, recorded_by) select tenant_id, "
        "project_id, {number}, {scope}, {phase}, {on}, 'FAKE Pat', 'paper', {warranty}, "
        "created_by from gba.construction_pay_applications where project_id = %s and number = 1"
    )
    release_sql = (
        "insert into gba.construction_retainage_releases (tenant_id, project_id, acceptance, "
        "released_on, amount_minor, recorded_by) select tenant_id, project_id, {acceptance}, "
        "{on}, {amount}, created_by from gba.construction_pay_applications "
        "where project_id = %s and number = 1"
    )

    def day(value: str) -> str:
        return f"date '{value}'"

    def phase_row(number: int, phase: str, on: str = ago(1)) -> str:
        return accept_sql.format(
            number=number, scope="'phase'", phase=f"'{phase}'", on=day(on), warranty="null"
        )

    def final_row(number: int, warranty: str = later(365), on: str = ago(1)) -> str:
        return accept_sql.format(
            number=number, scope="'final'", phase="null", on=day(on), warranty=day(warranty)
        )

    def release_row(acceptance: int, on: str, amount: int) -> str:
        return release_sql.format(acceptance=acceptance, on=day(on), amount=amount)

    for statement, constraint in (
        (phase_row(5, "Framing"), "construction_acceptances_sequence_check"),
        (phase_row(1, "Framing", later(2)), "construction_acceptances_date_check"),
        (phase_row(1, "Roof"), "construction_acceptances_phase_check"),
        (phase_row(1, "Finishes"), "construction_acceptances_completed_check"),
        (phase_row(1, "Framing"), "construction_acceptances_items_check"),
    ):
        assert await _refused_by(app_pool, tenant, statement, project) == constraint, constraint
    assert (await move(b.c, project, 1, 0, "fixed")).status_code == 200
    assert (await move(b.c, project, 1, 1, "closed")).status_code == 200
    assert (await measure(b.c, project, 2, "3.3333", ago(8))).status_code == 200
    unbilled = await _refused_by(app_pool, tenant, final_row(1), project)
    assert unbilled == "construction_acceptances_billed_check"
    assert (await accept_phase(b, project, "Finishes", ago(8))).status_code == 200
    early = await _refused_by(app_pool, tenant, release_row(1, ago(7), 180), project)
    assert early == "construction_retainage_releases_billed_check"
    assert (await pay(b, project, ago(7))).status_code == 200  # 31007 billed, 4205: 420 held
    for statement, constraint in (
        (final_row(2, warranty=ago(1)), "construction_acceptances_warranty_check"),
        (phase_row(2, "Finishes"), "construction_acceptances_accepted_check"),
        (release_row(1, ago(9), 600), "construction_retainage_releases_date_check"),
        (release_row(1, ago(6), 599), "construction_retainage_releases_amount_check"),
    ):
        assert await _refused_by(app_pool, tenant, statement, project) == constraint, constraint
    # Finishes holds 1802 x 10% (180) + 4205 x 10% (420) = 600.
    freed = await release(b, project, 1, ago(6))
    assert freed.status_code == 200, freed.text
    assert freed.json()["release"]["amount_minor"] == 600
    twice = await _refused_by(app_pool, tenant, release_row(1, ago(5), 600), project)
    assert twice == "construction_retainage_releases_released_check"
    assert (await accept_final(b, project, ago(5))).status_code == 200
    after_final = await _refused_by(app_pool, tenant, phase_row(3, "Framing"), project)
    assert after_final == "construction_acceptances_accepted_check"
    # Closed by the final acceptance: a measurement, a pay application and an approval.
    measurement = (
        "insert into gba.construction_progress_measurements (tenant_id, project_id, number, "
        "change_order, budget_position, measured_on, quantity_to_date, note, created_by) "
        "select tenant_id, project_id, 4, null, 2, measured_on + 1, quantity_to_date, null, "
        "created_by from gba.construction_progress_measurements "
        "where project_id = %s and number = 3"
    )
    application = (
        "insert into gba.construction_pay_applications (tenant_id, project_id, number, "
        "period_end, previous_billed_minor, billed_to_date_minor, this_period_minor, "
        "rate_revision, rate_bp, retained_minor, due_minor, book_id, invoice_document_id, "
        "retainage_document_id, created_by) select tenant_id, project_id, 3, period_end + 1, "
        "billed_to_date_minor, billed_to_date_minor + 100, 100, rate_revision, rate_bp, 10, 90, "
        "book_id, invoice_document_id, retainage_document_id, created_by "
        "from gba.construction_pay_applications where project_id = %s and number = 2"
    )
    assert (await change(b.c, project, [add(phase="Finishes")])).status_code == 200
    approval = (
        "insert into gba.construction_change_order_decisions (tenant_id, project_id, number, "
        "decision, source, decided_by) select tenant_id, project_id, number, 'approved', "
        "'paper', created_by from gba.construction_change_orders "
        "where project_id = %s and number = 1"
    )
    for statement, constraint in (
        (measurement, "construction_progress_measurements_accepted_check"),
        (application, "construction_pay_applications_accepted_check"),
        (approval, "construction_change_order_decisions_accepted_check"),
    ):
        assert await _refused_by(app_pool, tenant, statement, project) == constraint, constraint
    # The final release takes what is still held: 2680 + 420 - 600 = 2500.
    rest = await release(b, project, 2, ago(4))
    assert rest.status_code == 200, rest.text
    assert rest.json()["release"]["amount_minor"] == 2500
    for table in TABLES:
        for statement in (
            f"update gba.{table} set tenant_id = tenant_id",
            f"delete from gba.{table}",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with tenant_transaction(app_pool, tenant) as conn:
                    await conn.execute(statement)
    assert await _counts(app_pool, tenant) == (2, 2)


# O6a-06 -----------------------------------------------------------------------------


async def test_without_the_module_acceptance_is_refused_and_scope_holds(
    billing: Billing,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    b = billing
    c = b.c
    world: BookingWorld = c.world
    project = await signed_at(c, TWO_LINES)
    assert (await rate(b, project, 0, 1000)).status_code == 200
    assert (await measure(c, project, 1, "10", ago(6))).status_code == 200
    assert (await pay(b, project, ago(5))).status_code == 200
    assert (await accept_phase(b, project, "Framing", ago(4))).status_code == 200
    # A manager of another branch does not see the project's acceptances.
    away, _ = seed_other_branch(c.owner_conn, world.a)
    elsewhere = c.member("manager", away)
    for path in ("acceptances", "acceptances/1"):
        hidden = await c.get(f"/projects/{project}/{path}", headers=elsewhere)
        assert error(hidden) == (404, "NOT_FOUND"), (path, hidden.text)
    hidden_write = await release(b, project, 1, ago(3), headers=elsewhere)
    assert error(hidden_write) == (404, "NOT_FOUND"), hidden_write.text
    # Another company sees nothing.
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await c.get(f"/projects/{project}/acceptances", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == NONE
    # Turned off: writes are refused and write nothing; reads continue.
    before = await _counts(app_pool, c.tenant)
    assert before == (1, 0)
    await Config(c.client, idp).publish(
        manager_a, c.tenant, 1, ["booking_resources", "counterparties"]
    )
    for answer in (
        await accept_phase(b, project, "Finishes", ago(1)),
        await release(b, project, 1, ago(3)),
    ):
        assert error(answer) == (409, "MODULE_DISABLED"), answer.text
    assert await _counts(app_pool, c.tenant) == before
    for path in ("acceptances", "acceptances/1"):
        read = await c.get(f"/projects/{project}/{path}")
        assert read.status_code == 200, (path, read.text)
