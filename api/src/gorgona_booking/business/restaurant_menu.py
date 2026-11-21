"""REST-01 Slice 2 (ADR-0037): versioned menu items, modifiers and recipe BOMs."""

import re
from typing import Literal, Self
from uuid import UUID

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
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
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

KitchenStation = Literal["hot", "cold", "bar", "pastry"]

_MAX_REVISION = 2_147_483_647
_MAX_MONEY = 999_999_999_999
_MAX_QUANTITY = 999_999_999_999
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def _clean_code(value: str) -> str:
    cleaned = value.strip()
    if not _CODE_RE.fullmatch(cleaned):
        raise ValueError("Code must be 1-32 uppercase letters, digits, '_' or '-'")
    return cleaned


def _clean_currency(value: str) -> str:
    cleaned = value.strip()
    if not _CURRENCY_RE.fullmatch(cleaned):
        raise ValueError("Currency must be a 3-letter uppercase ISO code")
    return cleaned


class MenuItemInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    location_id: UUID
    code: str
    name: str
    category: str
    kitchen_station: KitchenStation
    price_minor: StrictInt = Field(ge=0, le=_MAX_MONEY)
    currency: str
    description: str | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_single_line(value, 120)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        return _clean_single_line(value, 64)

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        return _clean_currency(value)

    @field_validator("description")
    @classmethod
    def valid_description(cls, value: str | None) -> str | None:
        return None if value is None else _clean_multiline(value, 1000)


class MenuItemRevisionView(Strict):
    schema_version: Literal[1] = 1
    menu_item_id: UUID
    location_id: UUID
    revision: int
    code: str
    name: str
    category: str
    kitchen_station: KitchenStation
    price_minor: int
    currency: str
    description: str | None
    is_active: bool
    recorded_by: UUID
    recorded_at: AwareDatetime


class MenuItemRevisionList(Strict):
    schema_version: Literal[1] = 1
    items: list[MenuItemRevisionView]


class MenuItemView(Strict):
    schema_version: Literal[1] = 1
    menu_item_id: UUID
    location_id: UUID
    code: str
    name: str
    category: str
    kitchen_station: KitchenStation
    price_minor: int
    currency: str
    description: str | None
    revision: int
    is_active: bool
    modifier_group_ids: list[UUID] = Field(default_factory=list)
    latest_recipe_revision: int | None = None
    recorded_by: UUID
    recorded_at: AwareDatetime


class MenuItemList(Strict):
    schema_version: Literal[1] = 1
    items: list[MenuItemView]
    next_after: UUID | None = None


class ModifierGroupInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    location_id: UUID
    code: str
    name: str
    min_select: StrictInt = Field(ge=0, le=50)
    max_select: StrictInt = Field(ge=1, le=50)
    currency: str
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_single_line(value, 120)

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        return _clean_currency(value)

    @model_validator(mode="after")
    def valid_bounds(self) -> Self:
        if self.max_select < self.min_select:
            raise ValueError("max_select must be greater than or equal to min_select")
        return self


class ModifierOptionInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    code: str
    name: str
    price_delta_minor: StrictInt = Field(ge=-_MAX_MONEY, le=_MAX_MONEY)
    sort_order: StrictInt = Field(default=0, ge=0, le=10000)
    stock_item_id: UUID | None = None
    stock_quantity: StrictInt | None = Field(default=None, ge=1, le=_MAX_QUANTITY)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_single_line(value, 120)

    @model_validator(mode="after")
    def valid_stock_pair(self) -> Self:
        if (self.stock_item_id is None) != (self.stock_quantity is None):
            raise ValueError("stock_item_id and stock_quantity must both be set or both null")
        return self


class ModifierOptionView(Strict):
    schema_version: Literal[1] = 1
    option_id: UUID
    group_id: UUID
    location_id: UUID
    code: str
    name: str
    price_delta_minor: int
    sort_order: int
    stock_item_id: UUID | None
    stock_quantity: int | None
    stock_item_code: str | None = None
    stock_item_unit: str | None = None
    stock_item_quantity_scale: int | None = None
    revision: int
    is_active: bool
    recorded_by: UUID
    recorded_at: AwareDatetime


class ModifierGroupView(Strict):
    schema_version: Literal[1] = 1
    group_id: UUID
    location_id: UUID
    code: str
    name: str
    min_select: int
    max_select: int
    currency: str
    revision: int
    is_active: bool
    options: list[ModifierOptionView] = Field(default_factory=list)
    recorded_by: UUID
    recorded_at: AwareDatetime


class ModifierGroupList(Strict):
    schema_version: Literal[1] = 1
    items: list[ModifierGroupView]
    next_after: UUID | None = None


class MenuItemModifierGroupsInput(Versioned):
    modifier_group_ids: list[UUID] = Field(max_length=50)

    @model_validator(mode="after")
    def unique_groups(self) -> Self:
        if len(set(self.modifier_group_ids)) != len(self.modifier_group_ids):
            raise ValueError("Duplicate modifier_group_id values are not allowed")
        return self


class MenuItemModifierGroupsView(Strict):
    schema_version: Literal[1] = 1
    menu_item_id: UUID
    location_id: UUID
    modifier_group_ids: list[UUID]


class RecipeLineInput(Strict):
    stock_item_id: UUID
    quantity: StrictInt = Field(ge=1, le=_MAX_QUANTITY)
    note: str | None = None

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        return None if value is None else _clean_single_line(value, 200)


class RecipeInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    note: str | None = None
    lines: list[RecipeLineInput] = Field(min_length=1, max_length=100)

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        return None if value is None else _clean_multiline(value, 1000)

    @model_validator(mode="after")
    def unique_materials(self) -> Self:
        ids = [line.stock_item_id for line in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate stock_item_id values are not allowed in a recipe")
        return self


class RecipeLineView(Strict):
    line_no: int
    stock_item_id: UUID
    stock_item_code: str
    stock_item_unit: str
    stock_item_quantity_scale: int
    quantity: int
    note: str | None


class RecipeView(Strict):
    schema_version: Literal[1] = 1
    menu_item_id: UUID
    location_id: UUID
    revision: int
    note: str | None
    lines: list[RecipeLineView]
    recorded_by: UUID
    recorded_at: AwareDatetime


class RecipeList(Strict):
    schema_version: Literal[1] = 1
    items: list[RecipeView]


class _MenuItemReceipt(Strict):
    menu_item_id: UUID


class _ModifierGroupReceipt(Strict):
    group_id: UUID


class _ModifierOptionReceipt(Strict):
    group_id: UUID
    option_id: UUID


class _RecipeReceipt(Strict):
    menu_item_id: UUID
    revision: int


class _MenuItemRow(Strict):
    menu_item_id: UUID
    location_id: UUID
    code: str
    name: str
    category: str
    kitchen_station: KitchenStation
    price_minor: int
    currency: str
    description: str | None
    revision: int
    is_active: bool
    latest_recipe_revision: int | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class _ModifierGroupRow(Strict):
    group_id: UUID
    location_id: UUID
    code: str
    name: str
    min_select: int
    max_select: int
    currency: str
    revision: int
    is_active: bool
    recorded_by: UUID
    recorded_at: AwareDatetime


class _RecipeHeadRow(Strict):
    menu_item_id: UUID
    location_id: UUID
    revision: int
    note: str | None
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


_SELECT_MENU_ITEM_BASE = """
select m.id as menu_item_id, m.location_id, m.code, m.name, m.category,
       m.kitchen_station, m.price_minor, m.currency, m.description,
       m.revision, m.is_active,
       (select max(r.revision) from gba.restaurant_recipes r
         where r.tenant_id = m.tenant_id and r.menu_item_id = m.id) as latest_recipe_revision,
       m.recorded_by, m.recorded_at
from gba.restaurant_menu_items m
where m.tenant_id = %s
"""


async def _attach_menu_item_groups(
    conn: RuntimeConnection, business: UUID, rows: list[_MenuItemRow]
) -> list[MenuItemView]:
    if not rows:
        return []
    item_ids = [r.menu_item_id for r in rows]
    links = await (
        await conn.execute(
            "select menu_item_id, group_id from gba.restaurant_menu_item_modifier_groups "
            "where tenant_id = %s and menu_item_id = any(%s) "
            "order by sort_order, group_id",
            (business, item_ids),
        )
    ).fetchall()
    by_item: dict[UUID, list[UUID]] = {}
    for mid, gid in links:
        by_item.setdefault(mid, []).append(gid)
    return [
        MenuItemView(
            menu_item_id=r.menu_item_id,
            location_id=r.location_id,
            code=r.code,
            name=r.name,
            category=r.category,
            kitchen_station=r.kitchen_station,
            price_minor=r.price_minor,
            currency=r.currency,
            description=r.description,
            revision=r.revision,
            is_active=r.is_active,
            modifier_group_ids=by_item.get(r.menu_item_id, []),
            latest_recipe_revision=r.latest_recipe_revision,
            recorded_by=r.recorded_by,
            recorded_at=r.recorded_at,
        )
        for r in rows
    ]


async def list_menu_items(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    category: str | None = None,
    kitchen_station: KitchenStation | None = None,
    active_only: bool = False,
    after: UUID | None = None,
    limit: int = 50,
) -> MenuItemList:
    await require_module(conn, business, RESTAURANT_MODULE)
    clauses: list[str] = []
    params: list[object] = [business]
    if location_id is not None:
        clauses.append("m.location_id = %s")
        params.append(location_id)
    if category is not None:
        clauses.append("m.category = %s")
        params.append(category.strip())
    if kitchen_station is not None:
        clauses.append("m.kitchen_station = %s")
        params.append(kitchen_station)
    if active_only:
        clauses.append("m.is_active = true")
    if after is not None:
        clauses.append("m.id > %s")
        params.append(after)
    params.append(limit + 1)
    where_extra = (" and " + " and ".join(clauses)) if clauses else ""
    sql = _SELECT_MENU_ITEM_BASE + where_extra + " order by m.id limit %s"
    async with conn.cursor(row_factory=class_row(_MenuItemRow)) as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    items = await _attach_menu_item_groups(conn, business, page)
    return MenuItemList(items=items, next_after=page[-1].menu_item_id if has_more else None)


async def get_menu_item(
    conn: RuntimeConnection,
    business: UUID,
    menu_item_id: UUID,
    *,
    revision: int | None = None,
) -> MenuItemView:
    await require_module(conn, business, RESTAURANT_MODULE)
    if revision is not None:
        async with conn.cursor(row_factory=class_row(MenuItemRevisionView)) as cur:
            await cur.execute(
                "select menu_item_id, location_id, revision, code, name, category, "
                "kitchen_station, price_minor, currency, description, is_active, "
                "recorded_by, recorded_at "
                "from gba.restaurant_menu_item_revisions "
                "where tenant_id = %s and menu_item_id = %s and revision = %s",
                (business, menu_item_id, revision),
            )
            rev = await cur.fetchone()
        if rev is None:
            raise NotFoundError("Restaurant menu item revision not found")
        latest_recipe = await (
            await conn.execute(
                "select max(revision) from gba.restaurant_recipes "
                "where tenant_id = %s and menu_item_id = %s",
                (business, menu_item_id),
            )
        ).fetchone()
        links = await (
            await conn.execute(
                "select group_id from gba.restaurant_menu_item_modifier_groups "
                "where tenant_id = %s and menu_item_id = %s order by sort_order, group_id",
                (business, menu_item_id),
            )
        ).fetchall()
        return MenuItemView(
            menu_item_id=rev.menu_item_id,
            location_id=rev.location_id,
            code=rev.code,
            name=rev.name,
            category=rev.category,
            kitchen_station=rev.kitchen_station,
            price_minor=rev.price_minor,
            currency=rev.currency,
            description=rev.description,
            revision=rev.revision,
            is_active=rev.is_active,
            modifier_group_ids=[row[0] for row in links],
            latest_recipe_revision=latest_recipe[0] if latest_recipe else None,
            recorded_by=rev.recorded_by,
            recorded_at=rev.recorded_at,
        )
    async with conn.cursor(row_factory=class_row(_MenuItemRow)) as cur:
        await cur.execute(
            _SELECT_MENU_ITEM_BASE + " and m.id = %s",
            (business, menu_item_id),
        )
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Restaurant menu item not found")
    return (await _attach_menu_item_groups(conn, business, [found]))[0]


async def list_menu_item_revisions(
    conn: RuntimeConnection, business: UUID, menu_item_id: UUID
) -> MenuItemRevisionList:
    await require_module(conn, business, RESTAURANT_MODULE)
    exists = await (
        await conn.execute(
            "select 1 from gba.restaurant_menu_items where tenant_id = %s and id = %s",
            (business, menu_item_id),
        )
    ).fetchone()
    if exists is None:
        raise NotFoundError("Restaurant menu item not found")
    async with conn.cursor(row_factory=class_row(MenuItemRevisionView)) as cur:
        await cur.execute(
            "select menu_item_id, location_id, revision, code, name, category, "
            "kitchen_station, price_minor, currency, description, is_active, "
            "recorded_by, recorded_at "
            "from gba.restaurant_menu_item_revisions "
            "where tenant_id = %s and menu_item_id = %s order by revision",
            (business, menu_item_id),
        )
        rows = await cur.fetchall()
    return MenuItemRevisionList(items=rows)


async def save_menu_item(
    conn: RuntimeConnection,
    business: UUID,
    menu_item_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: MenuItemInput,
) -> MenuItemView:
    if location_scope is not None and body.location_id != location_scope:
        raise PermissionDeniedError("You can only manage menu items in your assigned branch")
    scope = IdempotencyScope(business, actor, "restaurant.menu_item.save", key)
    fingerprint = commands.fingerprint(
        {"menu_item_id": str(menu_item_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _MenuItemReceipt)
    if receipt is not None:
        return await get_menu_item(conn, business, receipt.menu_item_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)
    await _ensure_location_exists(conn, business, body.location_id)

    async with module_writes(RESTAURANT_MODULE):
        existing = await (
            await conn.execute(
                "select location_id, code, revision from gba.restaurant_menu_items "
                "where tenant_id = %s and id = %s for update",
                (business, menu_item_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise RestaurantRevisionError(
                        "Restaurant menu item does not exist for this revision",
                        details={"revision": 0},
                    )
                await conn.execute(
                    "insert into gba.restaurant_menu_items "
                    "(tenant_id, id, location_id, code, name, category, kitchen_station, "
                    "price_minor, currency, description, revision, is_active, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)",
                    (
                        business,
                        menu_item_id,
                        body.location_id,
                        body.code,
                        body.name,
                        body.category,
                        body.kitchen_station,
                        body.price_minor,
                        body.currency,
                        body.description,
                        body.is_active,
                        user_id,
                    ),
                )
            else:
                existing_loc, existing_code, current_rev = existing
                if body.expected_revision != current_rev:
                    raise RestaurantRevisionError(
                        "Restaurant menu item has changed", details={"revision": current_rev}
                    )
                if existing_loc != body.location_id:
                    raise InvalidReferenceError(
                        "A menu item cannot move to another branch", field="location_id"
                    )
                if existing_code != body.code:
                    raise InvalidReferenceError("A menu item keeps its code", field="code")
                await conn.execute(
                    "update gba.restaurant_menu_items "
                    "set name = %s, category = %s, kitchen_station = %s, price_minor = %s, "
                    "currency = %s, description = %s, revision = %s, is_active = %s, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.name,
                        body.category,
                        body.kitchen_station,
                        body.price_minor,
                        body.currency,
                        body.description,
                        current_rev + 1,
                        body.is_active,
                        user_id,
                        business,
                        menu_item_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise ConflictError("Menu item code already exists in this branch") from exc
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.menu_item_saved",
        "restaurant_menu_item",
        str(menu_item_id),
        {"location_id": str(body.location_id), "code": body.code},
    )
    await commands.complete(conn, scope, _MenuItemReceipt(menu_item_id=menu_item_id))
    return await get_menu_item(conn, business, menu_item_id)


_SELECT_MODIFIER_OPTIONS = """
select o.id as option_id, o.group_id, o.location_id, o.code, o.name,
       o.price_delta_minor, o.sort_order, o.stock_item_id, o.stock_quantity,
       s.code as stock_item_code, s.unit as stock_item_unit,
       s.quantity_scale as stock_item_quantity_scale,
       o.revision, o.is_active, o.recorded_by, o.recorded_at
from gba.restaurant_modifier_options o
left join gba.stock_items s
  on s.tenant_id = o.tenant_id and s.id = o.stock_item_id
where o.tenant_id = %s
"""


async def _attach_group_options(
    conn: RuntimeConnection, business: UUID, rows: list[_ModifierGroupRow]
) -> list[ModifierGroupView]:
    if not rows:
        return []
    group_ids = [r.group_id for r in rows]
    async with conn.cursor(row_factory=class_row(ModifierOptionView)) as cur:
        await cur.execute(
            _SELECT_MODIFIER_OPTIONS
            + " and o.group_id = any(%s) order by o.sort_order, o.code, o.id",
            (business, group_ids),
        )
        opts = await cur.fetchall()
    by_group: dict[UUID, list[ModifierOptionView]] = {}
    for opt in opts:
        by_group.setdefault(opt.group_id, []).append(opt)
    return [
        ModifierGroupView(
            group_id=r.group_id,
            location_id=r.location_id,
            code=r.code,
            name=r.name,
            min_select=r.min_select,
            max_select=r.max_select,
            currency=r.currency,
            revision=r.revision,
            is_active=r.is_active,
            options=by_group.get(r.group_id, []),
            recorded_by=r.recorded_by,
            recorded_at=r.recorded_at,
        )
        for r in rows
    ]


async def list_modifier_groups(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    active_only: bool = False,
    after: UUID | None = None,
    limit: int = 50,
) -> ModifierGroupList:
    await require_module(conn, business, RESTAURANT_MODULE)
    clauses: list[str] = []
    params: list[object] = [business]
    if location_id is not None:
        clauses.append("location_id = %s")
        params.append(location_id)
    if active_only:
        clauses.append("is_active = true")
    if after is not None:
        clauses.append("id > %s")
        params.append(after)
    params.append(limit + 1)
    where_extra = (" and " + " and ".join(clauses)) if clauses else ""
    sql = (
        "select id as group_id, location_id, code, name, min_select, max_select, "
        "currency, revision, is_active, recorded_by, recorded_at "
        "from gba.restaurant_modifier_groups where tenant_id = %s"
        + where_extra
        + " order by id limit %s"
    )
    async with conn.cursor(row_factory=class_row(_ModifierGroupRow)) as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    items = await _attach_group_options(conn, business, page)
    return ModifierGroupList(items=items, next_after=page[-1].group_id if has_more else None)


async def get_modifier_group(
    conn: RuntimeConnection, business: UUID, group_id: UUID
) -> ModifierGroupView:
    await require_module(conn, business, RESTAURANT_MODULE)
    async with conn.cursor(row_factory=class_row(_ModifierGroupRow)) as cur:
        await cur.execute(
            "select id as group_id, location_id, code, name, min_select, max_select, "
            "currency, revision, is_active, recorded_by, recorded_at "
            "from gba.restaurant_modifier_groups where tenant_id = %s and id = %s",
            (business, group_id),
        )
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Restaurant modifier group not found")
    return (await _attach_group_options(conn, business, [found]))[0]


async def save_modifier_group(
    conn: RuntimeConnection,
    business: UUID,
    group_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: ModifierGroupInput,
) -> ModifierGroupView:
    if location_scope is not None and body.location_id != location_scope:
        raise PermissionDeniedError("You can only manage modifier groups in your assigned branch")
    scope = IdempotencyScope(business, actor, "restaurant.modifier_group.save", key)
    fingerprint = commands.fingerprint(
        {"group_id": str(group_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _ModifierGroupReceipt)
    if receipt is not None:
        return await get_modifier_group(conn, business, receipt.group_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)
    await _ensure_location_exists(conn, business, body.location_id)

    async with module_writes(RESTAURANT_MODULE):
        existing = await (
            await conn.execute(
                "select location_id, code, revision from gba.restaurant_modifier_groups "
                "where tenant_id = %s and id = %s for update",
                (business, group_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise RestaurantRevisionError(
                        "Restaurant modifier group does not exist for this revision",
                        details={"revision": 0},
                    )
                await conn.execute(
                    "insert into gba.restaurant_modifier_groups "
                    "(tenant_id, id, location_id, code, name, min_select, max_select, "
                    "currency, revision, is_active, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)",
                    (
                        business,
                        group_id,
                        body.location_id,
                        body.code,
                        body.name,
                        body.min_select,
                        body.max_select,
                        body.currency,
                        body.is_active,
                        user_id,
                    ),
                )
            else:
                existing_loc, existing_code, current_rev = existing
                if body.expected_revision != current_rev:
                    raise RestaurantRevisionError(
                        "Restaurant modifier group has changed",
                        details={"revision": current_rev},
                    )
                if existing_loc != body.location_id:
                    raise InvalidReferenceError(
                        "A modifier group cannot move to another branch", field="location_id"
                    )
                if existing_code != body.code:
                    raise InvalidReferenceError("A modifier group keeps its code", field="code")
                await conn.execute(
                    "update gba.restaurant_modifier_groups "
                    "set name = %s, min_select = %s, max_select = %s, currency = %s, "
                    "revision = %s, is_active = %s, recorded_by = %s, "
                    "recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.name,
                        body.min_select,
                        body.max_select,
                        body.currency,
                        current_rev + 1,
                        body.is_active,
                        user_id,
                        business,
                        group_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise ConflictError("Modifier group code already exists in this branch") from exc
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.modifier_group_saved",
        "restaurant_modifier_group",
        str(group_id),
        {"location_id": str(body.location_id), "code": body.code},
    )
    await commands.complete(conn, scope, _ModifierGroupReceipt(group_id=group_id))
    return await get_modifier_group(conn, business, group_id)


async def _get_modifier_option(
    conn: RuntimeConnection, business: UUID, group_id: UUID, option_id: UUID
) -> ModifierOptionView:
    async with conn.cursor(row_factory=class_row(ModifierOptionView)) as cur:
        await cur.execute(
            _SELECT_MODIFIER_OPTIONS + " and o.group_id = %s and o.id = %s",
            (business, group_id, option_id),
        )
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Restaurant modifier option not found")
    return found


async def save_modifier_option(
    conn: RuntimeConnection,
    business: UUID,
    group_id: UUID,
    option_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: ModifierOptionInput,
) -> ModifierOptionView:
    scope = IdempotencyScope(business, actor, "restaurant.modifier_option.save", key)
    fingerprint = commands.fingerprint(
        {
            "group_id": str(group_id),
            "option_id": str(option_id),
            "body": body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _ModifierOptionReceipt)
    if receipt is not None:
        return await _get_modifier_option(conn, business, receipt.group_id, receipt.option_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    grp = await (
        await conn.execute(
            "select location_id from gba.restaurant_modifier_groups "
            "where tenant_id = %s and id = %s for share",
            (business, group_id),
        )
    ).fetchone()
    if grp is None:
        raise NotFoundError("Restaurant modifier group not found")
    group_location: UUID = grp[0]
    if location_scope is not None and group_location != location_scope:
        raise PermissionDeniedError("You can only manage modifier options in your assigned branch")

    async with module_writes(RESTAURANT_MODULE):
        existing = await (
            await conn.execute(
                "select group_id, code, revision from gba.restaurant_modifier_options "
                "where tenant_id = %s and id = %s for update",
                (business, option_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise RestaurantRevisionError(
                        "Restaurant modifier option does not exist for this revision",
                        details={"revision": 0},
                    )
                await conn.execute(
                    "insert into gba.restaurant_modifier_options "
                    "(tenant_id, id, location_id, group_id, code, name, price_delta_minor, "
                    "sort_order, stock_item_id, stock_quantity, revision, is_active, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)",
                    (
                        business,
                        option_id,
                        group_location,
                        group_id,
                        body.code,
                        body.name,
                        body.price_delta_minor,
                        body.sort_order,
                        body.stock_item_id,
                        body.stock_quantity,
                        body.is_active,
                        user_id,
                    ),
                )
            else:
                existing_group, existing_code, current_rev = existing
                if existing_group != group_id:
                    raise InvalidReferenceError(
                        "Modifier option belongs to another group", field="group_id"
                    )
                if body.expected_revision != current_rev:
                    raise RestaurantRevisionError(
                        "Restaurant modifier option has changed",
                        details={"revision": current_rev},
                    )
                if existing_code != body.code:
                    raise InvalidReferenceError("A modifier option keeps its code", field="code")
                await conn.execute(
                    "update gba.restaurant_modifier_options "
                    "set name = %s, price_delta_minor = %s, sort_order = %s, "
                    "stock_item_id = %s, stock_quantity = %s, revision = %s, is_active = %s, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.name,
                        body.price_delta_minor,
                        body.sort_order,
                        body.stock_item_id,
                        body.stock_quantity,
                        current_rev + 1,
                        body.is_active,
                        user_id,
                        business,
                        option_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise ConflictError("Modifier option code already exists in this group") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Referenced inventory material not found", field="stock_item_id"
            ) from exc
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.modifier_option_saved",
        "restaurant_modifier_option",
        str(option_id),
        {"group_id": str(group_id), "location_id": str(group_location), "code": body.code},
    )
    await commands.complete(
        conn, scope, _ModifierOptionReceipt(group_id=group_id, option_id=option_id)
    )
    return await _get_modifier_option(conn, business, group_id, option_id)


async def set_menu_item_modifier_groups(
    conn: RuntimeConnection,
    business: UUID,
    menu_item_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: MenuItemModifierGroupsInput,
) -> MenuItemModifierGroupsView:
    scope = IdempotencyScope(business, actor, "restaurant.menu_item.modifier_groups.set", key)
    fingerprint = commands.fingerprint(
        {"menu_item_id": str(menu_item_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _MenuItemReceipt)
    if receipt is not None:
        item = await get_menu_item(conn, business, receipt.menu_item_id)
        return MenuItemModifierGroupsView(
            menu_item_id=item.menu_item_id,
            location_id=item.location_id,
            modifier_group_ids=item.modifier_group_ids,
        )
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    found = await (
        await conn.execute(
            "select location_id from gba.restaurant_menu_items "
            "where tenant_id = %s and id = %s for update",
            (business, menu_item_id),
        )
    ).fetchone()
    if found is None:
        raise NotFoundError("Restaurant menu item not found")
    item_location: UUID = found[0]
    if location_scope is not None and item_location != location_scope:
        raise PermissionDeniedError("You can only manage menu items in your assigned branch")

    async with module_writes(RESTAURANT_MODULE):
        await conn.execute(
            "delete from gba.restaurant_menu_item_modifier_groups "
            "where tenant_id = %s and menu_item_id = %s",
            (business, menu_item_id),
        )
        try:
            for sort_order, group_id in enumerate(body.modifier_group_ids):
                await conn.execute(
                    "insert into gba.restaurant_menu_item_modifier_groups "
                    "(tenant_id, menu_item_id, group_id, location_id, sort_order, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s)",
                    (business, menu_item_id, group_id, item_location, sort_order, user_id),
                )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Modifier group not found in this menu item's branch",
                field="modifier_group_ids",
            ) from exc
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.menu_item_modifier_groups_set",
        "restaurant_menu_item",
        str(menu_item_id),
        {"location_id": str(item_location), "count": len(body.modifier_group_ids)},
    )
    await commands.complete(conn, scope, _MenuItemReceipt(menu_item_id=menu_item_id))
    return MenuItemModifierGroupsView(
        menu_item_id=menu_item_id,
        location_id=item_location,
        modifier_group_ids=list(body.modifier_group_ids),
    )


async def _load_recipe_lines(
    conn: RuntimeConnection,
    business: UUID,
    menu_item_id: UUID,
    revisions: list[int],
) -> dict[int, list[RecipeLineView]]:
    if not revisions:
        return {}
    rows = await (
        await conn.execute(
            "select l.revision, l.line_no, l.stock_item_id, s.code, s.unit, "
            "s.quantity_scale, l.quantity, l.note "
            "from gba.restaurant_recipe_lines l "
            "join gba.stock_items s on s.tenant_id = l.tenant_id and s.id = l.stock_item_id "
            "where l.tenant_id = %s and l.menu_item_id = %s and l.revision = any(%s) "
            "order by l.revision, l.line_no",
            (business, menu_item_id, revisions),
        )
    ).fetchall()
    by_rev: dict[int, list[RecipeLineView]] = {}
    for rev, line_no, stock_item_id, code, unit, scale, quantity, note in rows:
        by_rev.setdefault(rev, []).append(
            RecipeLineView(
                line_no=line_no,
                stock_item_id=stock_item_id,
                stock_item_code=code,
                stock_item_unit=unit,
                stock_item_quantity_scale=scale,
                quantity=quantity,
                note=note,
            )
        )
    return by_rev


async def list_recipes(conn: RuntimeConnection, business: UUID, menu_item_id: UUID) -> RecipeList:
    await require_module(conn, business, RESTAURANT_MODULE)
    exists = await (
        await conn.execute(
            "select 1 from gba.restaurant_menu_items where tenant_id = %s and id = %s",
            (business, menu_item_id),
        )
    ).fetchone()
    if exists is None:
        raise NotFoundError("Restaurant menu item not found")
    async with conn.cursor(row_factory=class_row(_RecipeHeadRow)) as cur:
        await cur.execute(
            "select menu_item_id, location_id, revision, note, recorded_by, recorded_at "
            "from gba.restaurant_recipes "
            "where tenant_id = %s and menu_item_id = %s order by revision desc",
            (business, menu_item_id),
        )
        heads = await cur.fetchall()
    lines_by_rev = await _load_recipe_lines(
        conn, business, menu_item_id, [h.revision for h in heads]
    )
    return RecipeList(
        items=[
            RecipeView(
                menu_item_id=h.menu_item_id,
                location_id=h.location_id,
                revision=h.revision,
                note=h.note,
                lines=lines_by_rev.get(h.revision, []),
                recorded_by=h.recorded_by,
                recorded_at=h.recorded_at,
            )
            for h in heads
        ]
    )


async def get_recipe(
    conn: RuntimeConnection, business: UUID, menu_item_id: UUID, revision: int
) -> RecipeView:
    await require_module(conn, business, RESTAURANT_MODULE)
    async with conn.cursor(row_factory=class_row(_RecipeHeadRow)) as cur:
        await cur.execute(
            "select menu_item_id, location_id, revision, note, recorded_by, recorded_at "
            "from gba.restaurant_recipes "
            "where tenant_id = %s and menu_item_id = %s and revision = %s",
            (business, menu_item_id, revision),
        )
        head = await cur.fetchone()
    if head is None:
        raise NotFoundError("Restaurant recipe revision not found")
    lines_by_rev = await _load_recipe_lines(conn, business, menu_item_id, [head.revision])
    return RecipeView(
        menu_item_id=head.menu_item_id,
        location_id=head.location_id,
        revision=head.revision,
        note=head.note,
        lines=lines_by_rev.get(head.revision, []),
        recorded_by=head.recorded_by,
        recorded_at=head.recorded_at,
    )


async def create_recipe_revision(
    conn: RuntimeConnection,
    business: UUID,
    menu_item_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: RecipeInput,
) -> RecipeView:
    scope = IdempotencyScope(business, actor, "restaurant.recipe.create", key)
    fingerprint = commands.fingerprint(
        {"menu_item_id": str(menu_item_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _RecipeReceipt)
    if receipt is not None:
        return await get_recipe(conn, business, receipt.menu_item_id, receipt.revision)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    found = await (
        await conn.execute(
            "select location_id from gba.restaurant_menu_items "
            "where tenant_id = %s and id = %s for update",
            (business, menu_item_id),
        )
    ).fetchone()
    if found is None:
        raise NotFoundError("Restaurant menu item not found")
    item_location: UUID = found[0]
    if location_scope is not None and item_location != location_scope:
        raise PermissionDeniedError("You can only manage recipes in your assigned branch")

    latest_row = await (
        await conn.execute(
            "select coalesce(max(revision), 0) from gba.restaurant_recipes "
            "where tenant_id = %s and menu_item_id = %s",
            (business, menu_item_id),
        )
    ).fetchone()
    latest_rev = int(latest_row[0]) if latest_row is not None else 0
    if body.expected_revision != latest_rev:
        raise RestaurantRevisionError(
            "Restaurant recipe has changed", details={"revision": latest_rev}
        )
    next_rev = latest_rev + 1

    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "insert into gba.restaurant_recipes "
                "(tenant_id, menu_item_id, revision, location_id, note, line_count, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    menu_item_id,
                    next_rev,
                    item_location,
                    body.note,
                    len(body.lines),
                    user_id,
                ),
            )
            for idx, line in enumerate(body.lines, start=1):
                await conn.execute(
                    "insert into gba.restaurant_recipe_lines "
                    "(tenant_id, menu_item_id, revision, line_no, location_id, "
                    "stock_item_id, quantity, note) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        menu_item_id,
                        next_rev,
                        idx,
                        item_location,
                        line.stock_item_id,
                        line.quantity,
                        line.note,
                    ),
                )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Referenced inventory material not found", field="lines"
            ) from exc
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.recipe_created",
        "restaurant_recipe",
        f"{menu_item_id}:{next_rev}",
        {"location_id": str(item_location), "revision": next_rev, "lines": len(body.lines)},
    )
    await commands.complete(
        conn, scope, _RecipeReceipt(menu_item_id=menu_item_id, revision=next_rev)
    )
    return await get_recipe(conn, business, menu_item_id, next_rev)
