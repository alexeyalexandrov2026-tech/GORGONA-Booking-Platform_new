"""Strict version-one contracts of J2 and J3: accounts of materials, receipts, write-offs."""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from gorgona_booking.business.inventory_contracts import InventoryModel, RevisionInput

MAX_LINES = 100
MAX_QUANTITY = 999_999_999_999
MAX_AMOUNT = 999_999_999_999_999
ReceiptReason = Literal["purchase", "opening_balance", "surplus"]
# "used" debits material consumption; every other reason debits losses.
WriteOffReason = Literal["used", "damaged", "lost", "expired", "other"]
# Digits with at most three decimals. The scale of the material decides a quantity and
# the scale of the book's base currency decides an amount; extra decimals are refused.
type DecimalText = Annotated[
    str, StringConstraints(pattern=r"^(0|[1-9][0-9]{0,14})(\.[0-9]{1,3})?$")
]
type SupplierDocument = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
RULE_ACCOUNTS = (
    "inventory_account_id",
    "receipt_account_id",
    "opening_account_id",
    "surplus_account_id",
    "consumption_account_id",
    "loss_account_id",
    "difference_account_id",
)


def to_count(text: str, scale: int, limit: int, *, zero: bool = False) -> int:
    """A decimal string as a whole count of the smallest fraction; never rounded."""
    whole, _, fraction = text.partition(".")
    if len(fraction) > scale:
        raise ValueError(f"At most {scale} decimal places are accepted here")
    count: int = int(whole) * 10**scale + int(fraction.ljust(scale, "0") or "0")
    if not (0 if zero else 1) <= count <= limit:
        raise ValueError("The value is outside the supported range")
    return count


def from_count(count: int, scale: int) -> str:
    whole, fraction = divmod(count, 10**scale)
    return str(whole) if scale == 0 else f"{whole}.{fraction:0{scale}d}"


def issue_value(value: int, held: int, quantity: int) -> int:
    """What `quantity` of the `held` units takes of their `value`: the moving average.

    Rounded half up with whole numbers only. The whole quantity takes the whole value, so
    rounding strands nothing. The database computes the same amount and refuses any other.
    """
    if quantity == held:
        return value
    return (2 * value * quantity + held) // (2 * held)


class Part(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PostingRulesInput(RevisionInput):
    """Seven accounts of one book; a person chooses them."""

    inventory_account_id: UUID
    # An asset or an expense account, so a supplier's bill can use the same one.
    receipt_account_id: UUID
    opening_account_id: UUID
    surplus_account_id: UUID
    consumption_account_id: UUID
    loss_account_id: UUID
    difference_account_id: UUID

    @model_validator(mode="after")
    def inventory_stays_apart(self) -> Self:
        others = {getattr(self, name) for name in RULE_ACCOUNTS[1:]}
        if self.inventory_account_id in others:
            raise ValueError("The inventory account differs from the other six accounts")
        return self


class PostingRulesView(InventoryModel):
    business_id: UUID
    book_id: UUID
    revision: int
    inventory_account_id: UUID
    receipt_account_id: UUID
    opening_account_id: UUID
    surplus_account_id: UUID
    consumption_account_id: UUID
    loss_account_id: UUID
    difference_account_id: UUID


class Line(Part):
    item_id: UUID
    quantity: DecimalText


class ReceiptLine(Line):
    # What the whole line cost, in the base currency of the owner's book.
    amount: DecimalText


class ReceiptInput(InventoryModel):
    """One receipt, posted whole by one command; there is no server draft."""

    kind: Literal["receipt"]
    reason: ReceiptReason
    # The legal entity that owns the materials; its book takes the entry.
    legal_entity_id: UUID
    place_id: UUID
    document_date: date
    supplier_id: UUID | None = None
    supplier_document: SupplierDocument | None = None
    lines: tuple[ReceiptLine, ...] = Field(min_length=1, max_length=MAX_LINES)

    @model_validator(mode="after")
    def supplier_belongs_to_a_purchase(self) -> Self:
        named = self.supplier_id is not None or self.supplier_document is not None
        if named and self.reason != "purchase":
            raise ValueError("Only a purchase names a supplier")
        return self


class WriteOffLine(Line):
    """A quantity only: the database values an outbound line."""


class WriteOffInput(InventoryModel):
    """One write-off, posted whole by one command; the database values it."""

    kind: Literal["write_off"]
    reason: WriteOffReason
    legal_entity_id: UUID
    place_id: UUID
    document_date: date
    lines: tuple[WriteOffLine, ...] = Field(min_length=1, max_length=MAX_LINES)


# A document command names its kind; each kind has its own strict shape.
DocumentInput = Annotated[ReceiptInput | WriteOffInput, Field(discriminator="kind")]


class DocumentLine(Part):
    line_no: int
    item_id: UUID
    quantity: str
    # Absent for a reader without company-wide finance access.
    amount: str | None


class DocumentMoney(Part):
    book_id: UUID
    rule_revision: int
    currency: str
    total: str
    # A document with a zero total posts no journal entry.
    entry_id: UUID | None


class DocumentSummary(Part):
    document_id: UUID
    kind: str
    reason: str
    legal_entity_id: UUID
    place_id: UUID
    location_id: UUID
    document_date: date
    line_count: int
    created_at: AwareDatetime


class DocumentView(InventoryModel):
    business_id: UUID
    document_id: UUID
    kind: str
    reason: str
    legal_entity_id: UUID
    place_id: UUID
    location_id: UUID
    document_date: date
    supplier_id: UUID | None
    supplier_document: str | None
    created_at: AwareDatetime
    lines: tuple[DocumentLine, ...]
    # Absent for a reader without company-wide finance access.
    money: DocumentMoney | None


class DocumentList(InventoryModel):
    items: tuple[DocumentSummary, ...]
    next_cursor: UUID | None = None


class Balance(Part):
    item_id: UUID
    place_id: UUID
    location_id: UUID
    legal_entity_id: UUID
    quantity: str


class BalanceList(InventoryModel):
    items: tuple[Balance, ...]
    next_cursor: str | None = None


class Cost(Part):
    legal_entity_id: UUID
    item_id: UUID
    quantity: str
    value: str
    currency: str


class CostList(InventoryModel):
    items: tuple[Cost, ...]
    next_cursor: str | None = None
