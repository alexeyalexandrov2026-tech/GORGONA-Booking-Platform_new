"""R9: the acceptance of rental (RENT-01) end to end through the API and PostgreSQL (FAKE data).

docs/plan/PACKAGE_R9_DESIGN_2026-11-13.md: a class booking is separate from the assignment of a
unit; a double issue of one unit is impossible; the payment security, the damage and the refund are
recorded separately; until customers answer on the platform through a grant, a member cannot record
that one did (R-09).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
    rental,
)
from tests.integration.test_r2_rental_bookings import at, book, party, query
from tests.integration.test_r3a_rental_assignment import assign, booked, units
from tests.integration.test_r3b_rental_blocks import block
from tests.integration.test_r4a_rental_rates import card
from tests.integration.test_r4b_rental_agreements import accept, change
from tests.integration.test_r4c_rental_extensions import extend
from tests.integration.test_r5a_rental_security import event, request
from tests.integration.test_r5a_rental_security import figures as held
from tests.integration.test_r6a_rental_inspections import inspect, mark
from tests.integration.test_r6b_rental_usage import figures as used
from tests.integration.test_r6b_rental_usage import returned_at, usage
from tests.integration.test_r7a_rental_settlement import books, settle
from tests.integration.test_r7a_rental_settlement import figures as settled
from tests.integration.test_r7b_rental_charges import charge, external, refund, today
from tests.integration.test_r7c_rental_reconciliation import documents, totals, view
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]
LATE = "2031-06-04T11:00:01+00:00"
DENT = "FAKE dent on the rear door"


def holding(rental: Rental, car: UUID) -> list[tuple[Any, ...]]:
    """The current unit holds of the class's bookings: booking, unit and period (owner read)."""
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        rows = rental.owner_conn.execute(
            "select a.booking_id, a.unit_id, lower(x.during), upper(x.during) "
            "from gba.rental_assignments a "
            "join gba.rental_units u on u.tenant_id = a.tenant_id and u.id = a.unit_id "
            "join gba.resource_allocations x on x.tenant_id = a.tenant_id "
            "and x.source_kind = 'rental_assignment' and x.source_id = a.id "
            "where u.class_id = %s and x.state = 'confirmed' "
            "and not exists (select 1 from gba.rental_assignment_releases l "
            "where l.tenant_id = a.tenant_id and l.assignment_id = a.id) "
            "order by lower(x.during), a.unit_id",
            (car,),
        ).fetchall()
    return [(str(b), u, s, e) for b, u, s, e in rows]


def counts(rental: Rental, car: UUID, booking: str) -> tuple[int, ...]:
    """What the rental left in the database, read back as the owner."""
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        row = rental.owner_conn.execute(
            "select (select count(*) from gba.rental_bookings where class_id = %(car)s), "
            "(select count(*) from gba.rental_booking_periods where booking_id = %(b)s), "
            "(select count(*) from gba.rental_agreement_versions v join gba.rental_agreements g "
            "on g.tenant_id = v.tenant_id and g.id = v.agreement_id where g.booking_id = %(b)s), "
            "(select count(*) from gba.rental_assignments where booking_id = %(b)s), "
            "(select count(*) from gba.rental_unit_blocks k join gba.rental_units u "
            "on u.tenant_id = k.tenant_id and u.id = k.unit_id where u.class_id = %(car)s), "
            "(select count(*) from gba.rental_security_events e join gba.rental_securities s "
            "on s.tenant_id = e.tenant_id and s.id = e.security_id where s.booking_id = %(b)s), "
            "(select count(*) from gba.rental_inspections where booking_id = %(b)s), "
            "(select count(*) from gba.rental_settlements where booking_id = %(b)s), "
            "(select count(*) from gba.rental_damage_charges where booking_id = %(b)s), "
            "(select count(*) from gba.rental_refunds where booking_id = %(b)s)",
            {"car": car, "b": booking},
        ).fetchone()
    assert row is not None
    return tuple(int(n) for n in row)


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def test_a_whole_rental_keeps_rent_01(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    home = rental.world.a.location_id
    car, (first, second) = await units(rental, 2)
    made = await card(
        rental,
        car,
        home,
        {"day": 5_000, "hour": 300},
        currency="USD",
        meter_allowance_per_day=100,
        excess_rate=25,
    )
    assert made.is_success, made.text
    customer = await party(rental, "FAKE Renter", ["customer"])

    # R-02: two class bookings take both cars, and neither holds a unit yet.
    booking = await booked(rental, car, customer, at(1), at(3))
    other = await booked(rental, car, customer, at(2), at(4))
    third = await book(rental, car, customer, at(2), at(3))
    assert error(third) == (409, "RENTAL_UNAVAILABLE"), third.text
    full = (await rental.get(query(car, home, at(2), at(3)))).json()
    assert (full["units"], full["booked"], full["available"]) == (2, 2, 0)
    assert "unit_id" not in (await rental.get(f"/bookings/{booking}")).json()
    assert holding(rental, car) == []

    # R-09: no customer answers on the platform yet, so a member cannot record that one did.
    claimed = await accept(rental, booking, [], source="platform")
    assert claimed.status_code == 422, claimed.text

    # R-04: the agreement freezes the accepted quote; a later rate card version leaves it.
    agreed = await accept(rental, booking, [])
    assert agreed.status_code == 200, agreed.text
    versions = agreed.json()["versions"]
    assert [(v["version"], v["rental_days"], v["total"], v["source"]) for v in versions] == [
        (1, 2, 10_000, "paper")
    ]
    later = await card(rental, car, home, {"day": 9_000}, currency="USD")
    assert later.json()["version"] == 2, later.text
    kept = (await rental.get(f"/bookings/{booking}/agreement")).json()
    assert [(v["version"], v["total"]) for v in kept["versions"]] == [(1, 10_000)]
    for answer in (
        await change(rental, booking, [], source="platform"),
        await extend(rental, booking, at(1), at(4), source="platform"),
    ):
        assert answer.status_code == 422, answer.text

    # R-03: assigning is its own fact; one unit is never issued to two overlapping bookings.
    assert (await assign(rental, booking, first)).status_code == 200
    twice = await assign(rental, other, first)
    assert error(twice) == (409, "RENTAL_UNIT_BUSY"), twice.text
    assert (await assign(rental, other, second)).status_code == 200
    assert holding(rental, car) == [
        (booking, first, instant(at(1)), instant(at(3))),
        (other, second, instant(at(2)), instant(at(4))),
    ]

    # R-03 and R-04: a maintenance block after the period; an extension is checked against it.
    service = await block(rental, first, at(4, 12), at(6))
    assert service.status_code == 200, service.text
    into = await extend(rental, booking, at(1), at(5))
    assert error(into) == (409, "RENTAL_UNIT_BUSY"), into.text
    longer = await extend(rental, booking, at(1), at(4))
    assert longer.status_code == 200, longer.text
    assert [(v["version"], v["rental_days"], v["total"]) for v in longer.json()["versions"]] == [
        (1, 2, 10_000),
        (2, 3, 15_000),
    ]
    assert holding(rental, car) == [
        (booking, first, instant(at(1)), instant(at(4))),
        (other, second, instant(at(2)), instant(at(4))),
    ]

    # R-05: the security has its own states; a capture needs a basis.
    assert (await request(rental, booking, amount=20_000)).status_code == 200
    taken = await event(rental, booking, "held", 20_000, reference="FAKE-TERM-R9")
    assert taken.status_code == 200, taken.text
    bare = await event(rental, booking, "captured", 5_000)
    assert bare.status_code == 422, bare.text
    captured = await event(rental, booking, "captured", 5_000, basis=DENT)
    assert held(captured.json()) == ("held", 20_000, 20_000, 5_000, 0, 0, 15_000)

    # R-06: handover and return record the meters and a new dent; overdue and excess are derived.
    out = await inspect(rental, booking, "handover", meter=1_000, marks=[mark("FAKE bumper")])
    assert out.status_code == 200, out.text
    back = await inspect(
        rental,
        booking,
        "return",
        meter=1_500,
        marks=[mark("FAKE bumper", new=False), mark("FAKE rear door", "major", new=True)],
    )
    assert back.status_code == 200, back.text
    returned_at(rental, booking, LATE)
    assert used((await usage(rental, booking)).json()) == ("returned", 2, 500, 300, 200, 5_000)

    # R-08: the invoice is the frozen rental, the excess and the late return; the security stays.
    made_invoice = await settle(rental, b, booking, invoice_date=today(), due_date=None)
    assert made_invoice.status_code == 200, made_invoice.text
    settlement = made_invoice.json()
    assert settled(settlement) == ("USD", 15_000, 5_000, 600, 2, 20_600)
    security = (await rental.get(f"/bookings/{booking}/security")).json()
    assert held(security) == ("held", 20_000, 20_000, 5_000, 0, 0, 15_000)

    # R-07: the damage charge needs rental.approve and a new return mark; the settlement stays.
    desk = rental.member("front_desk", home)
    denied = await charge(rental, b, booking, [2], 8_000, headers=desk)
    assert denied.status_code == 403, denied.text
    old = await charge(rental, b, booking, [1], 8_000)
    assert error(old) == (409, "RENTAL_CHARGE_STATE"), old.text
    damage = await charge(rental, b, booking, [2], 8_000)
    assert damage.status_code == 200, damage.text
    assert [
        (c["number"], c["marks"], c["amount_minor"]) for c in damage.json()["damage_charges"]
    ] == [(1, [2], 8_000)]
    assert (await rental.get(f"/bookings/{booking}/settlement")).json() == settlement

    # R-07 and R-05: the refund is its own record; the rest of the security is released once.
    paid_back = await refund(rental, booking, 1_000, **external("FAKE-BANK-R9"))
    assert paid_back.status_code == 200, paid_back.text
    freed = await event(rental, booking, "released", 15_000)
    assert held(freed.json()) == ("released", 20_000, 20_000, 5_000, 15_000, 0, 0)
    again = await event(rental, booking, "released", 1)
    assert error(again) == (409, "RENTAL_SECURITY_STATE"), again.text

    # R-08: the reconciliation derives every figure from the records.
    shown = await view(rental, booking)
    assert documents(shown) == [
        ("settlement", None, 20_600, "draft", 0, 0, 0),
        ("damage_charge", 1, 8_000, "draft", 0, 0, 0),
    ]
    assert [(r["method"], r["state"], r["amount_minor"]) for r in shown["refunds"]] == [
        ("external", "recorded", 1_000)
    ]
    assert held(shown["security"]) == ("released", 20_000, 20_000, 5_000, 15_000, 0, 0)
    assert totals(shown) == (28_600, 0, 0, 0, 0, 1_000, 0)

    # R-01: the rows are read back; the database refuses edits; with the module off, writes stop.
    assert counts(rental, car, booking) == (2, 1, 2, 2, 1, 3, 2, 1, 1, 1)
    for statement in (
        "update gba.rental_bookings set ends_at = ends_at",
        "update gba.rental_agreement_versions set total = 1",
        "update gba.rental_security_events set amount = 1",
        "update gba.rental_settlements set booking_id = booking_id",
        "delete from gba.rental_refunds",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, rental.tenant) as conn:
                await conn.execute(statement)
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await refund(rental, booking, 1_000, **external("FAKE-BANK-OFF"))
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    assert counts(rental, car, booking) == (2, 1, 2, 2, 1, 3, 2, 1, 1, 1)
