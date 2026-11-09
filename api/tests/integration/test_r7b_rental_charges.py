"""R7b: damage charges and refunds of a rental agreement (FAKE data).

docs/plan/PACKAGE_R7B_DESIGN_2026-11-08.md: a damage charge on new return marks is its own FIN-03
receivable draft; a refund is a FIN-03 credit note against an issued obligation of the booking or
a recorded external refund; both need rental.approve and leave the settlement and the security as
they were.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch
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
from tests.integration.test_r6a_rental_inspections import inspect, mark
from tests.integration.test_r7a_rental_settlement import Books, books, rented, settle
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]
COUNTS = (
    "select (select count(*) from gba.rental_damage_charges), "
    "(select count(*) from gba.rental_refunds)"
)


# The FAKE business keeps its books in this zone; FIN-03 dates follow its "today".
ZONE = ZoneInfo("America/New_York")


def today() -> str:
    return datetime.now(ZONE).date().isoformat()


async def settled(rental: Rental, b: Books) -> tuple[str, dict[str, Any]]:
    """A booking returned with one old and two new marks and settled for 100.00 (today)."""
    booking = await rented(rental, {"day": 5_000})
    out = await inspect(rental, booking, "handover", meter=0, marks=[mark("FAKE door")])
    assert out.status_code == 200, out.text
    back = await inspect(
        rental,
        booking,
        "return",
        meter=10,
        marks=[
            mark("FAKE door", new=False),
            mark("FAKE bumper", "major", new=True),
            mark("FAKE mirror", new=True),
        ],
    )
    assert back.status_code == 200, back.text
    made = await settle(rental, b, booking, invoice_date=today(), due_date=None)
    assert made.status_code == 200, made.text
    view: dict[str, Any] = made.json()
    return booking, view


async def charge(
    rental: Rental,
    b: Books,
    booking: str,
    marks: list[int],
    amount: int,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/damage-charges",
        json={
            "schema_version": 1,
            "marks": marks,
            "amount": amount,
            "reason": "FAKE repaired damage",
            "book_id": str(b.book),
            "receivable_account_id": str(b.chart["1200"]),
            "revenue_account_id": str(b.chart["4100"]),
            "invoice_date": today(),
            "number": f"FAKE-DC-{uuid7().hex[-8:]}",
        },
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


async def refund(
    rental: Rental,
    booking: str,
    amount: int,
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/refunds",
        json={"schema_version": 1, "amount": amount, "reason": "FAKE goodwill", **fields},
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


def credit(document: str, number: str | None = None) -> dict[str, Any]:
    return {
        "method": "credit",
        "invoice_document_id": document,
        "credit_date": today(),
        "number": number or f"FAKE-CR-{uuid7().hex[-8:]}",
    }


def external(reference: str = "FAKE-BANK-1") -> dict[str, Any]:
    an_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    return {"method": "external", "reference": reference, "refunded_at": an_hour_ago}


async def issue(rental: Rental, b: Books, document: str) -> str:
    issued = await rental.client.post(
        f"/v1/businesses/{rental.tenant}/financial-documents/books/{b.book}/invoices/"
        f"{document}/issue",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "entry_date": today(),
            "attestation": "confirmed_account_treatment",
        },
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert issued.status_code == 200, issued.text
    obligation: str = issued.json()["obligation_id"]
    return obligation


async def principal(pool: RuntimePool, tenant: UUID, document: str) -> tuple[Any, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (
            await conn.execute(
                "select d.kind, v.direction, v.principal_minor, v.credited_obligation_id "
                "from gba.financial_documents d join gba.financial_document_versions v "
                "on v.tenant_id = d.tenant_id and v.book_id = d.book_id and v.document_id = d.id "
                "where d.id = %s order by v.revision desc limit 1",
                (document,),
            )
        ).fetchone()
    assert row is not None
    return tuple(row)


# R7b-01 and R7b-03 -------------------------------------------------------------------


async def test_a_damage_charge_and_two_refunds(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    booking, settlement = await settled(rental, b)
    first = await charge(rental, b, booking, [2], 4_000)
    assert first.status_code == 200, first.text
    (charged,) = first.json()["damage_charges"]
    assert (charged["number"], charged["marks"], charged["amount_minor"]) == (1, [2], 4_000)
    assert await principal(app_pool, rental.tenant, charged["invoice_document_id"]) == (
        "invoice",
        "receivable",
        4_000,
        None,
    )
    assert (await charge(rental, b, booking, [3], 1_000)).status_code == 200
    early = await refund(rental, booking, 3_000, **credit(settlement["invoice_document_id"]))
    assert error(early) == (409, "RENTAL_CHARGE_STATE"), early.text
    obligation = await issue(rental, b, settlement["invoice_document_id"])
    credited = await refund(rental, booking, 3_000, **credit(settlement["invoice_document_id"]))
    assert credited.status_code == 200, credited.text
    paid_back = await refund(rental, booking, 2_000, **external())
    assert paid_back.status_code == 200, paid_back.text
    view = (await rental.get(f"/bookings/{booking}/charges")).json()
    assert [(c["number"], c["marks"], c["amount_minor"]) for c in view["damage_charges"]] == [
        (1, [2], 4_000),
        (2, [3], 1_000),
    ]
    assert [(r["number"], r["method"], r["amount_minor"]) for r in view["refunds"]] == [
        (1, "credit", 3_000),
        (2, "external", 2_000),
    ]
    assert view["refunds"][1]["reference"] == "FAKE-BANK-1"
    note = view["refunds"][0]["credit_document_id"]
    assert await principal(app_pool, rental.tenant, note) == (
        "credit_note",
        "receivable",
        3_000,
        UUID(obligation),
    )
    assert (await rental.get(f"/bookings/{booking}/settlement")).json() == settlement
    security = await rental.client.get(
        f"{rental.base}/bookings/{booking}/security", headers=rental.headers
    )
    assert security.status_code == 404, security.text
    edited = await rental.client.put(
        f"/v1/businesses/{rental.tenant}/financial-documents/books/{b.book}/credits/{note}",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "credited_obligation_id": obligation,
            "counterparty_revision": 1,
            "credit_date": today(),
            "title": "FAKE edited here",
            "number": f"FAKE-CR-{uuid7().hex[-8:]}",
            "lines": [
                {
                    "line_id": str(uuid7()),
                    "credited_line_id": str(uuid7()),
                    "counter_account_id": str(b.chart["4100"]),
                    "description": "FAKE less",
                    "amount": "1.00",
                }
            ],
        },
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert error(edited) == (409, "FINANCIAL_DOCUMENT_LINKED"), edited.text


# R7b-02 -----------------------------------------------------------------------------


async def test_charges_and_refunds_follow_their_rules(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    open_booking = await rented(rental, {"day": 5_000})
    early = await charge(rental, b, open_booking, [1], 1_000)
    assert error(early) == (409, "RENTAL_CHARGE_STATE"), early.text
    unsettled = await refund(rental, open_booking, 1_000, **external())
    assert error(unsettled) == (409, "RENTAL_CHARGE_STATE"), unsettled.text
    booking, _ = await settled(rental, b)
    for basis in ([1], [4], [2, 2]):
        refused = await charge(rental, b, booking, basis, 1_000)
        assert error(refused) == (409, "RENTAL_CHARGE_STATE"), (basis, refused.text)
    assert (await charge(rental, b, booking, [2, 3], 5_000)).status_code == 200
    again = await charge(rental, b, booking, [3], 1_000)
    assert error(again) == (409, "RENTAL_CHARGE_STATE"), again.text
    for invalid in (
        await charge(rental, b, booking, [], 1_000),
        await charge(rental, b, booking, [2], 0),
        await refund(rental, booking, 0, **external()),
        await refund(rental, booking, 1_000, method="cash"),
    ):
        assert invalid.status_code == 422, invalid.text
    stranger = await refund(rental, booking, 1, **credit(str(uuid7())))
    assert error(stranger) == (409, "RENTAL_CHARGE_STATE"), stranger.text
    assert (await refund(rental, booking, 14_000, **external("FAKE-BANK-2"))).status_code == 200
    over = await refund(rental, booking, 1_001, **external("FAKE-BANK-3"))
    assert error(over) == (409, "RENTAL_REFUND_EXCEEDS"), over.text
    assert (await refund(rental, booking, 1_000, **external("FAKE-BANK-4"))).status_code == 200
    desk = rental.member("front_desk", rental.world.a.location_id)
    denied = await charge(rental, b, booking, [2], 1_000, headers=desk)
    assert denied.status_code == 403, denied.text
    refused = await refund(rental, booking, 1, headers=desk, **external())
    assert refused.status_code == 403, refused.text


# R7b-04 -----------------------------------------------------------------------------


async def test_sql_keeps_charges_and_refunds_whole(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    booking, _ = await settled(rental, b)
    assert (await charge(rental, b, booking, [2], 4_000)).status_code == 200
    assert (await refund(rental, booking, 1_000, **external())).status_code == 200
    tenant = rental.tenant
    for statement in (
        "update gba.rental_damage_charges set amount_minor = amount_minor + 1",
        "delete from gba.rental_damage_charges",
        "update gba.rental_damage_charge_marks set position = 3",
        "delete from gba.rental_damage_charge_marks",
        "update gba.rental_refunds set amount_minor = amount_minor + 1",
        "delete from gba.rental_refunds",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    over = (
        "insert into gba.rental_refunds (tenant_id, booking_id, number, amount_minor, reason, "
        "method, reference, refunded_at, recorded_by) select tenant_id, booking_id, {number}, "
        "{amount}, reason, 'external', 'FAKE-FORGED', refunded_at, recorded_by "
        "from gba.rental_refunds where booking_id = %s"
    )
    for number, amount in ((2, 13_001), (5, 1)):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(over.format(number=number, amount=amount), (booking,))
    twice = (
        "insert into gba.rental_damage_charge_marks (tenant_id, booking_id, number, position) "
        "select tenant_id, booking_id, number, position from gba.rental_damage_charge_marks "
        "where booking_id = %s"
    )
    with pytest.raises((psycopg.errors.UniqueViolation, psycopg.errors.CheckViolation)):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(twice, (booking,))
    view = (await rental.get(f"/bookings/{booking}/charges")).json()
    assert (len(view["damage_charges"]), len(view["refunds"])) == (1, 1)


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    booking, _ = await settled(rental, b)
    branch = rental.member("manager", away)
    hidden = await charge(rental, b, booking, [2], 1_000, headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    unseen = await rental.client.get(f"{rental.base}/bookings/{booking}/charges", headers=branch)
    assert error(unseen) == (404, "NOT_FOUND"), unseen.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await refund(rental, booking, 1, headers=other, **external())
    assert foreign.status_code in (403, 404), foreign.text
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await charge(rental, b, booking, [2], 1_000)
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        mine = await (await conn.execute(COUNTS)).fetchone()
    assert mine == (0, 0)
    async with tenant_transaction(app_pool, rental.world.b.tenant_id) as conn:
        row = await (await conn.execute(COUNTS)).fetchone()
    assert row == (0, 0)
