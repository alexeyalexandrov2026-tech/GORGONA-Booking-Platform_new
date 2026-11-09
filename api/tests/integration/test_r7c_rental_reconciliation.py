"""R7c: the reconciliation per rental agreement, derived on read (FAKE data).

docs/plan/PACKAGE_R7C_DESIGN_2026-11-08.md: the settlement and damage charge documents with their
FIN-03 state and balances, the refunds with their credit note and refund obligation, the security
figures and the totals; nothing is stored.
"""

from typing import Any
from uuid import UUID, uuid7

import httpx
import pytest

from gorgona_booking.db.pool import RuntimePool
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
from tests.integration.test_r5a_rental_security import event, request
from tests.integration.test_r7a_rental_settlement import Books, books, rented
from tests.integration.test_r7b_rental_charges import (
    charge,
    credit,
    external,
    issue,
    refund,
    settled,
    today,
)
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]


async def reconciliation(
    rental: Rental, booking: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    return await rental.client.get(
        f"{rental.base}/bookings/{booking}/reconciliation", headers=headers or rental.headers
    )


async def view(rental: Rental, booking: str) -> dict[str, Any]:
    found = await reconciliation(rental, booking)
    assert found.status_code == 200, found.text
    shown: dict[str, Any] = found.json()
    return shown


def root(rental: Rental, b: Books) -> str:
    return f"/v1/businesses/{rental.tenant}/financial-documents/books/{b.book}"


async def pay(rental: Rental, b: Books, obligation: str, customer: str, amount: str) -> None:
    """A FIN-03 payment of the obligation: prepare, approve, reserve, confirm (FAKE bank)."""
    settlement = uuid7()
    allocations = [{"obligation_id": obligation, "amount": amount}]
    steps: list[tuple[str, str, dict[str, Any]]] = [
        (
            "PUT",
            f"/settlements/{settlement}",
            {
                "schema_version": 1,
                "expected_sequence": 0,
                "direction": "receivable",
                "counterparty_id": customer,
                "currency": "USD",
                "allocations": allocations,
            },
        ),
        (
            "POST",
            f"/settlements/{settlement}/approve",
            {"schema_version": 1, "expected_sequence": 1},
        ),
        (
            "POST",
            f"/settlements/{settlement}/reserve",
            {"schema_version": 1, "expected_sequence": 2},
        ),
        (
            "POST",
            f"/settlements/{settlement}/confirmations/{uuid7()}",
            {
                "schema_version": 1,
                "expected_sequence": 3,
                "amount": amount,
                "actual_external_date": today(),
                "entry_date": today(),
                "cash_account_id": str(b.chart["1100"]),
                "source_account_alias": "FAKE main bank account",
                "external_reference": f"FAKE-TXN-{uuid7().hex[-8:]}",
                "attestation": "manual_attestation",
                "allocations": allocations,
            },
        ),
    ]
    for method, path, body in steps:
        sent = await rental.client.request(
            method,
            root(rental, b) + path,
            json=body,
            headers={**rental.headers, "Idempotency-Key": str(uuid7())},
        )
        assert sent.status_code == 200, (path, sent.text)


async def issue_credit(rental: Rental, b: Books, document: str, refund_account: UUID) -> None:
    issued = await rental.client.post(
        f"{root(rental, b)}/credits/{document}/issue",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "entry_date": today(),
            "attestation": "confirmed_account_treatment",
            "refund_control_account_id": str(refund_account),
        },
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert issued.status_code == 200, issued.text


def documents(shown: dict[str, Any]) -> list[tuple[Any, ...]]:
    keys = (
        "kind",
        "number",
        "amount_minor",
        "state",
        "principal_minor",
        "paid_minor",
        "open_minor",
    )
    return [tuple(d[k] for k in keys) for d in shown["documents"]]


def totals(shown: dict[str, Any]) -> tuple[Any, ...]:
    keys = (
        "charged_minor",
        "invoiced_minor",
        "paid_minor",
        "credited_minor",
        "open_minor",
        "refunded_external_minor",
        "refund_owed_minor",
    )
    return tuple(shown["totals"][k] for k in keys)


# R7c-01 and R7c-02 -------------------------------------------------------------------


async def test_documents_payments_charges_and_refunds_reconcile(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    booking, settlement = await settled(rental, b)
    first = await view(rental, booking)
    assert first["currency"] == "USD"
    assert documents(first) == [("settlement", None, 10_000, "draft", 0, 0, 0)]
    assert totals(first) == (10_000, 0, 0, 0, 0, 0, 0)
    assert first["security"] is None
    obligation = await issue(rental, b, settlement["invoice_document_id"])
    issued = await view(rental, booking)
    assert documents(issued) == [("settlement", None, 10_000, "issued", 10_000, 0, 10_000)]
    invoice = await rental.client.get(
        f"{root(rental, b)}/invoices/{settlement['invoice_document_id']}", headers=rental.headers
    )
    await pay(rental, b, obligation, invoice.json()["counterparty_id"], "100.00")
    paid = await view(rental, booking)
    assert documents(paid) == [("settlement", None, 10_000, "issued", 10_000, 10_000, 0)]
    assert (await charge(rental, b, booking, [2], 4_000)).status_code == 200
    credited = await refund(rental, booking, 3_000, **credit(settlement["invoice_document_id"]))
    assert credited.status_code == 200, credited.text
    note = credited.json()["refunds"][0]["credit_document_id"]
    drafted = await view(rental, booking)
    assert [
        (r["method"], r["state"], r["refund_obligation_minor"]) for r in drafted["refunds"]
    ] == [("credit", "draft", None)]
    await issue_credit(rental, b, note, b.chart["2100"])
    assert (await refund(rental, booking, 1_000, **external())).status_code == 200
    shown = await view(rental, booking)
    assert documents(shown) == [
        ("settlement", None, 10_000, "issued", 10_000, 10_000, 0),
        ("damage_charge", 1, 4_000, "draft", 0, 0, 0),
    ]
    assert [
        (r["number"], r["method"], r["state"], r["amount_minor"], r["refund_obligation_minor"])
        for r in shown["refunds"]
    ] == [(1, "credit", "issued", 3_000, 3_000), (2, "external", "recorded", 1_000, None)]
    assert totals(shown) == (14_000, 10_000, 10_000, 0, 0, 1_000, 3_000)


# R7c-03 -----------------------------------------------------------------------------


async def test_the_security_and_the_totals(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    booking, settlement = await settled(rental, b)
    assert (await request(rental, booking, amount=20_000)).status_code == 200
    assert (await event(rental, booking, "held", 20_000, reference="FAKE-TERM-9")).is_success
    taken = await event(rental, booking, "captured", 5_000, basis="FAKE damage")
    assert taken.is_success, taken.text
    shown = await view(rental, booking)
    security = shown["security"]
    assert (security["state"], security["amount"], security["held"], security["captured"]) == (
        "held",
        20_000,
        20_000,
        5_000,
    )
    assert security["remaining"] == 15_000
    await issue(rental, b, settlement["invoice_document_id"])
    assert (await charge(rental, b, booking, [2, 3], 2_500)).status_code == 200
    final = await view(rental, booking)
    rows = final["documents"]
    assert final["totals"]["charged_minor"] == sum(d["amount_minor"] for d in rows) == 12_500
    assert final["totals"]["invoiced_minor"] == sum(d["principal_minor"] for d in rows) == 10_000
    assert final["totals"]["open_minor"] == sum(d["open_minor"] for d in rows) == 10_000


# R7c-04 -----------------------------------------------------------------------------


async def test_scope_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    open_booking = await rented(rental, {"day": 5_000})
    early = await reconciliation(rental, open_booking)
    assert error(early) == (404, "NOT_FOUND"), early.text
    booking, _ = await settled(rental, b)
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    hidden = await reconciliation(rental, booking, rental.member("manager", away))
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await reconciliation(rental, booking, other)
    assert foreign.status_code in (403, 404), foreign.text
    missing = await reconciliation(rental, str(uuid7()))
    assert error(missing) == (404, "NOT_FOUND"), missing.text
