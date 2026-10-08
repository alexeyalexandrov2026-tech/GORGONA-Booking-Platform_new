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
# A manual accrual is the same immutable document shape with its own origin.
DocumentKind = Literal["invoice", "manual_accrual"]
FinancialCommandKind = Literal[
    "invoice_draft",
    "invoice_issue",
    "accrual_draft",
    "accrual_issue",
    "credit_draft",
    "credit_issue",
    "settlement_prepare",
    "settlement_approve",
    "settlement_reserve",
    "settlement_sent",
    "settlement_confirm",
    "settlement_release",
    "settlement_cancel",
    "settlement_payment_void",
    "settlement_payment_correct",
]
# Commands that can create the first immutable row of their subject.
_FIRST_COMMANDS = ("invoice_draft", "accrual_draft", "credit_draft", "settlement_prepare")
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
    kind: DocumentKind
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
    def possible_revision(self) -> Self:
        if self.operation not in _FIRST_COMMANDS and self.revision < 2:
            raise ValueError("This command follows an earlier saved fact")
        if self.operation == "settlement_prepare" and self.revision != 1:
            raise ValueError("A settlement is prepared once")
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


# Credit lines plus the unpaid and refund control lines fit G's 200-line bound.
_MAX_CREDIT_LINES = 198


class CreditLineInput(Strict):
    line_id: UUID
    # The line of the credited document that this line reduces.
    credited_line_id: UUID
    counter_account_id: UUID
    description: str = Field(min_length=1, max_length=500)
    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT_PATTERN, strict=True)
    # A counter account other than the credited line's needs a reason. It may cite the
    # G entry of this book and currency that changed the recognition; the citation is
    # context for a reviewer, never proof of the recognition of this document.
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    reference_entry_id: UUID | None = None

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("reason")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        return single_line_text(value)

    @model_validator(mode="after")
    def citation_has_reason(self) -> Self:
        if self.reference_entry_id is not None and self.reason is None:
            raise ValueError("A cited recognition entry needs its reason")
        return self


class CreditDraftInput(Versioned):
    """A credit note against one invoice or manual-accrual obligation of this book.

    Direction, counterparty, currency and control account follow that obligation.
    """

    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION)
    credited_obligation_id: UUID
    counterparty_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)
    credit_date: date
    due_date: date | None = None
    title: str = Field(min_length=1, max_length=200)
    number: str = Field(min_length=1, max_length=64)
    lines: tuple[CreditLineInput, ...] = Field(min_length=1, max_length=_MAX_CREDIT_LINES)

    @field_validator("title", "number")
    @classmethod
    def single_line(cls, value: str) -> str:
        return _required_text(value)

    @model_validator(mode="after")
    def ordered_and_unique(self) -> Self:
        if self.due_date is not None and self.due_date < self.credit_date:
            raise ValueError("Due date cannot precede the credit date")
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("Each credit line has its own stable identifier")
        return self


class CreditIssueInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)
    entry_date: date
    attestation: Literal["confirmed_account_treatment"]
    # Required exactly when part of the credit was already paid: that part becomes a
    # separate refund obligation with this control account.
    refund_control_account_id: UUID | None = None


class CreditNoteView(Versioned):
    business_id: UUID
    book_id: UUID
    document_id: UUID
    revision: StrictInt = Field(ge=1, le=_MAX_REVISION + 1)
    state: InvoiceState
    credited_obligation_id: UUID
    direction: Direction
    counterparty_id: UUID
    counterparty_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    minor_units: StrictInt
    credit_date: date
    due_date: date | None
    control_account_id: UUID
    title: str
    number: str
    lines: tuple[CreditLineInput, ...] = Field(min_length=1, max_length=_MAX_CREDIT_LINES)
    total: str
    entry_id: UUID | None
    issued_on: date | None
    attestation: Literal["confirmed_account_treatment"] | None
    # At issue: the unpaid part, now C of the credited obligation, and the paid part,
    # now the principal of a separate opposite-direction refund obligation.
    applied: str | None
    refund: str | None
    refund_control_account_id: UUID | None
    refund_obligation_id: UUID | None
    created_at: AwareDatetime

    @model_validator(mode="after")
    def issued_effect(self) -> Self:
        if self.minor_units not in (0, 2, 3):
            raise ValueError("Unsupported currency scale")
        if self.due_date is not None and self.due_date < self.credit_date:
            raise ValueError("Due date cannot precede the credit date")
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("Each credit line has its own stable identifier")
        total = to_minor(self.total, self.minor_units)
        if sum(to_minor(line.amount, self.minor_units) for line in self.lines) != total:
            raise ValueError("Credit total must equal the exact line amounts")
        issued = (self.entry_id, self.issued_on, self.attestation, self.applied, self.refund)
        refunded = (self.refund_control_account_id, self.refund_obligation_id)
        if self.state == "draft":
            if any(value is not None for value in (*issued, *refunded)):
                raise ValueError("A draft cannot claim an issued money effect")
            return self
        if self.revision < 2 or any(value is None for value in issued):
            raise ValueError("An issued credit has its actual journal and split")
        applied = _minor_or_zero(self.applied, self.minor_units)
        refund = _minor_or_zero(self.refund, self.minor_units)
        if applied + refund != total:
            raise ValueError("The unpaid part and the refund together are the credit")
        if any((value is not None) != (refund > 0) for value in refunded):
            raise ValueError("A refund obligation exists exactly when part was paid")
        return self


def _minor_or_zero(amount: str | None, scale: int) -> int:
    """Minor units of a nonnegative stored split; zero is a valid split part."""
    if amount is None:
        raise ValueError("An issued credit states its split")
    whole, _, fraction = amount.partition(".")
    if len(fraction) != scale or not whole.isdigit() or (fraction and not fraction.isdigit()):
        raise ValueError("A split part uses the currency scale")
    # Exactly `scale` decimals, so the digits together are the minor units.
    return int(whole + fraction)


class CreditSummary(Strict):
    document_id: UUID
    revision: StrictInt = Field(ge=1)
    state: InvoiceState
    credited_obligation_id: UUID
    direction: Direction
    counterparty_id: UUID
    currency: str
    credit_date: date
    title: str
    number: str
    total: str
    applied: str | None
    refund: str | None
    entry_id: UUID | None
    refund_obligation_id: UUID | None
    created_at: AwareDatetime


class CreditList(Versioned):
    business_id: UUID
    book_id: UUID
    items: tuple[CreditSummary, ...]
    next_cursor: UUID | None
