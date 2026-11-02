"""O6a (package O, BUILD-01): stage and final acceptance, retainage release.

docs/plan/PACKAGE_O6A_DESIGN_2026-11-02.md. An acceptance is the customer's recorded answer on one
phase or on the whole project, accepted once, only when its work is finished and no open or fixed
quality item blocks it; the final one needs the contract billed in full and records the warranty
period. Accepted work is closed (the database refuses measurements, approvals and billing touching
it). Retainage is released once per acceptance by an amount derived here and rechecked by the
database: a phase's held retainage once it is billed in full, or at the final acceptance the rest.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation, UniqueViolation
from pydantic import AfterValidator, BaseModel, Field, model_validator

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
from gorgona_booking.business.construction_billing import BASIS
from gorgona_booking.business.construction_budget import BudgetKey, budget_lines
from gorgona_booking.business.construction_contracts import (
    ConstructionAcceptedError,
    ConstructionNoContractError,
    Source,
)
from gorgona_booking.business.construction_progress import (
    ConstructionFutureDateError,
    SiteDate,
    check_contract,
    not_blank,
    one_line,
    project_currency,
    site_today,
)
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

Scope = Literal["phase", "final"]
Label = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(one_line)]
Signatory = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(one_line)]
Remark = Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(not_blank)]
BLOCKING = ("open", "fixed")


class ConstructionNotCompletedError(ConflictError):
    code = "CONSTRUCTION_NOT_COMPLETED"


class ConstructionOpenItemsError(ConflictError):
    code = "CONSTRUCTION_OPEN_ITEMS"


class ConstructionNotFullyBilledError(ConflictError):
    code = "CONSTRUCTION_NOT_FULLY_BILLED"


class ConstructionReleasedError(ConflictError):
    code = "CONSTRUCTION_RELEASED"


class ConstructionNothingToReleaseError(ConflictError):
    code = "CONSTRUCTION_NOTHING_TO_RELEASE"


class ConstructionBeforeAcceptanceError(DomainError):
    code = "CONSTRUCTION_BEFORE_ACCEPTANCE"


def ten_years_after(day: date) -> date:
    """The same day ten years on (28 February for 29 February), as PostgreSQL adds 10 years."""
    try:
        return day.replace(year=day.year + 10)
    except ValueError:
        return day.replace(year=day.year + 10, day=28)


class AcceptanceInput(Strict):
    schema_version: Literal[1]
    scope: Scope
    phase: Label | None = None
    accepted_on: SiteDate
    signatory: Signatory
    source: Source
    note: Remark | None = None
    warranty_ends_on: SiteDate | None = None

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if (self.scope == "phase") != (self.phase is not None):
            raise ValueError("a phase acceptance names its phase; the final one names none")
        if (self.scope == "final") != (self.warranty_ends_on is not None):
            raise ValueError("the final acceptance, and only it, sets the warranty end")
        if self.warranty_ends_on is not None and not (
            self.accepted_on < self.warranty_ends_on <= ten_years_after(self.accepted_on)
        ):
            raise ValueError("the warranty ends after the acceptance and within 10 years of it")
        return self


class ReleaseInput(Strict):
    schema_version: Literal[1]
    released_on: SiteDate
    note: Remark | None = None


class ReleaseView(BaseModel):
    released_on: date
    amount_minor: int
    note: str | None
    recorded_at: datetime


class AcceptanceView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    number: int
    scope: str
    phase: str | None
    accepted_on: date
    signatory: str
    source: str
    note: str | None
    warranty_starts_on: date | None
    warranty_ends_on: date | None
    recorded_at: datetime
    release: ReleaseView | None


class PhaseAcceptanceView(BaseModel):
    phase: str
    finished: bool
    open_items: int
    billed_in_full: bool
    retained_minor: int
    acceptance: int | None
    released_minor: int | None


class AcceptanceList(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    currency: str
    retained_minor: int
    released_minor: int
    held_minor: int
    phases: list[PhaseAcceptanceView]
    final: AcceptanceView | None
    items: list[AcceptanceView]


@dataclass(frozen=True)
class _State:
    """What an acceptance or a release depends on, read once under the project lock."""

    lines: list[dict[str, Any]]
    measured: dict[BudgetKey, tuple[date, Decimal]]
    items: list[tuple[str | None, str]]
    applications: list[tuple[int, int, int, int]]
    billed_lines: dict[int, dict[BudgetKey, tuple[Decimal, int]]]
    released: int

    def phases(self) -> list[str]:
        return list(dict.fromkeys(str(line["phase"]) for line in self.lines))

    def scoped(self, phase: str | None) -> list[dict[str, Any]]:
        return [line for line in self.lines if phase is None or line["phase"] == phase]

    def unfinished(self, phase: str | None, on: date | None = None) -> list[BudgetKey]:
        """Lines in scope that are not finished (by `on`, if given): decision 4."""
        late = []
        for line in self.scoped(phase):
            key: BudgetKey = (line["change_order"], line["position"])
            if line["quantity"] <= 0:
                continue
            latest = self.measured.get(key)
            if (
                latest is None
                or latest[1] < line["quantity"]
                or (on is not None and latest[0] > on)
            ):
                late.append(key)
        return late

    def blocking(self, phase: str | None) -> int:
        """Open or fixed items of the phase, or of the whole project for `None`: decision 5."""
        return sum(
            1
            for where, state in self.items
            if state in BLOCKING and (phase is None or where == phase)
        )

    def billed(self) -> int:
        return self.applications[-1][3] if self.applications else 0

    def retained(self) -> int:
        return sum(application[2] for application in self.applications)

    def billed_in_full(self, phase: str) -> bool:
        latest = self.billed_lines.get(self.applications[-1][0], {}) if self.applications else {}
        return all(
            latest.get((line["change_order"], line["position"]), (Decimal(0), 0))[0]
            >= line["quantity"]
            for line in self.scoped(phase)
        )

    def phase_retained(self, phase: str) -> int:
        """`construction_phase_retained`: each application's change of the phase's billed value
        times its rate, rounded down, summed (decision 8)."""
        keys = {(line["change_order"], line["position"]) for line in self.scoped(phase)}
        held = previous = 0
        for number, rate, _, _ in self.applications:
            value = sum(
                v for key, (_, v) in self.billed_lines.get(number, {}).items() if key in keys
            )
            held += (value - previous) * rate // BASIS
            previous = value
        return held


async def _state(conn: RuntimeConnection, project_id: UUID) -> _State:
    measured = await (
        await conn.execute(
            "select distinct on (change_order, budget_position) change_order, budget_position, "
            "measured_on, quantity_to_date from gba.construction_progress_measurements "
            "where project_id = %s order by change_order, budget_position, number desc",
            (project_id,),
        )
    ).fetchall()
    items = await (
        await conn.execute(
            "select i.phase, coalesce((select e.state from gba.construction_quality_item_events e "
            "where e.project_id = i.project_id and e.item = i.number "
            "order by e.sequence desc limit 1), 'open') "
            "from gba.construction_quality_items i where i.project_id = %s",
            (project_id,),
        )
    ).fetchall()
    applications = await (
        await conn.execute(
            "select number, rate_bp, retained_minor, billed_to_date_minor "
            "from gba.construction_pay_applications where project_id = %s order by number",
            (project_id,),
        )
    ).fetchall()
    rows = await (
        await conn.execute(
            "select number, change_order, budget_position, quantity_to_date, value_to_date_minor "
            "from gba.construction_pay_application_lines where project_id = %s",
            (project_id,),
        )
    ).fetchall()
    billed_lines: dict[int, dict[BudgetKey, tuple[Decimal, int]]] = {}
    for number, change_order, position, quantity, value in rows:
        billed_lines.setdefault(int(number), {})[(change_order, int(position))] = (
            Decimal(quantity),
            int(value),
        )
    released = await (
        await conn.execute(
            "select coalesce(sum(amount_minor), 0) from gba.construction_retainage_releases "
            "where project_id = %s",
            (project_id,),
        )
    ).fetchone()
    return _State(
        lines=await budget_lines(conn, project_id),
        measured={(r[0], int(r[1])): (r[2], Decimal(r[3])) for r in measured},
        items=[(r[0], str(r[1])) for r in items],
        applications=[(int(r[0]), int(r[1]), int(r[2]), int(r[3])) for r in applications],
        billed_lines=billed_lines,
        released=int(released[0]) if released else 0,
    )


def _releasable(state: _State, scope: str, phase: str | None) -> int:
    """The amount an acceptance releases (decision 8), never above what is still held."""
    held = state.retained() - state.released
    if scope == "final" or phase is None:
        return held
    return min(max(state.phase_retained(phase), 0), held)


# Views ------------------------------------------------------------------------------

_HEAD = (
    "select a.number, a.scope, a.phase, a.accepted_on, a.signatory, a.source, a.note, "
    "a.warranty_ends_on, a.recorded_at, r.released_on, r.amount_minor, r.note, r.recorded_at "
    "from gba.construction_acceptances a left join gba.construction_retainage_releases r "
    "on r.tenant_id = a.tenant_id and r.project_id = a.project_id and r.acceptance = a.number "
    "where a.project_id = %s "
)


def _view(project_id: UUID, row: tuple[Any, ...]) -> AcceptanceView:
    return AcceptanceView(
        project_id=project_id,
        number=row[0],
        scope=row[1],
        phase=row[2],
        accepted_on=row[3],
        signatory=row[4],
        source=row[5],
        note=row[6],
        warranty_starts_on=row[3] if row[1] == "final" else None,
        warranty_ends_on=row[7],
        recorded_at=row[8],
        release=(
            ReleaseView(released_on=row[9], amount_minor=row[10], note=row[11], recorded_at=row[12])
            if row[9] is not None
            else None
        ),
    )


async def load_acceptance(
    conn: RuntimeConnection, project_id: UUID, number: int
) -> AcceptanceView | None:
    """One acceptance with its release, or None (decision 11)."""
    await check_contract(conn, project_id)
    row = await (await conn.execute(_HEAD + "and a.number = %s", (project_id, number))).fetchone()
    return _view(project_id, row) if row is not None else None


async def list_acceptances(conn: RuntimeConnection, project_id: UUID) -> AcceptanceList:
    """Every acceptance, every phase of the budget and the retainage totals, derived (11)."""
    await check_contract(conn, project_id)
    currency = await project_currency(conn, project_id)
    rows = await (await conn.execute(_HEAD + "order by a.number", (project_id,))).fetchall()
    items = [_view(project_id, row) for row in rows]
    state = await _state(conn, project_id)
    accepted = {item.phase: item for item in items if item.scope == "phase"}
    phases = []
    for phase in state.phases():
        own = accepted.get(phase)
        phases.append(
            PhaseAcceptanceView(
                phase=phase,
                finished=not state.unfinished(phase),
                open_items=state.blocking(phase),
                billed_in_full=state.billed_in_full(phase),
                retained_minor=state.phase_retained(phase),
                acceptance=own.number if own is not None else None,
                released_minor=(
                    own.release.amount_minor if own is not None and own.release else None
                ),
            )
        )
    retained = state.retained()
    return AcceptanceList(
        project_id=project_id,
        currency=currency,
        retained_minor=retained,
        released_minor=state.released,
        held_minor=retained - state.released,
        phases=phases,
        final=next((item for item in items if item.scope == "final"), None),
        items=items,
    )


async def _stored(
    conn: RuntimeConnection, project_id: UUID, body: dict[str, object]
) -> AcceptanceView:
    number = body.get("number")
    view = await load_acceptance(conn, project_id, number) if isinstance(number, int) else None
    if view is None:
        raise NotFoundError("Acceptance not found", project_id=str(project_id))
    return view


# Acceptance -------------------------------------------------------------------------


def _refused_acceptance(exc: CheckViolation) -> Exception | None:
    """The database's answer to an acceptance it refused, as the error the client sees."""
    name = exc.diag.constraint_name
    if name == "construction_acceptances_sequence_check":
        return ConstructionRevisionConflictError("The project's acceptances changed; try again")
    if name == "construction_acceptances_accepted_check":
        return ConstructionAcceptedError("This scope is already accepted")
    if name == "construction_acceptances_date_check":
        return ConstructionFutureDateError("The date is after today on the site")
    if name == "construction_acceptances_phase_check":
        return InvalidReferenceError("An acceptance names a phase of the budget", field="phase")
    if name == "construction_acceptances_completed_check":
        return ConstructionNotCompletedError("Only finished work is accepted")
    if name == "construction_acceptances_items_check":
        return ConstructionOpenItemsError("Open or fixed items block the acceptance")
    if name == "construction_acceptances_billed_check":
        return ConstructionNotFullyBilledError("The final acceptance needs the contract billed")
    return None


async def record_acceptance(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AcceptanceInput,
) -> AcceptanceView:
    """Record the customer's acceptance of a phase or of the whole project (decisions 2-6)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.acceptance", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("An acceptance needs a contract")
    earlier = await (
        await conn.execute(
            "select number, scope, phase from gba.construction_acceptances where project_id = %s "
            "order by number",
            (project_id,),
        )
    ).fetchall()
    for _, done, phase in earlier:
        if done == "final" or (body.scope == "phase" and phase == body.phase):
            raise ConstructionAcceptedError(
                "The project is finally accepted"
                if done == "final"
                else "This phase is already accepted",
                phase=phase,
            )
    if body.accepted_on > await site_today(conn, project_id):
        raise ConstructionFutureDateError("The date is after today on the site")
    state = await _state(conn, project_id)
    if body.phase is not None and body.phase not in state.phases():
        raise InvalidReferenceError("An acceptance names a phase of the budget", field="phase")
    late = state.unfinished(body.phase, body.accepted_on)
    if late:
        raise ConstructionNotCompletedError(
            "Only finished work, measured by the acceptance date, is accepted",
            unfinished_lines=len(late),
        )
    blocking = state.blocking(body.phase)
    if blocking:
        raise ConstructionOpenItemsError("Open or fixed items block the acceptance", items=blocking)
    if body.scope == "final":
        contract = sum(int(line["contract_minor"]) for line in state.lines)
        if state.billed() != contract:
            raise ConstructionNotFullyBilledError(
                "Bill the whole contract before the final acceptance",
                billed_to_date=state.billed(),
                contract=contract,
            )
    number = (int(earlier[-1][0]) if earlier else 0) + 1
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_acceptances (tenant_id, project_id, number, scope, "
                "phase, accepted_on, signatory, source, note, warranty_ends_on, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    project_id,
                    number,
                    body.scope,
                    body.phase,
                    body.accepted_on,
                    body.signatory,
                    body.source,
                    body.note,
                    body.warranty_ends_on,
                    user_id,
                ),
            )
    except UniqueViolation as exc:
        raise ConstructionAcceptedError("This scope is already accepted") from exc
    except CheckViolation as exc:
        mapped = _refused_acceptance(exc)
        if mapped is None:
            raise
        raise mapped from exc
    view = await load_acceptance(conn, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


# Release ----------------------------------------------------------------------------


def _refused_release(exc: CheckViolation) -> Exception | None:
    """The database's answer to a release it refused, as the error the client sees."""
    name = exc.diag.constraint_name
    if name == "construction_retainage_releases_released_check":
        return ConstructionReleasedError("This retainage is already released")
    if name == "construction_retainage_releases_date_check":
        return ConstructionFutureDateError("A release is dated from its acceptance to today")
    if name == "construction_retainage_releases_billed_check":
        return ConstructionNotFullyBilledError("Bill the phase in full before its release")
    if name in (
        "construction_retainage_releases_amount_check",
        "construction_retainage_releases_positive_check",
    ):
        return ConstructionRevisionConflictError("The project changed meanwhile; try again")
    return None


async def record_release(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    number: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ReleaseInput,
) -> AcceptanceView:
    """Release the retainage an acceptance frees, once (decision 8)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.retainage_release", key)
    fingerprint = request_fingerprint(f"{project_id}:{number}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    current = await load_acceptance(conn, project_id, number)
    if current is None:
        raise NotFoundError("Acceptance not found", project_id=str(project_id), number=number)
    final_release = await (
        await conn.execute(
            "select 1 from gba.construction_retainage_releases r "
            "join gba.construction_acceptances a on a.tenant_id = r.tenant_id "
            "and a.project_id = r.project_id and a.number = r.acceptance "
            "where r.project_id = %s and a.scope = 'final'",
            (project_id,),
        )
    ).fetchone()
    if current.release is not None or final_release is not None:
        raise ConstructionReleasedError(
            "This retainage is already released"
            if current.release is not None
            else "The final release took all retainage"
        )
    if body.released_on > await site_today(conn, project_id):
        raise ConstructionFutureDateError("The date is after today on the site")
    if body.released_on < current.accepted_on:
        raise ConstructionBeforeAcceptanceError(
            "Retainage is released on or after its acceptance",
            accepted_on=current.accepted_on.isoformat(),
        )
    state = await _state(conn, project_id)
    if current.phase is not None and not state.billed_in_full(current.phase):
        raise ConstructionNotFullyBilledError(
            "Bill the phase in full before its retainage is released", phase=current.phase
        )
    amount = _releasable(state, current.scope, current.phase)
    if amount <= 0:
        raise ConstructionNothingToReleaseError("No retainage is held for this acceptance")
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_retainage_releases (tenant_id, project_id, "
                "acceptance, released_on, amount_minor, note, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (business, project_id, number, body.released_on, amount, body.note, user_id),
            )
    except UniqueViolation as exc:
        raise ConstructionReleasedError("This retainage is already released") from exc
    except CheckViolation as exc:
        mapped = _refused_release(exc)
        if mapped is None:
            raise
        raise mapped from exc
    view = await load_acceptance(conn, project_id, number)
    assert view is not None  # noqa: S101 - read above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view
