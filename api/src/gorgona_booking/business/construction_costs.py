"""O3b (package O, BUILD-01): actual costs as links of existing facts to budget lines.

docs/plan/PACKAGE_O3B_DESIGN_2026-10-31.md. A link names one STOCK-01 write-off line, one line of an
issued FIN-03 payable or one approved WORK-01 time entry with a rate per hour, and one budget line.
The database computes the fact's amount (gba.construction_cost_fact) and rechecks it, the branch,
the currency, the budget line and that a fact counts on one link at a time. A reversal is a new row.
"""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation, UniqueViolation
from pydantic import BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.construction import (
    ConstructionRevisionConflictError,
    Strict,
    has_contract,
    lock_project,
    request_fingerprint,
    require_construction,
)
from gorgona_booking.business.construction_contracts import ConstructionNoContractError
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

CostKind = Literal["stock_write_off", "payable", "time_entry"]
BudgetKey = tuple[int | None, int]
_FACT_FIELDS: dict[str, tuple[str, ...]] = {
    "stock_write_off": ("stock_document_id", "stock_line_no"),
    "payable": ("book_id", "document_id", "line_id"),
    "time_entry": ("time_entry_id", "rate_per_hour_minor"),
}


class ConstructionCostAlreadyLinkedError(ConflictError):
    code = "CONSTRUCTION_COST_ALREADY_LINKED"


class ConstructionCostReversedError(ConflictError):
    code = "CONSTRUCTION_COST_REVERSED"


class ConstructionCostCurrencyError(ConflictError):
    code = "CONSTRUCTION_COST_CURRENCY"


class CostLinkInput(Strict):
    schema_version: Literal[1]
    kind: CostKind
    change_order: int | None = Field(default=None, ge=1, le=100_000)
    position: int = Field(ge=1, le=500)
    note: str | None = Field(default=None, min_length=1, max_length=500)
    stock_document_id: UUID | None = None
    stock_line_no: int | None = Field(default=None, ge=1, le=100)
    book_id: UUID | None = None
    document_id: UUID | None = None
    line_id: UUID | None = None
    time_entry_id: UUID | None = None
    rate_per_hour_minor: int | None = Field(default=None, ge=1, le=1_000_000_000)

    @model_validator(mode="after")
    def _one_fact(self) -> Self:
        """The fields of the named kind are all given; those of the other kinds are not (1)."""
        for kind, names in _FACT_FIELDS.items():
            for name in names:
                if (getattr(self, name) is not None) != (kind == self.kind):
                    raise ValueError(f"a {self.kind} link takes exactly the fields of its fact")
        return self


class ReversalInput(Strict):
    schema_version: Literal[1]
    reason: str = Field(min_length=1, max_length=500)


class ReversalView(BaseModel):
    reason: str
    reversed_at: datetime


class CostLinkView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    number: int
    kind: str
    change_order: int | None
    position: int
    amount_minor: int
    currency: str
    note: str | None
    attempt: int
    stock_document_id: UUID | None
    stock_line_no: int | None
    book_id: UUID | None
    document_id: UUID | None
    document_revision: int | None
    line_id: UUID | None
    time_entry_id: UUID | None
    time_entry_revision: int | None
    worked_microseconds: int | None
    rate_per_hour_minor: int | None
    linked_at: datetime
    reversal: ReversalView | None


class CostLinkList(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    items: list[CostLinkView]


_COLUMNS = (
    "c.number, c.kind, c.change_order, c.budget_position, c.amount_minor, c.currency, c.note, "
    "c.attempt, c.stock_document_id, c.stock_line_no, c.book_id, c.document_id, "
    "c.document_revision, c.line_id, c.time_entry_id, c.time_entry_revision, "
    "c.worked_microseconds, c.rate_per_hour_minor, c.created_at, r.reason, r.created_at "
    "from gba.construction_cost_links c left join gba.construction_cost_reversals r "
    "on r.tenant_id = c.tenant_id and r.project_id = c.project_id and r.number = c.number "
)


def _view(project_id: UUID, row: tuple[object, ...]) -> CostLinkView:
    reversal = (
        None
        if row[19] is None
        else ReversalView.model_validate({"reason": row[19], "reversed_at": row[20]})
    )
    return CostLinkView.model_validate(
        {
            "project_id": project_id,
            "number": row[0],
            "kind": row[1],
            "change_order": row[2],
            "position": row[3],
            "amount_minor": row[4],
            "currency": row[5],
            "note": row[6],
            "attempt": row[7],
            "stock_document_id": row[8],
            "stock_line_no": row[9],
            "book_id": row[10],
            "document_id": row[11],
            "document_revision": row[12],
            "line_id": row[13],
            "time_entry_id": row[14],
            "time_entry_revision": row[15],
            "worked_microseconds": row[16],
            "rate_per_hour_minor": row[17],
            "linked_at": row[18],
            "reversal": reversal,
        }
    )


async def load_link(conn: RuntimeConnection, project_id: UUID, number: int) -> CostLinkView | None:
    row = await (
        await conn.execute(
            f"select {_COLUMNS}where c.project_id = %s and c.number = %s",
            (project_id, number),
        )
    ).fetchone()
    return None if row is None else _view(project_id, row)


async def list_links(conn: RuntimeConnection, project_id: UUID) -> CostLinkList:
    found = await (
        await conn.execute("select 1 from gba.construction_projects where id = %s", (project_id,))
    ).fetchone()
    if found is None:
        raise NotFoundError("Project not found", project_id=str(project_id))
    rows = await (
        await conn.execute(
            f"select {_COLUMNS}where c.project_id = %s order by c.number",
            (project_id,),
        )
    ).fetchall()
    return CostLinkList(project_id=project_id, items=[_view(project_id, row) for row in rows])


async def actual_by_line(conn: RuntimeConnection, project_id: UUID) -> dict[BudgetKey, int]:
    """The links not reversed, per budget line (decision 5)."""
    rows = await (
        await conn.execute(
            "select c.change_order, c.budget_position, sum(c.amount_minor) "
            "from gba.construction_cost_links c where c.project_id = %s and not exists ("
            "select 1 from gba.construction_cost_reversals r where r.tenant_id = c.tenant_id "
            "and r.project_id = c.project_id and r.number = c.number) "
            "group by c.change_order, c.budget_position",
            (project_id,),
        )
    ).fetchall()
    return {(row[0], int(row[1])): int(row[2]) for row in rows}


async def _stored(
    conn: RuntimeConnection, project_id: UUID, body: dict[str, object]
) -> CostLinkView:
    number = body.get("number")
    view = await load_link(conn, project_id, number) if isinstance(number, int) else None
    if view is None:
        raise NotFoundError("Cost link not found", project_id=str(project_id))
    return view


def _refused(exc: CheckViolation) -> Exception | None:
    """The database's answer to a link it refused, as the error the client sees."""
    name = exc.diag.constraint_name
    if name in ("construction_cost_links_fact_check", "construction_cost_links_amount_check"):
        return InvalidReferenceError("The link names no fact it may cost", field="kind")
    if name == "construction_cost_links_budget_check":
        return InvalidReferenceError("A cost link names a line of the budget", field="position")
    if name == "construction_cost_links_currency_check":
        return ConstructionCostCurrencyError("The fact is not in the project's currency")
    if name == "construction_cost_links_attempt_check":
        return ConstructionCostAlreadyLinkedError("The fact already counts on a cost link")
    if name == "construction_cost_links_sequence_check":
        return ConstructionRevisionConflictError("The project's costs changed; try again")
    return None


async def link(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CostLinkInput,
) -> CostLinkView:
    """Put one fact on one budget line (decisions 1-3)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.cost_link", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored(conn, project_id, stored.body)
    currency = await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("A cost link needs a contract")
    fact = await (
        await conn.execute(
            "select f.fact_key, f.amount_minor, f.currency, f.location_id, f.source_revision, "
            "f.worked_microseconds, p.location_id from gba.construction_cost_fact("
            "%s::uuid, %s::text, %s::uuid, %s::smallint, %s::uuid, %s::uuid, %s::uuid, "
            "%s::uuid, %s::bigint) f "
            "join gba.construction_projects p on p.id = %s",
            (
                business,
                body.kind,
                body.stock_document_id,
                body.stock_line_no,
                body.book_id,
                body.document_id,
                body.line_id,
                body.time_entry_id,
                body.rate_per_hour_minor,
                project_id,
            ),
        )
    ).fetchone()
    if fact is None or (fact[3] is not None and fact[3] != fact[6]) or int(fact[1]) < 1:
        raise InvalidReferenceError("The link names no fact it may cost", field="kind")
    if (fact[2] or currency) != currency:
        raise ConstructionCostCurrencyError("The fact is not in the project's currency")
    counts = await (
        await conn.execute(
            "select count(*), count(*) filter (where not exists ("
            "select 1 from gba.construction_cost_reversals r where r.tenant_id = c.tenant_id "
            "and r.project_id = c.project_id and r.number = c.number)) "
            "from gba.construction_cost_links c where c.fact_key = %s",
            (fact[0],),
        )
    ).fetchone()
    assert counts is not None  # noqa: S101 - an aggregate returns one row
    if int(counts[1]) > 0:
        raise ConstructionCostAlreadyLinkedError("The fact already counts on a cost link")
    row = await (
        await conn.execute(
            "select coalesce(max(number), 0) + 1 from gba.construction_cost_links "
            "where project_id = %s",
            (project_id,),
        )
    ).fetchone()
    number = int(row[0]) if row else 1
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_cost_links (tenant_id, project_id, number, kind, "
                "change_order, budget_position, stock_document_id, stock_line_no, book_id, "
                "document_id, document_revision, line_id, time_entry_id, time_entry_revision, "
                "worked_microseconds, rate_per_hour_minor, fact_key, attempt, amount_minor, "
                "currency, note, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    project_id,
                    number,
                    body.kind,
                    body.change_order,
                    body.position,
                    body.stock_document_id,
                    body.stock_line_no,
                    body.book_id,
                    body.document_id,
                    fact[4] if body.kind == "payable" else None,
                    body.line_id,
                    body.time_entry_id,
                    fact[4] if body.kind == "time_entry" else None,
                    fact[5],
                    body.rate_per_hour_minor,
                    fact[0],
                    int(counts[0]) + 1,
                    fact[1],
                    currency,
                    body.note,
                    user_id,
                ),
            )
    except UniqueViolation as exc:
        raise ConstructionCostAlreadyLinkedError("The fact already counts on a cost link") from exc
    except CheckViolation as exc:
        mapped = _refused(exc)
        if mapped is None:
            raise
        raise mapped from exc
    view = await load_link(conn, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


async def reverse(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    number: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ReversalInput,
) -> CostLinkView:
    """Take a link out of actual with a reason, once (decision 4)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.cost_reversal", key)
    fingerprint = request_fingerprint(f"{project_id}:{number}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    current = await load_link(conn, project_id, number)
    if current is None:
        raise NotFoundError("Cost link not found", project_id=str(project_id), number=number)
    if current.reversal is not None:
        raise ConstructionCostReversedError("The cost link is already reversed")
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_cost_reversals (tenant_id, project_id, number, "
                "reason, created_by) values (%s, %s, %s, %s, %s)",
                (business, project_id, number, body.reason, user_id),
            )
    except UniqueViolation as exc:
        raise ConstructionCostReversedError("The cost link is already reversed") from exc
    view = await load_link(conn, project_id, number)
    assert view is not None  # noqa: S101 - read above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view
