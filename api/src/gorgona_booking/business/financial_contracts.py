"""Strict H1 financial-document commands and immutable reference receipts.

Amounts remain decimal strings at the API boundary. Currency-aware quantization
uses the existing G money conversion, after the book/currency is resolved.
"""

from datetime import date
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.ledger_contracts import CURRENCY_PATTERN, single_line_text, to_minor

Direction = Literal["receivable", "payable"]
InvoiceState = Literal["draft", "issued"]
FinancialCommandKind = Literal["invoice_draft", "invoice_issue"]
_MAX_REVISION = 2_147_483_646
_AMOUNT_PATTERN = r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?$"


def _required_text(value: str) -> str:
    clean = single_line_text(value)
    if clean is None:
        raise ValueError("Provide nonblank single-line text")
    return clean


class InvoiceLineInput(Strict):
    line_id: UUID
    counter_account_id: UUID
    description: str = Field(min_length=1, max_length=500)
    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT_PATTERN, strict=True)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        return _required_text(value)


class InvoiceDraftInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION)
    direction: Direction
    counterparty_id: UUID
    counterparty_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    invoice_date: date
    due_date: date | None = None
    control_account_id: UUID
    title: str = Field(min_length=1, max_length=200)
    number: str = Field(min_length=1, max_length=64)
    # One control line plus at most 199 counter lines fits G's 200-line bound.
    lines: tuple[InvoiceLineInput, ...] = Field(min_length=1, max_length=199)

    @field_validator("title", "number")
    @classmethod
    def single_line(cls, value: str) -> str:
        return _required_text(value)

    @model_validator(mode="after")
    def ordered_and_unique(self) -> Self:
        if self.due_date is not None and self.due_date < self.invoice_date:
            raise ValueError("Due date cannot precede invoice date")
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("Each invoice line has its own stable identifier")
        return self


class InvoiceIssueInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)
    entry_date: date
    attestation: Literal["confirmed_account_treatment"]


class InvoiceDocumentView(Versioned):
    business_id: UUID
    book_id: UUID
    document_id: UUID
    revision: StrictInt = Field(ge=1, le=_MAX_REVISION + 1)
    state: InvoiceState
    direction: Direction
    counterparty_id: UUID
    counterparty_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    minor_units: StrictInt
    invoice_date: date
    due_date: date | None
    control_account_id: UUID
    title: str
    number: str
    lines: tuple[InvoiceLineInput, ...] = Field(min_length=1, max_length=199)
    total: str
    entry_id: UUID | None
    obligation_id: UUID | None
    issued_on: date | None
    attestation: Literal["confirmed_account_treatment"] | None
    created_at: AwareDatetime

    @model_validator(mode="after")
    def issued_references(self) -> Self:
        if self.minor_units not in (0, 2, 3):
            raise ValueError("Unsupported currency scale")
        if self.due_date is not None and self.due_date < self.invoice_date:
            raise ValueError("Due date cannot precede invoice date")
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("Each invoice line has its own stable identifier")
        if sum(to_minor(line.amount, self.minor_units) for line in self.lines) != to_minor(
            self.total, self.minor_units
        ):
            raise ValueError("Invoice total must equal the exact line amounts")
        if self.state == "issued" and self.revision < 2:
            raise ValueError("An issued version follows a saved draft")
        refs = (self.entry_id, self.obligation_id, self.issued_on, self.attestation)
        if self.state == "issued" and any(value is None for value in refs):
            raise ValueError("An issued invoice has its actual obligation and journal references")
        if self.state == "draft" and any(value is not None for value in refs):
            raise ValueError("A draft cannot claim an issued money effect")
        return self


class FinancialReceipt(Strict):
    book_id: UUID
    document_id: UUID
    revision: StrictInt = Field(ge=1, le=_MAX_REVISION + 1)


class FinancialCommandReference(Versioned):
    """Finite recovery metadata only; never a saved financial command body."""

    operation: FinancialCommandKind
    book_id: UUID
    subject_id: UUID
    revision: StrictInt = Field(ge=1, le=_MAX_REVISION + 1)

    @model_validator(mode="after")
    def possible_issue_revision(self) -> Self:
        if self.operation == "invoice_issue" and self.revision < 2:
            raise ValueError("An issued version follows a saved draft")
        return self


class FinancialCommandStatus(Versioned):
    business_id: UUID
    key: str
    operation: FinancialCommandKind
    state: Literal["committed", "unresolved", "cancelled"]


class InvoiceSummary(Strict):
    document_id: UUID
    revision: StrictInt = Field(ge=1)
    state: InvoiceState
    direction: Direction
    counterparty_id: UUID
    currency: str
    invoice_date: date
    due_date: date | None
    title: str
    number: str
    total: str
    entry_id: UUID | None
    obligation_id: UUID | None
    created_at: AwareDatetime


class InvoiceList(Versioned):
    business_id: UUID
    book_id: UUID
    items: tuple[InvoiceSummary, ...]
    next_cursor: UUID | None
