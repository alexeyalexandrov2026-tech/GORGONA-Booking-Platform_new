"""O2: the construction contract and change orders (package O, BUILD-01; FAKE data only).

docs/plan/PACKAGE_O2_DESIGN_2026-10-30.md: the accepted proposal is the frozen original contract;
change orders are insert-only and decided once; the current sum = original + approved changes.
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
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "construction", "idp", "manager_a", "manager_b"]
LOCK = "select 1 from gba.construction_projects where id = %s for update"


def add(description: str = "FAKE extra outlet", **changes: Any) -> dict[str, Any]:
    return {"action": "add", **line(description, **changes)}


def remove(position: int, quantity: str) -> dict[str, Any]:
    return {"action": "remove", "contract_position": position, "quantity": quantity}


async def signed(c: Construction, lines: list[dict[str, Any]] | None = None) -> UUID:
    """A project whose first estimate version was proposed and accepted on paper."""
    project = uuid7()
    assert (await c.project(project)).status_code == 200
    made = await c.estimate(project, lines or [line()])
    assert made.status_code == 200, made.text
    assert (await c.propose(project, 1)).status_code == 200
    contract = await accept(c, project, 1)
    assert contract.status_code == 200, contract.text
    return project


async def accept(
    c: Construction,
    project: UUID,
    version: int,
    headers: dict[str, str] | None = None,
    key: str | None = None,
    source: str = "paper",
) -> httpx.Response:
    body = {"version": version, "signatory": "FAKE Pat Homeowner", "source": source}
    return await c.send("POST", f"/projects/{project}/contract", body, headers, key)


async def change(
    c: Construction,
    project: UUID,
    lines: list[dict[str, Any]],
    days: int = 0,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    body = {"title": "FAKE change", "reason": "FAKE owner request", "days_delta": days}
    return await c.send(
        "POST", f"/projects/{project}/change-orders", {**body, "lines": lines}, headers
    )


async def decide(
    c: Construction,
    project: UUID,
    number: int,
    decision: str,
    headers: dict[str, str] | None = None,
    key: str | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {"decision": decision}
    if decision != "withdrawn":
        body["source"] = "email"
    return await c.send(
        "POST", f"/projects/{project}/change-orders/{number}/decision", body, headers, key
    )


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (
            await conn.execute(
                "select (select count(*) from gba.construction_contracts), "
                "(select count(*) from gba.construction_change_orders), "
                "(select count(*) from gba.construction_change_order_lines), "
                "(select count(*) from gba.construction_change_order_decisions)"
            )
        ).fetchone()
    assert row is not None
    return tuple(int(n) for n in row)


# O2-01 ------------------------------------------------------------------------------


async def test_only_the_latest_proposal_becomes_the_contract(
    construction: Construction,
) -> None:
    c = construction
    project = uuid7()
    assert (await c.project(project)).status_code == 200
    missing = await c.get(f"/projects/{project}/contract")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    assert (await c.estimate(project, [line()])).status_code == 200
    assert (await c.propose(project, 1)).status_code == 200
    assert (await c.estimate(project, [line(quantity="12")], based_on=1)).status_code == 200
    unproposed = await accept(c, project, 2)
    assert error(unproposed) == (409, "CONSTRUCTION_NOT_PROPOSED"), unproposed.text
    older = await accept(c, project, 1)
    assert error(older) == (409, "CONSTRUCTION_ESTIMATE_STALE"), older.text
    platform = await accept(c, project, 2, source="platform")
    assert platform.status_code == 422, platform.text
    assert (await c.propose(project, 2)).status_code == 200
    key = str(uuid7())
    made = await accept(c, project, 2, key=key)
    assert made.status_code == 200, made.text
    view = made.json()
    assert (view["version"], view["signatory"], view["source"]) == (
        2,
        "FAKE Pat Homeowner",
        "paper",
    )
    assert view["recorded_at"] is not None
    # 12 x 2500 = 30000 price; 12 x 1500 = 18000 cost; nothing changed yet.
    assert (view["original_price_minor"], view["original_cost_minor"]) == (30000, 18000)
    assert (view["current_price_minor"], view["current_cost_minor"]) == (30000, 18000)
    assert (view["approved_days"], view["change_orders"]) == (0, [])
    repeat = await accept(c, project, 2, key=key)
    assert (repeat.status_code, repeat.json()) == (200, view)
    second = await accept(c, project, 2)
    assert error(second) == (409, "CONSTRUCTION_CONTRACT_EXISTS"), second.text
    read = await c.get(f"/projects/{project}/contract")
    assert (read.status_code, read.json()) == (200, view)


# O2-02 ------------------------------------------------------------------------------


async def test_the_contract_freezes_the_estimate_and_the_customer(
    construction: Construction, app_pool: RuntimePool
) -> None:
    c = construction
    project = await signed(c)
    later = await c.estimate(project, [line(quantity="20")], based_on=1)
    assert error(later) == (409, "CONSTRUCTION_CONTRACT_EXISTS"), later.text
    other = uuid7()
    saved = await c.client.put(
        f"/v1/businesses/{c.tenant}/counterparties/{other}",
        json=card(display_name="FAKE Second Owner", roles=["customer"]),
        headers={**c.headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    moved = await c.project(project, revision=1, customer_id=str(other))
    assert error(moved) == (409, "CONSTRUCTION_CUSTOMER_FIXED"), moved.text
    renamed = await c.project(project, revision=1, name="FAKE kitchen, signed")
    assert renamed.status_code == 200, renamed.text
    assert (await change(c, project, [add()])).status_code == 200
    assert (await decide(c, project, 1, "approved")).status_code == 200
    tenant = c.tenant
    for statement in (
        "update gba.construction_contracts set signatory = 'FAKE'",
        "delete from gba.construction_contracts",
        "update gba.construction_change_orders set title = 'FAKE'",
        "delete from gba.construction_change_orders",
        "update gba.construction_change_order_lines set quantity = 1",
        "delete from gba.construction_change_order_lines",
        "update gba.construction_change_order_decisions set decision = 'rejected'",
        "delete from gba.construction_change_order_decisions",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    for statement, values in (
        (
            "insert into gba.construction_estimate_versions (tenant_id, project_id, version, "
            "created_by) select tenant_id, project_id, 2, created_by "
            "from gba.construction_estimate_versions where project_id = %s",
            (project,),
        ),
        (
            "update gba.construction_projects set customer_id = %s where id = %s",
            (other, project),
        ),
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement, values)


# O2-03 ------------------------------------------------------------------------------


async def test_change_orders_follow_the_contract_in_sequence(
    construction: Construction, app_pool: RuntimePool
) -> None:
    c = construction
    bare = uuid7()
    assert (await c.project(bare)).status_code == 200
    early = await change(c, bare, [add()])
    assert error(early) == (409, "CONSTRUCTION_NO_CONTRACT"), early.text
    project = await signed(c)  # one contract line: 10 sheets
    first = await change(c, project, [add()], days=2)
    assert first.status_code == 200, first.text
    assert (first.json()["number"], first.json()["state"]) == (1, "proposed")
    nowhere = await change(c, project, [remove(9, "1")])
    assert error(nowhere) == (422, "INVALID_REFERENCE"), nowhere.text
    too_much = await change(c, project, [remove(1, "11")])
    assert error(too_much) == (409, "CONSTRUCTION_SCOPE_EXCEEDED"), too_much.text
    second = await change(c, project, [remove(1, "4")])
    assert (second.status_code, second.json()["number"]) == (200, 2), second.text
    assert (await decide(c, project, 2, "approved")).status_code == 200
    # Six sheets remain: seven is refused; two proposals of six each are accepted as proposals,
    # but approving the second one would remove more than the contract holds.
    over = await change(c, project, [remove(1, "7")])
    assert error(over) == (409, "CONSTRUCTION_SCOPE_EXCEEDED"), over.text
    assert (await change(c, project, [remove(1, "6")])).json()["number"] == 3
    assert (await change(c, project, [remove(1, "6")])).json()["number"] == 4
    assert (await decide(c, project, 3, "approved")).status_code == 200
    late = await decide(c, project, 4, "approved")
    assert error(late) == (409, "CONSTRUCTION_SCOPE_EXCEEDED"), late.text
    shown = await c.get(f"/projects/{project}/change-orders/2")
    assert shown.status_code == 200, shown.text
    (removed,) = shown.json()["lines"]
    assert (removed["action"], removed["contract_position"], removed["description"]) == (
        "remove",
        1,
        "FAKE drywall",
    )
    # 4 x 1500 = 6000 cost and 4 x 2500 = 10000 price taken away.
    assert (removed["cost_minor"], removed["price_minor"]) == (-6000, -10000)
    listed = await c.get(f"/projects/{project}/change-orders")
    assert [(i["number"], i["state"]) for i in listed.json()["items"]] == [
        (1, "proposed"),
        (2, "approved"),
        (3, "approved"),
        (4, "proposed"),
    ]
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, c.tenant) as conn:
            await conn.execute(
                "insert into gba.construction_change_orders (tenant_id, project_id, number, "
                "title, days_delta, created_by) select tenant_id, project_id, 9, 'FAKE', 0, "
                "created_by from gba.construction_change_orders where project_id = %s "
                "and number = 1",
                (project,),
            )


# O2-04 ------------------------------------------------------------------------------


async def test_the_current_sum_is_the_original_plus_approved_changes(
    construction: Construction,
) -> None:
    c = construction
    project = await signed(
        c,
        [
            line(),  # 10 sheets: cost 15000, price 25000
            line("FAKE carpenter", kind="labor", quantity="8", cost=3000, price=5000, unit="hour"),
        ],
    )
    original = (await c.get(f"/projects/{project}/estimates/1")).json()
    assert (original["cost_total_minor"], original["price_total_minor"]) == (39000, 65000)
    # 1: an extra outlet, two of them, approved: +2000 cost, +4000 price, +3 days.
    assert (await change(c, project, [add(quantity="2", cost=1000, price=2000)], 3)).json()[
        "number"
    ] == 1
    assert (await decide(c, project, 1, "approved")).status_code == 200
    # 2: reprice the sheets (remove 10, add 10 at the new price), approved: +1000, +2000.
    reprice = [remove(1, "10"), add("FAKE drywall, moisture resistant", cost=1600, price=2700)]
    repriced = await change(c, project, reprice)
    assert (repriced.json()["cost_minor"], repriced.json()["price_minor"]) == (1000, 2000)
    assert (await decide(c, project, 2, "approved")).status_code == 200
    # 3 rejected, 4 withdrawn, 5 still proposed: none of them counts.
    assert (await change(c, project, [remove(2, "2")], -1)).status_code == 200
    assert (await decide(c, project, 3, "rejected")).status_code == 200
    assert (await change(c, project, [add(price=99999)])).status_code == 200
    assert (await decide(c, project, 4, "withdrawn")).status_code == 200
    assert (await change(c, project, [add(quantity="1", price=999)], 5)).status_code == 200
    view = (await c.get(f"/projects/{project}/contract")).json()
    assert (view["original_cost_minor"], view["original_price_minor"]) == (39000, 65000)
    assert (view["approved_cost_minor"], view["approved_price_minor"]) == (3000, 6000)
    assert (view["current_cost_minor"], view["current_price_minor"]) == (42000, 71000)
    assert view["approved_days"] == 3
    assert [(i["number"], i["state"], i["price_minor"]) for i in view["change_orders"]] == [
        (1, "approved", 4000),
        (2, "approved", 2000),
        (3, "rejected", -10000),
        (4, "withdrawn", 999990),
        (5, "proposed", 999),
    ]
    # The accepted version, the original contract, never changes.
    assert (await c.get(f"/projects/{project}/estimates/1")).json() == original


# O2-05 ------------------------------------------------------------------------------


async def test_a_decided_change_order_refuses_another_decision(
    construction: Construction,
) -> None:
    c = construction
    project = await signed(c)
    assert (await change(c, project, [add()])).status_code == 200
    staff = c.member("front_desk", None)
    refused = await decide(c, project, 1, "approved", headers=staff)
    assert refused.status_code == 403, refused.text
    unsigned = await accept(c, await _proposed(c), 1, headers=staff)
    assert unsigned.status_code == 403, unsigned.text
    key = str(uuid7())
    approved = await decide(c, project, 1, "approved", key=key)
    assert (approved.status_code, approved.json()["state"]) == (200, "approved"), approved.text
    assert approved.json()["source"] == "email"
    repeat = await decide(c, project, 1, "approved", key=key)
    assert (repeat.status_code, repeat.json()) == (200, approved.json())
    again = await decide(c, project, 1, "approved")
    assert error(again) == (409, "CONSTRUCTION_CHANGE_ORDER_DECIDED"), again.text
    withdrawn = await decide(c, project, 1, "withdrawn")
    assert error(withdrawn) == (409, "CONSTRUCTION_CHANGE_ORDER_DECIDED"), withdrawn.text
    sourceless = await c.send(
        "POST", f"/projects/{project}/change-orders/1/decision", {"decision": "rejected"}
    )
    assert sourceless.status_code == 422, sourceless.text
    unknown = await decide(c, project, 7, "approved")
    assert error(unknown) == (404, "NOT_FOUND"), unknown.text


async def _proposed(c: Construction) -> UUID:
    project = uuid7()
    assert (await c.project(project)).status_code == 200
    assert (await c.estimate(project, [line()])).status_code == 200
    assert (await c.propose(project, 1)).status_code == 200
    return project


# O2-06 ------------------------------------------------------------------------------


async def test_two_racing_approvals_leave_one_decision(
    construction: Construction, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    c = construction
    project = await signed(c)
    assert (await change(c, project, [add()])).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        c.tenant,
        LOCK,
        project,
        [decide(c, project, 1, "approved"), decide(c, project, 1, "approved")],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_CHANGE_ORDER_DECIDED")
    assert (await _counts(app_pool, c.tenant))[3] == 1


async def test_an_approval_racing_a_withdrawal_leaves_one_outcome(
    construction: Construction, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    c = construction
    project = await signed(c)
    assert (await change(c, project, [add()])).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        c.tenant,
        LOCK,
        project,
        [decide(c, project, 1, "approved"), decide(c, project, 1, "withdrawn")],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (won,) = [a for a in answers if a.status_code == 200]
    view = (await c.get(f"/projects/{project}/contract")).json()
    (only,) = view["change_orders"]
    assert only["state"] == won.json()["state"]
    counted = 25000 if only["state"] == "approved" else 0
    assert view["current_price_minor"] == 25000 + counted


async def test_two_racing_acceptances_leave_one_contract(
    construction: Construction, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    c = construction
    project = await _proposed(c)
    answers = await race(
        app_pool,
        test_database,
        c.tenant,
        LOCK,
        project,
        [accept(c, project, 1), accept(c, project, 1, source="email")],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (lost,) = [a for a in answers if a.status_code == 409]
    assert error(lost) == (409, "CONSTRUCTION_CONTRACT_EXISTS")
    assert (await _counts(app_pool, c.tenant))[0] == 1


# O2-07 ------------------------------------------------------------------------------


async def test_without_the_module_contract_writes_are_refused_and_scope_holds(
    construction: Construction,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    c = construction
    world: BookingWorld = c.world
    project = await signed(c)
    assert (await change(c, project, [add()])).status_code == 200
    pending = await _proposed(c)
    # A manager of another branch does not see the contract.
    away, _ = seed_other_branch(c.owner_conn, world.a)
    elsewhere = c.member("manager", away)
    hidden = await c.get(f"/projects/{project}/contract", headers=elsewhere)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    hidden_orders = await c.get(f"/projects/{project}/change-orders", headers=elsewhere)
    assert error(hidden_orders) == (404, "NOT_FOUND"), hidden_orders.text
    # Another company sees nothing.
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await c.get(f"/projects/{project}/contract", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == (0, 0, 0, 0)
    # Turned off: writes are refused and write nothing; reads continue.
    before = await _counts(app_pool, c.tenant)
    assert before == (1, 1, 1, 0)
    await Config(c.client, idp).publish(
        manager_a, c.tenant, 1, ["booking_resources", "counterparties"]
    )
    for answer in (
        await accept(c, pending, 1),
        await change(c, project, [add()]),
        await decide(c, project, 1, "approved"),
    ):
        assert error(answer) == (409, "MODULE_DISABLED"), answer.text
    assert await _counts(app_pool, c.tenant) == before
    read = await c.get(f"/projects/{project}/contract")
    assert (read.status_code, len(read.json()["change_orders"])) == (200, 1), read.text
