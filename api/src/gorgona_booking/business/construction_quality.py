"""O4b (package O, BUILD-01): inspections, defects and the punch list.

docs/plan/PACKAGE_O4B_DESIGN_2026-11-01.md. An inspection is an insert-only check of a phase (or
of the whole project) with a result and photos. A quality item is a defect or a punch item; the row
never changes and its state moves by insert-only events: open -> fixed or void, fixed -> closed or
open (reopened). The database rechecks the order, the phase, the site date, a passed inspection and
every move under the project lock. State, overdue and the summary per phase and kind are derived.
"""

from collections import defaultdict
from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
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
from gorgona_booking.business.construction_contracts import ConstructionNoContractError
from gorgona_booking.business.construction_daily_reports import IMAGES, PhotoInput, PhotoView
from gorgona_booking.business.construction_progress import (
    ConstructionFutureDateError,
    SiteDate,
    not_blank,
    one_line,
    project_currency,
    site_today,
)
from gorgona_booking.business.construction_schedule import budget_phases
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

Label = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(one_line)]
Title = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(one_line)]
Place = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(one_line)]
Text = Annotated[str, Field(min_length=1, max_length=4000), AfterValidator(not_blank)]
EventNote = Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(not_blank)]
InspectionKind = Literal["internal", "customer", "authority", "third_party"]
InspectionResult = Literal["passed", "passed_with_items", "failed"]
ItemKind = Literal["defect", "punch"]
Severity = Literal["minor", "major", "critical"]
ItemState = Literal["open", "fixed", "closed", "void"]
MOVES: frozenset[tuple[str, str]] = frozenset(
    {("open", "fixed"), ("open", "void"), ("fixed", "closed"), ("fixed", "open")}
)
KINDS: tuple[ItemKind, ...] = ("defect", "punch")


class ConstructionItemTransitionError(ConflictError):
    code = "CONSTRUCTION_ITEM_TRANSITION"


class ConstructionInspectionPassedError(DomainError):
    code = "CONSTRUCTION_INSPECTION_PASSED"


class InspectionInput(Strict):
    schema_version: Literal[1]
    inspected_on: SiteDate
    kind: InspectionKind
    phase: Label | None = None
    inspector: Label
    inspector_counterparty_id: UUID | None = None
    result: InspectionResult
    notes: Text | None = None
    photos: list[PhotoInput] = Field(default_factory=list, max_length=50)


class ItemInput(Strict):
    schema_version: Literal[1]
    kind: ItemKind
    title: Title
    description: Text | None = None
    phase: Label | None = None
    location: Place | None = None
    severity: Severity
    raised_on: SiteDate
    due_on: SiteDate | None = None
    responsible_id: UUID | None = None
    inspection: int | None = Field(default=None, ge=1, le=1_000_000)
    photos: list[PhotoInput] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _due_after_raised(self) -> Self:
        if self.due_on is not None and self.due_on < self.raised_on:
            raise ValueError("an item is not due before it was raised")
        return self


class EventInput(Strict):
    schema_version: Literal[1]
    expected_sequence: int = Field(ge=0, le=10_000)
    state: ItemState
    note: EventNote | None = None
    photos: list[PhotoInput] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _note_when_needed(self) -> Self:
        if self.state in ("open", "void") and self.note is None:
            raise ValueError("voiding or reopening an item needs a note")
        return self


class InspectionView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    number: int
    inspected_on: date
    kind: str
    phase: str | None
    inspector: str
    inspector_counterparty_id: UUID | None
    result: str
    notes: str | None
    photos: list[PhotoView]
    recorded_at: datetime


class InspectionSummary(BaseModel):
    number: int
    inspected_on: date
    kind: str
    phase: str | None
    result: str
    photo_count: int
    item_count: int


class InspectionList(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    items: list[InspectionSummary]


class ItemEventView(BaseModel):
    sequence: int
    state: str
    note: str | None
    photos: list[PhotoView]
    recorded_at: datetime


class ItemView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    number: int
    kind: str
    title: str
    description: str | None
    phase: str | None
    location: str | None
    severity: str
    raised_on: date
    due_on: date | None
    responsible_id: UUID | None
    inspection: int | None
    state: str
    sequence: int
    overdue: bool
    photos: list[PhotoView]
    events: list[ItemEventView]
    recorded_at: datetime


class ItemSummary(BaseModel):
    number: int
    kind: str
    title: str
    phase: str | None
    severity: str
    state: str
    due_on: date | None
    overdue: bool
    responsible_id: UUID | None


class QualitySummary(BaseModel):
    phase: str | None
    kind: str
    open: int
    fixed: int
    closed: int
    void: int
    overdue: int


class ItemList(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    items: list[ItemSummary]
    summary: list[QualitySummary]


def overdue(state: str, due_on: date | None, today: date) -> bool:
    """Open past its due date in the site's time zone (decision 6)."""
    return state == "open" and due_on is not None and due_on < today


def _photo(row: tuple[object, ...]) -> PhotoView:
    return PhotoView.model_validate(
        {
            "position": row[0],
            "document_id": row[1],
            "revision": row[2],
            "file_id": row[3],
            "media_type": row[4],
        }
    )


_PHOTO_COLUMNS = (
    "p.position, p.document_id, p.document_revision, v.file_id, f.media_type "
    "from {table} p "
    "left join gba.document_versions v on v.tenant_id = p.tenant_id "
    "and v.document_id = p.document_id and v.revision = p.document_revision "
    "left join gba.document_files f on f.tenant_id = v.tenant_id and f.id = v.file_id "
)


async def load_inspection(
    conn: RuntimeConnection, project_id: UUID, number: int
) -> InspectionView | None:
    """One inspection with its photos, or None."""
    await project_currency(conn, project_id)
    row = await (
        await conn.execute(
            "select inspected_on, kind, phase, inspector, inspector_counterparty_id, result, "
            "notes, created_at from gba.construction_inspections "
            "where project_id = %s and number = %s",
            (project_id, number),
        )
    ).fetchone()
    if row is None:
        return None
    photos = await (
        await conn.execute(
            "select "
            + _PHOTO_COLUMNS.format(table="gba.construction_inspection_photos")
            + "where p.project_id = %s and p.number = %s order by p.position",
            (project_id, number),
        )
    ).fetchall()
    return InspectionView(
        project_id=project_id,
        number=number,
        inspected_on=row[0],
        kind=row[1],
        phase=row[2],
        inspector=row[3],
        inspector_counterparty_id=row[4],
        result=row[5],
        notes=row[6],
        photos=[_photo(p) for p in photos],
        recorded_at=row[7],
    )


async def list_inspections(conn: RuntimeConnection, project_id: UUID) -> InspectionList:
    """Every inspection of the project in order, with its photo and item counts."""
    await project_currency(conn, project_id)
    rows = await (
        await conn.execute(
            "select i.number, i.inspected_on, i.kind, i.phase, i.result, "
            "(select count(*) from gba.construction_inspection_photos p "
            "where p.tenant_id = i.tenant_id and p.project_id = i.project_id "
            "and p.number = i.number), "
            "(select count(*) from gba.construction_quality_items q "
            "where q.tenant_id = i.tenant_id and q.project_id = i.project_id "
            "and q.inspection = i.number) "
            "from gba.construction_inspections i where i.project_id = %s order by i.number",
            (project_id,),
        )
    ).fetchall()
    return InspectionList(
        project_id=project_id,
        items=[
            InspectionSummary(
                number=row[0],
                inspected_on=row[1],
                kind=row[2],
                phase=row[3],
                result=row[4],
                photo_count=int(row[5]),
                item_count=int(row[6]),
            )
            for row in rows
        ],
    )


async def load_item(conn: RuntimeConnection, project_id: UUID, number: int) -> ItemView | None:
    """One item with its state, events and photos, or None."""
    today = await site_today(conn, project_id)
    row = await (
        await conn.execute(
            "select kind, title, description, phase, location, severity, raised_on, due_on, "
            "responsible_id, inspection, created_at from gba.construction_quality_items "
            "where project_id = %s and number = %s",
            (project_id, number),
        )
    ).fetchone()
    if row is None:
        return None
    events = await (
        await conn.execute(
            "select sequence, state, note, created_at from gba.construction_quality_item_events "
            "where project_id = %s and item = %s order by sequence",
            (project_id, number),
        )
    ).fetchall()
    photos = await (
        await conn.execute(
            "select p.sequence, "
            + _PHOTO_COLUMNS.format(table="gba.construction_quality_item_photos")
            + "where p.project_id = %s and p.item = %s order by p.sequence, p.position",
            (project_id, number),
        )
    ).fetchall()
    by_sequence: dict[int, list[PhotoView]] = defaultdict(list)
    for photo in photos:
        by_sequence[int(photo[0])].append(_photo(photo[1:]))
    state = str(events[-1][1]) if events else "open"
    return ItemView(
        project_id=project_id,
        number=number,
        kind=row[0],
        title=row[1],
        description=row[2],
        phase=row[3],
        location=row[4],
        severity=row[5],
        raised_on=row[6],
        due_on=row[7],
        responsible_id=row[8],
        inspection=row[9],
        state=state,
        sequence=len(events),
        overdue=overdue(state, row[7], today),
        photos=by_sequence[0],
        events=[
            ItemEventView(
                sequence=e[0], state=e[1], note=e[2], photos=by_sequence[e[0]], recorded_at=e[3]
            )
            for e in events
        ],
        recorded_at=row[10],
    )


def _summary(items: list[ItemSummary], phases: list[str]) -> list[QualitySummary]:
    """Counts per phase (budget order, then the whole project) and kind, rows with items only."""
    counts: dict[tuple[str | None, str], dict[str, int]] = {}
    for item in items:
        row = counts.setdefault((item.phase, item.kind), defaultdict(int))
        row[item.state] += 1
        row["overdue"] += int(item.overdue)
    order: list[str | None] = [*phases]
    order += sorted({p for p, _ in counts if p is not None and p not in phases})
    order.append(None)
    return [
        QualitySummary(
            phase=phase,
            kind=kind,
            open=counts[phase, kind]["open"],
            fixed=counts[phase, kind]["fixed"],
            closed=counts[phase, kind]["closed"],
            void=counts[phase, kind]["void"],
            overdue=counts[phase, kind]["overdue"],
        )
        for phase in order
        for kind in KINDS
        if (phase, kind) in counts
    ]


async def list_items(
    conn: RuntimeConnection,
    project_id: UUID,
    kind: ItemKind | None = None,
    state: ItemState | None = None,
    phase: str | None = None,
) -> ItemList:
    """The items (filtered) with their derived state; the summary covers every item (decision 6)."""
    today = await site_today(conn, project_id)
    rows = await (
        await conn.execute(
            "select q.number, q.kind, q.title, q.phase, q.severity, q.due_on, q.responsible_id, "
            "coalesce((select e.state from gba.construction_quality_item_events e "
            "where e.tenant_id = q.tenant_id and e.project_id = q.project_id "
            "and e.item = q.number order by e.sequence desc limit 1), 'open') "
            "from gba.construction_quality_items q where q.project_id = %s order by q.number",
            (project_id,),
        )
    ).fetchall()
    every = [
        ItemSummary(
            number=row[0],
            kind=row[1],
            title=row[2],
            phase=row[3],
            severity=row[4],
            state=row[7],
            due_on=row[5],
            overdue=overdue(str(row[7]), row[5], today),
            responsible_id=row[6],
        )
        for row in rows
    ]
    chosen = [
        item
        for item in every
        if (kind is None or item.kind == kind)
        and (state is None or item.state == state)
        and (phase is None or item.phase == phase)
    ]
    phases = await budget_phases(conn, project_id) if every else []
    return ItemList(project_id=project_id, items=chosen, summary=_summary(every, phases))


async def _check_counterparty(conn: RuntimeConnection, party: UUID | None, field: str) -> None:
    if party is None:
        return
    found = await (
        await conn.execute("select 1 from gba.counterparties where id = %s", (party,))
    ).fetchone()
    if found is None:
        raise InvalidReferenceError("An unknown counterparty", field=field)


async def _check_photos(conn: RuntimeConnection, photos: list[PhotoInput]) -> None:
    for photo in photos:
        image = await (
            await conn.execute(
                "select 1 from gba.document_versions v join gba.document_files f "
                "on f.tenant_id = v.tenant_id and f.id = v.file_id "
                "where v.document_id = %s and v.revision = %s and f.media_type = any(%s)",
                (photo.document_id, photo.revision, list(IMAGES)),
            )
        ).fetchone()
        if image is None:
            raise InvalidReferenceError(
                "A photo is a document version with a PNG or JPEG file", field="photos"
            )


async def _check_phase(conn: RuntimeConnection, project_id: UUID, phase: str | None) -> None:
    if phase is not None and phase not in await budget_phases(conn, project_id):
        raise InvalidReferenceError("A phase of the budget", field="phase", phase=phase)


async def _ready(conn: RuntimeConnection, project_id: UUID, on: date, what: str) -> None:
    """The project is locked, has a contract and the date is not after today on the site."""
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError(f"{what} needs a contract")
    if on > await site_today(conn, project_id):
        raise ConstructionFutureDateError("The date is after today on the site")


NEXT_INSPECTION = (
    "select coalesce(max(number), 0) + 1 from gba.construction_inspections where project_id = %s"
)
NEXT_ITEM = (
    "select coalesce(max(number), 0) + 1 from gba.construction_quality_items where project_id = %s"
)


async def _next(conn: RuntimeConnection, query: str, project_id: UUID) -> int:
    row = await (await conn.execute(query, (project_id,))).fetchone()
    return int(row[0]) if row else 1


def _refused(exc: CheckViolation) -> Exception | None:
    """The database's answer to a record it refused, as the error the client sees."""
    name = str(exc.diag.constraint_name)
    if name.endswith("_sequence_check") or name.endswith("_record_check"):
        return ConstructionRevisionConflictError("The record changed since it was read")
    if name.endswith("_budget_check"):
        return InvalidReferenceError("A phase of the budget", field="phase")
    if name.endswith("_date_check"):
        return ConstructionFutureDateError("The date is after today on the site")
    if name.endswith("_image_check"):
        return InvalidReferenceError("A photo is a document version with an image", field="photos")
    if name == "construction_quality_items_inspection_check":
        return ConstructionInspectionPassedError("An inspection that passed raises no items")
    if name == "construction_quality_item_events_transition_check":
        return ConstructionItemTransitionError("The item's state does not allow this move")
    return None


def _translated(exc: Exception) -> Exception:
    if isinstance(exc, UniqueViolation):
        return ConstructionRevisionConflictError("The record changed since it was read")
    if isinstance(exc, ForeignKeyViolation):
        return InvalidReferenceError("The record names an unknown record")
    if isinstance(exc, CheckViolation):
        mapped = _refused(exc)
        if mapped is not None:
            return mapped
    return exc


async def _photos(
    conn: RuntimeConnection, sql: str, head: tuple[object, ...], photos: list[PhotoInput]
) -> None:
    for position, photo in enumerate(photos, start=1):
        await conn.execute(sql, (*head, position, photo.document_id, photo.revision))


async def record_inspection(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: InspectionInput,
) -> InspectionView:
    """The next inspection of the project (decision 2)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.inspection", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        saved = stored.body.get("number")
        view = await load_inspection(conn, project_id, saved) if isinstance(saved, int) else None
        if view is None:
            raise NotFoundError("Inspection not found", project_id=str(project_id))
        return view
    await _ready(conn, project_id, body.inspected_on, "An inspection")
    await _check_phase(conn, project_id, body.phase)
    await _check_counterparty(conn, body.inspector_counterparty_id, "inspector_counterparty_id")
    await _check_photos(conn, body.photos)
    number = await _next(conn, NEXT_INSPECTION, project_id)
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_inspections (tenant_id, project_id, number, "
                "inspected_on, kind, phase, inspector, inspector_counterparty_id, result, notes, "
                "created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    project_id,
                    number,
                    body.inspected_on,
                    body.kind,
                    body.phase,
                    body.inspector,
                    body.inspector_counterparty_id,
                    body.result,
                    body.notes,
                    user_id,
                ),
            )
            await _photos(
                conn,
                "insert into gba.construction_inspection_photos (tenant_id, project_id, number, "
                "position, document_id, document_revision) values (%s, %s, %s, %s, %s, %s)",
                (business, project_id, number),
                body.photos,
            )
    except (UniqueViolation, ForeignKeyViolation, CheckViolation) as exc:
        raise _translated(exc) from exc
    view = await load_inspection(conn, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


async def record_item(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ItemInput,
) -> ItemView:
    """The next defect or punch item of the project, open (decisions 3-4)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.quality_item", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        saved = stored.body.get("number")
        view = await load_item(conn, project_id, saved) if isinstance(saved, int) else None
        if view is None:
            raise NotFoundError("Item not found", project_id=str(project_id))
        return view
    await _ready(conn, project_id, body.raised_on, "An item")
    await _check_phase(conn, project_id, body.phase)
    if body.inspection is not None:
        found = await (
            await conn.execute(
                "select result from gba.construction_inspections "
                "where project_id = %s and number = %s",
                (project_id, body.inspection),
            )
        ).fetchone()
        if found is None:
            raise InvalidReferenceError("An unknown inspection", field="inspection")
        if found[0] == "passed":
            raise ConstructionInspectionPassedError("An inspection that passed raises no items")
    await _check_counterparty(conn, body.responsible_id, "responsible_id")
    await _check_photos(conn, body.photos)
    number = await _next(conn, NEXT_ITEM, project_id)
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_quality_items (tenant_id, project_id, number, kind, "
                "title, description, phase, location, severity, raised_on, due_on, "
                "responsible_id, inspection, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    project_id,
                    number,
                    body.kind,
                    body.title,
                    body.description,
                    body.phase,
                    body.location,
                    body.severity,
                    body.raised_on,
                    body.due_on,
                    body.responsible_id,
                    body.inspection,
                    user_id,
                ),
            )
            await _photos(
                conn,
                "insert into gba.construction_quality_item_photos (tenant_id, project_id, item, "
                "sequence, position, document_id, document_revision) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (business, project_id, number, 0),
                body.photos,
            )
    except (UniqueViolation, ForeignKeyViolation, CheckViolation) as exc:
        raise _translated(exc) from exc
    view = await load_item(conn, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view


async def move_item(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    number: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: EventInput,
) -> ItemView:
    """The next event of an item, on the events the client saw (decision 5)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.quality_event", key)
    fingerprint = request_fingerprint(f"{project_id}:{number}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_item(conn, project_id, number)
        if view is None:
            raise NotFoundError("Item not found", project_id=str(project_id), number=number)
        return view
    await lock_project(conn, project_id)
    item = await (
        await conn.execute(
            "select 1 from gba.construction_quality_items where project_id = %s and number = %s",
            (project_id, number),
        )
    ).fetchone()
    if item is None:
        raise NotFoundError("Item not found", project_id=str(project_id), number=number)
    events = await (
        await conn.execute(
            "select sequence, state from gba.construction_quality_item_events "
            "where project_id = %s and item = %s order by sequence desc limit 1",
            (project_id, number),
        )
    ).fetchone()
    current, previous = (int(events[0]), str(events[1])) if events else (0, "open")
    if body.expected_sequence != current:
        raise ConstructionRevisionConflictError(
            "The item changed since it was read", sequence=current
        )
    if (previous, body.state) not in MOVES:
        raise ConstructionItemTransitionError(
            "The item's state does not allow this move", state=previous, to=body.state
        )
    await _check_photos(conn, body.photos)
    sequence = current + 1
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_quality_item_events (tenant_id, project_id, item, "
                "sequence, state, note, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (business, project_id, number, sequence, body.state, body.note, user_id),
            )
            await _photos(
                conn,
                "insert into gba.construction_quality_item_photos (tenant_id, project_id, item, "
                "sequence, position, document_id, document_revision) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (business, project_id, number, sequence),
                body.photos,
            )
    except (UniqueViolation, ForeignKeyViolation, CheckViolation) as exc:
        raise _translated(exc) from exc
    view = await load_item(conn, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"sequence": sequence})
    return view
