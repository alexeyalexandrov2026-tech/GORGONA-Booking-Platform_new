"""O2 (package O, BUILD-01): the construction contract and change orders.

docs/plan/PACKAGE_O2_DESIGN_2026-10-30.md. The contract is the accepted proposal, the frozen
original; change orders, their lines and their one decision are insert-only. The current contract
sum = original + approved changes, derived on read. The database rechecks the proposal, the
sequence of change orders, the contract lines a removal names and the quantity it takes.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.construction import (
    ConstructionContractExistsError,
    ConstructionEstimateStaleError,
    LineInput,
    LineView,
    Strict,
    amount,
    has_contract,
    latest_version,
    load_estimate,
    lock_project,
    request_fingerprint,
    require_construction,
)
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError


class ConstructionNotProposedError(ConflictError):
    code = "CONSTRUCTION_NOT_PROPOSED"


class ConstructionNoContractError(ConflictError):
    code = "CONSTRUCTION_NO_CONTRACT"


class ConstructionScopeExceededError(ConflictError):
    code = "CONSTRUCTION_SCOPE_EXCEEDED"


class ConstructionChangeOrderDecidedError(ConflictError):
    code = "CONSTRUCTION_CHANGE_ORDER_DECIDED"


Source = Literal["paper", "email"]
Decision = Literal["approved", "rejected", "withdrawn"]


class ContractInput(Strict):
    schema_version: Literal[1]
    version: int = Field(ge=1, le=100_000)
    signatory: str = Field(min_length=1, max_length=200)
    source: Source
    note: str | None = Field(default=None, min_length=1, max_length=1000)


class AddInput(LineInput):
    action: Literal["add"]


class RemoveInput(Strict):
    action: Literal["remove"]
    contract_position: int = Field(ge=1, le=500)
    quantity: Decimal = Field(gt=0, le=Decimal("999999999.9999"), max_digits=13, decimal_places=4)


ChangeLineInput = Annotated[AddInput | RemoveInput, Field(discriminator="action")]


class ChangeOrderInput(Strict):
    schema_version: Literal[1]
    title: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, min_length=1, max_length=1000)
    days_delta: int = Field(ge=-3650, le=3650)
    lines: list[ChangeLineInput] = Field(min_length=1, max_length=200)


class DecisionInput(Strict):
    schema_version: Literal[1]
    decision: Decision
    source: Source | None = None
    note: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _answer_has_a_source(self) -> Self:
        if (self.decision == "withdrawn") != (self.source is None):
            raise ValueError("the customer's answer has a source; a withdrawal has none")
        return self


class ChangeLineView(BaseModel):
    position: int
    action: str
    contract_position: int | None
    kind: str
    description: str
    phase: str
    quantity: Decimal
    unit: str
    unit_cost_minor: int
    unit_price_minor: int
    material_id: UUID | None
    cost_minor: int
    price_minor: int


class ChangeOrderSummary(BaseModel):
    number: int
    title: str
    reason: str | None
    days_delta: int
    state: str
    source: str | None
    decided_at: datetime | None
    cost_minor: int
    price_minor: int


class ChangeOrderView(ChangeOrderSummary):
    project_id: UUID
    currency: str
    lines: list[ChangeLineView]


class ChangeOrderList(BaseModel):
    items: list[ChangeOrderSummary]


class ContractView(BaseModel):
    project_id: UUID
    version: int
    signatory: str
    source: str
    note: str | None
    recorded_at: datetime
    currency: str
    original_cost_minor: int
    original_price_minor: int
    approved_cost_minor: int
    approved_price_minor: int
    approved_days: int
    current_cost_minor: int
    current_price_minor: int
    change_orders: list[ChangeOrderSummary]


_SUMMARY = set(ChangeOrderSummary.model_fields)


async def _contract_row(conn: RuntimeConnection, project_id: UUID) -> tuple[Any, ...] | None:
    return await (
        await conn.execute(
            "select version, signatory, source, note, recorded_at "
            "from gba.construction_contracts where project_id = %s",
            (project_id,),
        )
    ).fetchone()


async def _contract_lines(conn: RuntimeConnection, project_id: UUID) -> dict[int, LineView]:
    row = await _contract_row(conn, project_id)
    if row is None:
        return {}
    estimate = await load_estimate(conn, project_id, int(row[0]))
    return {} if estimate is None else {item.position: item for item in estimate.lines}


async def load_change_order(
    conn: RuntimeConnection, project_id: UUID, number: int
) -> ChangeOrderView | None:
    head = await (
        await conn.execute(
            "select o.title, o.reason, o.days_delta, d.decision, d.source, d.decided_at, "
            "p.currency from gba.construction_change_orders o "
            "join gba.construction_projects p on p.tenant_id = o.tenant_id and p.id = o.project_id "
            "left join gba.construction_change_order_decisions d on d.tenant_id = o.tenant_id "
            "and d.project_id = o.project_id and d.number = o.number "
            "where o.project_id = %s and o.number = %s",
            (project_id, number),
        )
    ).fetchone()
    if head is None:
        return None
    contract = await _contract_lines(conn, project_id)
    rows = await (
        await conn.execute(
            "select position, action, contract_position, kind, description, phase, quantity, "
            "unit, unit_cost_minor, unit_price_minor, material_id "
            "from gba.construction_change_order_lines where project_id = %s and number = %s "
            "order by position",
            (project_id, number),
        )
    ).fetchall()
    lines: list[ChangeLineView] = []
    for row in rows:
        if row[1] == "add":
            lines.append(
                ChangeLineView(
                    position=row[0],
                    action="add",
                    contract_position=None,
                    kind=row[3],
                    description=row[4],
                    phase=row[5],
                    quantity=row[6],
                    unit=row[7],
                    unit_cost_minor=row[8],
                    unit_price_minor=row[9],
                    material_id=row[10],
                    cost_minor=amount(row[6], row[8]),
                    price_minor=amount(row[6], row[9]),
                )
            )
            continue
        base = contract[row[2]]
        lines.append(
            ChangeLineView(
                position=row[0],
                action="remove",
                contract_position=row[2],
                kind=base.kind,
                description=base.description,
                phase=base.phase,
                quantity=row[6],
                unit=base.unit,
                unit_cost_minor=base.unit_cost_minor,
                unit_price_minor=base.unit_price_minor,
                material_id=base.material_id,
                cost_minor=-amount(row[6], base.unit_cost_minor),
                price_minor=-amount(row[6], base.unit_price_minor),
            )
        )
    return ChangeOrderView(
        project_id=project_id,
        number=number,
        title=head[0],
        reason=head[1],
        days_delta=head[2],
        state=head[3] or "proposed",
        source=head[4],
        decided_at=head[5],
        currency=head[6],
        cost_minor=sum(item.cost_minor for item in lines),
        price_minor=sum(item.price_minor for item in lines),
        lines=lines,
    )


async def _summaries(conn: RuntimeConnection, project_id: UUID) -> list[ChangeOrderSummary]:
    rows = await (
        await conn.execute(
            "select number from gba.construction_change_orders where project_id = %s "
            "order by number",
            (project_id,),
        )
    ).fetchall()
    items: list[ChangeOrderSummary] = []
    for row in rows:
        view = await load_change_order(conn, project_id, row[0])
        if view is not None:
            items.append(ChangeOrderSummary.model_validate(view.model_dump(include=_SUMMARY)))
    return items


async def list_change_orders(conn: RuntimeConnection, project_id: UUID) -> ChangeOrderList:
    found = await (
        await conn.execute("select 1 from gba.construction_projects where id = %s", (project_id,))
    ).fetchone()
    if found is None:
        raise NotFoundError("Project not found", project_id=str(project_id))
    return ChangeOrderList(items=await _summaries(conn, project_id))


async def load_contract(conn: RuntimeConnection, project_id: UUID) -> ContractView | None:
    row = await _contract_row(conn, project_id)
    if row is None:
        return None
    original = await load_estimate(conn, project_id, int(row[0]))
    assert original is not None  # noqa: S101 - the contract names an existing version
    orders = await _summaries(conn, project_id)
    approved = [item for item in orders if item.state == "approved"]
    cost = sum(item.cost_minor for item in approved)
    price = sum(item.price_minor for item in approved)
    return ContractView(
        project_id=project_id,
        version=row[0],
        signatory=row[1],
        source=row[2],
        note=row[3],
        recorded_at=row[4],
        currency=original.currency,
        original_cost_minor=original.cost_total_minor,
        original_price_minor=original.price_total_minor,
        approved_cost_minor=cost,
        approved_price_minor=price,
        approved_days=sum(item.days_delta for item in approved),
        current_cost_minor=original.cost_total_minor + cost,
        current_price_minor=original.price_total_minor + price,
        change_orders=orders,
    )


async def _stored_contract(conn: RuntimeConnection, project_id: UUID) -> ContractView:
    view = await load_contract(conn, project_id)
    if view is None:
        raise NotFoundError("Contract not found", project_id=str(project_id))
    return view


async def accept(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ContractInput,
) -> ContractView:
    """Record the customer's acceptance of the latest proposal: the original contract (1-2)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.contract", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored_contract(conn, project_id)
    await lock_project(conn, project_id)
    if await has_contract(conn, project_id):
        raise ConstructionContractExistsError("The project already has a contract")
    estimate = await load_estimate(conn, project_id, body.version)
    if estimate is None:
        raise NotFoundError("Estimate not found", project_id=str(project_id), version=body.version)
    latest = await latest_version(conn, project_id)
    if body.version != latest:
        raise ConstructionEstimateStaleError(
            "Only the latest estimate version becomes the contract", latest_version=latest
        )
    if estimate.proposed_at is None:
        raise ConstructionNotProposedError(
            "Only a proposed estimate version becomes the contract", version=body.version
        )
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_contracts (tenant_id, project_id, version, "
                "signatory, source, note, recorded_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    project_id,
                    body.version,
                    body.signatory,
                    body.source,
                    body.note,
                    user_id,
                ),
            )
    except UniqueViolation as exc:
        raise ConstructionContractExistsError("The project already has a contract") from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "construction_contracts_proposal_check":
            raise ConstructionEstimateStaleError(
                "Only the latest proposed estimate version becomes the contract"
            ) from exc
        raise
    view = await _stored_contract(conn, project_id)
    await idempotency.complete(conn, scope, 200, {"project_id": str(project_id)})
    return view


async def _next_number(conn: RuntimeConnection, project_id: UUID) -> int:
    row = await (
        await conn.execute(
            "select coalesce(max(number), 0) from gba.construction_change_orders "
            "where project_id = %s",
            (project_id,),
        )
    ).fetchone()
    return (int(row[0]) if row else 0) + 1


def _added(
    business: UUID, project_id: UUID, number: int, position: int, item: AddInput
) -> tuple[object, ...]:
    return (
        business,
        project_id,
        number,
        position,
        "add",
        None,
        item.kind,
        item.description,
        item.phase,
        item.quantity,
        item.unit,
        item.unit_cost_minor,
        item.unit_price_minor,
        item.material_id,
    )


async def _stored_change(
    conn: RuntimeConnection, project_id: UUID, body: dict[str, object]
) -> ChangeOrderView:
    number = body.get("number")
    view = await load_change_order(conn, project_id, number) if isinstance(number, int) else None
    if view is None:
        raise NotFoundError("Change order not found", project_id=str(project_id))
    return view


async def propose_change(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ChangeOrderInput,
) -> ChangeOrderView:
    """Add the next change order with its lines, proposed (decision 3)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.change_order", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored_change(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("A change order needs a contract")
    number = await _next_number(conn, project_id)
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_change_orders (tenant_id, project_id, number, "
                "title, reason, days_delta, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (business, project_id, number, body.title, body.reason, body.days_delta, user_id),
            )
            for position, item in enumerate(body.lines, start=1):
                if isinstance(item, RemoveInput):
                    await conn.execute(
                        "insert into gba.construction_change_order_lines (tenant_id, project_id, "
                        "number, position, action, contract_position, quantity) "
                        "values (%s, %s, %s, %s, %s, %s, %s)",
                        (
                            business,
                            project_id,
                            number,
                            position,
                            "remove",
                            item.contract_position,
                            item.quantity,
                        ),
                    )
                    continue
                await conn.execute(
                    "insert into gba.construction_change_order_lines (tenant_id, project_id, "
                    "number, position, action, contract_position, kind, description, phase, "
                    "quantity, unit, unit_cost_minor, unit_price_minor, material_id) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    _added(business, project_id, number, position, item),
                )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown material", field="material_id") from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "construction_change_order_lines_contract_check":
            raise InvalidReferenceError(
                "A removal names a line of the contract", field="contract_position"
            ) from exc
        if exc.diag.constraint_name == "construction_change_order_lines_scope_check":
            raise ConstructionScopeExceededError(
                "A removal takes more than the contract line holds"
            ) from exc
        raise
    view = await load_change_order(conn, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


async def decide(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    number: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: DecisionInput,
) -> ChangeOrderView:
    """Record the one decision of a proposed change order (decision 4)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.change_order_decision", key)
    fingerprint = request_fingerprint(f"{project_id}:{number}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored_change(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    current = await load_change_order(conn, project_id, number)
    if current is None:
        raise NotFoundError("Change order not found", project_id=str(project_id), number=number)
    if current.state != "proposed":
        raise ConstructionChangeOrderDecidedError(
            "The change order is already decided", state=current.state
        )
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_change_order_decisions (tenant_id, project_id, "
                "number, decision, source, note, decided_by) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (business, project_id, number, body.decision, body.source, body.note, user_id),
            )
    except UniqueViolation as exc:
        raise ConstructionChangeOrderDecidedError("The change order is already decided") from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "construction_change_order_decisions_scope_check":
            raise ConstructionScopeExceededError(
                "Approving it would remove more than the contract line holds"
            ) from exc
        raise
    view = await load_change_order(conn, project_id, number)
    assert view is not None  # noqa: S101 - read above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view
