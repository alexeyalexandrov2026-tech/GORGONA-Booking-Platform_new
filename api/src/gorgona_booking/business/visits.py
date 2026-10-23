"""L3: recipes, visit completion and material consumption (package L, BEAUTY-01).

Design docs/plan/PACKAGE_L3_DESIGN_2026-10-22.md. A recipe lists what one variant or add-on uses;
completing a started confirmed visit records the planned and the actual quantities (the booking
stays CONFIRMED); posting the consumption writes the actual quantities off once through STOCK-01.
"""

import hashlib
import json
from datetime import date, datetime
from typing import Any, Literal, Self
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import fee_policies, stock, visit_billing
from gorgona_booking.business.module_gate import INVENTORY_MODULE, require_module
from gorgona_booking.business.stock_contracts import (
    MAX_QUANTITY,
    DecimalText,
    WriteOffInput,
    WriteOffLine,
    from_count,
    to_count,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

type RecipeOwner = Literal["variant", "add_on"]
_OWNER = {
    "variant": ("gba.service_variants", "gba.variant_materials", "variant_id"),
    "add_on": ("gba.add_ons", "gba.add_on_materials", "add_on_id"),
}


class RecipeRevisionConflictError(ConflictError):
    code = "SERVICE_REVISION_CONFLICT"


class MaterialQuantityError(DomainError):
    code = "MATERIAL_QUANTITY_INVALID"


class VisitNotCompletableError(ConflictError):
    code = "VISIT_NOT_COMPLETABLE"


class VisitAlreadyCompletedError(ConflictError):
    code = "VISIT_ALREADY_COMPLETED"


class VisitPlaceOtherBranchError(DomainError):
    code = "VISIT_PLACE_OTHER_BRANCH"


class VisitNotCompletedError(ConflictError):
    code = "VISIT_NOT_COMPLETED"


class VisitNoShowError(ConflictError):
    """L9 decision 78: a no-show visit is never completed."""

    code = "VISIT_NO_SHOW"


class VisitNotStartedError(ConflictError):
    code = "VISIT_NOT_STARTED"


class VisitNoShowNotFoundError(NotFoundError):
    code = "VISIT_NO_SHOW_NOT_FOUND"


class NoShowView(BaseModel):
    booking_id: UUID
    recorded_at: datetime
    # The fee policy version in force when the visit was booked, and its no-show fee.
    policy_version: int | None
    fee: str | None


class VisitCompletionNotFoundError(NotFoundError):
    """L7b1: reading the completion of a visit that is not completed."""

    code = "VISIT_NOT_COMPLETED"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MaterialLine(_Strict):
    item_id: UUID
    quantity: DecimalText


def _unique(lines: list[MaterialLine]) -> None:
    if len({line.item_id for line in lines}) != len(lines):
        raise ValueError("A material is listed twice")


class RecipeReplace(_Strict):
    expected_revision: int = Field(ge=1)
    lines: list[MaterialLine] = Field(max_length=20)

    @model_validator(mode="after")
    def materials_once(self) -> Self:
        _unique(self.lines)
        return self


class RecipeView(BaseModel):
    owner_id: UUID
    owner_revision: int
    lines: list[MaterialLine]


class CompletionInput(_Strict):
    # Actual quantities; a material left out is used as planned.
    quantities: list[MaterialLine] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def materials_once(self) -> Self:
        _unique(self.quantities)
        return self


class ConsumptionInput(_Strict):
    legal_entity_id: UUID
    place_id: UUID
    document_date: date


class MaterialUseView(BaseModel):
    item_id: UUID
    planned: str
    actual: str


class CompletionView(BaseModel):
    booking_id: UUID
    location_id: UUID
    completed_at: datetime
    completed_by: UUID
    materials: list[MaterialUseView]
    stock_document_id: UUID | None
    consumption_posted_at: datetime | None


async def _scales(conn: RuntimeConnection, items: list[UUID]) -> dict[UUID, int]:
    rows = await (
        await conn.execute(
            "select id, quantity_scale from gba.stock_items where id = any(%s::uuid[])", (items,)
        )
    ).fetchall()
    return {UUID(str(row[0])): int(row[1]) for row in rows}


def _count(line: MaterialLine, scales: dict[UUID, int], *, zero: bool) -> int:
    scale = scales.get(line.item_id)
    if scale is None:
        raise InvalidReferenceError("Unknown material", item_id=str(line.item_id))
    try:
        return to_count(line.quantity, scale, MAX_QUANTITY, zero=zero)
    except ValueError as exc:
        raise MaterialQuantityError(
            str(exc), item_id=str(line.item_id), quantity_scale=scale
        ) from exc


async def replace_recipe(
    conn: RuntimeConnection, owner: RecipeOwner, owner_id: UUID, body: RecipeReplace
) -> RecipeView:
    """Replace the whole recipe of a variant or an add-on; its revision moves (decision 16)."""
    owner_table, table, column = _OWNER[owner]
    current = await (
        await conn.execute(
            f"select tenant_id, revision from {owner_table} where id = %s for update",  # noqa: S608
            (owner_id,),
        )
    ).fetchone()
    if current is None:
        raise NotFoundError("Service not found", owner_id=str(owner_id))
    if current[1] != body.expected_revision:
        raise RecipeRevisionConflictError(
            "The service changed since it was read; reload it", revision=current[1]
        )
    scales = await _scales(conn, [line.item_id for line in body.lines])
    counts = [_count(line, scales, zero=False) for line in body.lines]
    await conn.execute(f"delete from {table} where {column} = %s", (owner_id,))  # noqa: S608
    for position, (line, count) in enumerate(zip(body.lines, counts, strict=True), start=1):
        await conn.execute(
            f"insert into {table} (tenant_id, {column}, position, item_id, quantity) "  # noqa: S608
            "values (%s, %s, %s, %s, %s)",
            (current[0], owner_id, position, line.item_id, count),
        )
    moved = await (
        await conn.execute(
            f"update {owner_table} set updated_at = clock_timestamp() where id = %s "  # noqa: S608
            "returning revision",
            (owner_id,),
        )
    ).fetchone()
    assert moved is not None  # noqa: S101 - the row is locked above
    return await load_recipe(conn, owner, owner_id, int(moved[0]))


async def read_recipe(conn: RuntimeConnection, owner: RecipeOwner, owner_id: UUID) -> RecipeView:
    """L7a: the current recipe of a variant or an add-on with that owner's revision."""
    owner_table, _, _ = _OWNER[owner]
    current = await (
        await conn.execute(
            f"select revision from {owner_table} where id = %s",  # noqa: S608 - fixed table
            (owner_id,),
        )
    ).fetchone()
    if current is None:
        raise NotFoundError("Service not found", owner_id=str(owner_id))
    return await load_recipe(conn, owner, owner_id, int(current[0]))


async def load_recipe(
    conn: RuntimeConnection, owner: RecipeOwner, owner_id: UUID, revision: int
) -> RecipeView:
    _, table, column = _OWNER[owner]
    rows = await (
        await conn.execute(
            f"select m.item_id, m.quantity, s.quantity_scale from {table} m "  # noqa: S608
            "join gba.stock_items s on s.tenant_id = m.tenant_id and s.id = m.item_id "
            f"where m.{column} = %s order by m.position",
            (owner_id,),
        )
    ).fetchall()
    return RecipeView(
        owner_id=owner_id,
        owner_revision=revision,
        lines=[MaterialLine(item_id=r[0], quantity=from_count(int(r[1]), int(r[2]))) for r in rows],
    )


async def load_completion(conn: RuntimeConnection, booking_id: UUID) -> CompletionView | None:
    head = await (
        await conn.execute(
            "select booking_id, location_id, completed_at, completed_by, stock_document_id, "
            "consumption_posted_at from gba.visit_completions where booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    if head is None:
        return None
    uses = await (
        await conn.execute(
            "select u.item_id, u.planned, u.actual, s.quantity_scale "
            "from gba.visit_material_uses u join gba.stock_items s "
            "on s.tenant_id = u.tenant_id and s.id = u.item_id "
            "where u.booking_id = %s order by u.item_id",
            (booking_id,),
        )
    ).fetchall()
    return CompletionView(
        booking_id=head[0],
        location_id=head[1],
        completed_at=head[2],
        completed_by=head[3],
        materials=[
            MaterialUseView(
                item_id=r[0],
                planned=from_count(int(r[1]), int(r[3])),
                actual=from_count(int(r[2]), int(r[3])),
            )
            for r in uses
        ],
        stock_document_id=head[4],
        consumption_posted_at=head[5],
    )


async def _planned(conn: RuntimeConnection, quote: dict[str, Any]) -> dict[UUID, int]:
    """The recipes of every quoted variant and add-on, summed per material (decision 18)."""
    lines = quote.get("lines") or []
    variants = [UUID(line["id"]) for line in lines if line.get("kind") == "variant"]
    add_ons = [UUID(line["id"]) for line in lines if line.get("kind") == "add_on"]
    rows = await (
        await conn.execute(
            "select item_id, sum(quantity) from ("
            "select item_id, quantity from gba.variant_materials where variant_id = any(%s) "
            "union all select item_id, quantity from gba.add_on_materials "
            "where add_on_id = any(%s)) recipes group by item_id",
            (variants, add_ons),
        )
    ).fetchall()
    return {UUID(str(r[0])): int(r[1]) for r in rows}


async def complete_visit(
    conn: RuntimeConnection,
    tenant_id: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CompletionInput,
) -> CompletionView:
    """Record a completion of a started confirmed visit, once (decisions 17-18)."""
    scope = IdempotencyScope(tenant_id, actor, "visit.complete", key)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"booking_id": str(booking_id), "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return CompletionView.model_validate(stored.body)
    booking = await (
        await conn.execute(
            "select status, starts_at <= now(), location_id, quote from gba.bookings "
            "where id = %s for update",
            (booking_id,),
        )
    ).fetchone()
    if booking is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    if await load_completion(conn, booking_id) is not None:
        raise VisitAlreadyCompletedError("This visit is already completed")
    if await load_no_show(conn, booking_id) is not None:
        raise VisitNoShowError("This visit is recorded as a no-show")
    if booking[0] != "CONFIRMED" or not booking[1]:
        raise VisitNotCompletableError(
            "Only a confirmed visit that has started can be completed", status=booking[0]
        )
    planned = await _planned(conn, booking[3])
    scales = await _scales(conn, [*planned, *(line.item_id for line in body.quantities)])
    actual = dict(planned) | {
        line.item_id: _count(line, scales, zero=True) for line in body.quantities
    }
    await conn.execute(
        "insert into gba.visit_completions (tenant_id, booking_id, location_id, completed_by) "
        "values (%s, %s, %s, %s)",
        (tenant_id, booking_id, booking[2], user_id),
    )
    for item_id in sorted(actual):
        await conn.execute(
            "insert into gba.visit_material_uses (tenant_id, booking_id, item_id, planned, "
            "actual) values (%s, %s, %s, %s, %s)",
            (tenant_id, booking_id, item_id, planned.get(item_id, 0), actual[item_id]),
        )
    view = await load_completion(conn, booking_id)
    assert view is not None  # noqa: S101 - inserted above
    await idempotency.complete(conn, scope, 200, view.model_dump(mode="json"))
    return view


async def post_consumption(
    conn: RuntimeConnection,
    tenant_id: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ConsumptionInput,
) -> CompletionView:
    """Write the actual quantities off once through STOCK-01 (decision 19)."""
    locked = await (
        await conn.execute(
            "select consumption_posted_at from gba.visit_completions where booking_id = %s "
            "for update",
            (booking_id,),
        )
    ).fetchone()
    if locked is None:
        raise VisitNotCompletedError("Complete the visit before posting its consumption")
    view = await load_completion(conn, booking_id)
    assert view is not None  # noqa: S101 - locked above
    if locked[0] is not None:
        return view  # posted once; a repeat answers the same document
    # L8 decision 64: posting needs the inventory module even when nothing is written off.
    await require_module(conn, tenant_id, INVENTORY_MODULE)
    # L8 decision 65: the materials leave a storage place of the visit's own branch.
    branches = await (
        await conn.execute(
            "select p.location_id, b.location_id from gba.bookings b "
            "left join gba.stock_places p on p.tenant_id = b.tenant_id and p.id = %s "
            "where b.id = %s",
            (body.place_id, booking_id),
        )
    ).fetchone()
    if branches is not None and branches[0] is not None and branches[0] != branches[1]:
        raise VisitPlaceOtherBranchError(
            "Write the visit's materials off from a place of its own branch",
            place_id=str(body.place_id),
        )
    used = await (
        await conn.execute(
            "select u.item_id, u.actual, s.quantity_scale from gba.visit_material_uses u "
            "join gba.stock_items s on s.tenant_id = u.tenant_id and s.id = u.item_id "
            "where u.booking_id = %s and u.actual > 0 order by u.item_id",
            (booking_id,),
        )
    ).fetchall()
    document: UUID | None = None
    if used:
        document = uuid7()
        await stock.post_document(
            conn,
            tenant_id,
            document,
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
                    WriteOffLine(item_id=r[0], quantity=from_count(int(r[1]), int(r[2])))
                    for r in used
                ),
            ),
        )
    await conn.execute(
        "update gba.visit_completions set stock_document_id = %s, consumption_posted_at = now() "
        "where booking_id = %s",
        (document, booking_id),
    )
    posted = await load_completion(conn, booking_id)
    assert posted is not None  # noqa: S101
    return posted


async def load_no_show(conn: RuntimeConnection, booking_id: UUID) -> NoShowView | None:
    row = await (
        await conn.execute(
            "select n.recorded_at, n.policy_version, b.quote from gba.visit_no_shows n "
            "join gba.bookings b on b.id = n.booking_id where n.booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    if row is None:
        return None
    _, units = await visit_billing.currency_units(conn, row[2])
    fee = await visit_billing.policy_fee(conn, booking_id, row[2], "no_show")
    return NoShowView(
        booking_id=booking_id,
        recorded_at=row[0],
        policy_version=row[1],
        fee=None if fee is None else visit_billing.money(fee, units),
    )


async def record_no_show(
    conn: RuntimeConnection,
    tenant_id: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
) -> NoShowView:
    """L9 decision 78: once, for a started confirmed visit that was not completed."""
    scope = IdempotencyScope(tenant_id, actor, "visit.no_show", key)
    fingerprint = hashlib.sha256(str(booking_id).encode()).hexdigest()
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return NoShowView.model_validate(stored.body)
    booking = await (
        await conn.execute(
            "select status, starts_at <= now(), location_id from gba.bookings "
            "where id = %s for update",
            (booking_id,),
        )
    ).fetchone()
    if booking is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    recorded = await load_no_show(conn, booking_id)
    if recorded is not None:
        return recorded  # once; a repeat answers the same fact
    if await load_completion(conn, booking_id) is not None:
        raise VisitAlreadyCompletedError("This visit is already completed")
    if booking[0] != "CONFIRMED":
        raise VisitNotCompletableError("Only a confirmed visit can be a no-show", status=booking[0])
    if not booking[1]:
        raise VisitNotStartedError("This visit has not started yet")
    policy = await fee_policies.policy_for_booking(conn, booking_id)
    await conn.execute(
        "insert into gba.visit_no_shows (tenant_id, booking_id, location_id, policy_version, "
        "recorded_by) values (%s, %s, %s, %s, %s)",
        (tenant_id, booking_id, booking[2], None if policy is None else policy.version, user_id),
    )
    view = await load_no_show(conn, booking_id)
    assert view is not None  # noqa: S101 - inserted above
    await idempotency.complete(conn, scope, 200, view.model_dump(mode="json"))
    return view
