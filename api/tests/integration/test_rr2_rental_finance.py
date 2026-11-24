"""Package R review of refund lifecycle and immutable financial links."""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.seed import FakeUser
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    idp,
    manager_a,
    manager_b,
    rental,
)
from tests.integration.test_r7a_rental_settlement import books
from tests.integration.test_r7a_rental_settlement import invoice as invoice_view
from tests.integration.test_r7b_rental_charges import charge, credit, issue, refund, settled, today
from tests.integration.test_r7c_rental_reconciliation import issue_credit, pay, root, view
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]


async def test_issued_credit_takes_one_share_and_void_restores_it(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    book = await books(rental, app_pool, idp, manager_a)
    booking, settlement = await settled(rental, book)
    invoice = settlement["invoice_document_id"]
    obligation = await issue(rental, book, invoice)
    issued = await invoice_view(rental, book, invoice)
    await pay(rental, book, obligation, issued["counterparty_id"], "100.00")
    first = await refund(rental, booking, 6_000, **credit(invoice))
    assert first.is_success, first.text
    document = first.json()["refunds"][0]["credit_document_id"]
    await issue_credit(rental, book, document, book.chart["2100"])
    second = await refund(rental, booking, 4_000, **credit(invoice))
    assert second.is_success, second.text

    voided = await rental.client.post(
        f"{root(rental, book)}/credits/{document}/void",
        json={
            "schema_version": 1,
            "expected_revision": 2,
            "entry_date": today(),
            "attestation": "attested_erroneous_credit",
            "reason": "FAKE mistaken credit",
            "evidence_source": "FAKE incident record",
        },
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert voided.is_success, voided.text
    shown = await view(rental, booking)
    assert [(r["state"], r["amount_minor"]) for r in shown["refunds"]] == [
        ("voided", 6_000),
        ("draft", 4_000),
    ]
    replacement = await refund(rental, booking, 6_000, **credit(invoice))
    assert replacement.is_success, replacement.text


async def test_maximum_damage_reason_is_preserved(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    book = await books(rental, app_pool, idp, manager_a)
    booking, _ = await settled(rental, book)
    reason = "x" * 500
    reply = await charge(rental, book, booking, [2], 2_000, reason=reason)
    assert reply.is_success, reply.text
    assert reply.json()["damage_charges"][0]["reason"] == reason


async def test_a_rental_invoice_stays_linked_to_its_draft(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    book = await books(rental, app_pool, idp, manager_a)
    _, settlement = await settled(rental, book)
    with pytest.raises(psycopg.errors.CheckViolation) as refused:
        async with tenant_transaction(app_pool, rental.tenant) as conn:
            await conn.execute(
                "insert into gba.financial_document_versions "
                "(tenant_id, book_id, document_id, revision, state, direction, counterparty_id, "
                "counterparty_revision, currency, invoice_date, due_date, control_account_id, "
                "title, number, principal_minor, line_count, created_by) "
                "select tenant_id, book_id, document_id, revision + 1, state, direction, "
                "counterparty_id, counterparty_revision, currency, invoice_date, due_date, "
                "control_account_id, 'FAKE revised', number, principal_minor, line_count, "
                "created_by "
                "from gba.financial_document_versions where document_id = %s",
                (settlement["invoice_document_id"],),
            )
    assert refused.value.diag.constraint_name == "rental_financial_draft_linked_check"
