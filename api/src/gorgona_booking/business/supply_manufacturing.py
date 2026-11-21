"""SUPPLY-01 Slice 2 (ADR-0039): Manufacturing BOMs, production work orders,
component lot issues (STOCK-01 write_off), unused material returns (STOCK-01 return),
quality control, and finished-goods lot output (STOCK-01 receipt) with cost conservation.
"""

from datetime import date
from typing import Literal, Self
from uuid import UUID, uuid7

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, field_validator, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, stock
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.ledger_contracts import from_minor
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.stock_contracts import (
    ReceiptInput,
    ReceiptLine,
    ReturnInput,
    ReturnLine,
    WriteOffInput,
    WriteOffLine,
)
from gorgona_booking.business.supply_wms import (
    SUPPLY_MODULE,
    SupplyInsufficientLotError,
    SupplyOwnerMismatchError,
    SupplyRevisionConflictError,
    SupplyStateError,
    _check_ready,
    _clean_code,
    _clean_single_line,
    _item_quantity_text,
    _verify_owner_lot_bin,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError

WorkOrderStatus = Literal["draft", "released", "in_progress", "qc_passed", "completed", "cancelled"]


class BomComponentInput(Strict):
    component_item_id: UUID
    quantity_per_batch: int = Field(ge=1, le=999_999_999_999)
    scrap_bps: int = Field(default=0, ge=0, le=10_000)


class BomInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    code: str
    title: str
    output_item_id: UUID
    batch_output_quantity: int = Field(ge=1, le=999_999_999_999)
    standard_labor_minor: int = Field(default=0, ge=0, le=999_999_999_999_999)
    standard_overhead_minor: int = Field(default=0, ge=0, le=999_999_999_999_999)
    is_active: bool = True
    components: list[BomComponentInput] = Field(min_length=1, max_length=100)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value, 64)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_single_line(value, 200)

    @model_validator(mode="after")
    def unique_components(self) -> Self:
        comp_ids = [c.component_item_id for c in self.components]
        if len(set(comp_ids)) != len(comp_ids):
            raise ValueError("Duplicate component_item_id in BOM components")
        if self.output_item_id in comp_ids:
            raise ValueError("BOM output_item_id cannot be one of its own direct components")
        return self


class BomComponentView(Strict):
    schema_version: Literal[1] = 1
    component_id: UUID
    bom_id: UUID
    line_no: int
    component_item_id: UUID
    quantity_per_batch: int
    scrap_bps: int


class BomView(Strict):
    schema_version: Literal[1] = 1
    bom_id: UUID
    location_id: UUID
    code: str
    title: str
    output_item_id: UUID
    batch_output_quantity: int
    standard_labor_minor: int
    standard_overhead_minor: int
    is_active: bool
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime
    components: list[BomComponentView]


class BomList(Strict):
    schema_version: Literal[1] = 1
    items: list[BomView]


class WorkOrderInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    code: str
    goods_owner_id: UUID
    bom_id: UUID
    place_id: UUID
    planned_quantity: int = Field(ge=1, le=999_999_999_999)
    labor_cost_minor: int | None = Field(default=None, ge=0, le=999_999_999_999_999)
    overhead_cost_minor: int | None = Field(default=None, ge=0, le=999_999_999_999_999)
    status: Literal["draft", "released", "cancelled"] = "released"

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value, 64)


class WorkOrderView(Strict):
    schema_version: Literal[1] = 1
    work_order_id: UUID
    location_id: UUID
    code: str
    goods_owner_id: UUID
    bom_id: UUID
    output_item_id: UUID
    place_id: UUID
    planned_quantity: int
    issued_material_cost_minor: int
    returned_material_cost_minor: int
    labor_cost_minor: int
    overhead_cost_minor: int
    completed_quantity: int
    scrap_quantity: int
    output_total_cost_minor: int
    status: WorkOrderStatus
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class WorkOrderList(Strict):
    schema_version: Literal[1] = 1
    items: list[WorkOrderView]


class WorkOrderIssueInput(Versioned):
    bin_id: UUID
    component_item_id: UUID
    lot_id: UUID
    quantity: int = Field(ge=1, le=999_999_999_999)
    document_date: date


class WorkOrderIssueView(Strict):
    schema_version: Literal[1] = 1
    issue_id: UUID
    work_order_id: UUID
    location_id: UUID
    goods_owner_id: UUID
    place_id: UUID
    bin_id: UUID
    component_item_id: UUID
    lot_id: UUID
    quantity: int
    returned_quantity: int
    stock_document_id: UUID
    stock_line_no: int
    cost_minor: int
    returned_cost_minor: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class WorkOrderIssueList(Strict):
    schema_version: Literal[1] = 1
    items: list[WorkOrderIssueView]


class WorkOrderReturnInput(Versioned):
    issue_id: UUID
    bin_id: UUID
    quantity: int = Field(ge=1, le=999_999_999_999)
    document_date: date


class WorkOrderReturnView(Strict):
    schema_version: Literal[1] = 1
    return_id: UUID
    work_order_id: UUID
    issue_id: UUID
    location_id: UUID
    goods_owner_id: UUID
    place_id: UUID
    bin_id: UUID
    component_item_id: UUID
    lot_id: UUID
    quantity: int
    stock_return_document_id: UUID
    stock_return_line_no: int
    cost_returned_minor: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class WorkOrderReturnList(Strict):
    schema_version: Literal[1] = 1
    items: list[WorkOrderReturnView]


class WorkOrderQcInput(Versioned):
    passed_quantity: int = Field(ge=1, le=999_999_999_999)
    scrap_quantity: int = Field(default=0, ge=0, le=999_999_999_999)
    notes: str | None = None

    @field_validator("notes")
    @classmethod
    def valid_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_single_line(value, 500)


class WorkOrderQcView(Strict):
    schema_version: Literal[1] = 1
    qc_id: UUID
    work_order_id: UUID
    location_id: UUID
    passed_quantity: int
    scrap_quantity: int
    notes: str | None
    inspected_by: UUID
    inspected_at: AwareDatetime


class WorkOrderOutputInput(Versioned):
    bin_id: UUID
    output_lot_code: str
    manufactured_on: date
    expires_on: date | None = None

    @field_validator("output_lot_code")
    @classmethod
    def valid_lot(cls, value: str) -> str:
        return _clean_code(value, 64, allow_dots=True)

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        if self.expires_on is not None and self.expires_on < self.manufactured_on:
            raise ValueError("expires_on cannot precede manufactured_on")
        return self


class WorkOrderOutputView(Strict):
    schema_version: Literal[1] = 1
    output_id: UUID
    work_order_id: UUID
    location_id: UUID
    goods_owner_id: UUID
    place_id: UUID
    bin_id: UUID
    output_item_id: UUID
    output_lot_id: UUID
    quantity: int
    material_cost_minor: int
    labor_cost_minor: int
    overhead_cost_minor: int
    total_cost_minor: int
    unit_cost_minor: int
    stock_receipt_document_id: UUID
    stock_receipt_line_no: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class _BomReceipt(Strict):
    bom_id: UUID
    revision: int


class _WoReceipt(Strict):
    work_order_id: UUID
    revision: int


class _IssueReceipt(Strict):
    issue_id: UUID


class _ReturnReceipt(Strict):
    return_id: UUID


class _QcReceipt(Strict):
    qc_id: UUID


class _OutputReceipt(Strict):
    output_id: UUID


async def _load_bom(conn: RuntimeConnection, business: UUID, bom_id: UUID) -> BomView:
    row = await (
        await conn.execute(
            "select id, location_id, code, title, output_item_id, batch_output_quantity, "
            "standard_labor_minor, standard_overhead_minor, is_active, revision, "
            "recorded_by, recorded_at "
            "from gba.supply_boms where tenant_id = %s and id = %s",
            (business, bom_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("BOM not found")
    async with conn.cursor(row_factory=class_row(BomComponentView)) as cur:
        await cur.execute(
            "select id as component_id, bom_id, line_no, component_item_id, "
            "quantity_per_batch, scrap_bps "
            "from gba.supply_bom_components where tenant_id = %s and bom_id = %s order by "
            "line_no",
            (business, bom_id),
        )
        comps = await cur.fetchall()
    return BomView(
        bom_id=UUID(str(row[0])),
        location_id=UUID(str(row[1])),
        code=str(row[2]),
        title=str(row[3]),
        output_item_id=UUID(str(row[4])),
        batch_output_quantity=int(row[5]),
        standard_labor_minor=int(row[6]),
        standard_overhead_minor=int(row[7]),
        is_active=bool(row[8]),
        revision=int(row[9]),
        recorded_by=UUID(str(row[10])),
        recorded_at=row[11],
        components=comps,
    )


async def list_boms(
    conn: RuntimeConnection, business: UUID, *, location_id: UUID | None = None
) -> BomList:
    sql = "select id from gba.supply_boms where tenant_id = %s"
    params: list[object] = [business]
    if location_id is not None:
        sql += " and location_id = %s"
        params.append(location_id)
    sql += " order by code, id"
    rows = await (await conn.execute(sql, tuple(params))).fetchall()
    items = [await _load_bom(conn, business, UUID(str(r[0]))) for r in rows]
    return BomList(items=items)


async def save_bom(
    conn: RuntimeConnection,
    business: UUID,
    bom_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: BomInput,
) -> BomView:
    scope = IdempotencyScope(business, actor, "supply.bom.save", key)
    fp = commands.fingerprint({"bom_id": str(bom_id), "body": body.model_dump(mode="json")})
    receipt = await commands.claim(conn, scope, fp, _BomReceipt)
    if receipt is not None:
        return await _load_bom(conn, business, receipt.bom_id)

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    existing = await (
        await conn.execute(
            "select revision, location_id, output_item_id from gba.supply_boms "
            "where tenant_id = %s and id = %s for update",
            (business, bom_id),
        )
    ).fetchone()

    try:
        async with module_writes(SUPPLY_MODULE):
            if existing is None:
                if body.expected_revision != 0:
                    raise SupplyRevisionConflictError("Expected revision 0 for new BOM")
                next_rev = 1
                await conn.execute(
                    "insert into gba.supply_boms "
                    "(tenant_id, id, location_id, code, title, output_item_id, "
                    "batch_output_quantity, "
                    "standard_labor_minor, standard_overhead_minor, is_active, revision, "
                    "recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        business,
                        bom_id,
                        body.location_id,
                        body.code,
                        body.title,
                        body.output_item_id,
                        body.batch_output_quantity,
                        body.standard_labor_minor,
                        body.standard_overhead_minor,
                        body.is_active,
                        user_id,
                    ),
                )
            else:
                curr_rev = int(existing[0])
                if body.expected_revision != curr_rev:
                    raise SupplyRevisionConflictError("BOM revision mismatch")
                if (
                    UUID(str(existing[1])) != body.location_id
                    or UUID(str(existing[2])) != body.output_item_id
                ):
                    raise SupplyStateError("BOM branch and output_item_id cannot change")
                next_rev = curr_rev + 1
                await conn.execute(
                    "update gba.supply_boms "
                    "set code = %s, title = %s, batch_output_quantity = %s, "
                    "standard_labor_minor = %s, standard_overhead_minor = %s, is_active = %s, "
                    "revision = %s, recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.code,
                        body.title,
                        body.batch_output_quantity,
                        body.standard_labor_minor,
                        body.standard_overhead_minor,
                        body.is_active,
                        next_rev,
                        user_id,
                        business,
                        bom_id,
                    ),
                )
                await conn.execute(
                    "delete from gba.supply_bom_components where tenant_id = %s and bom_id = %s",
                    (business, bom_id),
                )

            for idx, comp in enumerate(body.components, start=1):
                await conn.execute(
                    "insert into gba.supply_bom_components "
                    "(tenant_id, id, location_id, bom_id, line_no, component_item_id, "
                    "quantity_per_batch, scrap_bps) values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        uuid7(),
                        body.location_id,
                        bom_id,
                        idx,
                        comp.component_item_id,
                        comp.quantity_per_batch,
                        comp.scrap_bps,
                    ),
                )
    except errors.UniqueViolation as exc:
        raise SupplyStateError("Duplicate BOM code in this branch") from exc
    except errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError(
            "Referenced branch, output item, or component item not found"
        ) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "supply.bom.saved",
        "supply_bom",
        str(bom_id),
        {"revision": next_rev},
    )
    await commands.complete(conn, scope, _BomReceipt(bom_id=bom_id, revision=next_rev))
    return await _load_bom(conn, business, bom_id)


async def _load_work_order(
    conn: RuntimeConnection, business: UUID, work_order_id: UUID
) -> WorkOrderView:
    async with conn.cursor(row_factory=class_row(WorkOrderView)) as cur:
        await cur.execute(
            "select id as work_order_id, location_id, code, goods_owner_id, bom_id, "
            "output_item_id, place_id, planned_quantity, issued_material_cost_minor, "
            "returned_material_cost_minor, labor_cost_minor, overhead_cost_minor, "
            "completed_quantity, scrap_quantity, output_total_cost_minor, status, "
            "revision, recorded_by, recorded_at "
            "from gba.supply_work_orders where tenant_id = %s and id = %s",
            (business, work_order_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise NotFoundError("Work order not found")
    return row


async def list_work_orders(
    conn: RuntimeConnection, business: UUID, *, location_id: UUID | None = None
) -> WorkOrderList:
    sql = (
        "select id as work_order_id, location_id, code, goods_owner_id, bom_id, "
        "output_item_id, place_id, planned_quantity, issued_material_cost_minor, "
        "returned_material_cost_minor, labor_cost_minor, overhead_cost_minor, "
        "completed_quantity, scrap_quantity, output_total_cost_minor, status, "
        "revision, recorded_by, recorded_at "
        "from gba.supply_work_orders where tenant_id = %s"
    )
    params: list[object] = [business]
    if location_id is not None:
        sql += " and location_id = %s"
        params.append(location_id)
    sql += " order by recorded_at desc, id desc"
    async with conn.cursor(row_factory=class_row(WorkOrderView)) as cur:
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()
    return WorkOrderList(items=rows)


async def save_work_order(
    conn: RuntimeConnection,
    business: UUID,
    work_order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: WorkOrderInput,
) -> WorkOrderView:
    scope = IdempotencyScope(business, actor, "supply.work_order.save", key)
    fp = commands.fingerprint(
        {"work_order_id": str(work_order_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fp, _WoReceipt)
    if receipt is not None:
        return await _load_work_order(conn, business, receipt.work_order_id)

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    owner_row = await (
        await conn.execute(
            "select owner_kind, location_id from gba.supply_goods_owners where tenant_id = "
            "%s and id = %s",
            (business, body.goods_owner_id),
        )
    ).fetchone()
    if owner_row is None or UUID(str(owner_row[1])) != body.location_id:
        raise InvalidReferenceError("Goods owner not found in this branch", field="goods_owner_id")
    if str(owner_row[0]) != "company_entity":
        raise SupplyOwnerMismatchError(
            "Manufacturing work orders require a company_entity goods owner"
        )

    bom_row = await (
        await conn.execute(
            "select output_item_id, standard_labor_minor, standard_overhead_minor, location_id "
            "from gba.supply_boms where tenant_id = %s and id = %s",
            (business, body.bom_id),
        )
    ).fetchone()
    if bom_row is None or UUID(str(bom_row[3])) != body.location_id:
        raise InvalidReferenceError("BOM not found in this branch", field="bom_id")
    output_item_id = UUID(str(bom_row[0]))
    labor_minor = body.labor_cost_minor if body.labor_cost_minor is not None else int(bom_row[1])
    overhead_minor = (
        body.overhead_cost_minor if body.overhead_cost_minor is not None else int(bom_row[2])
    )

    existing = await (
        await conn.execute(
            "select revision, status from gba.supply_work_orders "
            "where tenant_id = %s and id = %s for update",
            (business, work_order_id),
        )
    ).fetchone()

    try:
        async with module_writes(SUPPLY_MODULE):
            if existing is None:
                if body.expected_revision != 0:
                    raise SupplyRevisionConflictError("Expected revision 0 for new work order")
                next_rev = 1
                await conn.execute(
                    "insert into gba.supply_work_orders "
                    "(tenant_id, id, location_id, code, goods_owner_id, bom_id, output_item_id, "
                    "place_id, planned_quantity, labor_cost_minor, overhead_cost_minor, status, "
                    "revision, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        business,
                        work_order_id,
                        body.location_id,
                        body.code,
                        body.goods_owner_id,
                        body.bom_id,
                        output_item_id,
                        body.place_id,
                        body.planned_quantity,
                        labor_minor,
                        overhead_minor,
                        body.status,
                        user_id,
                    ),
                )
            else:
                curr_rev = int(existing[0])
                curr_status = str(existing[1])
                if body.expected_revision != curr_rev:
                    raise SupplyRevisionConflictError("Work order revision mismatch")
                if curr_status in ("completed", "cancelled"):
                    raise SupplyStateError(f"Cannot modify {curr_status} work order")
                next_rev = curr_rev + 1
                await conn.execute(
                    "update gba.supply_work_orders "
                    "set code = %s, planned_quantity = %s, labor_cost_minor = %s, "
                    "overhead_cost_minor = %s, status = %s, revision = %s, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.code,
                        body.planned_quantity,
                        labor_minor,
                        overhead_minor,
                        body.status,
                        next_rev,
                        user_id,
                        business,
                        work_order_id,
                    ),
                )
    except errors.UniqueViolation as exc:
        raise SupplyStateError("Duplicate work order code in this branch") from exc
    except errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError("Referenced storage place or BOM not found") from exc

    await commands.audit(
        conn,
        business,
        actor,
        "supply.work_order.saved",
        "supply_work_order",
        str(work_order_id),
        {"revision": next_rev, "status": body.status},
    )
    await commands.complete(conn, scope, _WoReceipt(work_order_id=work_order_id, revision=next_rev))
    return await _load_work_order(conn, business, work_order_id)


async def list_work_order_issues(
    conn: RuntimeConnection, business: UUID, work_order_id: UUID
) -> WorkOrderIssueList:
    async with conn.cursor(row_factory=class_row(WorkOrderIssueView)) as cur:
        await cur.execute(
            "select id as issue_id, work_order_id, location_id, goods_owner_id, place_id, "
            "bin_id, component_item_id, lot_id, quantity, returned_quantity, "
            "stock_document_id, stock_line_no, cost_minor, returned_cost_minor, "
            "recorded_by, recorded_at "
            "from gba.supply_work_order_issues where tenant_id = %s and work_order_id = %s "
            "order by recorded_at, id",
            (business, work_order_id),
        )
        rows = await cur.fetchall()
    return WorkOrderIssueList(items=rows)


async def issue_work_order_material(
    conn: RuntimeConnection,
    business: UUID,
    work_order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: WorkOrderIssueInput,
) -> WorkOrderIssueView:
    scope = IdempotencyScope(business, actor, "supply.work_order.issue", key)
    fp = commands.fingerprint(
        {"work_order_id": str(work_order_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fp, _IssueReceipt)
    if receipt is not None:
        items = (await list_work_order_issues(conn, business, work_order_id)).items
        for it in items:
            if it.issue_id == receipt.issue_id:
                return it

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    wo = await (
        await conn.execute(
            "select location_id, goods_owner_id, status, revision "
            "from gba.supply_work_orders where tenant_id = %s and id = %s for update",
            (business, work_order_id),
        )
    ).fetchone()
    if wo is None:
        raise NotFoundError("Work order not found")
    loc_id, owner_id, wo_status, wo_rev = (
        UUID(str(wo[0])),
        UUID(str(wo[1])),
        str(wo[2]),
        int(wo[3]),
    )
    if wo_status not in ("released", "in_progress"):
        raise SupplyStateError(f"Cannot issue materials to work order in status {wo_status}")

    owner_kind, legal_entity_id, place_id, lot_status = await _verify_owner_lot_bin(
        conn,
        business,
        location_id=loc_id,
        goods_owner_id=owner_id,
        item_id=body.component_item_id,
        lot_id=body.lot_id,
        bin_id=body.bin_id,
    )
    if owner_kind != "company_entity" or legal_entity_id is None:
        raise SupplyOwnerMismatchError("Work order requires company_entity owner")
    if lot_status != "active":
        raise SupplyStateError(f"Cannot issue component from {lot_status} lot")

    bal_row = await (
        await conn.execute(
            "select id, quantity from gba.supply_lot_balances "
            "where tenant_id = %s and bin_id = %s and goods_owner_id = %s "
            "and item_id = %s and lot_id = %s for update",
            (business, body.bin_id, owner_id, body.component_item_id, body.lot_id),
        )
    ).fetchone()
    if bal_row is None or int(bal_row[1]) < body.quantity:
        raise SupplyInsufficientLotError("Insufficient component lot balance in bin")

    qty_text = await _item_quantity_text(conn, business, body.component_item_id, body.quantity)
    wo_doc_id = uuid7()
    await stock.post_document(
        conn,
        business,
        wo_doc_id,
        user=user_id,
        actor=actor,
        key=f"sup-mfg-iss-{key}"[:120],
        body=WriteOffInput(
            kind="write_off",
            legal_entity_id=legal_entity_id,
            place_id=place_id,
            reason="used",
            document_date=body.document_date,
            lines=(WriteOffLine(item_id=body.component_item_id, quantity=qty_text),),
        ),
    )

    val_row = await (
        await conn.execute(
            "select amount_minor from gba.stock_valuations "
            "where tenant_id = %s and document_id = %s and line_no = 1",
            (business, wo_doc_id),
        )
    ).fetchone()
    cost_minor = int(val_row[0]) if val_row is not None else 0

    issue_id = uuid7()
    async with module_writes(SUPPLY_MODULE):
        await conn.execute(
            "update gba.supply_lot_balances set quantity = quantity - %s, updated_at = "
            "clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (body.quantity, business, bal_row[0]),
        )
        await conn.execute(
            "insert into gba.supply_wms_movements "
            "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, lot_id, "
            "movement_kind, direction, quantity, stock_document_id, stock_line_no, "
            "reference_code, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, 'production_issue', 'out', %s, %s, 1, "
            "%s, %s)",
            (
                business,
                uuid7(),
                loc_id,
                place_id,
                body.bin_id,
                owner_id,
                body.component_item_id,
                body.lot_id,
                body.quantity,
                wo_doc_id,
                f"WO-ISS-{str(work_order_id)[:8]}",
                user_id,
            ),
        )
        await conn.execute(
            "insert into gba.supply_work_order_issues "
            "(tenant_id, id, location_id, work_order_id, goods_owner_id, place_id, bin_id, "
            "component_item_id, lot_id, quantity, returned_quantity, stock_document_id, "
            "stock_line_no, cost_minor, returned_cost_minor, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, 1, %s, 0, %s)",
            (
                business,
                issue_id,
                loc_id,
                work_order_id,
                owner_id,
                place_id,
                body.bin_id,
                body.component_item_id,
                body.lot_id,
                body.quantity,
                wo_doc_id,
                cost_minor,
                user_id,
            ),
        )
        await conn.execute(
            "update gba.supply_work_orders "
            "set issued_material_cost_minor = issued_material_cost_minor + %s, "
            "status = 'in_progress', revision = %s, recorded_by = %s, recorded_at = "
            "clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (cost_minor, wo_rev + 1, user_id, business, work_order_id),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "supply.work_order.material_issued",
        "supply_work_order_issue",
        str(issue_id),
        {"work_order_id": str(work_order_id), "cost_minor": cost_minor},
    )
    await commands.complete(conn, scope, _IssueReceipt(issue_id=issue_id))
    items = (await list_work_order_issues(conn, business, work_order_id)).items
    return next(it for it in items if it.issue_id == issue_id)


async def list_work_order_returns(
    conn: RuntimeConnection, business: UUID, work_order_id: UUID
) -> WorkOrderReturnList:
    async with conn.cursor(row_factory=class_row(WorkOrderReturnView)) as cur:
        await cur.execute(
            "select id as return_id, work_order_id, issue_id, location_id, goods_owner_id, "
            "place_id, bin_id, component_item_id, lot_id, quantity, stock_return_document_id, "
            "stock_return_line_no, cost_returned_minor, recorded_by, recorded_at "
            "from gba.supply_work_order_returns where tenant_id = %s and work_order_id = %s "
            "order by recorded_at, id",
            (business, work_order_id),
        )
        rows = await cur.fetchall()
    return WorkOrderReturnList(items=rows)


async def return_work_order_material(
    conn: RuntimeConnection,
    business: UUID,
    work_order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: WorkOrderReturnInput,
) -> WorkOrderReturnView:
    scope = IdempotencyScope(business, actor, "supply.work_order.return", key)
    fp = commands.fingerprint(
        {"work_order_id": str(work_order_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fp, _ReturnReceipt)
    if receipt is not None:
        items = (await list_work_order_returns(conn, business, work_order_id)).items
        for it in items:
            if it.return_id == receipt.return_id:
                return it

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    wo = await (
        await conn.execute(
            "select location_id, goods_owner_id, status, revision "
            "from gba.supply_work_orders where tenant_id = %s and id = %s for update",
            (business, work_order_id),
        )
    ).fetchone()
    if wo is None:
        raise NotFoundError("Work order not found")
    loc_id, owner_id, wo_status, wo_rev = (
        UUID(str(wo[0])),
        UUID(str(wo[1])),
        str(wo[2]),
        int(wo[3]),
    )
    if wo_status not in ("in_progress", "qc_passed"):
        raise SupplyStateError(f"Cannot return materials from work order in status {wo_status}")

    iss = await (
        await conn.execute(
            "select component_item_id, lot_id, quantity, returned_quantity, "
            "stock_document_id, stock_line_no "
            "from gba.supply_work_order_issues "
            "where tenant_id = %s and work_order_id = %s and id = %s for update",
            (business, work_order_id, body.issue_id),
        )
    ).fetchone()
    if iss is None:
        raise InvalidReferenceError("Work order issue not found", field="issue_id")
    comp_item_id = UUID(str(iss[0]))
    lot_id = UUID(str(iss[1]))
    issued_qty = int(iss[2])
    already_ret = int(iss[3])
    src_doc_id = UUID(str(iss[4]))
    src_line_no = int(iss[5])

    if already_ret + body.quantity > issued_qty:
        raise SupplyStateError("Returned quantity exceeds remaining issued quantity")

    owner_kind, legal_entity_id, place_id, _lot_status = await _verify_owner_lot_bin(
        conn,
        business,
        location_id=loc_id,
        goods_owner_id=owner_id,
        item_id=comp_item_id,
        lot_id=lot_id,
        bin_id=body.bin_id,
    )
    if owner_kind != "company_entity" or legal_entity_id is None:
        raise SupplyOwnerMismatchError("Work order requires company_entity owner")

    qty_text = await _item_quantity_text(conn, business, comp_item_id, body.quantity)
    ret_doc_id = uuid7()
    await stock.post_document(
        conn,
        business,
        ret_doc_id,
        user=user_id,
        actor=actor,
        key=f"sup-mfg-ret-{key}"[:120],
        body=ReturnInput(
            kind="return",
            reason="unused",
            legal_entity_id=legal_entity_id,
            place_id=place_id,
            document_date=body.document_date,
            source_document_id=src_doc_id,
            lines=(ReturnLine(source_line_no=src_line_no, quantity=qty_text),),
        ),
    )

    val_row = await (
        await conn.execute(
            "select amount_minor from gba.stock_valuations "
            "where tenant_id = %s and document_id = %s and line_no = 1",
            (business, ret_doc_id),
        )
    ).fetchone()
    cost_ret_minor = int(val_row[0]) if val_row is not None else 0

    return_id = uuid7()
    async with module_writes(SUPPLY_MODULE):
        bal_row = await (
            await conn.execute(
                "select id from gba.supply_lot_balances "
                "where tenant_id = %s and bin_id = %s and goods_owner_id = %s "
                "and item_id = %s and lot_id = %s for update",
                (business, body.bin_id, owner_id, comp_item_id, lot_id),
            )
        ).fetchone()
        if bal_row is None:
            await conn.execute(
                "insert into gba.supply_lot_balances "
                "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, "
                "lot_id, quantity) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    uuid7(),
                    loc_id,
                    place_id,
                    body.bin_id,
                    owner_id,
                    comp_item_id,
                    lot_id,
                    body.quantity,
                ),
            )
        else:
            await conn.execute(
                "update gba.supply_lot_balances set quantity = quantity + %s, updated_at = "
                "clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (body.quantity, business, bal_row[0]),
            )

        await conn.execute(
            "insert into gba.supply_wms_movements "
            "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, lot_id, "
            "movement_kind, direction, quantity, stock_document_id, stock_line_no, "
            "reference_code, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, 'production_return', 'in', %s, %s, 1, "
            "%s, %s)",
            (
                business,
                uuid7(),
                loc_id,
                place_id,
                body.bin_id,
                owner_id,
                comp_item_id,
                lot_id,
                body.quantity,
                ret_doc_id,
                f"WO-RET-{str(work_order_id)[:8]}",
                user_id,
            ),
        )
        await conn.execute(
            "update gba.supply_work_order_issues "
            "set returned_quantity = returned_quantity + %s, "
            "returned_cost_minor = returned_cost_minor + %s "
            "where tenant_id = %s and id = %s",
            (body.quantity, cost_ret_minor, business, body.issue_id),
        )
        await conn.execute(
            "insert into gba.supply_work_order_returns "
            "(tenant_id, id, location_id, work_order_id, issue_id, goods_owner_id, place_id, "
            "bin_id, component_item_id, lot_id, quantity, stock_return_document_id, "
            "stock_return_line_no, cost_returned_minor, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)",
            (
                business,
                return_id,
                loc_id,
                work_order_id,
                body.issue_id,
                owner_id,
                place_id,
                body.bin_id,
                comp_item_id,
                lot_id,
                body.quantity,
                ret_doc_id,
                cost_ret_minor,
                user_id,
            ),
        )
        await conn.execute(
            "update gba.supply_work_orders "
            "set returned_material_cost_minor = returned_material_cost_minor + %s, "
            "revision = %s, recorded_by = %s, recorded_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (cost_ret_minor, wo_rev + 1, user_id, business, work_order_id),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "supply.work_order.material_returned",
        "supply_work_order_return",
        str(return_id),
        {"work_order_id": str(work_order_id), "cost_returned_minor": cost_ret_minor},
    )
    await commands.complete(conn, scope, _ReturnReceipt(return_id=return_id))
    items = (await list_work_order_returns(conn, business, work_order_id)).items
    return next(it for it in items if it.return_id == return_id)


async def record_work_order_qc(
    conn: RuntimeConnection,
    business: UUID,
    work_order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: WorkOrderQcInput,
) -> WorkOrderQcView:
    scope = IdempotencyScope(business, actor, "supply.work_order.qc", key)
    fp = commands.fingerprint(
        {"work_order_id": str(work_order_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fp, _QcReceipt)
    if receipt is not None:
        async with conn.cursor(row_factory=class_row(WorkOrderQcView)) as cur:
            await cur.execute(
                "select id as qc_id, work_order_id, location_id, passed_quantity, "
                "scrap_quantity, notes, inspected_by, inspected_at "
                "from gba.supply_work_order_qc where tenant_id = %s and id = %s",
                (business, receipt.qc_id),
            )
            found = await cur.fetchone()
        if found is not None:
            return found

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    wo = await (
        await conn.execute(
            "select location_id, status, revision from gba.supply_work_orders "
            "where tenant_id = %s and id = %s for update",
            (business, work_order_id),
        )
    ).fetchone()
    if wo is None:
        raise NotFoundError("Work order not found")
    loc_id, wo_status, wo_rev = UUID(str(wo[0])), str(wo[1]), int(wo[2])
    if wo_status != "in_progress":
        raise SupplyStateError("Work order must have materials issued (in_progress) before QC")

    qc_id = uuid7()
    async with module_writes(SUPPLY_MODULE):
        await conn.execute(
            "insert into gba.supply_work_order_qc "
            "(tenant_id, id, location_id, work_order_id, passed_quantity, scrap_quantity, "
            "notes, inspected_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                qc_id,
                loc_id,
                work_order_id,
                body.passed_quantity,
                body.scrap_quantity,
                body.notes,
                user_id,
            ),
        )
        await conn.execute(
            "update gba.supply_work_orders "
            "set completed_quantity = %s, scrap_quantity = %s, status = 'qc_passed', "
            "revision = %s, recorded_by = %s, recorded_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (
                body.passed_quantity,
                body.scrap_quantity,
                wo_rev + 1,
                user_id,
                business,
                work_order_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "supply.work_order.qc_recorded",
        "supply_work_order_qc",
        str(qc_id),
        {"work_order_id": str(work_order_id), "passed_quantity": body.passed_quantity},
    )
    await commands.complete(conn, scope, _QcReceipt(qc_id=qc_id))
    async with conn.cursor(row_factory=class_row(WorkOrderQcView)) as cur:
        await cur.execute(
            "select id as qc_id, work_order_id, location_id, passed_quantity, "
            "scrap_quantity, notes, inspected_by, inspected_at "
            "from gba.supply_work_order_qc where tenant_id = %s and id = %s",
            (business, qc_id),
        )
        res = await cur.fetchone()
    if res is None:
        raise NotFoundError("Work order QC record not found")
    return res


async def get_work_order_output(
    conn: RuntimeConnection, business: UUID, work_order_id: UUID
) -> WorkOrderOutputView:
    async with conn.cursor(row_factory=class_row(WorkOrderOutputView)) as cur:
        await cur.execute(
            "select id as output_id, work_order_id, location_id, goods_owner_id, place_id, "
            "bin_id, output_item_id, output_lot_id, quantity, material_cost_minor, "
            "labor_cost_minor, overhead_cost_minor, total_cost_minor, unit_cost_minor, "
            "stock_receipt_document_id, stock_receipt_line_no, recorded_by, recorded_at "
            "from gba.supply_work_order_outputs where tenant_id = %s and work_order_id = %s",
            (business, work_order_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise NotFoundError("Work order output not found")
    return row


async def complete_work_order_output(
    conn: RuntimeConnection,
    business: UUID,
    work_order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: WorkOrderOutputInput,
) -> WorkOrderOutputView:
    scope = IdempotencyScope(business, actor, "supply.work_order.output", key)
    fp = commands.fingerprint(
        {"work_order_id": str(work_order_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fp, _OutputReceipt)
    if receipt is not None:
        return await get_work_order_output(conn, business, work_order_id)

    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)

    wo = await (
        await conn.execute(
            "select location_id, goods_owner_id, output_item_id, issued_material_cost_minor, "
            "returned_material_cost_minor, labor_cost_minor, overhead_cost_minor, "
            "completed_quantity, status, revision "
            "from gba.supply_work_orders where tenant_id = %s and id = %s for update",
            (business, work_order_id),
        )
    ).fetchone()
    if wo is None:
        raise NotFoundError("Work order not found")
    (
        loc_id,
        owner_id,
        out_item_id,
        iss_mat_minor,
        ret_mat_minor,
        labor_minor,
        overhead_minor,
        comp_qty,
        wo_status,
        wo_rev,
    ) = (
        UUID(str(wo[0])),
        UUID(str(wo[1])),
        UUID(str(wo[2])),
        int(wo[3]),
        int(wo[4]),
        int(wo[5]),
        int(wo[6]),
        int(wo[7]),
        str(wo[8]),
        int(wo[9]),
    )
    if wo_status != "qc_passed" or comp_qty <= 0:
        raise SupplyStateError(
            "Work order must pass QC with positive passed_quantity before output"
        )

    owner_row = await (
        await conn.execute(
            "select owner_kind, legal_entity_id from gba.supply_goods_owners where "
            "tenant_id = %s and id = %s",
            (business, owner_id),
        )
    ).fetchone()
    if owner_row is None or str(owner_row[0]) != "company_entity" or owner_row[1] is None:
        raise SupplyOwnerMismatchError("Work order requires company_entity owner")
    legal_entity_id = UUID(str(owner_row[1]))

    bin_row = await (
        await conn.execute(
            "select place_id, dedicated_owner_id, is_active, location_id "
            "from gba.supply_warehouse_bins where tenant_id = %s and id = %s",
            (business, body.bin_id),
        )
    ).fetchone()
    if bin_row is None or UUID(str(bin_row[3])) != loc_id:
        raise InvalidReferenceError("Destination bin not found in this branch", field="bin_id")
    if not bool(bin_row[2]):
        raise SupplyStateError("Destination bin is inactive")
    if bin_row[1] is not None and UUID(str(bin_row[1])) != owner_id:
        raise SupplyOwnerMismatchError("Destination bin is dedicated to another goods owner")
    place_id = UUID(str(bin_row[0]))

    net_mat_minor = iss_mat_minor - ret_mat_minor
    total_cost_minor = net_mat_minor + labor_minor + overhead_minor
    unit_cost_minor = (total_cost_minor + comp_qty // 2) // comp_qty

    book_row = await (
        await conn.execute(
            "select c.minor_units from gba.ledger_books b "
            "join lateral (select base_currency from gba.ledger_book_versions "
            "where tenant_id = b.tenant_id and book_id = b.id "
            "order by revision desc limit 1) v on true "
            "join gba.currencies c on c.code = v.base_currency "
            "where b.tenant_id = %s and b.legal_entity_id = %s",
            (business, legal_entity_id),
        )
    ).fetchone()
    places = int(book_row[0]) if book_row is not None else 2
    amount_text = from_minor(total_cost_minor, places)
    qty_text = await _item_quantity_text(conn, business, out_item_id, comp_qty)

    rcpt_doc_id = uuid7()
    await stock.post_document(
        conn,
        business,
        rcpt_doc_id,
        user=user_id,
        actor=actor,
        key=f"sup-mfg-out-{key}"[:120],
        body=ReceiptInput(
            kind="receipt",
            legal_entity_id=legal_entity_id,
            place_id=place_id,
            reason="purchase",
            document_date=body.manufactured_on,
            lines=(
                ReceiptLine(
                    item_id=out_item_id,
                    quantity=qty_text,
                    amount=amount_text,
                ),
            ),
        ),
    )

    output_id = uuid7()
    async with module_writes(SUPPLY_MODULE):
        existing_lot = await (
            await conn.execute(
                "select id from gba.supply_lots "
                "where tenant_id = %s and location_id = %s and goods_owner_id = %s "
                "and item_id = %s and lot_code = %s for update",
                (business, loc_id, owner_id, out_item_id, body.output_lot_code),
            )
        ).fetchone()
        if existing_lot is None:
            output_lot_id = uuid7()
            await conn.execute(
                "insert into gba.supply_lots "
                "(tenant_id, id, location_id, goods_owner_id, item_id, lot_code, "
                "manufactured_on, expires_on, status, unit_cost_minor, notes, revision, "
                "recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s, 1, %s)",
                (
                    business,
                    output_lot_id,
                    loc_id,
                    owner_id,
                    out_item_id,
                    body.output_lot_code,
                    body.manufactured_on,
                    body.expires_on,
                    unit_cost_minor,
                    f"Manufactured by work order {work_order_id}",
                    user_id,
                ),
            )
        else:
            output_lot_id = UUID(str(existing_lot[0]))
            await conn.execute(
                "update gba.supply_lots set unit_cost_minor = %s, revision = revision + 1, "
                "recorded_by = %s, recorded_at = clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (unit_cost_minor, user_id, business, output_lot_id),
            )

        bal_row = await (
            await conn.execute(
                "select id from gba.supply_lot_balances "
                "where tenant_id = %s and bin_id = %s and goods_owner_id = %s "
                "and item_id = %s and lot_id = %s for update",
                (business, body.bin_id, owner_id, out_item_id, output_lot_id),
            )
        ).fetchone()
        if bal_row is None:
            await conn.execute(
                "insert into gba.supply_lot_balances "
                "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, "
                "lot_id, quantity) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    uuid7(),
                    loc_id,
                    place_id,
                    body.bin_id,
                    owner_id,
                    out_item_id,
                    output_lot_id,
                    comp_qty,
                ),
            )
        else:
            await conn.execute(
                "update gba.supply_lot_balances set quantity = quantity + %s, updated_at = "
                "clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (comp_qty, business, bal_row[0]),
            )

        await conn.execute(
            "insert into gba.supply_wms_movements "
            "(tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, lot_id, "
            "movement_kind, direction, quantity, stock_document_id, stock_line_no, "
            "reference_code, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, 'production_output', 'in', %s, %s, 1, "
            "%s, %s)",
            (
                business,
                uuid7(),
                loc_id,
                place_id,
                body.bin_id,
                owner_id,
                out_item_id,
                output_lot_id,
                comp_qty,
                rcpt_doc_id,
                f"WO-OUT-{str(work_order_id)[:8]}",
                user_id,
            ),
        )
        await conn.execute(
            "insert into gba.supply_work_order_outputs "
            "(tenant_id, id, location_id, work_order_id, goods_owner_id, place_id, bin_id, "
            "output_item_id, output_lot_id, quantity, material_cost_minor, labor_cost_minor, "
            "overhead_cost_minor, total_cost_minor, unit_cost_minor, stock_receipt_document_id, "
            "stock_receipt_line_no, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
            (
                business,
                output_id,
                loc_id,
                work_order_id,
                owner_id,
                place_id,
                body.bin_id,
                out_item_id,
                output_lot_id,
                comp_qty,
                net_mat_minor,
                labor_minor,
                overhead_minor,
                total_cost_minor,
                unit_cost_minor,
                rcpt_doc_id,
                user_id,
            ),
        )
        await conn.execute(
            "update gba.supply_work_orders "
            "set output_total_cost_minor = %s, status = 'completed', revision = %s, "
            "recorded_by = %s, recorded_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (total_cost_minor, wo_rev + 1, user_id, business, work_order_id),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "supply.work_order.completed",
        "supply_work_order_output",
        str(output_id),
        {"work_order_id": str(work_order_id), "total_cost_minor": total_cost_minor},
    )
    await commands.complete(conn, scope, _OutputReceipt(output_id=output_id))
    return await get_work_order_output(conn, business, work_order_id)
