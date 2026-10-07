"""Strict H2 settlement and obligation contracts (ADR-0024).

A settlement document plans exact amounts against obligations of one book, party,
direction and currency. Approval, reserve, release and cancel move no money. Amounts
cross the API as decimal strings; the scale comes from the settlement currency.
"""

from datetime import date
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.financial_contracts import Direction
from gorgona_booking.business.ledger_contracts import CURRENCY_PATTERN, single_line_text

SettlementEventKind = Literal[
    "prepared", "approved", "reserved", "sent", "confirmed", "released", "cancelled"
]
# partially_confirmed and confirmed are read from the payments of a held reserve.
SettlementStatus = Literal[
    "prepared",
    "approved",
    "reserved",
    "sent",
    "partially_confirmed",
    "confirmed",
    "released",
    "cancelled",
]
SettlementAction = Literal["approve", "reserve", "sent", "release", "cancel"]
Resolution = Literal["attested_no_payment"]
ObligationSource = Literal["invoice", "manual"]
_MAX_SEQUENCE = 2_147_483_646
_AMOUNT_PATTERN = r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?$"


class SettlementAllocationInput(Strict):
    obligation_id: UUID
    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT_PATTERN, strict=True)


class SettlementPrepareInput(Versioned):
    # A settlement document is created once; its planned allocations never change.
    expected_sequence: StrictInt = Field(ge=0, le=0)
    direction: Direction
    counterparty_id: UUID
    currency: str = Field(pattern=CURRENCY_PATTERN)
    allocations: tuple[SettlementAllocationInput, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def one_line_per_obligation(self) -> Self:
        if len({line.obligation_id for line in self.allocations}) != len(self.allocations):
            raise ValueError("A settlement names each obligation once")
        return self


class SettlementActionInput(Versioned):
    expected_sequence: StrictInt = Field(ge=1, le=_MAX_SEQUENCE)


class SettlementReleaseInput(SettlementActionInput):
    """A sent or unknown outcome is released only by an explicit human attestation."""

    resolution: Resolution | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    evidence_source: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("reason", "evidence_source")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        return single_line_text(value)

    @model_validator(mode="after")
    def attestation_is_complete(self) -> Self:
        stated = (self.reason is not None, self.evidence_source is not None)
        if self.resolution is None and any(stated):
            raise ValueError("A reason and evidence source belong to an attested resolution")
        if self.resolution is not None and not all(stated):
            raise ValueError("An attested resolution needs its reason and evidence source")
        return self


class PaymentConfirmInput(SettlementActionInput):
    """A human attests one external money fact; nothing here is provider-verified."""

    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT_PATTERN, strict=True)
    actual_external_date: date
    # The posting date; it must fall in an open period of the book.
    entry_date: date
    cash_account_id: UUID
    # Together with book and direction these two stay bound to one payment forever.
    source_account_alias: str = Field(min_length=1, max_length=100)
    external_reference: str = Field(min_length=1, max_length=200)
    attestation: Literal["manual_attestation"]
    allocations: tuple[SettlementAllocationInput, ...] = Field(min_length=1, max_length=50)

    @field_validator("source_account_alias", "external_reference")
    @classmethod
    def single_line(cls, value: str) -> str | None:
        return single_line_text(value)

    @model_validator(mode="after")
    def one_line_per_obligation(self) -> Self:
        if len({line.obligation_id for line in self.allocations}) != len(self.allocations):
            raise ValueError("A confirmation names each obligation once")
        return self


class SettlementCancelInput(SettlementActionInput):
    reason: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        return single_line_text(value)


class SettlementAllocationView(Strict):
    obligation_id: UUID
    amount: str
    confirmed: str
    # What this document still holds of the obligation right now.
    reserved: str


class SettlementEventView(Strict):
    sequence: int = Field(ge=1)
    kind: SettlementEventKind
    created_by: UUID
    created_at: AwareDatetime
    resolution: Resolution | None
    reason: str | None
    evidence_source: str | None
    # The external payment recorded by a confirmed fact.
    payment_id: UUID | None


class SettlementView(Versioned):
    business_id: UUID
    book_id: UUID
    settlement_id: UUID
    sequence: int = Field(ge=1)
    status: SettlementStatus
    direction: Direction
    counterparty_id: UUID
    currency: str
    minor_units: int = Field(ge=0, le=3)
    total: str
    confirmed: str
    reserved: str
    prepared_by: UUID
    approved_by: UUID | None
    # One authorized person may prepare and approve in H2; the view states it.
    approved_by_preparer: bool | None
    # A sent outcome whose remainder is neither confirmed nor explicitly resolved.
    outcome_unresolved: bool
    allocations: tuple[SettlementAllocationView, ...] = Field(min_length=1, max_length=50)
    events: tuple[SettlementEventView, ...] = Field(min_length=1)
    created_at: AwareDatetime


class SettlementSummary(Strict):
    settlement_id: UUID
    sequence: int = Field(ge=1)
    status: SettlementStatus
    direction: Direction
    counterparty_id: UUID
    currency: str
    total: str
    confirmed: str
    reserved: str
    created_at: AwareDatetime


class SettlementList(Versioned):
    business_id: UUID
    book_id: UUID
    items: tuple[SettlementSummary, ...]
    next_cursor: UUID | None


class SettlementReceipt(Strict):
    book_id: UUID
    settlement_id: UUID
    sequence: StrictInt = Field(ge=1, le=_MAX_SEQUENCE + 1)


class PaymentAllocationView(Strict):
    obligation_id: UUID
    amount: str


class PaymentView(Versioned):
    """A manually attested external fact; never a provider-verified payment."""

    business_id: UUID
    book_id: UUID
    payment_id: UUID
    settlement_id: UUID
    sequence: int = Field(ge=1)
    direction: Direction
    currency: str
    minor_units: int = Field(ge=0, le=3)
    amount: str
    actual_external_date: date
    entry_date: date
    cash_account_id: UUID
    source_account_alias: str
    external_reference: str
    attestation: Literal["manual_attestation"]
    entry_id: UUID
    recorded_by: UUID
    recorded_at: AwareDatetime
    allocations: tuple[PaymentAllocationView, ...] = Field(min_length=1, max_length=50)


class ObligationSummary(Strict):
    obligation_id: UUID
    source_kind: ObligationSource
    source_id: UUID
    source_revision: int = Field(ge=1)
    component: Literal["principal"]
    counterparty_id: UUID
    counterparty_revision: int = Field(ge=1)
    direction: Direction
    currency: str
    minor_units: int = Field(ge=0, le=3)
    control_account_id: UUID
    # principal >= paid + credited + reserved, all computed from immutable history.
    principal: str
    paid: str
    credited: str
    reserved: str
    available: str
    created_at: AwareDatetime


class ObligationView(ObligationSummary, Versioned):
    business_id: UUID
    book_id: UUID


class ObligationList(Versioned):
    business_id: UUID
    book_id: UUID
    items: tuple[ObligationSummary, ...]
    next_cursor: UUID | None
