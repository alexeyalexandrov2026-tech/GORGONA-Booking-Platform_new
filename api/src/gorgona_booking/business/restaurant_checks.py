"""REST-01 Slice 3 (ADR-0037): checks, kitchen station tickets and STOCK-01 write-offs."""

from datetime import date
from typing import Literal
from uuid import UUID, uuid7

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules, stock
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.restaurant_floor import (
    RESTAURANT_MODULE,
    RestaurantNotReadyError,
    RestaurantRevisionError,
    RestaurantStateError,
    _clean_multiline,
    _clean_single_line,
)
from gorgona_booking.business.restaurant_menu import KitchenStation, _clean_currency
from gorgona_booking.business.stock_contracts import WriteOffInput, WriteOffLine, from_count
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

ServiceMode = Literal["dine_in", "takeout", "bar", "delivery"]
CheckStatus = Literal["open", "closed", "voided"]
CheckLineStatus = Literal["draft", "fired", "served", "voided"]
KitchenTicketStatus = Literal["queued", "preparing", "ready", "served", "voided"]
KitchenTicketAction = Literal["start", "mark_ready", "serve", "void"]

_MAX_REVISION = 2_147_483_647

_TICKET_TARGET: dict[KitchenTicketAction, KitchenTicketStatus] = {
    "start": "preparing",
    "mark_ready": "ready",
    "serve": "served",
    "void": "voided",
}
_TICKET_TRANSITIONS: dict[KitchenTicketStatus, frozenset[KitchenTicketStatus]] = {
    "queued": frozenset({"preparing", "voided"}),
    "preparing": frozenset({"ready", "voided"}),
    "ready": frozenset({"served", "voided"}),
    "served": frozenset(),
    "voided": frozenset(),
}


class OpenCheckInput(Versioned):
    location_id: UUID
    service_mode: ServiceMode
    currency: str
    table_id: UUID | None = None
    reservation_id: UUID | None = None
    guest_counterparty_id: UUID | None = None
    guest_name: str | None = None
    note: str | None = None

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        return _clean_currency(value)

    @field_validator("guest_name")
    @classmethod
    def valid_guest_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_single_line(value, 120)

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        return None if value is None else _clean_multiline(value, 1000)


class AddCheckLineInput(Versioned):
    menu_item_id: UUID
    quantity: StrictInt = Field(ge=1, le=100)
    modifier_option_ids: list[UUID] = Field(default_factory=list, max_length=100)
    note: str | None = None

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        return None if value is None else _clean_single_line(value, 500)


class VoidCheckLineInput(Versioned):
    reason: str

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        return _clean_single_line(value, 500)


class FireCheckInput(Versioned):
    line_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=500)


class CloseCheckInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION - 1)
    void_check: bool = False


class KitchenTicketEventInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION - 1)
    action: KitchenTicketAction
    note: str | None = None

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        return None if value is None else _clean_multiline(value, 1000)


class PostConsumptionInput(Versioned):
    legal_entity_id: UUID
    place_id: UUID
    document_date: date


class CheckLineModifierView(Strict):
    modifier_no: int
    group_id: UUID
    option_id: UUID
    group_name: str
    option_code: str
    option_name: str
    price_delta_minor: int
    stock_item_id: UUID | None
    stock_quantity: int | None


class CheckLineView(Strict):
    line_id: UUID
    check_id: UUID
    line_no: int
    menu_item_id: UUID
    menu_item_revision: int
    recipe_revision: int | None
    item_code: str
    item_name: str
    kitchen_station: KitchenStation
    quantity: int
    base_price_minor: int
    modifiers_delta_minor: int
    unit_price_minor: int
    line_total_minor: int
    status: CheckLineStatus
    kitchen_ticket_id: UUID | None
    note: str | None
    void_reason: str | None
    modifiers: list[CheckLineModifierView] = Field(default_factory=list)
    recorded_by: UUID
    recorded_at: AwareDatetime


class CheckView(Strict):
    schema_version: Literal[1] = 1
    check_id: UUID
    location_id: UUID
    service_mode: ServiceMode
    table_id: UUID | None
    reservation_id: UUID | None
    guest_counterparty_id: UUID | None
    guest_name: str | None
    currency: str
    status: CheckStatus
    subtotal_minor: int
    note: str | None
    revision: int
    opened_by: UUID
    opened_at: AwareDatetime
    closed_by: UUID | None
    closed_at: AwareDatetime | None
    consumption_posted: bool = False
    stock_document_id: UUID | None = None
    lines: list[CheckLineView] = Field(default_factory=list)


class CheckList(Strict):
    schema_version: Literal[1] = 1
    items: list[CheckView]
    next_after: UUID | None = None


class KitchenTicketEventView(Strict):
    revision: int
    action: KitchenTicketAction
    note: str | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class KitchenTicketView(Strict):
    schema_version: Literal[1] = 1
    ticket_id: UUID
    check_id: UUID
    location_id: UUID
    ticket_no: int
    kitchen_station: KitchenStation
    status: KitchenTicketStatus
    revision: int
    fired_by: UUID
    fired_at: AwareDatetime
    recorded_by: UUID
    recorded_at: AwareDatetime
    lines: list[CheckLineView] = Field(default_factory=list)
    events: list[KitchenTicketEventView] = Field(default_factory=list)


class KitchenTicketList(Strict):
    schema_version: Literal[1] = 1
    items: list[KitchenTicketView]
    next_after: UUID | None = None


class FireResultView(Strict):
    schema_version: Literal[1] = 1
    check_id: UUID
    tickets: list[KitchenTicketView]


class ConsumptionLineView(Strict):
    stock_item_id: UUID
    stock_item_code: str
    stock_item_unit: str
    stock_item_quantity_scale: int
    quantity: int


class CheckConsumptionView(Strict):
    schema_version: Literal[1] = 1
    check_id: UUID
    location_id: UUID
    posted: bool
    legal_entity_id: UUID | None = None
    place_id: UUID | None = None
    document_date: date | None = None
    stock_document_id: UUID | None = None
    posted_by: UUID | None = None
    posted_at: AwareDatetime | None = None
    lines: list[ConsumptionLineView]


class _CheckReceipt(Strict):
    check_id: UUID


class _CheckLineReceipt(Strict):
    check_id: UUID
    line_id: UUID


class _FireReceipt(Strict):
    check_id: UUID
    ticket_ids: list[UUID]


class _TicketReceipt(Strict):
    ticket_id: UUID


class _CheckRow(Strict):
    check_id: UUID
    location_id: UUID
    service_mode: ServiceMode
    table_id: UUID | None
    reservation_id: UUID | None
    guest_counterparty_id: UUID | None
    guest_name: str | None
    currency: str
    status: CheckStatus
    subtotal_minor: int
    note: str | None
    revision: int
    opened_by: UUID
    opened_at: AwareDatetime
    closed_by: UUID | None
    closed_at: AwareDatetime | None
    consumption_posted: bool
    stock_document_id: UUID | None


class _CheckLineRow(Strict):
    line_id: UUID
    check_id: UUID
    line_no: int
    menu_item_id: UUID
    menu_item_revision: int
    recipe_revision: int | None
    item_code: str
    item_name: str
    kitchen_station: KitchenStation
    quantity: int
    base_price_minor: int
    modifiers_delta_minor: int
    unit_price_minor: int
    line_total_minor: int
    status: CheckLineStatus
    kitchen_ticket_id: UUID | None
    note: str | None
    void_reason: str | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class _TicketRow(Strict):
    ticket_id: UUID
    check_id: UUID
    location_id: UUID
    ticket_no: int
    kitchen_station: KitchenStation
    status: KitchenTicketStatus
    revision: int
    fired_by: UUID
    fired_at: AwareDatetime
    recorded_by: UUID
    recorded_at: AwareDatetime


def _check_ready() -> None:
    if not modules.MODULES_BY_ID[RESTAURANT_MODULE].enableable:
        raise RestaurantNotReadyError("The restaurant module is not enabled for use")


async def _ensure_location_exists(
    conn: RuntimeConnection, business: UUID, location_id: UUID
) -> None:
    found = await (
        await conn.execute(
            "select 1 from gba.locations where tenant_id = %s and id = %s",
            (business, location_id),
        )
    ).fetchone()
    if found is None:
        raise InvalidReferenceError("Branch location not found", field="location_id")


_SELECT_CHECKS = """
select c.id as check_id, c.location_id, c.service_mode, c.table_id, c.reservation_id,
       c.guest_counterparty_id, c.guest_name, c.currency, c.status, c.subtotal_minor,
       c.note, c.revision, c.opened_by, c.opened_at, c.closed_by, c.closed_at,
       (cons.check_id is not null) as consumption_posted,
       cons.stock_document_id
from gba.restaurant_checks c
left join gba.restaurant_check_consumptions cons
  on cons.tenant_id = c.tenant_id and cons.check_id = c.id
where c.tenant_id = %s
"""

_SELECT_LINES = """
select id as line_id, check_id, line_no, menu_item_id, menu_item_revision,
       recipe_revision, item_code, item_name, kitchen_station, quantity,
       base_price_minor, modifiers_delta_minor, unit_price_minor, line_total_minor,
       status, kitchen_ticket_id, note, void_reason, recorded_by, recorded_at
from gba.restaurant_check_lines
where tenant_id = %s
"""


async def _load_lines_with_modifiers(
    conn: RuntimeConnection,
    business: UUID,
    *,
    check_ids: list[UUID] | None = None,
    ticket_ids: list[UUID] | None = None,
) -> list[CheckLineView]:
    if check_ids is not None:
        if not check_ids:
            return []
        sql = _SELECT_LINES + " and check_id = any(%s) order by check_id, line_no"
        params: tuple[object, ...] = (business, check_ids)
    elif ticket_ids is not None:
        if not ticket_ids:
            return []
        sql = _SELECT_LINES + " and kitchen_ticket_id = any(%s) order by kitchen_ticket_id, line_no"
        params = (business, ticket_ids)
    else:
        return []
    async with conn.cursor(row_factory=class_row(_CheckLineRow)) as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
    if not rows:
        return []
    line_ids = [r.line_id for r in rows]
    mod_rows = await (
        await conn.execute(
            "select check_line_id, modifier_no, group_id, option_id, group_name, "
            "option_code, option_name, price_delta_minor, stock_item_id, stock_quantity "
            "from gba.restaurant_check_line_modifiers "
            "where tenant_id = %s and check_line_id = any(%s) "
            "order by check_line_id, modifier_no",
            (business, line_ids),
        )
    ).fetchall()
    by_line: dict[UUID, list[CheckLineModifierView]] = {}
    for (
        lid,
        mod_no,
        gid,
        oid,
        gname,
        ocode,
        oname,
        delta,
        sid,
        sqty,
    ) in mod_rows:
        by_line.setdefault(lid, []).append(
            CheckLineModifierView(
                modifier_no=mod_no,
                group_id=gid,
                option_id=oid,
                group_name=gname,
                option_code=ocode,
                option_name=oname,
                price_delta_minor=delta,
                stock_item_id=sid,
                stock_quantity=sqty,
            )
        )
    return [
        CheckLineView(
            **r.model_dump(),
            modifiers=by_line.get(r.line_id, []),
        )
        for r in rows
    ]


async def _hydrate_checks(
    conn: RuntimeConnection, business: UUID, rows: list[_CheckRow]
) -> list[CheckView]:
    if not rows:
        return []
    lines = await _load_lines_with_modifiers(conn, business, check_ids=[r.check_id for r in rows])
    by_check: dict[UUID, list[CheckLineView]] = {}
    for line in lines:
        by_check.setdefault(line.check_id, []).append(line)
    return [CheckView(**r.model_dump(), lines=by_check.get(r.check_id, [])) for r in rows]


async def _hydrate_tickets(
    conn: RuntimeConnection, business: UUID, rows: list[_TicketRow]
) -> list[KitchenTicketView]:
    if not rows:
        return []
    tids = [r.ticket_id for r in rows]
    lines = await _load_lines_with_modifiers(conn, business, ticket_ids=tids)
    lines_by_ticket: dict[UUID, list[CheckLineView]] = {}
    for line in lines:
        if line.kitchen_ticket_id is not None:
            lines_by_ticket.setdefault(line.kitchen_ticket_id, []).append(line)
    ev_rows = await (
        await conn.execute(
            "select ticket_id, revision, action, note, recorded_by, recorded_at "
            "from gba.restaurant_kitchen_ticket_events "
            "where tenant_id = %s and ticket_id = any(%s) order by ticket_id, revision",
            (business, tids),
        )
    ).fetchall()
    ev_by_ticket: dict[UUID, list[KitchenTicketEventView]] = {}
    for tid, rev, act, note, rec_by, rec_at in ev_rows:
        ev_by_ticket.setdefault(tid, []).append(
            KitchenTicketEventView(
                revision=rev, action=act, note=note, recorded_by=rec_by, recorded_at=rec_at
            )
        )
    return [
        KitchenTicketView(
            **r.model_dump(),
            lines=lines_by_ticket.get(r.ticket_id, []),
            events=ev_by_ticket.get(r.ticket_id, []),
        )
        for r in rows
    ]


async def list_checks(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    status: CheckStatus | None = None,
    table_id: UUID | None = None,
    after: UUID | None = None,
    limit: int = 50,
) -> CheckList:
    await require_module(conn, business, RESTAURANT_MODULE)
    clauses: list[str] = []
    params: list[object] = [business]
    if location_id is not None:
        clauses.append("c.location_id = %s")
        params.append(location_id)
    if status is not None:
        clauses.append("c.status = %s")
        params.append(status)
    if table_id is not None:
        clauses.append("c.table_id = %s")
        params.append(table_id)
    if after is not None:
        clauses.append("c.id > %s")
        params.append(after)
    params.append(limit + 1)
    where_extra = (" and " + " and ".join(clauses)) if clauses else ""
    async with conn.cursor(row_factory=class_row(_CheckRow)) as cur:
        await cur.execute(_SELECT_CHECKS + where_extra + " order by c.id limit %s", params)
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    return CheckList(
        items=await _hydrate_checks(conn, business, page),
        next_after=page[-1].check_id if has_more else None,
    )


async def get_check(conn: RuntimeConnection, business: UUID, check_id: UUID) -> CheckView:
    await require_module(conn, business, RESTAURANT_MODULE)
    async with conn.cursor(row_factory=class_row(_CheckRow)) as cur:
        await cur.execute(_SELECT_CHECKS + " and c.id = %s", (business, check_id))
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Restaurant check not found")
    return (await _hydrate_checks(conn, business, [found]))[0]


async def open_check(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: OpenCheckInput,
) -> CheckView:
    if location_scope is not None and body.location_id != location_scope:
        raise PermissionDeniedError("You can only open checks in your assigned branch")
    scope = IdempotencyScope(business, actor, "restaurant.check.open", key)
    fingerprint = commands.fingerprint({"body": body.model_dump(mode="json")})
    receipt = await commands.claim(conn, scope, fingerprint, _CheckReceipt)
    if receipt is not None:
        return await get_check(conn, business, receipt.check_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)
    await _ensure_location_exists(conn, business, body.location_id)

    check_id = uuid7()
    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "insert into gba.restaurant_checks "
                "(tenant_id, id, location_id, service_mode, table_id, reservation_id, "
                "guest_counterparty_id, guest_name, currency, status, subtotal_minor, "
                "note, revision, opened_by, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', 0, %s, 1, %s, %s)",
                (
                    business,
                    check_id,
                    body.location_id,
                    body.service_mode,
                    body.table_id,
                    body.reservation_id,
                    body.guest_counterparty_id,
                    body.guest_name,
                    body.currency,
                    body.note,
                    user_id,
                    user_id,
                ),
            )
        except errors.ForeignKeyViolation as exc:
            cname = exc.diag.constraint_name or ""
            if "guest_fk" in cname:
                raise InvalidReferenceError(
                    "Guest counterparty not found", field="guest_counterparty_id"
                ) from exc
            if "table" in cname:
                raise InvalidReferenceError(
                    "Table not found in this branch", field="table_id"
                ) from exc
            raise InvalidReferenceError(
                "Referenced table or reservation not found in this branch",
                field="reservation_id",
            ) from exc
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.check_opened",
        "restaurant_check",
        str(check_id),
        {"location_id": str(body.location_id), "service_mode": body.service_mode},
    )
    await commands.complete(conn, scope, _CheckReceipt(check_id=check_id))
    return await get_check(conn, business, check_id)


async def _recompute_check_subtotal(
    conn: RuntimeConnection, business: UUID, check_id: UUID, user_id: UUID
) -> int:
    total_row = await (
        await conn.execute(
            "select coalesce(sum(line_total_minor), 0) from gba.restaurant_check_lines "
            "where tenant_id = %s and check_id = %s and status <> 'voided'",
            (business, check_id),
        )
    ).fetchone()
    subtotal = int(total_row[0]) if total_row is not None else 0
    await conn.execute(
        "update gba.restaurant_checks "
        "set subtotal_minor = %s, revision = revision + 1, "
        "recorded_by = %s, recorded_at = clock_timestamp() "
        "where tenant_id = %s and id = %s",
        (subtotal, user_id, business, check_id),
    )
    return subtotal


async def add_check_line(
    conn: RuntimeConnection,
    business: UUID,
    check_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: AddCheckLineInput,
) -> CheckView:
    scope = IdempotencyScope(business, actor, "restaurant.check_line.add", key)
    fingerprint = commands.fingerprint(
        {"check_id": str(check_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _CheckLineReceipt)
    if receipt is not None:
        return await get_check(conn, business, receipt.check_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    chk = await (
        await conn.execute(
            "select location_id, currency, status from gba.restaurant_checks "
            "where tenant_id = %s and id = %s for update",
            (business, check_id),
        )
    ).fetchone()
    if chk is None:
        raise NotFoundError("Restaurant check not found")
    check_loc: UUID = chk[0]
    check_currency: str = chk[1]
    check_status: str = chk[2]
    if location_scope is not None and check_loc != location_scope:
        raise PermissionDeniedError("You can only modify checks in your assigned branch")
    if check_status != "open":
        raise RestaurantStateError("Lines can only be added to an open check")

    item = await (
        await conn.execute(
            "select id, location_id, code, name, kitchen_station, price_minor, currency, "
            "revision, is_active from gba.restaurant_menu_items "
            "where tenant_id = %s and id = %s and location_id = %s for share",
            (business, body.menu_item_id, check_loc),
        )
    ).fetchone()
    if item is None:
        raise InvalidReferenceError("Menu item not found in this branch", field="menu_item_id")
    (
        _,
        _,
        item_code,
        item_name,
        kitchen_station,
        base_price_minor,
        item_currency,
        item_rev,
        item_active,
    ) = item
    if not item_active:
        raise RestaurantStateError("Cannot order an inactive menu item")
    if item_currency != check_currency:
        raise RestaurantStateError("Menu item currency does not match check currency")

    # Validate attached modifier groups and selected options
    attached_groups = await (
        await conn.execute(
            "select g.id, g.name, g.min_select, g.max_select, g.is_active "
            "from gba.restaurant_menu_item_modifier_groups l "
            "join gba.restaurant_modifier_groups g "
            "  on g.tenant_id = l.tenant_id and g.id = l.group_id "
            "where l.tenant_id = %s and l.menu_item_id = %s "
            "order by l.sort_order, g.id",
            (business, body.menu_item_id),
        )
    ).fetchall()
    group_meta: dict[UUID, tuple[str, int, int, bool]] = {
        gid: (gname, min_s, max_s, gact) for gid, gname, min_s, max_s, gact in attached_groups
    }

    selected_snapshots: list[tuple[UUID, UUID, str, str, str, int, UUID | None, int | None]] = []
    counts_by_group: dict[UUID, int] = {}

    if body.modifier_option_ids:
        unique_opt_ids = list(dict.fromkeys(body.modifier_option_ids))
        opt_rows = await (
            await conn.execute(
                "select id, group_id, code, name, price_delta_minor, stock_item_id, "
                "stock_quantity, is_active from gba.restaurant_modifier_options "
                "where tenant_id = %s and location_id = %s and id = any(%s)",
                (business, check_loc, unique_opt_ids),
            )
        ).fetchall()
        opts_by_id = {row[0]: row for row in opt_rows}
        for oid in body.modifier_option_ids:
            opt = opts_by_id.get(oid)
            if opt is None:
                raise InvalidReferenceError(
                    "Modifier option not found in this branch", field="modifier_option_ids"
                )
            _, gid, ocode, oname, delta, sid, sqty, oactive = opt
            if gid not in group_meta:
                raise RestaurantStateError(
                    "Selected modifier option does not belong to an attached modifier group"
                )
            if not oactive:
                raise RestaurantStateError("Selected modifier option is inactive")
            gname, _, _, gactive = group_meta[gid]
            if not gactive:
                raise RestaurantStateError("Selected modifier group is inactive")
            counts_by_group[gid] = counts_by_group.get(gid, 0) + 1
            selected_snapshots.append((gid, oid, gname, ocode, oname, int(delta), sid, sqty))

    for gid, (gname, min_s, max_s, gactive) in group_meta.items():
        if not gactive and counts_by_group.get(gid, 0) == 0:
            continue
        selected_count = counts_by_group.get(gid, 0)
        if selected_count < min_s or selected_count > max_s:
            raise RestaurantStateError(
                f"Modifier group '{gname}' requires between {min_s} and {max_s} selections"
            )

    modifiers_delta = sum(s[5] for s in selected_snapshots)
    unit_price = int(base_price_minor) + modifiers_delta
    if unit_price < 0:
        raise RestaurantStateError("Line unit price after modifiers cannot be negative")
    line_total = unit_price * body.quantity

    rec_row = await (
        await conn.execute(
            "select max(revision) from gba.restaurant_recipes "
            "where tenant_id = %s and menu_item_id = %s",
            (business, body.menu_item_id),
        )
    ).fetchone()
    recipe_rev: int | None = rec_row[0] if rec_row is not None else None

    line_no_row = await (
        await conn.execute(
            "select coalesce(max(line_no), 0) + 1 from gba.restaurant_check_lines "
            "where tenant_id = %s and check_id = %s",
            (business, check_id),
        )
    ).fetchone()
    next_line_no = int(line_no_row[0]) if line_no_row is not None else 1
    line_id = uuid7()

    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "insert into gba.restaurant_check_lines "
                "(tenant_id, id, check_id, location_id, line_no, menu_item_id, "
                "menu_item_revision, recipe_revision, item_code, item_name, kitchen_station, "
                "quantity, base_price_minor, modifiers_delta_minor, unit_price_minor, "
                "line_total_minor, status, note, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "'draft', %s, %s)",
                (
                    business,
                    line_id,
                    check_id,
                    check_loc,
                    next_line_no,
                    body.menu_item_id,
                    item_rev,
                    recipe_rev,
                    item_code,
                    item_name,
                    kitchen_station,
                    body.quantity,
                    base_price_minor,
                    modifiers_delta,
                    unit_price,
                    line_total,
                    body.note,
                    user_id,
                ),
            )
            for mod_no, snap in enumerate(selected_snapshots, start=1):
                gid, oid, gname, ocode, oname, delta, sid, sqty = snap
                await conn.execute(
                    "insert into gba.restaurant_check_line_modifiers "
                    "(tenant_id, check_line_id, modifier_no, location_id, group_id, option_id, "
                    "group_name, option_code, option_name, price_delta_minor, "
                    "stock_item_id, stock_quantity) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        line_id,
                        mod_no,
                        check_loc,
                        gid,
                        oid,
                        gname,
                        ocode,
                        oname,
                        delta,
                        sid,
                        sqty,
                    ),
                )
            await _recompute_check_subtotal(conn, business, check_id, user_id)
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.check_line_added",
        "restaurant_check",
        str(check_id),
        {"line_id": str(line_id), "menu_item_id": str(body.menu_item_id), "total": line_total},
    )
    await commands.complete(conn, scope, _CheckLineReceipt(check_id=check_id, line_id=line_id))
    return await get_check(conn, business, check_id)


async def void_check_line(
    conn: RuntimeConnection,
    business: UUID,
    check_id: UUID,
    line_id: UUID,
    *,
    location_scope: UUID | None,
    can_manage: bool,
    user_id: UUID,
    actor: str,
    key: str,
    body: VoidCheckLineInput,
) -> CheckView:
    scope = IdempotencyScope(business, actor, "restaurant.check_line.void", key)
    fingerprint = commands.fingerprint(
        {
            "check_id": str(check_id),
            "line_id": str(line_id),
            "body": body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _CheckLineReceipt)
    if receipt is not None:
        return await get_check(conn, business, receipt.check_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    chk = await (
        await conn.execute(
            "select location_id, status from gba.restaurant_checks "
            "where tenant_id = %s and id = %s for update",
            (business, check_id),
        )
    ).fetchone()
    if chk is None:
        raise NotFoundError("Restaurant check not found")
    check_loc: UUID = chk[0]
    if location_scope is not None and check_loc != location_scope:
        raise PermissionDeniedError("You can only modify checks in your assigned branch")
    if chk[1] != "open":
        raise RestaurantStateError("Only open checks can void lines")

    line = await (
        await conn.execute(
            "select status, kitchen_ticket_id from gba.restaurant_check_lines "
            "where tenant_id = %s and check_id = %s and id = %s for update",
            (business, check_id, line_id),
        )
    ).fetchone()
    if line is None:
        raise NotFoundError("Restaurant check line not found")
    line_status, ticket_id = line
    if line_status == "voided":
        raise RestaurantStateError("Check line is already voided")
    if line_status != "draft" and not can_manage:
        raise PermissionDeniedError("Voiding a fired or served line requires restaurant.manage")

    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "update gba.restaurant_check_lines "
                "set status = 'voided', void_reason = %s, "
                "recorded_by = %s, recorded_at = clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (body.reason, user_id, business, line_id),
            )
            # If every line on its kitchen ticket is now voided and ticket is not terminal, void it
            if ticket_id is not None:
                rem = await (
                    await conn.execute(
                        "select count(*) from gba.restaurant_check_lines "
                        "where tenant_id = %s and kitchen_ticket_id = %s and status <> 'voided'",
                        (business, ticket_id),
                    )
                ).fetchone()
                if rem is not None and int(rem[0]) == 0:
                    trow = await (
                        await conn.execute(
                            "select status, revision from gba.restaurant_kitchen_tickets "
                            "where tenant_id = %s and id = %s for update",
                            (business, ticket_id),
                        )
                    ).fetchone()
                    if trow is not None and trow[0] in ("queued", "preparing", "ready"):
                        next_rev = int(trow[1]) + 1
                        await conn.execute(
                            "update gba.restaurant_kitchen_tickets "
                            "set status = 'voided', revision = %s, "
                            "recorded_by = %s, recorded_at = clock_timestamp() "
                            "where tenant_id = %s and id = %s",
                            (next_rev, user_id, business, ticket_id),
                        )
                        await conn.execute(
                            "insert into gba.restaurant_kitchen_ticket_events "
                            "(tenant_id, ticket_id, revision, location_id, action, "
                            "note, recorded_by) "
                            "values (%s, %s, %s, %s, 'void', %s, %s)",
                            (business, ticket_id, next_rev, check_loc, body.reason, user_id),
                        )
            await _recompute_check_subtotal(conn, business, check_id, user_id)
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.check_line_voided",
        "restaurant_check",
        str(check_id),
        {"line_id": str(line_id), "reason": body.reason},
    )
    await commands.complete(conn, scope, _CheckLineReceipt(check_id=check_id, line_id=line_id))
    return await get_check(conn, business, check_id)


async def fire_check_lines(
    conn: RuntimeConnection,
    business: UUID,
    check_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: FireCheckInput,
) -> FireResultView:
    scope = IdempotencyScope(business, actor, "restaurant.check.fire", key)
    fingerprint = commands.fingerprint(
        {"check_id": str(check_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _FireReceipt)
    if receipt is not None:
        tickets = await _load_tickets_by_ids(conn, business, receipt.ticket_ids)
        return FireResultView(check_id=receipt.check_id, tickets=tickets)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    chk = await (
        await conn.execute(
            "select location_id, status from gba.restaurant_checks "
            "where tenant_id = %s and id = %s for update",
            (business, check_id),
        )
    ).fetchone()
    if chk is None:
        raise NotFoundError("Restaurant check not found")
    check_loc: UUID = chk[0]
    if location_scope is not None and check_loc != location_scope:
        raise PermissionDeniedError("You can only fire checks in your assigned branch")
    if chk[1] != "open":
        raise RestaurantStateError("Only open checks can be fired to the kitchen")

    if body.line_ids is not None:
        draft_rows = await (
            await conn.execute(
                "select id, kitchen_station from gba.restaurant_check_lines "
                "where tenant_id = %s and check_id = %s and status = 'draft' "
                "and id = any(%s) order by line_no for update",
                (business, check_id, body.line_ids),
            )
        ).fetchall()
        if len(draft_rows) != len(set(body.line_ids)):
            raise RestaurantStateError("Every requested line must be in draft state on this check")
    else:
        draft_rows = await (
            await conn.execute(
                "select id, kitchen_station from gba.restaurant_check_lines "
                "where tenant_id = %s and check_id = %s and status = 'draft' "
                "order by line_no for update",
                (business, check_id),
            )
        ).fetchall()
    if not draft_rows:
        raise RestaurantStateError("No draft lines available to fire")

    by_station: dict[str, list[UUID]] = {}
    for lid, station in draft_rows:
        by_station.setdefault(str(station), []).append(lid)

    max_no_row = await (
        await conn.execute(
            "select coalesce(max(ticket_no), 0) from gba.restaurant_kitchen_tickets "
            "where tenant_id = %s and check_id = %s",
            (business, check_id),
        )
    ).fetchone()
    next_ticket_no = (int(max_no_row[0]) if max_no_row is not None else 0) + 1
    created_ticket_ids: list[UUID] = []

    async with module_writes(RESTAURANT_MODULE):
        try:
            for station in sorted(by_station):
                tid = uuid7()
                await conn.execute(
                    "insert into gba.restaurant_kitchen_tickets "
                    "(tenant_id, id, check_id, location_id, ticket_no, kitchen_station, "
                    "status, revision, fired_by, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, 'queued', 1, %s, %s)",
                    (business, tid, check_id, check_loc, next_ticket_no, station, user_id, user_id),
                )
                await conn.execute(
                    "update gba.restaurant_check_lines "
                    "set status = 'fired', kitchen_ticket_id = %s, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = any(%s)",
                    (tid, user_id, business, by_station[station]),
                )
                created_ticket_ids.append(tid)
                next_ticket_no += 1
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.check_fired",
        "restaurant_check",
        str(check_id),
        {"ticket_ids": [str(t) for t in created_ticket_ids]},
    )
    await commands.complete(
        conn, scope, _FireReceipt(check_id=check_id, ticket_ids=created_ticket_ids)
    )
    return FireResultView(
        check_id=check_id,
        tickets=await _load_tickets_by_ids(conn, business, created_ticket_ids),
    )


async def close_check(
    conn: RuntimeConnection,
    business: UUID,
    check_id: UUID,
    *,
    location_scope: UUID | None,
    can_manage: bool,
    user_id: UUID,
    actor: str,
    key: str,
    body: CloseCheckInput,
) -> CheckView:
    scope = IdempotencyScope(business, actor, "restaurant.check.close", key)
    fingerprint = commands.fingerprint(
        {"check_id": str(check_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _CheckReceipt)
    if receipt is not None:
        return await get_check(conn, business, receipt.check_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    chk = await (
        await conn.execute(
            "select location_id, status, revision from gba.restaurant_checks "
            "where tenant_id = %s and id = %s for update",
            (business, check_id),
        )
    ).fetchone()
    if chk is None:
        raise NotFoundError("Restaurant check not found")
    check_loc: UUID = chk[0]
    if location_scope is not None and check_loc != location_scope:
        raise PermissionDeniedError("You can only close checks in your assigned branch")
    if body.void_check and not can_manage:
        raise PermissionDeniedError("Voiding a check requires restaurant.manage")
    if int(chk[2]) != body.expected_revision:
        raise RestaurantRevisionError(
            "Restaurant check has changed", details={"revision": int(chk[2])}
        )
    target_status: CheckStatus = "voided" if body.void_check else "closed"

    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "update gba.restaurant_checks "
                "set status = %s, revision = %s, closed_by = %s, closed_at = clock_timestamp(), "
                "recorded_by = %s, recorded_at = clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (target_status, int(chk[2]) + 1, user_id, user_id, business, check_id),
            )
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        f"restaurant.check_{target_status}",
        "restaurant_check",
        str(check_id),
        {"location_id": str(check_loc)},
    )
    await commands.complete(conn, scope, _CheckReceipt(check_id=check_id))
    return await get_check(conn, business, check_id)


async def _load_tickets_by_ids(
    conn: RuntimeConnection, business: UUID, ticket_ids: list[UUID]
) -> list[KitchenTicketView]:
    if not ticket_ids:
        return []
    async with conn.cursor(row_factory=class_row(_TicketRow)) as cur:
        await cur.execute(
            "select id as ticket_id, check_id, location_id, ticket_no, kitchen_station, "
            "status, revision, fired_by, fired_at, recorded_by, recorded_at "
            "from gba.restaurant_kitchen_tickets "
            "where tenant_id = %s and id = any(%s) order by ticket_no, id",
            (business, ticket_ids),
        )
        rows = await cur.fetchall()
    return await _hydrate_tickets(conn, business, rows)


async def list_kitchen_tickets(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    kitchen_station: KitchenStation | None = None,
    status: KitchenTicketStatus | None = None,
    check_id: UUID | None = None,
    after: UUID | None = None,
    limit: int = 50,
) -> KitchenTicketList:
    await require_module(conn, business, RESTAURANT_MODULE)
    clauses: list[str] = []
    params: list[object] = [business]
    if location_id is not None:
        clauses.append("location_id = %s")
        params.append(location_id)
    if kitchen_station is not None:
        clauses.append("kitchen_station = %s")
        params.append(kitchen_station)
    if status is not None:
        clauses.append("status = %s")
        params.append(status)
    if check_id is not None:
        clauses.append("check_id = %s")
        params.append(check_id)
    if after is not None:
        clauses.append("id > %s")
        params.append(after)
    params.append(limit + 1)
    where_extra = (" and " + " and ".join(clauses)) if clauses else ""
    sql = (
        "select id as ticket_id, check_id, location_id, ticket_no, kitchen_station, "
        "status, revision, fired_by, fired_at, recorded_by, recorded_at "
        "from gba.restaurant_kitchen_tickets where tenant_id = %s"
        + where_extra
        + " order by id limit %s"
    )
    async with conn.cursor(row_factory=class_row(_TicketRow)) as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    return KitchenTicketList(
        items=await _hydrate_tickets(conn, business, page),
        next_after=page[-1].ticket_id if has_more else None,
    )


async def get_kitchen_ticket(
    conn: RuntimeConnection, business: UUID, ticket_id: UUID
) -> KitchenTicketView:
    await require_module(conn, business, RESTAURANT_MODULE)
    tickets = await _load_tickets_by_ids(conn, business, [ticket_id])
    if not tickets:
        raise NotFoundError("Kitchen ticket not found")
    return tickets[0]


async def record_kitchen_ticket_event(
    conn: RuntimeConnection,
    business: UUID,
    ticket_id: UUID,
    *,
    location_scope: UUID | None,
    can_manage: bool,
    user_id: UUID,
    actor: str,
    key: str,
    body: KitchenTicketEventInput,
) -> KitchenTicketView:
    scope = IdempotencyScope(business, actor, "restaurant.kitchen_ticket.event", key)
    fingerprint = commands.fingerprint(
        {"ticket_id": str(ticket_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _TicketReceipt)
    if receipt is not None:
        return await get_kitchen_ticket(conn, business, receipt.ticket_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    if body.action == "void" and not can_manage:
        raise PermissionDeniedError("Voiding a kitchen ticket requires restaurant.manage")

    trow = await (
        await conn.execute(
            "select check_id, location_id, status, revision from gba.restaurant_kitchen_tickets "
            "where tenant_id = %s and id = %s for update",
            (business, ticket_id),
        )
    ).fetchone()
    if trow is None:
        raise NotFoundError("Kitchen ticket not found")
    check_id, ticket_loc, current_status, current_rev = trow
    if location_scope is not None and ticket_loc != location_scope:
        raise PermissionDeniedError("You can only update kitchen tickets in your assigned branch")
    if int(current_rev) != body.expected_revision:
        raise RestaurantRevisionError(
            "Kitchen ticket has changed", details={"revision": int(current_rev)}
        )
    target = _TICKET_TARGET[body.action]
    if target not in _TICKET_TRANSITIONS[current_status]:
        raise RestaurantStateError(f"Cannot {body.action} a {current_status} kitchen ticket")

    next_rev = int(current_rev) + 1
    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "update gba.restaurant_kitchen_tickets "
                "set status = %s, revision = %s, "
                "recorded_by = %s, recorded_at = clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (target, next_rev, user_id, business, ticket_id),
            )
            await conn.execute(
                "insert into gba.restaurant_kitchen_ticket_events "
                "(tenant_id, ticket_id, revision, location_id, action, note, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (business, ticket_id, next_rev, ticket_loc, body.action, body.note, user_id),
            )
            if body.action == "serve":
                await conn.execute(
                    "update gba.restaurant_check_lines "
                    "set status = 'served', recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and kitchen_ticket_id = %s and status = 'fired'",
                    (user_id, business, ticket_id),
                )
            elif body.action == "void":
                reason = body.note or "Kitchen ticket voided"
                await conn.execute(
                    "update gba.restaurant_check_lines "
                    "set status = 'voided', void_reason = %s, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and kitchen_ticket_id = %s and status <> 'voided'",
                    (reason, user_id, business, ticket_id),
                )
                await _recompute_check_subtotal(conn, business, check_id, user_id)
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        f"restaurant.kitchen_ticket_{body.action}",
        "restaurant_kitchen_ticket",
        str(ticket_id),
        {"check_id": str(check_id), "revision": next_rev},
    )
    await commands.complete(conn, scope, _TicketReceipt(ticket_id=ticket_id))
    return await get_kitchen_ticket(conn, business, ticket_id)


async def _derive_planned_consumption(
    conn: RuntimeConnection, business: UUID, check_id: UUID
) -> list[ConsumptionLineView]:
    rows = await (
        await conn.execute(
            """
            with base_usage as (
                select rl.stock_item_id, (rl.quantity * cl.quantity)::bigint as qty
                from gba.restaurant_check_lines cl
                join gba.restaurant_recipe_lines rl
                  on rl.tenant_id = cl.tenant_id
                 and rl.menu_item_id = cl.menu_item_id
                 and rl.revision = cl.recipe_revision
                where cl.tenant_id = %s
                  and cl.check_id = %s
                  and cl.status in ('fired', 'served')
                  and cl.recipe_revision is not null
            ),
            mod_usage as (
                select m.stock_item_id, (m.stock_quantity * cl.quantity)::bigint as qty
                from gba.restaurant_check_lines cl
                join gba.restaurant_check_line_modifiers m
                  on m.tenant_id = cl.tenant_id
                 and m.check_line_id = cl.id
                where cl.tenant_id = %s
                  and cl.check_id = %s
                  and cl.status in ('fired', 'served')
                  and m.stock_item_id is not null
            ),
            combined as (
                select stock_item_id, qty from base_usage
                union all
                select stock_item_id, qty from mod_usage
            )
            select c.stock_item_id, s.code, s.unit, s.quantity_scale, sum(c.qty)::bigint
            from combined c
            join gba.stock_items s
              on s.tenant_id = %s and s.id = c.stock_item_id
            group by c.stock_item_id, s.code, s.unit, s.quantity_scale
            order by s.code, c.stock_item_id
            """,
            (business, check_id, business, check_id, business),
        )
    ).fetchall()
    return [
        ConsumptionLineView(
            stock_item_id=sid,
            stock_item_code=code,
            stock_item_unit=unit,
            stock_item_quantity_scale=int(scale),
            quantity=int(qty),
        )
        for sid, code, unit, scale, qty in rows
    ]


async def get_check_consumption(
    conn: RuntimeConnection, business: UUID, check_id: UUID
) -> CheckConsumptionView:
    await require_module(conn, business, RESTAURANT_MODULE)
    chk = await (
        await conn.execute(
            "select location_id from gba.restaurant_checks where tenant_id = %s and id = %s",
            (business, check_id),
        )
    ).fetchone()
    if chk is None:
        raise NotFoundError("Restaurant check not found")
    check_loc: UUID = chk[0]

    posted = await (
        await conn.execute(
            "select legal_entity_id, place_id, document_date, stock_document_id, "
            "posted_by, posted_at from gba.restaurant_check_consumptions "
            "where tenant_id = %s and check_id = %s",
            (business, check_id),
        )
    ).fetchone()
    if posted is None:
        planned = await _derive_planned_consumption(conn, business, check_id)
        return CheckConsumptionView(
            check_id=check_id,
            location_id=check_loc,
            posted=False,
            lines=planned,
        )
    line_rows = await (
        await conn.execute(
            "select l.stock_item_id, s.code, s.unit, s.quantity_scale, l.quantity "
            "from gba.restaurant_check_consumption_lines l "
            "join gba.stock_items s on s.tenant_id = l.tenant_id and s.id = l.stock_item_id "
            "where l.tenant_id = %s and l.check_id = %s order by l.line_no",
            (business, check_id),
        )
    ).fetchall()
    return CheckConsumptionView(
        check_id=check_id,
        location_id=check_loc,
        posted=True,
        legal_entity_id=posted[0],
        place_id=posted[1],
        document_date=posted[2],
        stock_document_id=posted[3],
        posted_by=posted[4],
        posted_at=posted[5],
        lines=[
            ConsumptionLineView(
                stock_item_id=sid,
                stock_item_code=code,
                stock_item_unit=unit,
                stock_item_quantity_scale=int(scale),
                quantity=int(qty),
            )
            for sid, code, unit, scale, qty in line_rows
        ],
    )


async def post_check_consumption(
    conn: RuntimeConnection,
    business: UUID,
    check_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: PostConsumptionInput,
) -> CheckConsumptionView:
    if location_scope is not None:
        raise PermissionDeniedError(
            "Posting ingredient write-offs requires company-wide owner or manager access"
        )
    scope = IdempotencyScope(business, actor, "restaurant.check.post_consumption", key)
    fingerprint = commands.fingerprint(
        {"check_id": str(check_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _CheckReceipt)
    if receipt is not None:
        return await get_check_consumption(conn, business, receipt.check_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    chk = await (
        await conn.execute(
            "select location_id, status from gba.restaurant_checks "
            "where tenant_id = %s and id = %s for update",
            (business, check_id),
        )
    ).fetchone()
    if chk is None:
        raise NotFoundError("Restaurant check not found")
    check_loc: UUID = chk[0]
    if chk[1] == "voided":
        raise RestaurantStateError("Voided checks cannot post ingredient consumption")

    already = await (
        await conn.execute(
            "select 1 from gba.restaurant_check_consumptions "
            "where tenant_id = %s and check_id = %s",
            (business, check_id),
        )
    ).fetchone()
    if already is not None:
        raise RestaurantStateError("Ingredient write-off has already been posted for this check")

    draft_cnt = await (
        await conn.execute(
            "select count(*) from gba.restaurant_check_lines "
            "where tenant_id = %s and check_id = %s and status = 'draft'",
            (business, check_id),
        )
    ).fetchone()
    if draft_cnt is not None and int(draft_cnt[0]) > 0:
        raise RestaurantStateError(
            "Fire or void all draft lines before posting ingredient consumption"
        )

    planned = await _derive_planned_consumption(conn, business, check_id)
    stock_doc_id: UUID | None = None
    if planned:
        stock_doc_id = uuid7()
        await stock.post_document(
            conn,
            business,
            stock_doc_id,
            user_id,
            actor,
            key,
            WriteOffInput(
                kind="write_off",
                reason="used",
                legal_entity_id=body.legal_entity_id,
                place_id=body.place_id,
                document_date=body.document_date,
                lines=tuple(
                    WriteOffLine(
                        item_id=line.stock_item_id,
                        quantity=from_count(line.quantity, line.stock_item_quantity_scale),
                    )
                    for line in planned
                ),
            ),
        )

    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "insert into gba.restaurant_check_consumptions "
                "(tenant_id, check_id, location_id, legal_entity_id, place_id, "
                "document_date, stock_document_id, line_count, posted_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    check_id,
                    check_loc,
                    body.legal_entity_id,
                    body.place_id,
                    body.document_date,
                    stock_doc_id,
                    len(planned),
                    user_id,
                ),
            )
            for idx, line in enumerate(planned, start=1):
                await conn.execute(
                    "insert into gba.restaurant_check_consumption_lines "
                    "(tenant_id, check_id, line_no, location_id, stock_item_id, quantity) "
                    "values (%s, %s, %s, %s, %s, %s)",
                    (business, check_id, idx, check_loc, line.stock_item_id, line.quantity),
                )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Storage place or legal entity not found for this branch",
                field="place_id",
            ) from exc
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.check_consumption_posted",
        "restaurant_check",
        str(check_id),
        {
            "location_id": str(check_loc),
            "stock_document_id": str(stock_doc_id) if stock_doc_id else None,
            "lines": len(planned),
        },
    )
    await commands.complete(conn, scope, _CheckReceipt(check_id=check_id))
    return await get_check_consumption(conn, business, check_id)
