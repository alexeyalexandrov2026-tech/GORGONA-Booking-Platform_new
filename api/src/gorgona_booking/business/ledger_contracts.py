"""Ledger contracts: books, accounts, journal entries, periods and reports (ADR-0023).

Amounts cross the API as decimal strings and are stored as integer minor units of
their currency; the scale (0, 2 or 3 decimals) comes from the built-in ISO 4217
table, never from an assumption. One entry has one currency; reports never sum
currencies. Months are written `YYYY-MM`.
"""

import re
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, field_validator, model_validator

from gorgona_booking.business.contracts import Strict, Versioned

AccountType = Literal["asset", "liability", "equity", "revenue", "expense"]
Side = Literal["debit", "credit"]
SourceKind = Literal["manual", "opening", "reversal"]
SourceKindV2 = Literal[
    "manual",
    "opening",
    "reversal",
    "invoice",
    "accrual",
    "payment",
    "credit",
    "payment_correction",
    "credit_void",
]
# Journals owned by a financial document; G never reverses them generically.
H_OWNED_SOURCE_KINDS = (
    "invoice",
    "accrual",
    "payment",
    "credit",
    "payment_correction",
    "credit_void",
)
PeriodAction = Literal["closed", "reopened"]
PeriodState = Literal["open", "closed"]
ChartTemplate = Literal["starter", "empty"]

CURRENCY_PATTERN = r"^[A-Z]{3}$"
ACCOUNT_CODE_PATTERN = r"^[0-9A-Za-z][0-9A-Za-z.-]{0,31}$"
SOURCE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
MONTH_PATTERN = r"^[1-9][0-9]{3}-(0[1-9]|1[0-2])$"
MAX_MINOR = 999_999_999_999_999_999
_MAX_REVISION = 2_147_483_646
_AMOUNT = re.compile(r"(0|[1-9][0-9]{0,17})(?:\.([0-9]{1,3}))?")


def single_line_text(value: str | None) -> str | None:
    """Trimmed single-line text without C0, DEL or C1 controls (the database agrees)."""
    if value is None:
        return None
    text = value.strip()
    if not text or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in text):
        raise ValueError("Provide nonblank single-line text without control characters")
    return text


def to_minor(amount: str, scale: int) -> int:
    """A positive decimal string in minor units; more decimals than the scale is refused."""
    if scale not in (0, 2, 3):
        raise ValueError("Unsupported currency scale")
    match = _AMOUNT.fullmatch(amount)
    if match is None:
        raise ValueError("Write the amount as digits with an optional decimal point")
    whole, fraction = match.group(1), match.group(2) or ""
    if len(fraction) > scale:
        raise ValueError(f"This currency has {scale} decimal places")
    minor: int = int(whole) * 10**scale + int(fraction.ljust(scale, "0") or "0")
    if not 1 <= minor <= MAX_MINOR:
        raise ValueError("The amount must be positive and within the supported range")
    return minor


def from_minor(minor: int, scale: int) -> str:
    if scale not in (0, 2, 3):
        raise ValueError("Unsupported currency scale")
    sign = "-" if minor < 0 else ""
    whole, fraction = divmod(abs(minor), 10**scale)
    return f"{sign}{whole}" if scale == 0 else f"{sign}{whole}.{fraction:0{scale}d}"


def month(value: str) -> date:
    if re.fullmatch(MONTH_PATTERN, value) is None:
        raise ValueError("Write the month as YYYY-MM")
    return date(int(value[:4]), int(value[5:]), 1)


def month_text(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


class Currency(Strict):
    code: str
    minor_units: int = Field(ge=0, le=3)


class BookInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION)
    legal_entity_id: UUID
    base_currency: str = Field(pattern=CURRENCY_PATTERN)
    fiscal_year_start_month: StrictInt = Field(ge=1, le=12)
    accounting_start: date
    # Only when the book is created; omitted means the neutral starter chart.
    chart: ChartTemplate | None = None


class LedgerBookView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    book_id: UUID
    legal_entity_id: UUID
    revision: int = Field(ge=1)
    base_currency: str
    minor_units: int = Field(ge=0, le=3)
    fiscal_year_start_month: int = Field(ge=1, le=12)
    accounting_start: date
    # Once entries exist the base currency and accounting start are fixed.
    has_entries: bool
    created_at: AwareDatetime


class LedgerEntity(Strict):
    legal_entity_id: UUID
    code: str
    legal_name: str
    book: LedgerBookView | None


class LedgerOverview(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[LedgerEntity, ...]
    next_cursor: str | None
    currencies: tuple[Currency, ...]


class AccountInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION)
    # The code and type are fixed when the account is created.
    code: str = Field(pattern=ACCOUNT_CODE_PATTERN)
    type: AccountType
    name: str = Field(min_length=1, max_length=200)
    archived: StrictBool = False

    @field_validator("name")
    @classmethod
    def single_line(cls, value: str) -> str | None:
        return single_line_text(value)


class LedgerAccount(Strict):
    account_id: UUID
    code: str
    type: AccountType
    name: str
    archived: bool
    revision: int = Field(ge=1)
    has_lines: bool
    updated_at: AwareDatetime


class LedgerAccountView(LedgerAccount):
    schema_version: Literal[1] = 1
    business_id: UUID
    book_id: UUID


class LedgerAccountList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    book_id: UUID
    items: tuple[LedgerAccount, ...]
    next_cursor: str | None


class LineInput(Strict):
    account_id: UUID
    side: Side
    amount: str = Field(min_length=1, max_length=24)


class _PostingFields(Versioned):
    entry_date: date
    currency: str = Field(pattern=CURRENCY_PATTERN)
    memo: str | None = Field(default=None, min_length=1, max_length=500)
    lines: tuple[LineInput, ...] = Field(min_length=2, max_length=200)

    @field_validator("memo")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        return single_line_text(value)


class EntryInput(_PostingFields):
    source_kind: Literal["manual", "opening"] = "manual"
    # The business operation this entry records; it posts once per book.
    # Omitted, the entry id is the operation.
    source_id: str | None = Field(default=None, pattern=SOURCE_ID_PATTERN)


class InvoicePosting(_PostingFields):
    """Public internal posting seam; SQL requires the issued invoice lineage."""

    source_kind: Literal["invoice"] = "invoice"
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)


class AccrualPosting(_PostingFields):
    """Manual-accrual posting; SQL requires the issued manual accrual lineage."""

    source_kind: Literal["accrual"] = "accrual"
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)


class PaymentPosting(_PostingFields):
    """Externally attested payment; SQL requires its payment row and exact lines."""

    source_kind: Literal["payment"] = "payment"
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)


class CreditPosting(_PostingFields):
    """Credit note; SQL requires its issued credit note, exact lines and split."""

    source_kind: Literal["credit"] = "credit"
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)


class PaymentCorrectionPosting(_PostingFields):
    """Reversal or replacement of a payment version; SQL requires its payment revision."""

    source_kind: Literal["payment_correction"] = "payment_correction"
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)


class CreditVoidPosting(_PostingFields):
    """Mirror of a voided credit note; SQL requires its voided version and exact lines."""

    source_kind: Literal["credit_void"] = "credit_void"
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)


FinancialPosting = (
    InvoicePosting
    | AccrualPosting
    | PaymentPosting
    | CreditPosting
    | PaymentCorrectionPosting
    | CreditVoidPosting
)


class ReversalInput(Versioned):
    reversal_entry_id: UUID
    entry_date: date
    memo: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("memo")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        return single_line_text(value)


class JournalLine(Strict):
    line_no: int = Field(ge=1)
    account_id: UUID
    account_code: str
    account_name: str
    side: Side
    amount: str


class _JournalFields(Strict):
    entry_id: UUID
    entry_date: date
    period: str
    currency: str
    source_id: str
    memo: str | None
    # The sum of the debit lines, equal to the sum of the credit lines.
    total: str
    reverses_entry_id: UUID | None
    reversed_by_entry_id: UUID | None
    created_at: AwareDatetime


class JournalEntrySummary(_JournalFields):
    source_kind: SourceKind


class JournalEntrySummaryV2(_JournalFields):
    source_kind: SourceKindV2


class JournalEntryView(JournalEntrySummary):
    schema_version: Literal[1] = 1
    business_id: UUID
    book_id: UUID
    minor_units: int = Field(ge=0, le=3)
    lines: tuple[JournalLine, ...]


class JournalEntryList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    book_id: UUID
    items: tuple[JournalEntrySummary, ...]
    next_cursor: UUID | None


class _JournalVersionV2(Strict):
    schema_version: Literal[2] = 2

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Journal view version must be an integer")
        return value


class JournalEntryViewV2(JournalEntrySummaryV2, _JournalVersionV2):
    business_id: UUID
    book_id: UUID
    minor_units: int = Field(ge=0, le=3)
    lines: tuple[JournalLine, ...]


class JournalEntryListV2(_JournalVersionV2):
    business_id: UUID
    book_id: UUID
    items: tuple[JournalEntrySummaryV2, ...]
    next_cursor: UUID | None


class CloseInput(Versioned):
    expected_sequence: StrictInt = Field(ge=0, le=_MAX_REVISION)
    reason: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        return single_line_text(value)


class ReopenInput(Versioned):
    expected_sequence: StrictInt = Field(ge=1, le=_MAX_REVISION)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def single_line(cls, value: str) -> str | None:
        return single_line_text(value)


class PeriodEvent(Strict):
    sequence: int = Field(ge=1)
    action: PeriodAction
    reason: str | None
    decided_at: AwareDatetime


class LedgerPeriod(Strict):
    period: str
    state: PeriodState
    # 0 while the month was never closed; the next change expects this value.
    sequence: int = Field(ge=0)
    last_event: PeriodEvent | None


class LedgerPeriodView(LedgerPeriod):
    schema_version: Literal[1] = 1
    business_id: UUID
    book_id: UUID
    # Newest first.
    events: tuple[PeriodEvent, ...]


class LedgerPeriodList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    book_id: UUID
    # Months that were ever closed, newest first; every other month is open.
    items: tuple[LedgerPeriod, ...]
    next_cursor: str | None


class Balances(Strict):
    opening_debit: str
    opening_credit: str
    debit: str
    credit: str
    closing_debit: str
    closing_credit: str


class TrialBalanceRow(Balances):
    account_id: UUID
    code: str
    name: str
    type: AccountType
    archived: bool


class TrialBalance(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    book_id: UUID
    currency: str
    minor_units: int = Field(ge=0, le=3)
    period_from: str
    period_to: str
    # Every currency with entries in this book; each is reported on its own.
    currencies: tuple[str, ...]
    rows: tuple[TrialBalanceRow, ...]
    totals: Balances


class BookReceipt(Strict):
    book_id: UUID
    revision: int


class AccountReceipt(Strict):
    book_id: UUID
    account_id: UUID
    revision: int


class EntryReceipt(Strict):
    book_id: UUID
    entry_id: UUID


class PeriodReceipt(Strict):
    book_id: UUID
    period: str
    sequence: int


CommandKind = Literal["book", "account", "entry", "reverse", "close", "reopen"]
CommandState = Literal["committed", "cancelled", "unresolved"]


class CommandReference(Versioned):
    """Recovery identity only; no amounts, names, notes or credentials."""

    operation: CommandKind
    book_id: UUID
    subject_id: UUID | None = None
    revision: StrictInt | None = Field(default=None, ge=1, le=2147483647)
    period: str | None = Field(default=None, pattern=MONTH_PATTERN)
    sequence: StrictInt | None = Field(default=None, ge=1, le=2147483647)

    @model_validator(mode="after")
    def valid_reference(self) -> CommandReference:
        wanted = {
            "book": (False, True, False, False),
            "account": (True, True, False, False),
            "entry": (True, False, False, False),
            "reverse": (True, False, False, False),
            "close": (False, False, True, True),
            "reopen": (False, False, True, True),
        }[self.operation]
        actual = (
            self.subject_id is not None,
            self.revision is not None,
            self.period is not None,
            self.sequence is not None,
        )
        if actual != wanted:
            raise ValueError("Provide the exact reference fields for this command")
        return self


class CommandStatus(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    key: str
    operation: CommandKind
    state: CommandState
