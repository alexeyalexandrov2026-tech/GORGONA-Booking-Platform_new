"""R6a: handover and return inspections of a rental booking (FAKE data).

docs/plan/PACKAGE_R6A_DESIGN_2026-11-07.md: one handover and one return per booking of its current
unit assignment, with the class meter reading, a level, a note and damage marks that may cite a
photo; insert-only and checked by the database.
"""

from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_documents import Documents, doc
from tests.integration.test_r1_rental_catalog import (
    ENABLED,
    Rental,
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
    rental,
)
from tests.integration.test_r2_rental_bookings import at, party
from tests.integration.test_r3a_rental_assignment import assign, booked
from tests.integration.test_r4a_rental_rates import SEAT, card
from tests.integration.test_r4b_rental_agreements import accept
from tests.integration.test_r4c_rental_extensions import agreed
from tests.support.fake_idp import FakeIdp
from tests.unit.test_file_validation import jpeg, pdf, png

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]


async def inspect(
    rental: Rental,
    booking: str,
    kind: str,
    meter: int | None = 1_000,
    marks: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/inspections",
        json={
            "schema_version": 1,
            "kind": kind,
            "meter": meter,
            "marks": marks or [],
            **fields,
        },
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


async def handed(rental: Rental) -> tuple[UUID, str]:
    """A booking with an agreement and its unit assigned (odometer class)."""
    _, (unit,), _, booking = await agreed(rental, 1)
    assert (await assign(rental, booking, unit)).status_code == 200
    return unit, booking


async def photos(rental: Rental, user: FakeUser, idp: FakeIdp) -> Documents:
    await Config(rental.client, idp).publish(user, rental.tenant, 1, [*ENABLED, "documents"])
    return Documents(rental.client, rental.tenant, user, idp)


async def photo(docs: Documents, data: bytes, media: str, name: str) -> dict[str, Any]:
    file_id = await docs.stored(data, media=media, name=name)
    subject = uuid7()
    saved = await docs.save(subject, doc(title=name, category="report", file_id=file_id))
    assert saved.status_code == 200, saved.text
    return {"document_id": str(subject), "revision": 1}


def mark(area: str, severity: str = "minor", **fields: Any) -> dict[str, Any]:
    return {"area": area, "severity": severity, **fields}


# R6a-01 -----------------------------------------------------------------------------


async def test_a_handover_and_a_return_record_the_unit(
    rental: Rental, idp: FakeIdp, manager_a: FakeUser
) -> None:
    docs = await photos(rental, manager_a, idp)
    door = await photo(docs, png(), "image/png", "FAKE door.png")
    bumper = await photo(docs, jpeg(), "image/jpeg", "FAKE bumper.jpg")
    unit, booking = await handed(rental)
    out = await inspect(
        rental,
        booking,
        "handover",
        meter=12_000,
        level=80,
        note="FAKE clean",
        marks=[mark("FAKE left door", photo=door)],
    )
    assert out.status_code == 200, out.text
    back = await inspect(
        rental,
        booking,
        "return",
        meter=12_450,
        level=40,
        marks=[
            mark("FAKE left door", photo=door, new=False),
            mark("FAKE rear bumper", "major", note="FAKE dent", photo=bumper, new=True),
        ],
    )
    assert back.status_code == 200, back.text
    view = (await rental.get(f"/bookings/{booking}/inspections")).json()
    assert view == back.json()
    first, second = view["inspections"]
    assert [(i["kind"], i["unit_id"], i["meter"], i["level"]) for i in view["inspections"]] == [
        ("handover", str(unit), 12_000, 80),
        ("return", str(unit), 12_450, 40),
    ]
    assert first["assignment_id"] == second["assignment_id"]
    assert first["note"] == "FAKE clean"
    assert second["note"] is None
    assert first["inspected_at"] <= second["inspected_at"]
    assert [(m["position"], m["area"], m["severity"], m["new"]) for m in first["marks"]] == [
        (1, "FAKE left door", "minor", False)
    ]
    assert [(m["position"], m["severity"], m["new"], m["note"]) for m in second["marks"]] == [
        (1, "minor", False, None),
        (2, "major", True, "FAKE dent"),
    ]
    assert second["marks"][1]["photo"] == bumper


async def test_a_class_without_a_meter_records_none(rental: Rental) -> None:
    van = uuid7()
    assert (await rental.klass(van, meter_kind="none")).status_code == 200
    unit = uuid7()
    assert (await rental.unit(unit, van)).status_code == 200
    home = rental.world.a.location_id
    assert (await card(rental, van, home, {"day": 5_000}, [SEAT])).is_success
    customer = await party(rental, "FAKE Renter", ["customer"])
    booking = await booked(rental, van, customer, at(1), at(3))
    assert (await accept(rental, booking, [])).is_success
    assert (await assign(rental, booking, unit)).status_code == 200
    metered = await inspect(rental, booking, "handover", meter=10)
    assert error(metered) == (409, "RENTAL_INSPECTION_INVALID"), metered.text
    out = await inspect(rental, booking, "handover", meter=None)
    assert out.status_code == 200, out.text
    back = await inspect(rental, booking, "return", meter=None)
    assert back.status_code == 200, back.text
    assert [i["meter"] for i in back.json()["inspections"]] == [None, None]


# R6a-02 -----------------------------------------------------------------------------


async def test_inspections_follow_the_booking(rental: Rental) -> None:
    _, booking = await handed(rental)
    early = await inspect(rental, booking, "return")
    assert error(early) == (409, "RENTAL_INSPECTION_STATE"), early.text
    assert (await inspect(rental, booking, "handover")).status_code == 200
    again = await inspect(rental, booking, "handover")
    assert error(again) == (409, "RENTAL_INSPECTION_STATE"), again.text
    assert (await inspect(rental, booking, "return", meter=1_000)).status_code == 200
    twice = await inspect(rental, booking, "return", meter=1_000)
    assert error(twice) == (409, "RENTAL_INSPECTION_STATE"), twice.text
    car, (unit,), customer, agreed_booking = await agreed(rental, 1)
    loose = await inspect(rental, agreed_booking, "handover")
    assert error(loose) == (409, "RENTAL_INSPECTION_STATE"), loose.text
    plain = await booked(rental, car, customer, at(10), at(11))
    assert (await assign(rental, plain, unit)).status_code == 200
    unsigned = await inspect(rental, plain, "handover")
    assert error(unsigned) == (409, "RENTAL_INSPECTION_STATE"), unsigned.text
    cancelled = await rental.client.post(
        f"{rental.base}/bookings/{agreed_booking}/cancellation",
        json={"schema_version": 1, "reason": "FAKE plans changed"},
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert cancelled.status_code == 200, cancelled.text
    gone = await inspect(rental, agreed_booking, "handover")
    assert error(gone) == (409, "RENTAL_INSPECTION_STATE"), gone.text
    missing = await inspect(rental, str(uuid7()), "handover")
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    desk = rental.member("front_desk", rental.world.a.location_id)
    denied = await inspect(rental, booking, "handover", headers=desk)
    assert denied.status_code == 403, denied.text


# R6a-03 -----------------------------------------------------------------------------


async def test_meters_levels_and_marks_are_checked(
    rental: Rental, idp: FakeIdp, manager_a: FakeUser
) -> None:
    docs = await photos(rental, manager_a, idp)
    paper = await photo(docs, pdf(), "application/pdf", "FAKE paper.pdf")
    _, booking = await handed(rental)
    for refused in (
        await inspect(rental, booking, "handover", meter=-1),
        await inspect(rental, booking, "handover", meter=10_000_001),
        await inspect(rental, booking, "handover", level=101),
        await inspect(rental, booking, "handover", marks=[mark("")]),
        await inspect(rental, booking, "handover", marks=[mark("x" * 101)]),
        await inspect(rental, booking, "handover", marks=[mark("FAKE roof", "total")]),
        await inspect(rental, booking, "handover", marks=[mark("FAKE roof")] * 51),
        await inspect(rental, booking, "pickup"),
    ):
        assert refused.status_code == 422, refused.text
    for invalid in (
        await inspect(rental, booking, "handover", meter=None),
        await inspect(rental, booking, "handover", marks=[mark("FAKE roof", new=True)]),
        await inspect(rental, booking, "handover", marks=[mark("FAKE roof", photo=paper)]),
        await inspect(
            rental,
            booking,
            "handover",
            marks=[mark("FAKE roof", photo={"document_id": str(uuid7()), "revision": 1})],
        ),
    ):
        assert error(invalid) == (409, "RENTAL_INSPECTION_INVALID"), invalid.text
    assert (await inspect(rental, booking, "handover", meter=5_000)).status_code == 200
    lower = await inspect(rental, booking, "return", meter=4_999)
    assert error(lower) == (409, "RENTAL_INSPECTION_INVALID"), lower.text
    view = (await rental.get(f"/bookings/{booking}/inspections")).json()
    assert [(i["kind"], i["meter"], i["marks"]) for i in view["inspections"]] == [
        ("handover", 5_000, [])
    ]


# R6a-04 -----------------------------------------------------------------------------


async def test_sql_keeps_inspections_whole(rental: Rental, app_pool: RuntimePool) -> None:
    _, booking = await handed(rental)
    out = await inspect(rental, booking, "handover", meter=2_000, marks=[mark("FAKE hood")])
    assert out.status_code == 200, out.text
    tenant = rental.tenant
    for statement in (
        "update gba.rental_inspections set meter = meter + 1",
        "delete from gba.rental_inspections",
        "update gba.rental_inspection_marks set severity = 'major'",
        "delete from gba.rental_inspection_marks",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    forged_return = (
        "insert into gba.rental_inspections (tenant_id, id, booking_id, assignment_id, kind, "
        "meter, inspected_by) select tenant_id, %s, booking_id, assignment_id, 'return', "
        "{meter}, inspected_by from gba.rental_inspections where booking_id = %s"
    )
    for meter in (1_999, "null"):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(forged_return.format(meter=meter), (uuid7(), booking))
    with pytest.raises(psycopg.errors.UniqueViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "insert into gba.rental_inspections (tenant_id, id, booking_id, assignment_id, "
                "kind, meter, inspected_by) select tenant_id, %s, booking_id, assignment_id, "
                "kind, meter, inspected_by from gba.rental_inspections where booking_id = %s",
                (uuid7(), booking),
            )
    late_mark = (
        "insert into gba.rental_inspection_marks (tenant_id, inspection_id, position, area, "
        "severity, new) select tenant_id, inspection_id, 2, 'FAKE late', 'minor', false "
        "from gba.rental_inspection_marks"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(late_mark)
    _, other = await handed(rental)
    stranger = (
        "insert into gba.rental_inspections (tenant_id, id, booking_id, assignment_id, kind, "
        "meter, inspected_by) select i.tenant_id, %s, b.id, i.assignment_id, 'handover', 1, "
        "i.inspected_by from gba.rental_inspections i join gba.rental_bookings b "
        "on b.tenant_id = i.tenant_id and b.id = %s"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(stranger, (uuid7(), other))
    view = (await rental.get(f"/bookings/{booking}/inspections")).json()
    assert [(i["kind"], i["meter"], len(i["marks"])) for i in view["inspections"]] == [
        ("handover", 2_000, 1)
    ]


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    _, booking = await handed(rental)
    branch = rental.member("manager", away)
    hidden = await inspect(rental, booking, "handover", headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    unseen = await rental.client.get(
        f"{rental.base}/bookings/{booking}/inspections", headers=branch
    )
    assert error(unseen) == (404, "NOT_FOUND"), unseen.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await inspect(rental, booking, "handover", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await inspect(rental, booking, "handover")
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    count = "select count(*) from gba.rental_inspections"
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        mine = await (await conn.execute(count)).fetchone()
    assert mine == (0,)
    async with tenant_transaction(app_pool, rental.world.b.tenant_id) as conn:
        row = await (await conn.execute(count)).fetchone()
    assert row == (0,)
