"""N7: a brokered two-leg load end to end (package N acceptance, FAKE data only).

docs/plan/PACKAGE_N7_DESIGN_2026-10-29.md, made true by N8 (review RN-09 and the record claims):
the broker needs a current authority and an eligible carrier; both legs are tendered before the trip
runs; leg 1 goes to carrier A, whose own company answers and records its leg through its grant;
leg 2 goes to carrier B, answered by email and recorded by the broker; a covered leg refuses carrier
A's second acceptance; a changed rate confirmation keeps its old version; a repeated event changes
nothing; each carrier's pay accrues once; the margin is derived, never stored.
"""

from datetime import UTC, datetime
from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_external_payments as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser
from tests.integration.test_delegations import Parties, owner_a, owner_b, parties
from tests.integration.test_m1_transport_planning import accepted, leg, load
from tests.integration.test_m3_transport_events import INTERSTATE, event
from tests.integration.test_m4_dispatcher_grants import acting, dispatcher
from tests.integration.test_m7a_transport_money import Money, code, money
from tests.integration.test_n1_broker_carriers import authority, carrier, profile
from tests.integration.test_n2_tenders import answer
from tests.integration.test_n3_rate_confirmations import agree, proposal
from tests.integration.test_n4_carrier_companies import (
    CARRIER,
    at,
    carrier_answer,
    fresh_offer,
    link,
)

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
    "dispatcher",
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
    money: Money,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
) -> None:
    m = money
    t = m.t
    today = datetime.now(UTC).date().isoformat()
    # A planned trip: leg 1 10 pallets stop 1 to 2, leg 2 6 crates stop 1 to 3; nothing has run.
    order, pallets, crates = uuid7(), uuid7(), uuid7()
    ordered = await t.order(order, [load(pallets, 10), load(crates, 6, "FAKE crates")])
    assert ordered.status_code == 200, ordered.text
    trip = uuid7()
    planned = await t.trip(trip, INTERSTATE, [leg(pallets, 10, 1, 2), leg(crates, 6, 1, 3)])
    assert planned.status_code == 200, planned.text
    first = await carrier(t, "FAKE Carrier A")
    # N-01: no broker authority, no tender.
    no_broker = await t.put(f"/tenders/{uuid7()}", fresh_offer(trip, first, [1]))
    assert (no_broker.status_code, code(no_broker)) == (409, "TRANSPORT_BROKER_NOT_ELIGIBLE")
    assert (await t.put("/broker-authority", authority(0, checked_on=today))).status_code == 200
    # N-02: a carrier without a profile is never tendered to.
    no_profile = await t.put(f"/tenders/{uuid7()}", fresh_offer(trip, first, [1]))
    assert (no_profile.status_code, code(no_profile)) == (409, "TRANSPORT_CARRIER_NOT_ELIGIBLE")
    assert no_profile.json()["error"]["details"]["reasons"] == ["no_profile"]
    second = await carrier(t, "FAKE Carrier B")
    for party in (first, second):
        saved = await t.put(f"/carriers/{party}/profile", profile(0, checked_on=today))
        assert saved.status_code == 200, saved.text
    # Carrier A is a company on the platform and acts through its grant (N-05, TMS-02).
    linked = await t.put(f"/carriers/{first}/company", link(world.b.tenant_id, 0))
    assert linked.status_code == 200, linked.text
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=CARRIER)
    a = acting(t, parties, dispatcher)
    # N-03 and decision 8: each leg to a different carrier, before any event.
    rival, to_first, to_second = uuid7(), uuid7(), uuid7()
    for made, party, legs, changes in (
        (rival, first, [2], {}),
        (to_first, first, [1], {}),
        (to_second, second, [2], {"amount": "400.00"}),
    ):
        offered = await t.put(f"/tenders/{made}", fresh_offer(trip, party, legs, **changes))
        assert offered.status_code == 200, offered.text
    took = await carrier_answer(a, to_first, "accepted")
    assert took.status_code == 200, took.text
    by_email = await answer(t, to_second, "accepted", at=at(0))
    assert by_email.status_code == 200, by_email.text
    covered = await carrier_answer(a, rival, "accepted")
    assert (covered.status_code, code(covered)) == (409, "TRANSPORT_LEG_TENDERED")
    # N-04: the change is in force once agreed; version 1 stays.
    changed = await t.put(
        f"/tenders/{to_second}/rate-confirmation", proposal(1, amount="450.00", proposed_at=at(0))
    )
    assert changed.status_code == 200, changed.text
    agreed = await agree(t, to_second, 2, occurred_at=at(0))
    assert agreed.status_code == 200, agreed.text
    confirmation = (await t.get(f"/tenders/{to_second}/rate-confirmation")).json()
    assert [(v["revision"], v["amount"], v["state"]) for v in confirmation["versions"]] == [
        (1, "400.00", "agreed"),
        (2, "450.00", "agreed"),
    ]
    assert confirmation["in_force"]["revision"] == 2
    # N-06: carrier A records its own leg; it may not close the stop shared with leg 2.
    for kind, stop, hour in (("loaded", 1, 9), ("delivered", 2, 15)):
        own = await event(
            a, trip, kind, stop, quantities=((1, 10),), source_id=f"FAKE-N7-A-{kind}", hour=hour
        )
        assert own.status_code == 200, own.text
    shared_stop = await event(a, trip, "departed", 1)
    assert (shared_stop.status_code, code(shared_stop)) == (403, "TRANSPORT_EVENT_OUT_OF_SCOPE")
    # The broker records leg 2 for carrier B; a repeated event changes nothing.
    loaded = await event(t, trip, "loaded", 1, quantities=((2, 6),), source_id="FAKE-N7-B", hour=9)
    assert loaded.status_code == 200, loaded.text
    for kind, quantity in (("delivered", 4), ("refused", 2)):
        done = await event(
            t, trip, kind, 3, quantities=((2, quantity),), source_id=f"FAKE-N7-{kind}", hour=21
        )
        assert done.status_code == 200, done.text
    seen = done.json()["events"]
    again = await event(
        t, trip, "refused", 3, quantities=((2, 2),), source_id="FAKE-N7-refused", hour=21
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
    # N8 (RN-04): a paid tender is neither withdrawn nor repriced.
    late = await answer(t, to_second, "withdrawn", at=at(0))
    assert (late.status_code, code(late)) == (409, "TRANSPORT_ALREADY_ACCRUED")
    assert (await m.rate(order, 0, basis="fixed", amount="1500.00")).status_code == 200
    invoiced = await m.post(f"/orders/{order}/invoice", m.invoice_body())
    assert invoiced.status_code == 200, invoiced.text
    margin = (await m.get(f"/orders/{order}/margin")).json()
    assert (margin["revenue"], margin["carrier_cost"], margin["margin"]) == (
        "1500.00",
        "1350.00",
        "150.00",
    )
    assert margin["currencies_differ"] is False
    assert sorted(item["tender_id"] for item in margin["tenders"]) == sorted(
        [str(to_first), str(to_second)]
    )
    assert margin["shared"] == []
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        rows = owner_conn.execute(
            "select (select count(*) from gba.transport_tenders), "
            "(select count(*) from gba.transport_tender_accruals), "
            "(select count(*) from gba.transport_tender_answers where source = 'platform'), "
            "(select count(*) from information_schema.columns "
            "where table_schema = 'gba' and column_name like '%margin%')"
        ).fetchone()
    # The refused offers were never stored; carrier A answered on the platform; no margin column.
    assert rows == (3, 2, 1, 0)
