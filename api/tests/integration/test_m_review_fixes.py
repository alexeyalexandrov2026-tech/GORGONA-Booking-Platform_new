"""Package M review fixes (docs/plan/PACKAGE_M_REVIEW_FIXES_2026-10-26.md; FAKE data only).

R-01 transport drafts are frozen in FIN-03; R-02 a leg loaded short closes once its pickup is
departed; R-03 an invoiced order keeps its loads; R-05 and R-06 amounts are bounded and exact;
R-07 a concurrent identical pay component is the stored one.
"""

import asyncio
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.test_m1_transport_planning import leg, load
from tests.integration.test_m3_transport_events import INTERSTATE, event
from tests.integration.test_m7a_transport_money import (
    Money,
    accepted,
    client,
    code,
    enabled,
    idp,
    invoices,
    manager_a,
    manager_b,
    money,
    owner_a,
    owner_b,
    parties,
    payments,
    shipped,
)
from tests.integration.test_manual_accruals import AccrualWorld

pytestmark = pytest.mark.anyio
__all__ = [
    "accepted",
    "client",
    "enabled",
    "idp",
    "invoices",
    "manager_a",
    "manager_b",
    "money",
    "owner_a",
    "owner_b",
    "parties",
    "payments",
]


async def _wait_for_row_wait(owner_conn: psycopg.Connection) -> None:
    """Observe the request waiting on the held insert of the same key; a sleep proves no race."""
    for _ in range(300):
        await asyncio.sleep(0.01)
        row = owner_conn.execute(
            "select count(*) from pg_catalog.pg_locks "
            "where locktype = 'transactionid' and not granted"
        ).fetchone()
        if row and row[0] >= 1:
            return
    pytest.fail("the request must be observed waiting on the held pay component insert")


def _driver(m: Money, **changes: object) -> dict[str, object]:
    return {
        "counterparty_id": str(m.kit.payee),
        "role": "driver",
        "currency": "USD",
        "basis": "per_mile",
        "rate": "0.55",
        **changes,
    }


# RF-01 ------------------------------------------------------------------------------


async def test_transport_drafts_are_not_edited_through_fin03(money: Money) -> None:
    m = money
    order, trip = await shipped(m)
    assert (await m.rate(order, 0, basis="fixed", amount="1250.00")).status_code == 200
    billed = await m.post(f"/orders/{order}/invoice", m.invoice_body())
    assert billed.status_code == 200, billed.text
    documents = m.payments.settlements.invoices
    invoice = UUID(billed.json()["invoice"]["document_id"])
    cheaper = await documents.save(
        document=invoice, body=documents.draft_body(expected_revision=1, number="FAKE-CHEAP")
    )
    assert cheaper.status_code == 409, cheaper.text
    assert code(cheaper) == "FINANCIAL_DOCUMENT_LINKED"
    component = uuid7()
    assert (await m.put(f"/trips/{trip}/pay/{component}", _driver(m))).status_code == 200
    accrued = await m.post(f"/trips/{trip}/pay/{component}/accrue", m.accrual_body(miles="412.5"))
    assert accrued.status_code == 200, accrued.text
    accrual = UUID(accrued.json()["accrual"]["accrual"]["document_id"])
    accruals = AccrualWorld(documents)
    moved = await accruals.save(
        document=accrual, body=accruals.body(expected_revision=1, number="FAKE-MOVED")
    )
    assert moved.status_code == 409, moved.text
    assert code(moved) == "FINANCIAL_DOCUMENT_LINKED"
    # Both drafts are unchanged and still issue through their own documents.
    seen = await m.get(f"/orders/{order}/invoice")
    assert [x["amount"] for x in seen.json()["invoice"]["lines"]] == ["1250.00"]


# RF-02 ------------------------------------------------------------------------------


async def test_a_leg_loaded_short_closes_once_its_pickup_is_departed(money: Money) -> None:
    m = money
    order, pallets = uuid7(), uuid7()
    assert (await m.t.order(order, [load(pallets, 10)])).status_code == 200
    trip = uuid7()
    made = await m.t.trip(trip, INTERSTATE[:2], [leg(pallets, 10, 1, 2)])
    assert made.status_code == 200, made.text
    assert (await m.rate(order, 0, basis="fixed", amount="900.00")).status_code == 200
    component = uuid7()
    assert (await m.put(f"/trips/{trip}/pay/{component}", _driver(m))).status_code == 200
    loaded = await event(m.t, trip, "loaded", 1, quantities=((1, 8),), hour=9)
    assert loaded.status_code == 200, loaded.text
    # Still at the dock: two more pallets may be loaded, so the leg is open.
    waiting = await m.post(f"/orders/{order}/invoice", m.invoice_body())
    assert code(waiting) == "TRANSPORT_ORDER_NOT_BILLABLE", waiting.text
    assert (await event(m.t, trip, "departed", 1, hour=10)).status_code == 200
    delivered = await event(m.t, trip, "delivered", 2, quantities=((1, 8),), hour=15)
    assert delivered.status_code == 200, delivered.text
    billed = await m.post(f"/orders/{order}/invoice", m.invoice_body())
    assert billed.status_code == 200, billed.text
    accrued = await m.post(f"/trips/{trip}/pay/{component}/accrue", m.accrual_body(miles="180"))
    assert accrued.status_code == 200, accrued.text


# RF-03 ------------------------------------------------------------------------------


async def test_an_invoiced_order_keeps_its_loads(money: Money) -> None:
    m = money
    order, _ = await shipped(m)
    assert (await m.rate(order, 0, basis="fixed", amount="1250.00")).status_code == 200
    assert (await m.post(f"/orders/{order}/invoice", m.invoice_body())).status_code == 200
    view = (await m.t.get(f"/orders/{order}")).json()
    loads = [
        {k: x[k] for k in ("load_id", "description", "quantity", "unit", "weight_grams")}
        for x in view["loads"]
    ]
    revision = int(view["revision"])
    for changed in (
        [*loads, load(uuid7(), 4, "FAKE extra")],
        [{**loads[0], "quantity": loads[0]["quantity"] + 2}, loads[1]],
    ):
        refused = await m.t.order(order, changed, revision)
        assert refused.status_code == 409, refused.text
        assert code(refused) == "TRANSPORT_ORDER_INVOICED"
    renamed = await m.t.order(order, loads, revision, reference=f"FAKE-RN-{uuid7().hex[-6:]}")
    assert renamed.status_code == 200, renamed.text


# RF-05, RF-06 -----------------------------------------------------------------------


async def test_amounts_are_bounded_and_exact(money: Money) -> None:
    m = money
    order, trip = await shipped(m)
    too_fine = await m.rate(order, 0, basis="fixed", amount="1250.005")
    assert too_fine.status_code == 422, too_fine.text
    assert code(too_fine) == "TRANSPORT_AMOUNT_PRECISION"
    assert (await m.rate(order, 0, basis="per_mile", amount="1000000000000")).status_code == 200
    huge = await m.post(f"/orders/{order}/invoice", m.invoice_body(miles="100000"))
    assert huge.status_code == 422, huge.text
    assert code(huge) == "TRANSPORT_AMOUNT_TOO_LARGE"
    assert (await m.rate(order, 1, basis="fixed", amount="1250.00")).status_code == 200
    revenue = str(m.payments.settlements.invoices.counter)
    extra = {"description": "FAKE detention", "amount": "75.005", "account_id": revenue}
    fine_extra = await m.post(f"/orders/{order}/invoice", m.invoice_body(extra_lines=[extra]))
    assert fine_extra.status_code == 422, fine_extra.text
    assert code(fine_extra) == "TRANSPORT_AMOUNT_PRECISION"
    bonus = _driver(m, role="other", basis="fixed", rate=None, amount="40.005")
    fine_pay = await m.put(f"/trips/{trip}/pay/{uuid7()}", bonus)
    assert fine_pay.status_code == 422, fine_pay.text
    assert code(fine_pay) == "TRANSPORT_AMOUNT_PRECISION"
    # A per-mile rate keeps its precision.
    assert (
        await m.put(f"/trips/{trip}/pay/{uuid7()}", _driver(m, rate="0.555"))
    ).status_code == 200


# RF-07 ------------------------------------------------------------------------------


@pytest.mark.parametrize(("held_rate", "expected"), [("0.55", 200), ("0.60", 409)])
async def test_a_concurrent_pay_component_on_the_same_id_waits_and_compares(
    money: Money,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    held_rate: str,
    expected: int,
) -> None:
    m = money
    _, trip = await shipped(m)
    component = uuid7()
    tenant = m.payments.ledger.business
    async with tenant_transaction(app_pool, tenant) as conn:
        await conn.execute(
            "insert into gba.transport_pay_components (tenant_id, id, trip_id, counterparty_id, "
            "role, currency, basis, rate, created_by) "
            "values (%s, %s, %s, %s, 'driver', 'USD', 'per_mile', %s, %s)",
            (tenant, component, trip, m.kit.payee, held_rate, m.payments.ledger.user.user_id),
        )
        pending = asyncio.create_task(m.put(f"/trips/{trip}/pay/{component}", _driver(m)))
        try:
            await _wait_for_row_wait(owner_conn)
        except BaseException:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            raise
    answer = await pending
    assert answer.status_code == expected, answer.text
    if expected == 200:
        assert (answer.json()["component_id"], answer.json()["rate"]) == (str(component), "0.55")
    else:
        assert code(answer) == "TRANSPORT_PAY_COMPONENT_CONFLICT"
