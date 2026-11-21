"""SUPPLY-01 Slice 1 (ADR-0039): Multi-warehouse WMS bins, goods-owner isolation
(company legal entity vs 3PL bailor), lot/batch & serial tracking, and STOCK-01 linked movements.
"""

import re
from datetime import UTC, date, datetime
from typing import Literal, Self
from uuid import UUID, uuid7

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, field_validator, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules, stock
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.business.stock_contracts import (
    ReceiptInput,
    ReceiptLine,
    TransferInput,
    TransferLine,
    WriteOffInput,
    WriteOffLine,
    from_count,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DomainError,
    InvalidReferenceError,
    NotFoundError,
)

SUPPLY_MODULE = "supply"

OwnerKind = Literal["company_entity", "counterparty_3pl"]
BinKind = Literal["receiving", "storage", "picking", "production", "quarantine", "shipping"]
LotStatus = Literal["active", "quarantine", "expired"]
SerialState = Literal["in_stock", "reserved", "shipped", "consumed", "returned"]
MovementKind = Literal[
    "inbound_putaway",
    "bin_relocation",
    "outbound_pick",
    "return_putaway",
    "production_issue",
    "production_output",
    "production_return",
]
MovementDirection = Literal["in", "out", "relocate"]


class SupplyNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class SupplyRevisionConflictError(ConflictError):
    code = "SUPPLY_REVISION_CONFLICT"


class SupplyStateError(ConflictError):
    code = "SUPPLY_INVALID_STATE"


class SupplyOwnerMismatchError(ConflictError):
    code = "SUPPLY_OWNER_MISMATCH"


class SupplyInsufficientLotError(ConflictError):
    code = "SUPPLY_INSUFFICIENT_LOT_BALANCE"


class SupplyValidationError(DomainError):
    code = "SUPPLY_VALIDATION_ERROR"


def _check_ready() -> None:
    current = modules.MODULES_BY_ID[SUPPLY_MODULE]
    if not current.enableable or not at_least(current.readiness, modules.MINIMUM_READINESS):
        raise SupplyNotReadyError(
            "Supply chain and WMS module has not been accepted", module_id=SUPPLY_MODULE
        )


def _clean_code(value: str, max_len: int = 64, allow_dots: bool = False) -> str:
    cleaned = value.strip().upper()
    pattern = r"^[A-Z0-9][A-Z0-9._-]*$" if allow_dots else r"^[A-Z0-9][A-Z0-9_-]*$"
    if not cleaned or len(cleaned) > max_len:
        raise ValueError(f"Code must be 1..{max_len} characters")
    if not re.match(pattern, cleaned):
        raise ValueError("Code contains unsupported characters")
    return cleaned


def _clean_single_line(value: str, max_len: int = 200) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_len:
        raise ValueError(f"Text must be 1..{max_len} characters")
    if any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in cleaned):
        raise ValueError("Control characters are not allowed")
    return cleaned


class GoodsOwnerInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    code: str
    display_name: str
    owner_kind: OwnerKind
    legal_entity_id: UUID | None = None
    counterparty_id: UUID | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value, 64)

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_single_line(value, 200)

    @model_validator(mode="after")
    def valid_owner_target(self) -> Self:
        if self.owner_kind == "company_entity":
            if self.legal_entity_id is None or self.counterparty_id is not None:
                raise ValueError(
                    "company_entity owner requires legal_entity_id and no counterparty_id"
                )
        else:
            if self.counterparty_id is None or self.legal_entity_id is not None:
                raise ValueError(
                    "counterparty_3pl owner requires counterparty_id and no legal_entity_id"
                )
        return self


class GoodsOwnerView(Strict):
    schema_version: Literal[1] = 1
    goods_owner_id: UUID
    location_id: UUID
    code: str
    display_name: str
    owner_kind: OwnerKind
    legal_entity_id: UUID | None
    counterparty_id: UUID | None
    is_active: bool
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class GoodsOwnerList(Strict):
    schema_version: Literal[1] = 1
    items: list[GoodsOwnerView]


class WarehouseBinInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    place_id: UUID
    zone_code: str
    bin_code: str
    bin_kind: BinKind = "storage"
    dedicated_owner_id: UUID | None = None
    is_active: bool = True

    @field_validator("zone_code")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        return _clean_code(value, 32)

    @field_validator("bin_code")
    @classmethod
    def valid_bin(cls, value: str) -> str:
        return _clean_code(value, 64)


class WarehouseBinView(Strict):
    schema_version: Literal[1] = 1
    bin_id: UUID
    location_id: UUID
    place_id: UUID
    zone_code: str
    bin_code: str
    bin_kind: BinKind
    dedicated_owner_id: UUID | None
    is_active: bool
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class WarehouseBinList(Strict):
    schema_version: Literal[1] = 1
    items: list[WarehouseBinView]


class LotInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    goods_owner_id: UUID
    item_id: UUID
    lot_code: str
    manufactured_on: date | None = None
    expires_on: date | None = None
    status: LotStatus = "active"
    unit_cost_minor: int = Field(default=0, ge=0, le=999_999_999_999_999)
    notes: str | None = None

    @field_validator("lot_code")
    @classmethod
    def valid_lot_code(cls, value: str) -> str:
        return _clean_code(value, 64, allow_dots=True)

    @field_validator("notes")
    @classmethod
    def valid_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_single_line(value, 500)

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        if (
            self.manufactured_on is not None
            and self.expires_on is not None
            and self.expires_on < self.manufactured_on
        ):
            raise ValueError("expires_on cannot precede manufactured_on")
        return self


class LotView(Strict):
    schema_version: Literal[1] = 1
    lot_id: UUID
    location_id: UUID
    goods_owner_id: UUID
    item_id: UUID
    lot_code: str
    manufactured_on: date | None
    expires_on: date | None
    status: LotStatus
    unit_cost_minor: int
    notes: str | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class LotList(Strict):
    schema_version: Literal[1] = 1
    items: list[LotView]


class LotBalanceView(Strict):
    schema_version: Literal[1] = 1
    balance_id: UUID
    location_id: UUID
    place_id: UUID
    bin_id: UUID
    goods_owner_id: UUID
    item_id: UUID
    lot_id: UUID
    quantity: int
    updated_at: AwareDatetime


class LotBalanceList(Strict):
    schema_version: Literal[1] = 1
    items: list[LotBalanceView]


class SerialUnitView(Strict):
    schema_version: Literal[1] = 1
    serial_id: UUID
    location_id: UUID
    place_id: UUID
    bin_id: UUID
    goods_owner_id: UUID
    item_id: UUID
    lot_id: UUID
    serial_code: str
    state: SerialState
    recorded_by: UUID
    recorded_at: AwareDatetime


class SerialUnitList(Strict):
    schema_version: Literal[1] = 1
    items: list[SerialUnitView]


class InboundPutawayInput(Versioned):
    location_id: UUID
    bin_id: UUID
    goods_owner_id: UUID
    item_id: UUID
    lot_id: UUID
    quantity: int = Field(ge=1, le=999_999_999_999)
    movement_kind: Literal["inbound_putaway", "return_putaway"] = "inbound_putaway"
    serial_codes: list[str] = Field(default_factory=list, max_length=200)
    stock_document_id: UUID | None = None
    stock_line_no: int | None = Field(default=None, ge=1, le=100)
    # Optional convenience: post a real STOCK-01 receipt automatically for company_entity owners
    auto_stock_receipt_date: date | None = None
    auto_stock_receipt_reason: Literal["purchase", "opening_balance", "surplus"] = "purchase"
    auto_stock_receipt_amount: str | None = None
    reference_code: str | None = None

    @field_validator("serial_codes")
    @classmethod
    def clean_serials(cls, values: list[str]) -> list[str]:
        cleaned = [_clean_code(v, 64, allow_dots=True) for v in values]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Duplicate serial codes are not allowed")
        return cleaned

    @model_validator(mode="after")
    def valid_serial_count(self) -> Self:
        if self.serial_codes and len(self.serial_codes) != self.quantity:
            raise ValueError("When serial_codes are provided, their count must equal quantity")
        if (self.stock_document_id is None) != (self.stock_line_no is None):
            raise ValueError("stock_document_id and stock_line_no must be provided together")
        return self


class BinRelocationInput(Versioned):
    location_id: UUID
    from_bin_id: UUID
    to_bin_id: UUID
    goods_owner_id: UUID
    item_id: UUID
    lot_id: UUID
    quantity: int = Field(ge=1, le=999_999_999_999)
    serial_codes: list[str] = Field(default_factory=list, max_length=200)
    document_date: date | None = None
    reference_code: str | None = None

    @field_validator("serial_codes")
    @classmethod
    def clean_serials(cls, values: list[str]) -> list[str]:
        cleaned = [_clean_code(v, 64, allow_dots=True) for v in values]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Duplicate serial codes are not allowed")
        return cleaned

    @model_validator(mode="after")
    def valid_relocation(self) -> Self:
        if self.from_bin_id == self.to_bin_id:
            raise ValueError("Destination bin must differ from source bin")
        if self.serial_codes and len(self.serial_codes) != self.quantity:
            raise ValueError("When serial_codes are provided, their count must equal quantity")
        return self


class OutboundPickInput(Versioned):
    location_id: UUID
    bin_id: UUID
    goods_owner_id: UUID
    item_id: UUID
    lot_id: UUID
    quantity: int = Field(ge=1, le=999_999_999_999)
    serial_codes: list[str] = Field(default_factory=list, max_length=200)
    stock_document_id: UUID | None = None
    stock_line_no: int | None = Field(default=None, ge=1, le=100)
    auto_stock_write_off_date: date | None = None
    auto_stock_write_off_reason: Literal["used", "damaged", "lost", "expired", "other"] = "used"
    reference_code: str | None = None

    @field_validator("serial_codes")
    @classmethod
    def clean_serials(cls, values: list[str]) -> list[str]:
        cleaned = [_clean_code(v, 64, allow_dots=True) for v in values]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Duplicate serial codes are not allowed")
        return cleaned

    @model_validator(mode="after")
    def valid_outbound(self) -> Self:
        if self.serial_codes and len(self.serial_codes) != self.quantity:
            raise ValueError("When serial_codes are provided, their count must equal quantity")
        if (self.stock_document_id is None) != (self.stock_line_no is None):
            raise ValueError("stock_document_id and stock_line_no must be provided together")
        return self


class WmsMovementView(Strict):
    schema_version: Literal[1] = 1
    movement_id: UUID
    location_id: UUID
    place_id: UUID
    bin_id: UUID
    to_place_id: UUID | None
    to_bin_id: UUID | None
    goods_owner_id: UUID
    item_id: UUID
    lot_id: UUID
    movement_kind: MovementKind
    direction: MovementDirection
    quantity: int
    stock_document_id: UUID | None
    stock_line_no: int | None
    reference_code: str | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class WmsMovementList(Strict):
    schema_version: Literal[1] = 1
    items: list[WmsMovementView]


class _OwnerReceipt(Strict):
    goods_owner_id: UUID
    revision: int


class _BinReceipt(Strict):
    bin_id: UUID
    revision: int


class _LotReceipt(Strict):
    lot_id: UUID
    revision: int


class _MovementReceipt(Strict):
    movement_id: UUID


async def _load_owner(conn: RuntimeConnection, business: UUID, owner_id: UUID) -> GoodsOwnerView:
    async with conn.cursor(row_factory=class_row(GoodsOwnerView)) as cur:
        await cur.execute(
            "select id as goods_owner_id, location_id, code, display_name, owner_kind, "
            "legal_entity_id, counterparty_id, is_active, revision, recorded_by, recorded_at "
            "from gba.supply_goods_owners where tenant_id = %s and id = %s",
            (business, owner_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise NotFoundError("Goods owner not found")
    return row


async def list_goods_owners(
    conn: RuntimeConnection, business: UUID, *, location_id: UUID | None = None
) -> GoodsOwnerList:
    sql = (
        "select id as goods_owner_id, location_id, code, display_name, owner_kind, "
        "legal_entity_id, counterparty_id, is_active, revision, recorded_by, recorded_at "
        "from gba.supply_goods_owners where tenant_id = %s"
    )
    params: list[object] = [business]
    if location_id is not None:
        sql += " and location_id = %s"
        params.append(location_id)
    sql += " order by code, id"
    async with conn.cursor(row_factory=class_row(GoodsOwnerView)) as cur:
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()
    return GoodsOwnerList(items=rows)


async def save_goods_owner(
    conn: RuntimeConnection,
    business: UUID,
    owner_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: GoodsOwnerInput,
) -> GoodsOwnerView:
    scope = IdempotencyScope(business, actor, "supply.owner.save", key)
    fp = commands.fingerprint({"owner_id": str(owner_id), "body": body.model_dump(mode="json")})
    receipt = await commands.claim(conn, scope, fp, _OwnerReceipt)
    if receipt is not None:
        return await _load_owner(conn, business, receipt.goods_owner_id)

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    existing = await (
        await conn.execute(
            "select revision, location_id, owner_kind, legal_entity_id, counterparty_id "
            "from gba.supply_goods_owners where tenant_id = %s and id = %s for update",
            (business, owner_id),
        )
    ).fetchone()

    try:
        async with module_writes(SUPPLY_MODULE):
            if existing is None:
                if body.expected_revision != 0:
                    raise SupplyRevisionConflictError("Expected revision 0 for new goods owner")
                next_rev = 1
                await conn.execute(
                    "insert into gba.supply_goods_owners "
                    "(tenant_id, id, location_id, code, display_name, owner_kind, "
                    "legal_entity_id, counterparty_id, is_active, revision, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        business,
                        owner_id,
                        body.location_id,
                        body.code,
                        body.display_name,
                        body.owner_kind,
                        body.legal_entity_id,
                        body.counterparty_id,
                        body.is_active,
                        user_id,
                    ),
                )
            else:
                curr_rev = int(existing[0])
                if body.expected_revision != curr_rev:
                    raise SupplyRevisionConflictError("Goods owner revision mismatch")
                if (
                    UUID(str(existing[1])) != body.location_id
                    or str(existing[2]) != body.owner_kind
                    or (UUID(str(existing[3])) if existing[3] else None) != body.legal_entity_id
                    or (UUID(str(existing[4])) if existing[4] else None) != body.counterparty_id
                ):
                    raise SupplyStateError("Goods owner identity and branch cannot change")
                next_rev = curr_rev + 1
                await conn.execute(
                    "update gba.supply_goods_owners "
                    "set code = %s, display_name = %s, is_active = %s, revision = %s, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.code,
                        body.display_name,
                        body.is_active,
                        next_rev,
                        user_id,
                        business,
                        owner_id,
                    ),
                )
    except errors.UniqueViolation as exc:
        raise SupplyStateError("Duplicate goods owner code or target entity/counterparty") from exc
    except errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError(
            "Referenced location, legal entity, or counterparty not found"
        ) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "supply.owner.saved",
        "supply_goods_owner",
        str(owner_id),
        {"revision": next_rev, "owner_kind": body.owner_kind},
    )
    await commands.complete(conn, scope, _OwnerReceipt(goods_owner_id=owner_id, revision=next_rev))
    return await _load_owner(conn, business, owner_id)


async def _load_bin(conn: RuntimeConnection, business: UUID, bin_id: UUID) -> WarehouseBinView:
    async with conn.cursor(row_factory=class_row(WarehouseBinView)) as cur:
        await cur.execute(
            "select id as bin_id, location_id, place_id, zone_code, bin_code, bin_kind, "
            "dedicated_owner_id, is_active, revision, recorded_by, recorded_at "
            "from gba.supply_warehouse_bins where tenant_id = %s and id = %s",
            (business, bin_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise NotFoundError("Warehouse bin not found")
    return row


async def list_warehouse_bins(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    place_id: UUID | None = None,
) -> WarehouseBinList:
    sql = (
        "select id as bin_id, location_id, place_id, zone_code, bin_code, bin_kind, "
        "dedicated_owner_id, is_active, revision, recorded_by, recorded_at "
        "from gba.supply_warehouse_bins where tenant_id = %s"
    )
    params: list[object] = [business]
    if location_id is not None:
        sql += " and location_id = %s"
        params.append(location_id)
    if place_id is not None:
        sql += " and place_id = %s"
        params.append(place_id)
    sql += " order by zone_code, bin_code, id"
    async with conn.cursor(row_factory=class_row(WarehouseBinView)) as cur:
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()
    return WarehouseBinList(items=rows)


async def save_warehouse_bin(
    conn: RuntimeConnection,
    business: UUID,
    bin_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: WarehouseBinInput,
) -> WarehouseBinView:
    scope = IdempotencyScope(business, actor, "supply.bin.save", key)
    fp = commands.fingerprint({"bin_id": str(bin_id), "body": body.model_dump(mode="json")})
    receipt = await commands.claim(conn, scope, fp, _BinReceipt)
    if receipt is not None:
        return await _load_bin(conn, business, receipt.bin_id)

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    existing = await (
        await conn.execute(
            "select revision, location_id, place_id from gba.supply_warehouse_bins "
            "where tenant_id = %s and id = %s for update",
            (business, bin_id),
        )
    ).fetchone()

    try:
        async with module_writes(SUPPLY_MODULE):
            if existing is None:
                if body.expected_revision != 0:
                    raise SupplyRevisionConflictError("Expected revision 0 for new warehouse bin")
                next_rev = 1
                await conn.execute(
                    "insert into gba.supply_warehouse_bins "
                    "(tenant_id, id, location_id, place_id, zone_code, bin_code, bin_kind, "
                    "dedicated_owner_id, is_active, revision, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        business,
                        bin_id,
                        body.location_id,
                        body.place_id,
                        body.zone_code,
                        body.bin_code,
                        body.bin_kind,
                        body.dedicated_owner_id,
                        body.is_active,
                        user_id,
                    ),
                )
            else:
                curr_rev = int(existing[0])
                if body.expected_revision != curr_rev:
                    raise SupplyRevisionConflictError("Warehouse bin revision mismatch")
                if (
                    UUID(str(existing[1])) != body.location_id
                    or UUID(str(existing[2])) != body.place_id
                ):
                    raise SupplyStateError("Warehouse bin branch and place cannot change")
                if body.dedicated_owner_id is not None:
                    other_bal = await (
                        await conn.execute(
                            "select 1 from gba.supply_lot_balances "
                            "where tenant_id = %s and bin_id = %s and goods_owner_id <> %s "
                            "and quantity > 0 limit 1",
                            (business, bin_id, body.dedicated_owner_id),
                        )
                    ).fetchone()
                    if other_bal is not None:
                        raise SupplyOwnerMismatchError(
                            "Cannot dedicate bin while it holds non-zero stock of another "
                            "goods owner"
                        )
                next_rev = curr_rev + 1
                await conn.execute(
                    "update gba.supply_warehouse_bins "
                    "set zone_code = %s, bin_code = %s, bin_kind = %s, dedicated_owner_id = %s, "
                    "is_active = %s, revision = %s, recorded_by = %s, recorded_at = "
                    "clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.zone_code,
                        body.bin_code,
                        body.bin_kind,
                        body.dedicated_owner_id,
                        body.is_active,
                        next_rev,
                        user_id,
                        business,
                        bin_id,
                    ),
                )
    except errors.UniqueViolation as exc:
        raise SupplyStateError("Duplicate bin_code in this storage place") from exc
    except errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError(
            "Referenced storage place or dedicated goods owner not found"
        ) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "supply.bin.saved",
        "supply_warehouse_bin",
        str(bin_id),
        {"revision": next_rev, "bin_kind": body.bin_kind},
    )
    await commands.complete(conn, scope, _BinReceipt(bin_id=bin_id, revision=next_rev))
    return await _load_bin(conn, business, bin_id)


async def _load_lot(conn: RuntimeConnection, business: UUID, lot_id: UUID) -> LotView:
    async with conn.cursor(row_factory=class_row(LotView)) as cur:
        await cur.execute(
            "select id as lot_id, location_id, goods_owner_id, item_id, lot_code, "
            "manufactured_on, expires_on, status, unit_cost_minor, notes, revision, "
            "recorded_by, recorded_at from gba.supply_lots where tenant_id = %s and id = %s",
            (business, lot_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise NotFoundError("Supply lot not found")
    return row


async def list_lots(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
    item_id: UUID | None = None,
) -> LotList:
    sql = (
        "select id as lot_id, location_id, goods_owner_id, item_id, lot_code, "
        "manufactured_on, expires_on, status, unit_cost_minor, notes, revision, "
        "recorded_by, recorded_at from gba.supply_lots where tenant_id = %s"
    )
    params: list[object] = [business]
    if location_id is not None:
        sql += " and location_id = %s"
        params.append(location_id)
    if goods_owner_id is not None:
        sql += " and goods_owner_id = %s"
        params.append(goods_owner_id)
    if item_id is not None:
        sql += " and item_id = %s"
        params.append(item_id)
    sql += " order by lot_code, id"
    async with conn.cursor(row_factory=class_row(LotView)) as cur:
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()
    return LotList(items=rows)


async def save_lot(
    conn: RuntimeConnection,
    business: UUID,
    lot_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: LotInput,
) -> LotView:
    scope = IdempotencyScope(business, actor, "supply.lot.save", key)
    fp = commands.fingerprint({"lot_id": str(lot_id), "body": body.model_dump(mode="json")})
    receipt = await commands.claim(conn, scope, fp, _LotReceipt)
    if receipt is not None:
        return await _load_lot(conn, business, receipt.lot_id)

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    existing = await (
        await conn.execute(
            "select revision, location_id, goods_owner_id, item_id from gba.supply_lots "
            "where tenant_id = %s and id = %s for update",
            (business, lot_id),
        )
    ).fetchone()

    try:
        async with module_writes(SUPPLY_MODULE):
            if existing is None:
                if body.expected_revision != 0:
                    raise SupplyRevisionConflictError("Expected revision 0 for new supply lot")
                next_rev = 1
                await conn.execute(
                    "insert into gba.supply_lots "
                    "(tenant_id, id, location_id, goods_owner_id, item_id, lot_code, "
                    "manufactured_on, expires_on, status, unit_cost_minor, notes, "
                    "revision, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        business,
                        lot_id,
                        body.location_id,
                        body.goods_owner_id,
                        body.item_id,
                        body.lot_code,
                        body.manufactured_on,
                        body.expires_on,
                        body.status,
                        body.unit_cost_minor,
                        body.notes,
                        user_id,
                    ),
                )
            else:
                curr_rev = int(existing[0])
                if body.expected_revision != curr_rev:
                    raise SupplyRevisionConflictError("Supply lot revision mismatch")
                if (
                    UUID(str(existing[1])) != body.location_id
                    or UUID(str(existing[2])) != body.goods_owner_id
                    or UUID(str(existing[3])) != body.item_id
                ):
                    raise SupplyOwnerMismatchError(
                        "Lot goods owner, item, and branch cannot change"
                    )
                next_rev = curr_rev + 1
                await conn.execute(
                    "update gba.supply_lots "
                    "set lot_code = %s, manufactured_on = %s, expires_on = %s, status = %s, "
                    "unit_cost_minor = %s, notes = %s, revision = %s, recorded_by = %s, "
                    "recorded_at = clock_timestamp() where tenant_id = %s and id = %s",
                    (
                        body.lot_code,
                        body.manufactured_on,
                        body.expires_on,
                        body.status,
                        body.unit_cost_minor,
                        body.notes,
                        next_rev,
                        user_id,
                        business,
                        lot_id,
                    ),
                )
    except errors.UniqueViolation as exc:
        raise SupplyStateError("Duplicate lot_code for this owner and item") from exc
    except errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError("Referenced goods owner or stock item not found") from exc

    await commands.audit(
        conn,
        business,
        actor,
        "supply.lot.saved",
        "supply_lot",
        str(lot_id),
        {"revision": next_rev, "status": body.status},
    )
    await commands.complete(conn, scope, _LotReceipt(lot_id=lot_id, revision=next_rev))
    return await _load_lot(conn, business, lot_id)


async def list_lot_balances(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
    item_id: UUID | None = None,
    bin_id: UUID | None = None,
    lot_id: UUID | None = None,
) -> LotBalanceList:
    sql = (
        "select id as balance_id, location_id, place_id, bin_id, goods_owner_id, "
        "item_id, lot_id, quantity, updated_at "
        "from gba.supply_lot_balances where tenant_id = %s"
    )
    params: list[object] = [business]
    if location_id is not None:
        sql += " and location_id = %s"
        params.append(location_id)
    if goods_owner_id is not None:
        sql += " and goods_owner_id = %s"
        params.append(goods_owner_id)
    if item_id is not None:
        sql += " and item_id = %s"
        params.append(item_id)
    if bin_id is not None:
        sql += " and bin_id = %s"
        params.append(bin_id)
    if lot_id is not None:
        sql += " and lot_id = %s"
        params.append(lot_id)
    sql += " order by bin_id, lot_id, id"
    async with conn.cursor(row_factory=class_row(LotBalanceView)) as cur:
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()
    return LotBalanceList(items=rows)


async def list_serial_units(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
    lot_id: UUID | None = None,
    item_id: UUID | None = None,
    state: SerialState | None = None,
) -> SerialUnitList:
    sql = (
        "select id as serial_id, location_id, place_id, bin_id, goods_owner_id, "
        "item_id, lot_id, serial_code, state, recorded_by, recorded_at "
        "from gba.supply_serial_units where tenant_id = %s"
    )
    params: list[object] = [business]
    if location_id is not None:
        sql += " and location_id = %s"
        params.append(location_id)
    if goods_owner_id is not None:
        sql += " and goods_owner_id = %s"
        params.append(goods_owner_id)
    if lot_id is not None:
        sql += " and lot_id = %s"
        params.append(lot_id)
    if item_id is not None:
        sql += " and item_id = %s"
        params.append(item_id)
    if state is not None:
        sql += " and state = %s"
        params.append(state)
    sql += " order by serial_code, id"
    async with conn.cursor(row_factory=class_row(SerialUnitView)) as cur:
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()
    return SerialUnitList(items=rows)


async def _load_movement(
    conn: RuntimeConnection, business: UUID, movement_id: UUID
) -> WmsMovementView:
    async with conn.cursor(row_factory=class_row(WmsMovementView)) as cur:
        await cur.execute(
            "select id as movement_id, location_id, place_id, bin_id, to_place_id, to_bin_id, "
            "goods_owner_id, item_id, lot_id, movement_kind, direction, quantity, "
            "stock_document_id, stock_line_no, reference_code, recorded_by, recorded_at "
            "from gba.supply_wms_movements where tenant_id = %s and id = %s",
            (business, movement_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise NotFoundError("WMS movement not found")
    return row


async def list_wms_movements(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
    lot_id: UUID | None = None,
) -> WmsMovementList:
    sql = (
        "select id as movement_id, location_id, place_id, bin_id, to_place_id, to_bin_id, "
        "goods_owner_id, item_id, lot_id, movement_kind, direction, quantity, "
        "stock_document_id, stock_line_no, reference_code, recorded_by, recorded_at "
        "from gba.supply_wms_movements where tenant_id = %s"
    )
    params: list[object] = [business]
    if location_id is not None:
        sql += " and location_id = %s"
        params.append(location_id)
    if goods_owner_id is not None:
        sql += " and goods_owner_id = %s"
        params.append(goods_owner_id)
    if lot_id is not None:
        sql += " and lot_id = %s"
        params.append(lot_id)
    sql += " order by recorded_at desc, id desc"
    async with conn.cursor(row_factory=class_row(WmsMovementView)) as cur:
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()
    return WmsMovementList(items=rows)


async def _verify_owner_lot_bin(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID,
    goods_owner_id: UUID,
    item_id: UUID,
    lot_id: UUID,
    bin_id: UUID,
) -> tuple[str, UUID | None, UUID, str]:
    """Returns (owner_kind, legal_entity_id, place_id, lot_status) or raises typed
    owner/reference errors."""
    owner_row = await (
        await conn.execute(
            "select owner_kind, legal_entity_id, is_active, location_id "
            "from gba.supply_goods_owners where tenant_id = %s and id = %s",
            (business, goods_owner_id),
        )
    ).fetchone()
    if owner_row is None or UUID(str(owner_row[3])) != location_id:
        raise InvalidReferenceError("Goods owner not found in this branch", field="goods_owner_id")
    if not bool(owner_row[2]):
        raise SupplyStateError("Goods owner is inactive")

    lot_row = await (
        await conn.execute(
            "select goods_owner_id, item_id, status, location_id "
            "from gba.supply_lots where tenant_id = %s and id = %s for update",
            (business, lot_id),
        )
    ).fetchone()
    if lot_row is None or UUID(str(lot_row[3])) != location_id:
        raise InvalidReferenceError("Lot not found in this branch", field="lot_id")
    if UUID(str(lot_row[0])) != goods_owner_id:
        raise SupplyOwnerMismatchError("Lot belongs to another goods owner")
    if UUID(str(lot_row[1])) != item_id:
        raise InvalidReferenceError("Lot item does not match requested item_id", field="item_id")

    bin_row = await (
        await conn.execute(
            "select place_id, dedicated_owner_id, is_active, location_id "
            "from gba.supply_warehouse_bins where tenant_id = %s and id = %s",
            (business, bin_id),
        )
    ).fetchone()
    if bin_row is None or UUID(str(bin_row[3])) != location_id:
        raise InvalidReferenceError("Warehouse bin not found in this branch", field="bin_id")
    if not bool(bin_row[2]):
        raise SupplyStateError("Warehouse bin is inactive")
    if bin_row[1] is not None and UUID(str(bin_row[1])) != goods_owner_id:
        raise SupplyOwnerMismatchError("Warehouse bin is dedicated to another goods owner")

    owner_kind = str(owner_row[0])
    legal_entity_id = UUID(str(owner_row[1])) if owner_row[1] is not None else None
    place_id = UUID(str(bin_row[0]))
    lot_status = str(lot_row[2])
    return owner_kind, legal_entity_id, place_id, lot_status


async def _item_quantity_text(
    conn: RuntimeConnection, business: UUID, item_id: UUID, qty: int
) -> str:
    row = await (
        await conn.execute(
            "select quantity_scale from gba.stock_items where tenant_id = %s and id = %s",
            (business, item_id),
        )
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Stock item not found", field="item_id")
    return from_count(qty, int(row[0]))


async def record_inbound_putaway(
    conn: RuntimeConnection,
    business: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: InboundPutawayInput,
) -> WmsMovementView:
    scope = IdempotencyScope(business, actor, "supply.movement.inbound", key)
    fp = commands.fingerprint(body.model_dump(mode="json"))
    receipt = await commands.claim(conn, scope, fp, _MovementReceipt)
    if receipt is not None:
        return await _load_movement(conn, business, receipt.movement_id)

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    owner_kind, legal_entity_id, place_id, _lot_status = await _verify_owner_lot_bin(
        conn,
        business,
        location_id=body.location_id,
        goods_owner_id=body.goods_owner_id,
        item_id=body.item_id,
        lot_id=body.lot_id,
        bin_id=body.bin_id,
    )

    stock_doc_id = body.stock_document_id
    stock_line_no = body.stock_line_no

    if owner_kind == "company_entity":
        if legal_entity_id is None:
            raise SupplyOwnerMismatchError("Company goods owner requires legal_entity_id")
        if stock_doc_id is None:
            if body.auto_stock_receipt_date is None or body.auto_stock_receipt_amount is None:
                raise SupplyValidationError(
                    "Company-owned inbound putaway requires stock_document_id or "
                    "auto_stock_receipt_date + auto_stock_receipt_amount"
                )
            qty_text = await _item_quantity_text(conn, business, body.item_id, body.quantity)
            new_doc_id = uuid7()
            await stock.post_document(
                conn,
                business,
                new_doc_id,
                user=user_id,
                actor=actor,
                key=f"sup-in-stk-{key}"[:120],
                body=ReceiptInput(
                    kind="receipt",
                    legal_entity_id=legal_entity_id,
                    place_id=place_id,
                    reason=body.auto_stock_receipt_reason,
                    document_date=body.auto_stock_receipt_date,
                    lines=(
                        ReceiptLine(
                            item_id=body.item_id,
                            quantity=qty_text,
                            amount=body.auto_stock_receipt_amount,
                        ),
                    ),
                ),
            )
            stock_doc_id = new_doc_id
            stock_line_no = 1
    else:
        if stock_doc_id is not None or body.auto_stock_receipt_date is not None:
            raise SupplyOwnerMismatchError(
                "3PL customer-owned goods cannot post or attach to a company STOCK-01 receipt"
            )

    movement_id = uuid7()
    try:
        async with module_writes(SUPPLY_MODULE):
            bal_row = await (
                await conn.execute(
                    "select id, quantity from gba.supply_lot_balances "
                    "where tenant_id = %s and bin_id = %s and goods_owner_id = %s "
                    "and item_id = %s and lot_id = %s for update",
                    (business, body.bin_id, body.goods_owner_id, body.item_id, body.lot_id),
                )
            ).fetchone()
            if bal_row is None:
                await conn.execute(
                    "insert into gba.supply_lot_balances "
                    "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, "
                    "item_id, lot_id, quantity) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        uuid7(),
                        body.location_id,
                        place_id,
                        body.bin_id,
                        body.goods_owner_id,
                        body.item_id,
                        body.lot_id,
                        body.quantity,
                    ),
                )
            else:
                await conn.execute(
                    "update gba.supply_lot_balances set quantity = quantity + %s, "
                    "updated_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (body.quantity, business, bal_row[0]),
                )

            for sc in body.serial_codes:
                existing_ser = await (
                    await conn.execute(
                        "select id, goods_owner_id, lot_id, state from gba.supply_serial_units "
                        "where tenant_id = %s and item_id = %s and serial_code = %s for update",
                        (business, body.item_id, sc),
                    )
                ).fetchone()
                if existing_ser is None:
                    await conn.execute(
                        "insert into gba.supply_serial_units "
                        "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, "
                        "item_id, lot_id, "
                        "serial_code, state, recorded_by) "
                        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'in_stock', %s)",
                        (
                            business,
                            uuid7(),
                            body.location_id,
                            place_id,
                            body.bin_id,
                            body.goods_owner_id,
                            body.item_id,
                            body.lot_id,
                            sc,
                            user_id,
                        ),
                    )
                else:
                    if (
                        UUID(str(existing_ser[1])) != body.goods_owner_id
                        or UUID(str(existing_ser[2])) != body.lot_id
                    ):
                        raise SupplyOwnerMismatchError(
                            "Serial unit belongs to another goods owner or lot"
                        )
                    if str(existing_ser[3]) not in ("shipped", "returned"):
                        raise SupplyStateError(f"Serial unit {sc} is already in stock")
                    await conn.execute(
                        "update gba.supply_serial_units "
                        "set location_id = %s, place_id = %s, bin_id = %s, state = 'in_stock', "
                        "recorded_by = %s, recorded_at = clock_timestamp() "
                        "where tenant_id = %s and id = %s",
                        (
                            body.location_id,
                            place_id,
                            body.bin_id,
                            user_id,
                            business,
                            existing_ser[0],
                        ),
                    )

            await conn.execute(
                "insert into gba.supply_wms_movements "
                "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, lot_id, "
                "movement_kind, direction, quantity, stock_document_id, stock_line_no, "
                "reference_code, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'in', %s, %s, %s, %s, %s)",
                (
                    business,
                    movement_id,
                    body.location_id,
                    place_id,
                    body.bin_id,
                    body.goods_owner_id,
                    body.item_id,
                    body.lot_id,
                    body.movement_kind,
                    body.quantity,
                    stock_doc_id,
                    stock_line_no,
                    body.reference_code,
                    user_id,
                ),
            )
    except errors.CheckViolation as exc:
        raise SupplyOwnerMismatchError(
            "WMS movement violated dedicated bin or STOCK-01 document owner/item/place invariant"
        ) from exc
    except errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError("Referenced STOCK-01 document line not found") from exc

    await commands.audit(
        conn,
        business,
        actor,
        "supply.movement.inbound",
        "supply_wms_movement",
        str(movement_id),
        {"lot_id": str(body.lot_id), "quantity": body.quantity},
    )
    await commands.complete(conn, scope, _MovementReceipt(movement_id=movement_id))
    return await _load_movement(conn, business, movement_id)


async def record_bin_relocation(
    conn: RuntimeConnection,
    business: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: BinRelocationInput,
) -> WmsMovementView:
    scope = IdempotencyScope(business, actor, "supply.movement.relocate", key)
    fp = commands.fingerprint(body.model_dump(mode="json"))
    receipt = await commands.claim(conn, scope, fp, _MovementReceipt)
    if receipt is not None:
        return await _load_movement(conn, business, receipt.movement_id)

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    owner_kind, legal_entity_id, from_place_id, _lot_status = await _verify_owner_lot_bin(
        conn,
        business,
        location_id=body.location_id,
        goods_owner_id=body.goods_owner_id,
        item_id=body.item_id,
        lot_id=body.lot_id,
        bin_id=body.from_bin_id,
    )
    _ok2, _le2, to_place_id, _ls2 = await _verify_owner_lot_bin(
        conn,
        business,
        location_id=body.location_id,
        goods_owner_id=body.goods_owner_id,
        item_id=body.item_id,
        lot_id=body.lot_id,
        bin_id=body.to_bin_id,
    )

    stock_doc_id: UUID | None = None
    stock_line_no: int | None = None
    if owner_kind == "company_entity" and from_place_id != to_place_id:
        if legal_entity_id is None:
            raise SupplyOwnerMismatchError("Company goods owner requires legal_entity_id")
        qty_text = await _item_quantity_text(conn, business, body.item_id, body.quantity)
        transfer_doc_id = uuid7()
        await stock.post_transfer(
            conn,
            business,
            transfer_doc_id,
            user=user_id,
            actor=actor,
            key=f"sup-rel-stk-{key}"[:120],
            body=TransferInput(
                kind="transfer",
                legal_entity_id=legal_entity_id,
                place_id=from_place_id,
                to_place_id=to_place_id,
                document_date=body.document_date or datetime.now(UTC).date(),
                lines=(TransferLine(item_id=body.item_id, quantity=qty_text),),
            ),
        )
        stock_doc_id = transfer_doc_id
        stock_line_no = 1

    movement_id = uuid7()
    async with module_writes(SUPPLY_MODULE):
        from_bal = await (
            await conn.execute(
                "select id, quantity from gba.supply_lot_balances "
                "where tenant_id = %s and bin_id = %s and goods_owner_id = %s "
                "and item_id = %s and lot_id = %s for update",
                (business, body.from_bin_id, body.goods_owner_id, body.item_id, body.lot_id),
            )
        ).fetchone()
        if from_bal is None or int(from_bal[1]) < body.quantity:
            raise SupplyInsufficientLotError("Insufficient lot balance in source bin")

        await conn.execute(
            "update gba.supply_lot_balances set quantity = quantity - %s, updated_at = "
            "clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (body.quantity, business, from_bal[0]),
        )

        to_bal = await (
            await conn.execute(
                "select id from gba.supply_lot_balances "
                "where tenant_id = %s and bin_id = %s and goods_owner_id = %s "
                "and item_id = %s and lot_id = %s for update",
                (business, body.to_bin_id, body.goods_owner_id, body.item_id, body.lot_id),
            )
        ).fetchone()
        if to_bal is None:
            await conn.execute(
                "insert into gba.supply_lot_balances "
                "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, "
                "lot_id, quantity) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    uuid7(),
                    body.location_id,
                    to_place_id,
                    body.to_bin_id,
                    body.goods_owner_id,
                    body.item_id,
                    body.lot_id,
                    body.quantity,
                ),
            )
        else:
            await conn.execute(
                "update gba.supply_lot_balances set quantity = quantity + %s, updated_at = "
                "clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (body.quantity, business, to_bal[0]),
            )

        for sc in body.serial_codes:
            ser = await (
                await conn.execute(
                    "select id, bin_id, goods_owner_id, lot_id, state from "
                    "gba.supply_serial_units "
                    "where tenant_id = %s and item_id = %s and serial_code = %s for update",
                    (business, body.item_id, sc),
                )
            ).fetchone()
            if ser is None:
                raise InvalidReferenceError(f"Serial unit {sc} not found", field="serial_codes")
            if UUID(str(ser[2])) != body.goods_owner_id or UUID(str(ser[3])) != body.lot_id:
                raise SupplyOwnerMismatchError("Serial unit belongs to another goods owner or lot")
            if UUID(str(ser[1])) != body.from_bin_id or str(ser[4]) != "in_stock":
                raise SupplyStateError(f"Serial unit {sc} is not in_stock in source bin")
            await conn.execute(
                "update gba.supply_serial_units set place_id = %s, bin_id = %s, "
                "recorded_by = %s, recorded_at = clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (to_place_id, body.to_bin_id, user_id, business, ser[0]),
            )

        await conn.execute(
            "insert into gba.supply_wms_movements "
            "(tenant_id, id, location_id, place_id, bin_id, to_place_id, to_bin_id, "
            "goods_owner_id, item_id, lot_id, movement_kind, direction, quantity, "
            "stock_document_id, stock_line_no, reference_code, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'bin_relocation', 'relocate', "
            "%s, %s, %s, %s, %s)",
            (
                business,
                movement_id,
                body.location_id,
                from_place_id,
                body.from_bin_id,
                to_place_id,
                body.to_bin_id,
                body.goods_owner_id,
                body.item_id,
                body.lot_id,
                body.quantity,
                stock_doc_id,
                stock_line_no,
                body.reference_code,
                user_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "supply.movement.relocated",
        "supply_wms_movement",
        str(movement_id),
        {"lot_id": str(body.lot_id), "quantity": body.quantity},
    )
    await commands.complete(conn, scope, _MovementReceipt(movement_id=movement_id))
    return await _load_movement(conn, business, movement_id)


async def record_outbound_pick(
    conn: RuntimeConnection,
    business: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: OutboundPickInput,
) -> WmsMovementView:
    scope = IdempotencyScope(business, actor, "supply.movement.outbound", key)
    fp = commands.fingerprint(body.model_dump(mode="json"))
    receipt = await commands.claim(conn, scope, fp, _MovementReceipt)
    if receipt is not None:
        return await _load_movement(conn, business, receipt.movement_id)

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    owner_kind, legal_entity_id, place_id, lot_status = await _verify_owner_lot_bin(
        conn,
        business,
        location_id=body.location_id,
        goods_owner_id=body.goods_owner_id,
        item_id=body.item_id,
        lot_id=body.lot_id,
        bin_id=body.bin_id,
    )
    if lot_status != "active":
        raise SupplyStateError(f"Cannot pick from {lot_status} lot")

    bal_row = await (
        await conn.execute(
            "select id, quantity from gba.supply_lot_balances "
            "where tenant_id = %s and bin_id = %s and goods_owner_id = %s "
            "and item_id = %s and lot_id = %s for update",
            (business, body.bin_id, body.goods_owner_id, body.item_id, body.lot_id),
        )
    ).fetchone()
    if bal_row is None or int(bal_row[1]) < body.quantity:
        raise SupplyInsufficientLotError("Insufficient lot balance in bin")

    stock_doc_id = body.stock_document_id
    stock_line_no = body.stock_line_no
    if owner_kind == "company_entity":
        if legal_entity_id is None:
            raise SupplyOwnerMismatchError("Company goods owner requires legal_entity_id")
        if stock_doc_id is None:
            if body.auto_stock_write_off_date is None:
                raise SupplyValidationError(
                    "Company-owned outbound pick requires stock_document_id or "
                    "auto_stock_write_off_date"
                )
            qty_text = await _item_quantity_text(conn, business, body.item_id, body.quantity)
            wo_doc_id = uuid7()
            await stock.post_document(
                conn,
                business,
                wo_doc_id,
                user=user_id,
                actor=actor,
                key=f"sup-out-stk-{key}"[:120],
                body=WriteOffInput(
                    kind="write_off",
                    legal_entity_id=legal_entity_id,
                    place_id=place_id,
                    reason=body.auto_stock_write_off_reason,
                    document_date=body.auto_stock_write_off_date,
                    lines=(WriteOffLine(item_id=body.item_id, quantity=qty_text),),
                ),
            )
            stock_doc_id = wo_doc_id
            stock_line_no = 1
    else:
        if stock_doc_id is not None or body.auto_stock_write_off_date is not None:
            raise SupplyOwnerMismatchError(
                "3PL customer-owned goods cannot post or attach to a company STOCK-01 write-off"
            )

    movement_id = uuid7()
    try:
        async with module_writes(SUPPLY_MODULE):
            await conn.execute(
                "update gba.supply_lot_balances set quantity = quantity - %s, updated_at = "
                "clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (body.quantity, business, bal_row[0]),
            )

            for sc in body.serial_codes:
                ser = await (
                    await conn.execute(
                        "select id, bin_id, goods_owner_id, lot_id, state from "
                        "gba.supply_serial_units "
                        "where tenant_id = %s and item_id = %s and serial_code = %s for update",
                        (business, body.item_id, sc),
                    )
                ).fetchone()
                if ser is None:
                    raise InvalidReferenceError(f"Serial unit {sc} not found", field="serial_codes")
                if UUID(str(ser[2])) != body.goods_owner_id or UUID(str(ser[3])) != body.lot_id:
                    raise SupplyOwnerMismatchError(
                        "Serial unit belongs to another goods owner or lot"
                    )
                if UUID(str(ser[1])) != body.bin_id or str(ser[4]) not in ("in_stock", "reserved"):
                    raise SupplyStateError(f"Serial unit {sc} is not available in bin")
                await conn.execute(
                    "update gba.supply_serial_units set state = 'shipped', "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (user_id, business, ser[0]),
                )

            await conn.execute(
                "insert into gba.supply_wms_movements "
                "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, lot_id, "
                "movement_kind, direction, quantity, stock_document_id, stock_line_no, "
                "reference_code, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, 'outbound_pick', 'out', %s, %s, "
                "%s, %s, %s)",
                (
                    business,
                    movement_id,
                    body.location_id,
                    place_id,
                    body.bin_id,
                    body.goods_owner_id,
                    body.item_id,
                    body.lot_id,
                    body.quantity,
                    stock_doc_id,
                    stock_line_no,
                    body.reference_code,
                    user_id,
                ),
            )
    except errors.CheckViolation as exc:
        raise SupplyOwnerMismatchError(
            "WMS outbound movement violated owner or STOCK-01 document line invariant"
        ) from exc
    except errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError("Referenced STOCK-01 document line not found") from exc

    await commands.audit(
        conn,
        business,
        actor,
        "supply.movement.outbound",
        "supply_wms_movement",
        str(movement_id),
        {"lot_id": str(body.lot_id), "quantity": body.quantity},
    )
    await commands.complete(conn, scope, _MovementReceipt(movement_id=movement_id))
    return await _load_movement(conn, business, movement_id)
