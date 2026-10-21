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
    "prepared",
    "approved",
    "reserved",
    "sent",
    "confirmed",
    "released",
    "cancelled",
    "payment_voided",
    "payment_corrected",
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
# A void or correction states that the earlier attestation was wrong; never a refund.
CorrectionAttestation = Literal["attested_erroneous_confirmation"]
PaymentState = Literal["confirmed", "corrected", "voided"]
# K3a: a human attests manual money; a provider payment comes from attested, decided facts.
PaymentAttestation = Literal["manual_attestation", "provider_observed"]
ProviderOperationKind = Literal["payment", "refund"]
# Not ready: an attested event undecided, a decision for review, or no success yet.
# `revoked`: not applied, and its connection or a verification config is revoked (K4a).
ProviderOperationState = Literal[
    "pending",
    "needs_review",
    "not_final",
    "revoked",
    "needs_link",
    "observed",
    "applied",
    "applied_with_conflict",
    "linked",
]
ObligationSource = Literal["invoice", "manual", "credit_refund"]
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


class ProviderPaymentConfirmInput(SettlementActionInput):
    """A finance user applies one observed provider operation (K3a, owner decision 1).

    There is no amount, date, account or reference here: the database takes them from the
    attested and decided facts and the registered clearing account. The allocations split
    exactly the provider's amount over lines of this settlement.
    """

    operation_id: UUID
    # The posting date; it must fall in an open period of the book.
    entry_date: date
    allocations: tuple[SettlementAllocationInput, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def one_line_per_obligation(self) -> Self:
        if len({line.obligation_id for line in self.allocations}) != len(self.allocations):
            raise ValueError("A confirmation names each obligation once")
        return self


class ProviderClearingAccountInput(Versioned):
    account_id: UUID


class ProviderClearingAccountView(Versioned):
    """The asset account a connection's observed gross money goes to; registered once."""

    business_id: UUID
    book_id: UUID
    connection_id: UUID
    account_id: UUID
    registered_by: UUID
    registered_at: AwareDatetime


class ProviderClearingAccountSummary(Strict):
    account_id: UUID
    registered_by: UUID
    registered_at: AwareDatetime


class ProviderConnectionSummary(Strict):
    """A provider connection of the book as the finance screen sees it; never a key or secret."""

    connection_id: UUID
    account_id: str
    revoked: bool
    clearing_account: ProviderClearingAccountSummary | None


class ProviderConnectionList(Versioned):
    business_id: UUID
    book_id: UUID
    items: tuple[ProviderConnectionSummary, ...]
    next_cursor: UUID | None


class ProviderOperationSummary(Strict):
    """One provider operation of the book and whether it can be, or was, applied."""

    operation_id: UUID
    connection_id: UUID
    kind: ProviderOperationKind
    provider_object_id: str
    parent_object_id: str | None
    currency: str
    # The observed success amount; absent until a success is decided.
    amount: str | None
    state: ProviderOperationState
    payment_id: UUID | None
    created_at: AwareDatetime


class ProviderOperationList(Versioned):
    business_id: UUID
    book_id: UUID
    items: tuple[ProviderOperationSummary, ...]
    next_cursor: UUID | None


class PaymentVoidInput(SettlementActionInput):
    """An attested erroneous confirmation: no money moved under this external identity.

    The identity stays bound to the payment; its journal is reversed on `entry_date`,
    which must fall in an open period, and its allocations return to the reserve.
    """

    attestation: CorrectionAttestation
    entry_date: date
    reason: str = Field(min_length=1, max_length=500)
    evidence_source: str = Field(min_length=1, max_length=200)

    @field_validator("reason", "evidence_source")
    @classmethod
    def single_line(cls, value: str) -> str | None:
        return single_line_text(value)


class PaymentCorrectInput(PaymentVoidInput):
    """The same external fact with corrected details; its identity never changes."""

    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT_PATTERN, strict=True)
    actual_external_date: date
    cash_account_id: UUID
    allocations: tuple[SettlementAllocationInput, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def one_line_per_obligation(self) -> Self:
        if len({line.obligation_id for line in self.allocations}) != len(self.allocations):
            raise ValueError("A correction names each obligation once")
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
    # The external payment a confirmed, voided or corrected fact recorded.
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


class PaymentRevisionView(Strict):
    """A void or correction recorded after the original confirmation."""

    revision: int = Field(ge=2)
    sequence: int = Field(ge=1)
    kind: Literal["voided", "corrected"]
    amount: str | None
    actual_external_date: date | None
    entry_date: date
    cash_account_id: UUID | None
    attestation: CorrectionAttestation
    reason: str
    evidence_source: str
    # The journal reversing the replaced version, and the replacement journal.
    reversal_entry_id: UUID
    entry_id: UUID | None
    recorded_by: UUID
    recorded_at: AwareDatetime
    allocations: tuple[PaymentAllocationView, ...] = Field(max_length=50)


class PaymentView(Versioned):
    """A manually attested external fact, or an observed provider payment (K3a).

    The amount, dates, account, journal and allocations describe the original
    confirmation; `effective_*` and `state` follow the latest revision. A provider payment
    names its operation; its voids and corrections are human attestations like any other.
    """

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
    attestation: PaymentAttestation
    provider_operation_id: UUID | None = None
    entry_id: UUID
    recorded_by: UUID
    recorded_at: AwareDatetime
    allocations: tuple[PaymentAllocationView, ...] = Field(min_length=1, max_length=50)
    state: PaymentState
    revision: int = Field(ge=1)
    effective_amount: str
    # Empty once voided: a voided payment confirms nothing.
    effective_allocations: tuple[PaymentAllocationView, ...] = Field(max_length=50)
    revisions: tuple[PaymentRevisionView, ...]


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


# K4b: why an operation needs review, what waits for attention, and acknowledgements.
ProviderDecisionOutcome = Literal["observed", "needs_review"]
ProviderDecisionReason = Literal[
    "success", "not_final", "conflicting_facts", "unkeyed_operation", "refund_without_payment"
]
ProviderOrphanReason = Literal["unkeyed_operation", "refund_without_payment"]


class ProviderDeliveryDifference(Strict):
    """One stored fact that a later delivery states differently; never a raw body."""

    field: str
    original: str
    delivered: str


class ProviderDeliveryView(Strict):
    received_at: AwareDatetime
    # The first 12 hex digits of the delivery digest: enough to tell deliveries apart.
    digest: str
    matches_original: bool
    differences: tuple[ProviderDeliveryDifference, ...]


class ProviderDecisionView(Strict):
    outcome: ProviderDecisionOutcome
    reason: ProviderDecisionReason
    decided_at: AwareDatetime


class ProviderEventView(Strict):
    event_id: UUID
    event_type: str
    created: AwareDatetime
    decision: ProviderDecisionView | None
    deliveries: tuple[ProviderDeliveryView, ...]


class ProviderLinkView(Strict):
    """K3b: the manual payment an operation is linked to; permanent history."""

    payment_id: UUID
    note: str
    linked_by: UUID
    linked_at: AwareDatetime


class ProviderLinkCandidate(Strict):
    """A manual payment of the book whose reference names the operation's provider ID."""

    payment_id: UUID
    state: PaymentState
    amount: str
    currency: str
    actual_external_date: date
    external_reference: str


class ProviderOperationDetail(Versioned):
    business_id: UUID
    book_id: UUID
    operation: ProviderOperationSummary
    events: tuple[ProviderEventView, ...]
    link: ProviderLinkView | None
    manual_payments: tuple[ProviderLinkCandidate, ...]


class ProviderLinkInput(Versioned):
    """Link an observed operation to the manual payment that recorded it (owner decision 1)."""

    payment_id: UUID
    note: str = Field(min_length=1, max_length=500, strict=True)

    @field_validator("note")
    @classmethod
    def single_line(cls, value: str) -> str:
        text = single_line_text(value)
        if text is None:
            raise ValueError("A note is required")
        return text


class ProviderLinkResult(Versioned):
    business_id: UUID
    book_id: UUID
    operation: ProviderOperationSummary
    link: ProviderLinkView


class ProviderAcknowledgementView(Strict):
    note: str
    acknowledged_by: UUID
    acknowledged_at: AwareDatetime


class ProviderFailureView(Strict):
    """K6a: failed decisions of an event in its current round; the error class only."""

    attempts: int
    error_class: str
    last_failed_at: AwareDatetime


class ProviderAttentionItem(Strict):
    """An attested event without a decision, or a decision without a provider operation.

    K6a: `failed` is an undecided event parked after five failed decisions; it waits for a
    finance user's release.
    """

    event_id: UUID
    connection_id: UUID
    kind: Literal["undecided", "no_operation", "failed"]
    event_type: str
    # The provider's own ID of the object (pi_, ch_ or re_), to find it at the provider.
    object_id: str
    created: AwareDatetime
    reason: ProviderOrphanReason | None
    acknowledgement: ProviderAcknowledgementView | None
    failure: ProviderFailureView | None = None


class ProviderAttentionList(Versioned):
    business_id: UUID
    book_id: UUID
    items: tuple[ProviderAttentionItem, ...]
    next_cursor: UUID | None


class ProviderAcknowledgeInput(Versioned):
    """A finance user's note that a decision without an operation was handled (owner decision 2)."""

    note: str = Field(min_length=1, max_length=500, strict=True)

    @field_validator("note")
    @classmethod
    def single_line(cls, value: str) -> str:
        text = single_line_text(value)
        if text is None:
            raise ValueError("A note is required")
        return text


class ProviderAcknowledgementResult(Versioned):
    business_id: UUID
    book_id: UUID
    item: ProviderAttentionItem


class ProviderReleaseInput(ProviderAcknowledgeInput):
    """K6a: a finance user's note that the cause of a parked event's failures was handled."""


class ProviderReleaseResult(Versioned):
    business_id: UUID
    book_id: UUID
    item: ProviderAttentionItem
