"""O4a (package O, BUILD-01): completed quantities and progress.

docs/plan/PACKAGE_O4A_DESIGN_2026-11-01.md, decisions 6-9. A measurement records the quantity
completed to date on one budget line; the latest one of a line counts. It never exceeds the line's
contracted quantity, is not dated after today on the site nor before the line's latest measurement,
and a lower value than the latest is a correction with a note; the database rechecks all of it under
the project lock. Progress is derived: a finished line is worth its contract value, so a finished
project's completed value is the current contract sum.
"""

import unicodedata
from datetime import date, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from psycopg.errors import CheckViolation, UniqueViolation
from pydantic import AfterValidator, BaseModel, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.construction import (
    ConstructionRevisionConflictError,
    Strict,
    amount,
    has_contract,
    lock_project,
    request_fingerprint,
    require_construction,
)
from gorgona_booking.business.construction_budget import BudgetKey, budget_lines
from gorgona_booking.business.construction_contracts import ConstructionNoContractError
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

FIRST_DAY = date(2000, 1, 1)
LAST_DAY = date(2100, 12, 31)
_HUNDRED = Decimal(100)
_CENT = Decimal("0.01")


def _in_range(day: date) -> date:
    if not FIRST_DAY <= day <= LAST_DAY:
        raise ValueError("a date from 2000-01-01 to 2100-12-31")
    return day


def not_blank(value: str) -> str:
    """Text that is not only blanks, as the database's checks require."""
    if not value.strip():
        raise ValueError("text that is not only blanks")
    return value


def one_line(value: str) -> str:
    """A short name: not only blanks and without control characters ([[:cntrl:]] checks)."""
    if not value.strip() or any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError("text without control characters")
    return value


SiteDate = Annotated[date, AfterValidator(_in_range)]
Note = Annotated[str, Field(min_length=1, max_length=500), AfterValidator(not_blank)]


class ConstructionAboveContractError(ConflictError):
    code = "CONSTRUCTION_ABOVE_CONTRACT"


class ConstructionFutureDateError(DomainError):
    code = "CONSTRUCTION_FUTURE_DATE"


class ConstructionMeasurementOrderError(DomainError):
    code = "CONSTRUCTION_MEASUREMENT_ORDER"


class ConstructionCorrectionNoteError(DomainError):
    code = "CONSTRUCTION_CORRECTION_NOTE"


class MeasurementInput(Strict):
    schema_version: Literal[1]
    change_order: int | None = Field(default=None, ge=1, le=100_000)
    position: int = Field(ge=1, le=500)
    measured_on: SiteDate
    quantity_to_date: Decimal = Field(ge=0, max_digits=13, decimal_places=4)
    note: Note | None = None


class MeasurementView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    number: int
    change_order: int | None
    position: int
    measured_on: date
    quantity_to_date: Decimal
    note: str | None
    recorded_at: datetime


class MeasurementList(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    items: list[MeasurementView]


class ProgressLineView(BaseModel):
    change_order: int | None
    position: int
    phase: str
    kind: str
    description: str
    unit: str
    quantity: Decimal
    completed: Decimal
    percent: Decimal
    unit_price_minor: int
    contract_minor: int
    completed_minor: int


class ProgressPhaseView(BaseModel):
    phase: str
    contract_minor: int
    completed_minor: int
    percent: Decimal


class ProgressView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    currency: str
    contract_minor: int
    completed_minor: int
    percent: Decimal
    lines: list[ProgressLineView]
    phases: list[ProgressPhaseView]


def percent(part: Decimal | int, whole: Decimal | int) -> Decimal:
    """Part of whole in percent, rounded down to 0.01 so that 100 means all of it (decision 9)."""
    if whole <= 0:
        return Decimal("0.00")
    return (Decimal(part) * _HUNDRED / Decimal(whole)).quantize(_CENT, rounding=ROUND_DOWN)


def completed_value(completed: Decimal, line: dict[str, Any]) -> int:
    """A finished line is worth its contract value; otherwise completed x price, never above it."""
    contract = int(line["contract_minor"])
    if completed >= line["quantity"]:
        return contract
    return min(amount(completed, int(line["unit_price_minor"])), contract)


async def project_currency(conn: RuntimeConnection, project_id: UUID) -> str:
    """The project's currency; a project the caller may not see is not found."""
    row = await (
        await conn.execute(
            "select currency from gba.construction_projects where id = %s", (project_id,)
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Project not found", project_id=str(project_id))
    return str(row[0])


async def site_today(conn: RuntimeConnection, project_id: UUID) -> date:
    """Today in the project's site time zone, as the database computes it."""
    row = await (
        await conn.execute(
            "select (now() at time zone time_zone)::date from gba.construction_projects "
            "where id = %s",
            (project_id,),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Project not found", project_id=str(project_id))
    day: date = row[0]
    return day


async def completed_by_line(conn: RuntimeConnection, project_id: UUID) -> dict[BudgetKey, Decimal]:
    """The latest measurement of every measured budget line (decision 6)."""
    rows = await (
        await conn.execute(
            "select distinct on (change_order, budget_position) change_order, budget_position, "
            "quantity_to_date from gba.construction_progress_measurements where project_id = %s "
            "order by change_order, budget_position, number desc",
            (project_id,),
        )
    ).fetchall()
    return {(row[0], int(row[1])): Decimal(row[2]) for row in rows}


async def load_progress(conn: RuntimeConnection, project_id: UUID) -> ProgressView:
    """Completed per budget line, phase and in total, with values (decision 9)."""
    currency = await project_currency(conn, project_id)
    done = await completed_by_line(conn, project_id)
    lines: list[ProgressLineView] = []
    phases: dict[str, list[int]] = {}
    for item in await budget_lines(conn, project_id):
        completed = done.get((item["change_order"], item["position"]), Decimal(0))
        value = completed_value(completed, item)
        lines.append(
            ProgressLineView(
                change_order=item["change_order"],
                position=item["position"],
                phase=item["phase"],
                kind=item["kind"],
                description=item["description"],
                unit=item["unit"],
                quantity=item["quantity"],
                completed=completed,
                percent=percent(completed, item["quantity"]),
                unit_price_minor=item["unit_price_minor"],
                contract_minor=item["contract_minor"],
                completed_minor=value,
            )
        )
        sums = phases.setdefault(item["phase"], [0, 0])
        sums[0] += int(item["contract_minor"])
        sums[1] += value
    contract_total = sum(item.contract_minor for item in lines)
    completed_total = sum(item.completed_minor for item in lines)
    return ProgressView(
        project_id=project_id,
        currency=currency,
        contract_minor=contract_total,
        completed_minor=completed_total,
        percent=percent(completed_total, contract_total),
        lines=lines,
        phases=[
            ProgressPhaseView(
                phase=phase,
                contract_minor=sums[0],
                completed_minor=sums[1],
                percent=percent(sums[1], sums[0]),
            )
            for phase, sums in phases.items()
        ],
    )


_COLUMNS = (
    "number, change_order, budget_position, measured_on, quantity_to_date, note, created_at "
    "from gba.construction_progress_measurements "
)


def _view(project_id: UUID, row: tuple[object, ...]) -> MeasurementView:
    return MeasurementView.model_validate(
        {
            "project_id": project_id,
            "number": row[0],
            "change_order": row[1],
            "position": row[2],
            "measured_on": row[3],
            "quantity_to_date": row[4],
            "note": row[5],
            "recorded_at": row[6],
        }
    )


async def load_measurement(
    conn: RuntimeConnection, project_id: UUID, number: int
) -> MeasurementView | None:
    row = await (
        await conn.execute(
            f"select {_COLUMNS}where project_id = %s and number = %s", (project_id, number)
        )
    ).fetchone()
    return None if row is None else _view(project_id, row)


async def list_measurements(conn: RuntimeConnection, project_id: UUID) -> MeasurementList:
    await project_currency(conn, project_id)
    rows = await (
        await conn.execute(f"select {_COLUMNS}where project_id = %s order by number", (project_id,))
    ).fetchall()
    return MeasurementList(project_id=project_id, items=[_view(project_id, row) for row in rows])


async def _stored(
    conn: RuntimeConnection, project_id: UUID, body: dict[str, object]
) -> MeasurementView:
    number = body.get("number")
    view = await load_measurement(conn, project_id, number) if isinstance(number, int) else None
    if view is None:
        raise NotFoundError("Measurement not found", project_id=str(project_id))
    return view


def _refused(exc: CheckViolation) -> Exception | None:
    """The database's answer to a measurement it refused, as the error the client sees."""
    name = exc.diag.constraint_name
    if name == "construction_progress_measurements_sequence_check":
        return ConstructionRevisionConflictError("The project's measurements changed; try again")
    if name == "construction_progress_measurements_budget_check":
        return InvalidReferenceError("A measurement names a line of the budget", field="position")
    if name == "construction_progress_measurements_date_check":
        return ConstructionFutureDateError("The date is after today on the site")
    if name == "construction_progress_measurements_order_check":
        return ConstructionMeasurementOrderError("A measurement is not dated before the latest")
    if name == "construction_progress_measurements_contract_check":
        return ConstructionAboveContractError("Completed never exceeds the contracted quantity")
    if name == "construction_progress_measurements_note_check":
        return ConstructionCorrectionNoteError("A lower quantity is a correction with a note")
    return None


async def record(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MeasurementInput,
) -> MeasurementView:
    """Record the quantity completed to date on one budget line (decisions 6-7)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.measurement", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("A measurement needs a contract")
    lines = {(i["change_order"], i["position"]): i for i in await budget_lines(conn, project_id)}
    line = lines.get((body.change_order, body.position))
    if line is None:
        raise InvalidReferenceError("A measurement names a line of the budget", field="position")
    if body.measured_on > await site_today(conn, project_id):
        raise ConstructionFutureDateError("The date is after today on the site")
    latest = await (
        await conn.execute(
            "select measured_on, quantity_to_date from gba.construction_progress_measurements "
            "where project_id = %s and budget_position = %s "
            "and change_order is not distinct from %s::integer order by number desc limit 1",
            (project_id, body.position, body.change_order),
        )
    ).fetchone()
    if latest is not None and body.measured_on < latest[0]:
        raise ConstructionMeasurementOrderError(
            "A measurement is not dated before the line's latest one", latest=str(latest[0])
        )
    if body.quantity_to_date > line["quantity"]:
        raise ConstructionAboveContractError(
            "Completed never exceeds the contracted quantity; approve a change order first",
            contracted=str(line["quantity"]),
        )
    if latest is not None and body.quantity_to_date < latest[1] and body.note is None:
        raise ConstructionCorrectionNoteError(
            "A lower quantity than the latest is a correction with a note"
        )
    row = await (
        await conn.execute(
            "select coalesce(max(number), 0) + 1 from gba.construction_progress_measurements "
            "where project_id = %s",
            (project_id,),
        )
    ).fetchone()
    number = int(row[0]) if row else 1
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_progress_measurements (tenant_id, project_id, "
                "number, change_order, budget_position, measured_on, quantity_to_date, note, "
                "created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    project_id,
                    number,
                    body.change_order,
                    body.position,
                    body.measured_on,
                    body.quantity_to_date,
                    body.note,
                    user_id,
                ),
            )
    except UniqueViolation as exc:
        raise ConstructionRevisionConflictError(
            "The project's measurements changed; try again"
        ) from exc
    except CheckViolation as exc:
        mapped = _refused(exc)
        if mapped is None:
            raise
        raise mapped from exc
    view = await load_measurement(conn, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


async def check_contract(conn: RuntimeConnection, project_id: UUID) -> None:
    """A project the caller sees, with a contract (decision 1)."""
    await project_currency(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("The project has no contract yet")
