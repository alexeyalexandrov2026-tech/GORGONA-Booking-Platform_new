"""O4a (package O, BUILD-01): the construction schedule.

docs/plan/PACKAGE_O4A_DESIGN_2026-11-01.md, decisions 2-4. The schedule is one versioned,
insert-only document per project: every version names budget phases with planned dates (site dates)
and finish-to-start dependencies that never form a cycle; the latest version counts. The view
derives conflicts (a phase starting on or before a predecessor's planned finish, shown and not
blocked), the critical chain and each phase's progress by value; nothing is optimised.
"""

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
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
from gorgona_booking.business.construction_budget import budget_lines
from gorgona_booking.business.construction_contracts import ConstructionNoContractError
from gorgona_booking.business.construction_progress import (
    SiteDate,
    check_contract,
    load_progress,
    not_blank,
    one_line,
)
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DomainError, InvalidReferenceError, NotFoundError

PhaseName = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(one_line)]
ScheduleNote = Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(not_blank)]


class ConstructionScheduleCycleError(DomainError):
    code = "CONSTRUCTION_SCHEDULE_CYCLE"


class PlannedPhase(Strict):
    phase: PhaseName
    planned_start: SiteDate
    planned_finish: SiteDate
    depends_on: list[PhaseName] = Field(default_factory=list, max_length=199)

    @model_validator(mode="after")
    def _dates_and_predecessors(self) -> Self:
        if self.planned_finish < self.planned_start:
            raise ValueError("a phase finishes on or after its start")
        if self.phase in self.depends_on:
            raise ValueError("a phase never depends on itself")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("each predecessor is named once")
        return self


class ScheduleInput(Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=100_000)
    note: ScheduleNote | None = None
    phases: list[PlannedPhase] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _phases_of_this_version(self) -> Self:
        names = [item.phase for item in self.phases]
        if len(set(names)) != len(names):
            raise ValueError("each phase is scheduled once")
        if any(before not in names for item in self.phases for before in item.depends_on):
            raise ValueError("a predecessor is a phase of the same schedule")
        if sum(len(item.depends_on) for item in self.phases) > 1000:
            raise ValueError("at most 1000 dependencies")
        return self


class ScheduledPhaseView(BaseModel):
    phase: str
    planned_start: date
    planned_finish: date
    depends_on: list[str]
    conflict: bool
    critical: bool
    percent: Decimal


class ScheduleView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    revision: int
    note: str | None
    recorded_at: datetime | None
    planned_finish: date | None
    phases: list[ScheduledPhaseView]
    unscheduled: list[str]


Plan = dict[str, tuple[date, date, list[str]]]


def has_cycle(graph: dict[str, list[str]]) -> bool:
    """True when the dependencies cannot be ordered: some phase waits on itself (decision 3)."""
    done: set[str] = set()
    pending = dict(graph)
    while pending:
        ready = [name for name, before in pending.items() if all(b in done for b in before)]
        if not ready:
            return True
        for name in ready:
            done.add(name)
            del pending[name]
    return False


def critical_chain(plan: Plan) -> set[str]:
    """From the latest planned finish back through the latest-finishing predecessor (decision 4)."""

    def latest(names: Iterable[str]) -> str:
        return min(names, key=lambda name: (-plan[name][1].toordinal(), name))

    chain: set[str] = set()
    if not plan:
        return chain
    node = latest(plan)
    while node not in chain:
        chain.add(node)
        before = plan[node][2]
        if not before:
            break
        node = latest(before)
    return chain


async def budget_phases(conn: RuntimeConnection, project_id: UUID) -> list[str]:
    """The phases of the budget in the order they first appear (decision 1)."""
    seen: list[str] = []
    for item in await budget_lines(conn, project_id):
        if item["phase"] not in seen:
            seen.append(item["phase"])
    return seen


async def _latest(conn: RuntimeConnection, project_id: UUID) -> int:
    row = await (
        await conn.execute(
            "select coalesce(max(revision), 0) from gba.construction_schedule_versions "
            "where project_id = %s",
            (project_id,),
        )
    ).fetchone()
    return int(row[0]) if row else 0


async def load_schedule(
    conn: RuntimeConnection, project_id: UUID, revision: int | None = None
) -> ScheduleView:
    """A version of the schedule (the latest by default) with what it derives (decision 4)."""
    await check_contract(conn, project_id)
    wanted = await _latest(conn, project_id) if revision is None else revision
    budget = await budget_phases(conn, project_id)
    if wanted == 0:
        return ScheduleView(
            project_id=project_id,
            revision=0,
            note=None,
            recorded_at=None,
            planned_finish=None,
            phases=[],
            unscheduled=budget,
        )
    head = await (
        await conn.execute(
            "select note, created_at from gba.construction_schedule_versions "
            "where project_id = %s and revision = %s",
            (project_id, wanted),
        )
    ).fetchone()
    if head is None:
        raise NotFoundError("Schedule version not found", revision=wanted)
    rows = await (
        await conn.execute(
            "select phase, planned_start, planned_finish from gba.construction_schedule_phases "
            "where project_id = %s and revision = %s order by planned_start, phase",
            (project_id, wanted),
        )
    ).fetchall()
    links = await (
        await conn.execute(
            "select phase, depends_on from gba.construction_schedule_dependencies "
            "where project_id = %s and revision = %s order by phase, depends_on",
            (project_id, wanted),
        )
    ).fetchall()
    plan: Plan = {str(row[0]): (row[1], row[2], []) for row in rows}
    for phase, before in links:
        plan[str(phase)][2].append(str(before))
    chain = critical_chain(plan)
    progress = {item.phase: item.percent for item in (await load_progress(conn, project_id)).phases}
    phases = [
        ScheduledPhaseView(
            phase=name,
            planned_start=start,
            planned_finish=finish,
            depends_on=sorted(before),
            conflict=any(plan[b][1] >= start for b in before),
            critical=name in chain,
            percent=progress.get(name, Decimal("0.00")),
        )
        for name, (start, finish, before) in plan.items()
    ]
    return ScheduleView(
        project_id=project_id,
        revision=wanted,
        note=head[0],
        recorded_at=head[1],
        planned_finish=max((finish for _, finish, _ in plan.values()), default=None),
        phases=phases,
        unscheduled=[name for name in budget if name not in plan],
    )


def _refused(exc: CheckViolation) -> Exception | None:
    """The database's answer to a schedule it refused, as the error the client sees."""
    name = exc.diag.constraint_name
    if name in (
        "construction_schedule_versions_sequence_check",
        "construction_schedule_phases_version_check",
        "construction_schedule_dependencies_version_check",
    ):
        return ConstructionRevisionConflictError("The schedule changed since it was read")
    if name == "construction_schedule_phases_budget_check":
        return InvalidReferenceError("A schedule names phases of the budget", field="phases")
    if name == "construction_schedule_dependencies_cycle_check":
        return ConstructionScheduleCycleError("Schedule dependencies never form a cycle")
    return None


async def put_schedule(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ScheduleInput,
) -> ScheduleView:
    """The next version of the schedule, on the version the client read (decisions 2-3)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.schedule", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        saved = stored.body.get("revision")
        if not isinstance(saved, int):
            raise NotFoundError("Schedule version not found", project_id=str(project_id))
        return await load_schedule(conn, project_id, saved)
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("A schedule needs a contract")
    current = await _latest(conn, project_id)
    if body.expected_revision != current:
        raise ConstructionRevisionConflictError(
            "The schedule changed since it was read", revision=current
        )
    budget = set(await budget_phases(conn, project_id))
    unknown = [item.phase for item in body.phases if item.phase not in budget]
    if unknown:
        raise InvalidReferenceError(
            "A schedule names phases of the budget", field="phases", phases=unknown
        )
    if has_cycle({item.phase: list(item.depends_on) for item in body.phases}):
        raise ConstructionScheduleCycleError("Schedule dependencies never form a cycle")
    revision = current + 1
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_schedule_versions (tenant_id, project_id, "
                "revision, note, created_by) values (%s, %s, %s, %s, %s)",
                (business, project_id, revision, body.note, user_id),
            )
            for item in body.phases:
                await conn.execute(
                    "insert into gba.construction_schedule_phases (tenant_id, project_id, "
                    "revision, phase, planned_start, planned_finish) "
                    "values (%s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        project_id,
                        revision,
                        item.phase,
                        item.planned_start,
                        item.planned_finish,
                    ),
                )
            for item in body.phases:
                for before in item.depends_on:
                    await conn.execute(
                        "insert into gba.construction_schedule_dependencies (tenant_id, "
                        "project_id, revision, phase, depends_on) values (%s, %s, %s, %s, %s)",
                        (business, project_id, revision, item.phase, before),
                    )
    except UniqueViolation as exc:
        raise ConstructionRevisionConflictError("The schedule changed since it was read") from exc
    except CheckViolation as exc:
        mapped = _refused(exc)
        if mapped is None:
            raise
        raise mapped from exc
    view = await load_schedule(conn, project_id, revision)
    await idempotency.complete(conn, scope, 200, {"revision": revision})
    return view
