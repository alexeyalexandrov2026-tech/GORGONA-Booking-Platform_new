"""PRO-01 Slice 4 unit contract tests (ADR-0038)."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.projects_billing import MatterInvoiceInput, PortfolioExportInput


def test_matter_invoice_input_validation() -> None:
    te_id = uuid7()
    inv = MatterInvoiceInput(
        schema_version=1,
        book_id=uuid7(),
        receivable_account_id=uuid7(),
        revenue_account_id=uuid7(),
        invoice_date=date(2026, 11, 21),
        due_date=date(2026, 12, 21),
        title="Legal Services Invoice #1",
        number="INV-PRO-001",
        time_entry_ids=[te_id],
    )
    assert inv.title == "Legal Services Invoice #1"

    # Must select at least one item
    with pytest.raises(ValidationError):
        MatterInvoiceInput(
            schema_version=1,
            book_id=uuid7(),
            receivable_account_id=uuid7(),
            revenue_account_id=uuid7(),
            invoice_date=date(2026, 11, 21),
            due_date=date(2026, 12, 21),
            title="Empty invoice",
        )

    # Duplicate IDs rejected
    with pytest.raises(ValidationError):
        MatterInvoiceInput(
            schema_version=1,
            book_id=uuid7(),
            receivable_account_id=uuid7(),
            revenue_account_id=uuid7(),
            invoice_date=date(2026, 11, 21),
            due_date=date(2026, 12, 21),
            title="Dup time",
            time_entry_ids=[te_id, te_id],
        )

    # Due date before invoice date rejected
    with pytest.raises(ValidationError):
        MatterInvoiceInput(
            schema_version=1,
            book_id=uuid7(),
            receivable_account_id=uuid7(),
            revenue_account_id=uuid7(),
            invoice_date=date(2026, 11, 21),
            due_date=date(2026, 11, 20),
            title="Bad dates",
            time_entry_ids=[te_id],
        )

    exp = PortfolioExportInput(schema_version=1, location_id=uuid7())
    assert exp.location_id is not None
