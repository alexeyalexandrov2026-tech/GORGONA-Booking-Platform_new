"""O3a (package O, BUILD-01): the construction budget and commitments.

docs/plan/PACKAGE_O3A_DESIGN_2026-10-31.md. The budget is the contract's cost side per line and
phase (the original contract plus approved change orders), derived on read, never stored.
Commitments (subcontracts and supplier orders) are versioned and insert-only; committed is the
latest version of every open commitment. Overruns are shown, not blocked. O3b adds actual costs
beside committed (construction_costs.actual_by_line). The database rechecks the
sequences, the counterparty's role, the cancellation and the budget line each commitment line names.
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.construction import (
    MONEY_MAX,
    ConstructionRevisionConflictError,
    Strict,
    amount,
    has_contract,
    load_estimate,
    lock_project,
    request_fingerprint,
    require_construction,
)
from gorgona_booking.business.construction_contracts import ConstructionNoContractError
from gorgona_booking.business.construction_costs import actual_by_line
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError


class ConstructionCommitmentCancelledError(ConflictError):
    code = "CONSTRUCTION_COMMITMENT_CANCELLED"


Kind = Literal["subcontract", "purchase_order"]
State = Literal["open", "cancelled"]
BudgetKey = tuple[int | None, int]


class CommitmentLineInput(Strict):
    change_order: int | None = Field(default=None, ge=1, le=100_000)
    position: int = Field(ge=1, le=500)
    amount_minor: int = Field(ge=1, le=MONEY_MAX)


def _once(lines: Sequence[CommitmentLineInput]) -> None:
    keys = [(item.change_order, item.position) for item in lines]
    if len(set(keys)) != len(keys):
        raise ValueError("a commitment names each budget line once")


class CommitmentInput(Strict):
    schema_version: Literal[1]
    kind: Kind
    counterparty_id: UUID
    title: str = Field(min_length=1, max_length=200)
    reference: str | None = Field(default=None, min_length=1, max_length=64)
    note: str | None = Field(default=None, min_length=1, max_length=1000)
    lines: list[CommitmentLineInput] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _lines_once(self) -> Self:
        _once(self.lines)
        return self


class RevisionInput(Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=100_000)
    state: State
    title: str = Field(min_length=1, max_length=200)
    reference: str | None = Field(default=None, min_length=1, max_length=64)
    note: str | None = Field(default=None, min_length=1, max_length=1000)
    lines: list[CommitmentLineInput] = Field(max_length=200)

    @model_validator(mode="after")
    def _open_has_lines(self) -> Self:
        if (self.state == "open") != bool(self.lines):
            raise ValueError("an open commitment has lines; a cancelled one has none")
        _once(self.lines)
        return self


class CommitmentLineView(BaseModel):
    change_order: int | None
    position: int
    amount_minor: int


class CommitmentSummary(BaseModel):
    number: int
    revision: int
    kind: str
    counterparty_id: UUID
    state: str
    title: str
    reference: str | None
    note: str | None
    revised_at: datetime
    total_minor: int


class CommitmentView(CommitmentSummary):
    project_id: UUID
    currency: str
    lines: list[CommitmentLineView]


class CommitmentList(BaseModel):
    items: list[CommitmentSummary]


class BudgetLineView(BaseModel):
    change_order: int | None
    position: int
    phase: str
    kind: str
    description: str
    unit: str
    quantity: Decimal
    unit_cost_minor: int
    budget_minor: int
    committed_minor: int
    uncommitted_minor: int
    over_committed: bool
    actual_minor: int
    remaining_minor: int
    over_budget: bool


class PhaseView(BaseModel):
    phase: str
    budget_minor: int
    committed_minor: int
    uncommitted_minor: int
    over_committed: bool
    actual_minor: int
    remaining_minor: int
    over_budget: bool


class BudgetView(BaseModel):
    project_id: UUID
    currency: str
    budget_minor: int
    committed_minor: int
    uncommitted_minor: int
    actual_minor: int
    remaining_minor: int
    lines: list[BudgetLineView]
    phases: list[PhaseView]


_SUMMARY = set(CommitmentSummary.model_fields)


async def _project_currency(conn: RuntimeConnection, project_id: UUID) -> str:
    row = await (
        await conn.execute(
            "select currency from gba.construction_projects where id = %s", (project_id,)
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Project not found", project_id=str(project_id))
    return str(row[0])


async def budget_lines(conn: RuntimeConnection, project_id: UUID) -> list[dict[str, Any]]:
    """The contract lines after approved removals, then the added lines of approved changes (1).

    Each line also carries its unit price and contract value as O2 sums the contract: the original
    line amount less the amounts of its approved removals, each rounded half up (O4a decision 9).
    """
    contract = await (
        await conn.execute(
            "select version from gba.construction_contracts where project_id = %s", (project_id,)
        )
    ).fetchone()
    if contract is None:
        raise ConstructionNoContractError("The project has no contract, so no budget yet")
    original = await load_estimate(conn, project_id, int(contract[0]))
    assert original is not None  # noqa: S101 - the contract names an existing version
    lines: dict[BudgetKey, dict[str, Any]] = {
        (None, item.position): {
            "change_order": None,
            "position": item.position,
            "phase": item.phase,
            "kind": item.kind,
            "description": item.description,
            "unit": item.unit,
            "quantity": item.quantity,
            "unit_cost_minor": item.unit_cost_minor,
            "budget_minor": item.cost_minor,
            "unit_price_minor": item.unit_price_minor,
            "contract_minor": item.price_minor,
        }
        for item in original.lines
    }
    approved = await (
        await conn.execute(
            "select o.number, o.position, o.action, o.contract_position, o.kind, o.description, "
            "o.phase, o.quantity, o.unit, o.unit_cost_minor, o.unit_price_minor "
            "from gba.construction_change_order_lines o "
            "join gba.construction_change_order_decisions d on d.tenant_id = o.tenant_id "
            "and d.project_id = o.project_id and d.number = o.number "
            "where o.project_id = %s and d.decision = 'approved' order by o.number, o.position",
            (project_id,),
        )
    ).fetchall()
    for row in approved:
        if row[2] == "remove":
            base = lines[(None, row[3])]
            base["quantity"] -= row[7]
            base["budget_minor"] -= amount(row[7], base["unit_cost_minor"])
            base["contract_minor"] -= amount(row[7], base["unit_price_minor"])
            continue
        lines[(row[0], row[1])] = {
            "change_order": row[0],
            "position": row[1],
            "phase": row[6],
            "kind": row[4],
            "description": row[5],
            "unit": row[8],
            "quantity": row[7],
            "unit_cost_minor": row[9],
            "budget_minor": amount(row[7], row[9]),
            "unit_price_minor": row[10],
            "contract_minor": amount(row[7], row[10]),
        }
    return list(lines.values())


async def _committed(conn: RuntimeConnection, project_id: UUID) -> dict[BudgetKey, int]:
    """The lines of the latest version of every open commitment, per budget line (5)."""
    rows = await (
        await conn.execute(
            "select l.change_order, l.budget_position, sum(l.amount_minor) "
            "from gba.construction_commitment_lines l "
            "join gba.construction_commitment_versions v on v.tenant_id = l.tenant_id "
            "and v.project_id = l.project_id and v.number = l.number and v.revision = l.revision "
            "where l.project_id = %s and v.state = 'open' and v.revision = ("
            "select max(x.revision) from gba.construction_commitment_versions x "
            "where x.tenant_id = v.tenant_id and x.project_id = v.project_id "
            "and x.number = v.number) group by l.change_order, l.budget_position",
            (project_id,),
        )
    ).fetchall()
    return {(row[0], int(row[1])): int(row[2]) for row in rows}


async def load_budget(conn: RuntimeConnection, project_id: UUID) -> BudgetView:
    currency = await _project_currency(conn, project_id)
    committed = await _committed(conn, project_id)
    spent = await actual_by_line(conn, project_id)
    lines: list[BudgetLineView] = []
    phases: dict[str, list[int]] = {}
    for item in await budget_lines(conn, project_id):
        key = (item["change_order"], item["position"])
        done, used = committed.get(key, 0), spent.get(key, 0)
        budget = int(item["budget_minor"])
        lines.append(
            BudgetLineView(
                **item,
                committed_minor=done,
                uncommitted_minor=budget - done,
                over_committed=done > budget,
                actual_minor=used,
                remaining_minor=budget - used,
                over_budget=used > budget,
            )
        )
        sums = phases.setdefault(item["phase"], [0, 0, 0])
        sums[0] += budget
        sums[1] += done
        sums[2] += used
    budget_total = sum(item.budget_minor for item in lines)
    committed_total = sum(item.committed_minor for item in lines)
    actual_total = sum(item.actual_minor for item in lines)
    return BudgetView(
        project_id=project_id,
        currency=currency,
        budget_minor=budget_total,
        committed_minor=committed_total,
        uncommitted_minor=budget_total - committed_total,
        actual_minor=actual_total,
        remaining_minor=budget_total - actual_total,
        lines=lines,
        phases=[
            PhaseView(
                phase=phase,
                budget_minor=sums[0],
                committed_minor=sums[1],
                uncommitted_minor=sums[0] - sums[1],
                over_committed=sums[1] > sums[0],
                actual_minor=sums[2],
                remaining_minor=sums[0] - sums[2],
                over_budget=sums[2] > sums[0],
            )
            for phase, sums in phases.items()
        ],
    )


async def load_commitment(
    conn: RuntimeConnection, project_id: UUID, number: int
) -> CommitmentView | None:
    head = await (
        await conn.execute(
            "select c.kind, c.counterparty_id, v.revision, v.state, v.title, v.reference, v.note, "
            "v.created_at, p.currency from gba.construction_commitments c "
            "join gba.construction_projects p on p.tenant_id = c.tenant_id and p.id = c.project_id "
            "join gba.construction_commitment_versions v on v.tenant_id = c.tenant_id "
            "and v.project_id = c.project_id and v.number = c.number "
            "where c.project_id = %s and c.number = %s order by v.revision desc limit 1",
            (project_id, number),
        )
    ).fetchone()
    if head is None:
        return None
    rows = await (
        await conn.execute(
            "select change_order, budget_position, amount_minor "
            "from gba.construction_commitment_lines "
            "where project_id = %s and number = %s and revision = %s order by line_no",
            (project_id, number, head[2]),
        )
    ).fetchall()
    lines = [
        CommitmentLineView(change_order=row[0], position=row[1], amount_minor=row[2])
        for row in rows
    ]
    return CommitmentView(
        project_id=project_id,
        number=number,
        revision=head[2],
        kind=head[0],
        counterparty_id=head[1],
        state=head[3],
        title=head[4],
        reference=head[5],
        note=head[6],
        revised_at=head[7],
        currency=head[8],
        total_minor=sum(item.amount_minor for item in lines),
        lines=lines,
    )


async def list_commitments(conn: RuntimeConnection, project_id: UUID) -> CommitmentList:
    await _project_currency(conn, project_id)
    rows = await (
        await conn.execute(
            "select number from gba.construction_commitments where project_id = %s order by number",
            (project_id,),
        )
    ).fetchall()
    items: list[CommitmentSummary] = []
    for row in rows:
        view = await load_commitment(conn, project_id, row[0])
        if view is not None:
            items.append(CommitmentSummary.model_validate(view.model_dump(include=_SUMMARY)))
    return CommitmentList(items=items)


async def _stored(
    conn: RuntimeConnection, project_id: UUID, body: dict[str, object]
) -> CommitmentView:
    number = body.get("number")
    view = await load_commitment(conn, project_id, number) if isinstance(number, int) else None
    if view is None:
        raise NotFoundError("Commitment not found", project_id=str(project_id))
    return view


async def _write_version(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    number: int,
    revision: int,
    user_id: UUID,
    body: CommitmentInput | RevisionInput,
    state: str,
) -> None:
    await conn.execute(
        "insert into gba.construction_commitment_versions (tenant_id, project_id, number, "
        "revision, state, title, reference, note, created_by) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            business,
            project_id,
            number,
            revision,
            state,
            body.title,
            body.reference,
            body.note,
            user_id,
        ),
    )
    for line_no, item in enumerate(body.lines, start=1):
        await conn.execute(
            "insert into gba.construction_commitment_lines (tenant_id, project_id, number, "
            "revision, line_no, change_order, budget_position, amount_minor) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                project_id,
                number,
                revision,
                line_no,
                item.change_order,
                item.position,
                item.amount_minor,
            ),
        )


def _refused(exc: CheckViolation) -> Exception | None:
    """The database's answer to a commitment it refused, as the error the client sees."""
    name = exc.diag.constraint_name
    if name == "construction_commitment_lines_budget_check":
        return InvalidReferenceError("A commitment line names a line of the budget", field="lines")
    if name == "construction_commitments_counterparty_check":
        return InvalidReferenceError(
            "A commitment names an active counterparty with the role of its kind",
            field="counterparty_id",
        )
    if name == "construction_commitment_versions_cancelled_check":
        return ConstructionCommitmentCancelledError("The commitment is cancelled")
    if name == "construction_commitment_versions_sequence_check":
        return ConstructionRevisionConflictError("The commitment changed since it was read")
    return None


async def create(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CommitmentInput,
) -> CommitmentView:
    """Add the next commitment with its first version (decisions 3-4)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.commitment", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("A commitment needs a contract")
    row = await (
        await conn.execute(
            "select coalesce(max(number), 0) + 1 from gba.construction_commitments "
            "where project_id = %s",
            (project_id,),
        )
    ).fetchone()
    number = int(row[0]) if row else 1
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_commitments (tenant_id, project_id, number, kind, "
                "counterparty_id, created_by) values (%s, %s, %s, %s, %s, %s)",
                (business, project_id, number, body.kind, body.counterparty_id, user_id),
            )
            await _write_version(conn, business, project_id, number, 1, user_id, body, "open")
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown counterparty", field="counterparty_id") from exc
    except CheckViolation as exc:
        mapped = _refused(exc)
        if mapped is None:
            raise
        raise mapped from exc
    view = await load_commitment(conn, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


async def revise(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    number: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RevisionInput,
) -> CommitmentView:
    """Write the next version of a commitment on the revision the client read (decision 4)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.commitment_revision", key)
    fingerprint = request_fingerprint(f"{project_id}:{number}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    current = await load_commitment(conn, project_id, number)
    if current is None:
        raise NotFoundError("Commitment not found", project_id=str(project_id), number=number)
    if current.state == "cancelled":
        raise ConstructionCommitmentCancelledError("The commitment is cancelled")
    if body.expected_revision != current.revision:
        raise ConstructionRevisionConflictError(
            "The commitment changed since it was read; reload it", revision=current.revision
        )
    revision = current.revision + 1
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await _write_version(
                conn, business, project_id, number, revision, user_id, body, body.state
            )
    except UniqueViolation as exc:
        raise ConstructionRevisionConflictError("The commitment changed since it was read") from exc
    except CheckViolation as exc:
        mapped = _refused(exc)
        if mapped is None:
            raise
        raise mapped from exc
    view = await load_commitment(conn, project_id, number)
    assert view is not None  # noqa: S101 - read above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view
