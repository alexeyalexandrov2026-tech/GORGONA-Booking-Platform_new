"""N7: a brokered two-leg load end to end (package N acceptance, FAKE data only).

docs/plan/PACKAGE_N7_DESIGN_2026-10-29.md: the broker needs a current authority and an eligible
carrier; leg 1 goes to one carrier and leg 2 to another; a covered leg refuses a second acceptance;
a changed rate confirmation keeps its old version; the broker closes the leg with stop events and a
repeat changes nothing; each carrier's pay accrues once; the margin is derived, never stored.
"""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_external_payments as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.test_delegations import owner_a, owner_b, parties
from tests.integration.test_m1_transport_planning import accepted
from tests.integration.test_m3_transport_events import event
from tests.integration.test_m7a_transport_money import Money, code, money, shipped
from tests.integration.test_n1_broker_carriers import authority, carrier, profile
from tests.integration.test_n2_tenders import answer, offer
from tests.integration.test_n3_rate_confirmations import agree, proposal
from tests.integration.test_n5_carrier_pay import tender

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
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


async def test_a_brokered_two_leg_load_end_to_end(
    money: Money, world: BookingWorld, owner_conn: psycopg.Connection
) -> None:
    m = money
    t = m.t
    # Leg 1 (10 pallets) is delivered; leg 2 (6 crates) is still on the road.
    order, trip = await shipped(m, close=False)
    first = await carrier(t, "FAKE Carrier A")
    # N-01: no broker authority, no tender.
    no_broker = await t.put(f"/tenders/{uuid7()}", offer(trip, first, [1]))
    assert (no_broker.status_code, code(no_broker)) == (409, "TRANSPORT_BROKER_NOT_ELIGIBLE")
    assert (await t.put("/broker-authority", authority(0))).status_code == 200
    # N-02: a carrier without a profile is never tendered to.
    no_profile = await t.put(f"/tenders/{uuid7()}", offer(trip, first, [1]))
    assert (no_profile.status_code, code(no_profile)) == (409, "TRANSPORT_CARRIER_NOT_ELIGIBLE")
    assert no_profile.json()["error"]["details"]["reasons"] == ["no_profile"]
    second = await carrier(t, "FAKE Carrier B")
    for party in (first, second):
        assert (await t.put(f"/carriers/{party}/profile", profile(0))).status_code == 200
    # N-03 and decision 8: each leg is covered by a different carrier; a covered leg refuses more.
    rival = uuid7()
    assert (await t.put(f"/tenders/{rival}", offer(trip, first, [2]))).status_code == 200
    to_first = await tender(m, trip, first, [1])
    to_second = await tender(m, trip, second, [2], amount="400.00")
    covered = await answer(t, rival, "accepted")
    assert (covered.status_code, code(covered)) == (409, "TRANSPORT_LEG_TENDERED")
    # N-04: the change is in force once agreed; version 1 stays.
    changed = await t.put(f"/tenders/{to_second}/rate-confirmation", proposal(1, amount="450.00"))
    assert changed.status_code == 200, changed.text
    agreed = await agree(t, to_second, 2)
    assert agreed.status_code == 200, agreed.text
    confirmation = (await t.get(f"/tenders/{to_second}/rate-confirmation")).json()
    assert [(v["revision"], v["amount"], v["state"]) for v in confirmation["versions"]] == [
        (1, "400.00", "agreed"),
        (2, "450.00", "agreed"),
    ]
    assert confirmation["in_force"]["revision"] == 2
    # N-06: the broker closes leg 2 with stop events; a repeated event changes nothing.
    for kind, quantity in (("delivered", 4), ("refused", 2)):
        done = await event(
            t,
            trip,
            kind,
            3,
            quantities=((2, quantity),),
            source="dispatcher",
            source_id=f"FAKE-N7-{kind}",
            hour=21,
        )
        assert done.status_code == 200, done.text
    seen = done.json()["events"]
    again = await event(
        t,
        trip,
        "refused",
        3,
        quantities=((2, 2),),
        source="dispatcher",
        source_id="FAKE-N7-refused",
        hour=21,
    )
    assert again.status_code == 200, again.text
    assert again.json()["events"] == seen
    # N-07: each carrier's pay accrues once, for the version in force.
    for made, total in ((to_first, "900.00"), (to_second, "450.00")):
        paid = await m.post(f"/tenders/{made}/accrual", m.accrual_body())
        assert paid.status_code == 200, paid.text
        assert paid.json()["accrual"]["total"] == total
    twice = await m.post(f"/tenders/{to_second}/accrual", m.accrual_body())
    assert (twice.status_code, code(twice)) == (409, "TRANSPORT_ALREADY_ACCRUED")
    assert (await m.rate(order, 0, basis="fixed", amount="1500.00")).status_code == 200
    invoiced = await m.post(f"/orders/{order}/invoice", m.invoice_body())
    assert invoiced.status_code == 200, invoiced.text
    margin = (await m.get(f"/orders/{order}/margin")).json()
    assert (margin["revenue"], margin["carrier_cost"], margin["margin"]) == (
        "1500.00",
        "1350.00",
        "150.00",
    )
    assert sorted(item["tender_id"] for item in margin["tenders"]) == sorted(
        [str(to_first), str(to_second)]
    )
    assert margin["shared"] == []
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        rows = owner_conn.execute(
            "select (select count(*) from gba.transport_tenders), "
            "(select count(*) from gba.transport_tender_accruals), "
            "(select count(*) from information_schema.columns "
            "where table_schema = 'gba' and column_name like '%margin%')"
        ).fetchone()
    # The refused offers were never stored; the margin lives in no column.
    assert rows == (3, 2, 0)
