"""O4a (package O, BUILD-01): daily reports.

docs/plan/PACKAGE_O4A_DESIGN_2026-11-01.md, decision 5. One report per site date, never after today
on the site; a correction is the next revision of the same date and earlier revisions stay. A report
carries weather, notes, crew lines (optionally naming the counterparty whose crew it was) and
photos, which are stage-1 document versions with a PNG or JPEG file. The database rechecks the
revision sequence, the date and the photos.
"""

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
from gorgona_booking.business.construction_progress import (
    ConstructionFutureDateError,
    not_blank,
    one_line,
    project_currency,
    site_today,
)
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError

IMAGES = ("image/png", "image/jpeg")
Weather = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(one_line)]
Notes = Annotated[str, Field(min_length=1, max_length=4000), AfterValidator(not_blank)]
Label = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(one_line)]


class CrewInput(Strict):
    label: Label
    headcount: int = Field(ge=1, le=1000)
    counterparty_id: UUID | None = None


class PhotoInput(Strict):
    document_id: UUID
    revision: int = Field(ge=1, le=2_147_483_647)


class DailyReportInput(Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=1000)
    weather: Weather | None = None
    notes: Notes | None = None
    crew: list[CrewInput] = Field(default_factory=list, max_length=50)
    photos: list[PhotoInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _says_something(self) -> Self:
        if self.weather is None and self.notes is None and not self.crew and not self.photos:
            raise ValueError("a daily report has weather, notes, crew or photos")
        return self


class CrewView(BaseModel):
    position: int
    label: str
    headcount: int
    counterparty_id: UUID | None


class PhotoView(BaseModel):
    position: int
    document_id: UUID
    revision: int
    file_id: UUID | None
    media_type: str | None


class DailyReportView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    report_date: date
    revision: int
    weather: str | None
    notes: str | None
    crew: list[CrewView]
    photos: list[PhotoView]
    recorded_at: datetime


class DailyReportSummary(BaseModel):
    report_date: date
    revision: int
    weather: str | None
    headcount: int
    photo_count: int
    recorded_at: datetime


class DailyReportList(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    items: list[DailyReportSummary]


async def _latest(conn: RuntimeConnection, project_id: UUID, report_date: date) -> int:
    row = await (
        await conn.execute(
            "select coalesce(max(revision), 0) from gba.construction_daily_reports "
            "where project_id = %s and report_date = %s",
            (project_id, report_date),
        )
    ).fetchone()
    return int(row[0]) if row else 0


async def load_report(
    conn: RuntimeConnection, project_id: UUID, report_date: date, revision: int | None = None
) -> DailyReportView | None:
    """A revision of the report of a site date (the latest by default), or None."""
    await project_currency(conn, project_id)
    wanted = await _latest(conn, project_id, report_date) if revision is None else revision
    head = await (
        await conn.execute(
            "select weather, notes, created_at from gba.construction_daily_reports "
            "where project_id = %s and report_date = %s and revision = %s",
            (project_id, report_date, wanted),
        )
    ).fetchone()
    if head is None:
        return None
    crew = await (
        await conn.execute(
            "select position, label, headcount, counterparty_id "
            "from gba.construction_daily_report_crew "
            "where project_id = %s and report_date = %s and revision = %s order by position",
            (project_id, report_date, wanted),
        )
    ).fetchall()
    photos = await (
        await conn.execute(
            "select p.position, p.document_id, p.document_revision, v.file_id, f.media_type "
            "from gba.construction_daily_report_photos p "
            "left join gba.document_versions v on v.tenant_id = p.tenant_id "
            "and v.document_id = p.document_id and v.revision = p.document_revision "
            "left join gba.document_files f on f.tenant_id = v.tenant_id and f.id = v.file_id "
            "where p.project_id = %s and p.report_date = %s and p.revision = %s "
            "order by p.position",
            (project_id, report_date, wanted),
        )
    ).fetchall()
    return DailyReportView(
        project_id=project_id,
        report_date=report_date,
        revision=wanted,
        weather=head[0],
        notes=head[1],
        crew=[
            CrewView(position=row[0], label=row[1], headcount=row[2], counterparty_id=row[3])
            for row in crew
        ],
        photos=[
            PhotoView(
                position=row[0],
                document_id=row[1],
                revision=row[2],
                file_id=row[3],
                media_type=row[4],
            )
            for row in photos
        ],
        recorded_at=head[2],
    )


async def list_reports(conn: RuntimeConnection, project_id: UUID) -> DailyReportList:
    """The latest revision of every reported date, newest date first."""
    await project_currency(conn, project_id)
    rows = await (
        await conn.execute(
            "select distinct on (r.report_date) r.report_date, r.revision, r.weather, "
            "(select coalesce(sum(c.headcount), 0) from gba.construction_daily_report_crew c "
            "where c.tenant_id = r.tenant_id and c.project_id = r.project_id "
            "and c.report_date = r.report_date and c.revision = r.revision), "
            "(select count(*) from gba.construction_daily_report_photos p "
            "where p.tenant_id = r.tenant_id and p.project_id = r.project_id "
            "and p.report_date = r.report_date and p.revision = r.revision), r.created_at "
            "from gba.construction_daily_reports r where r.project_id = %s "
            "order by r.report_date desc, r.revision desc",
            (project_id,),
        )
    ).fetchall()
    return DailyReportList(
        project_id=project_id,
        items=[
            DailyReportSummary(
                report_date=row[0],
                revision=row[1],
                weather=row[2],
                headcount=int(row[3]),
                photo_count=int(row[4]),
                recorded_at=row[5],
            )
            for row in rows
        ],
    )


async def _check_references(conn: RuntimeConnection, body: DailyReportInput) -> None:
    """Crew companies the caller sees; photos that are image document versions."""
    parties = {item.counterparty_id for item in body.crew if item.counterparty_id is not None}
    if parties:
        found = await (
            await conn.execute(
                "select count(*) from gba.counterparties where id = any(%s)", (list(parties),)
            )
        ).fetchone()
        if found is None or int(found[0]) != len(parties):
            raise InvalidReferenceError("A crew line names an unknown counterparty", field="crew")
    for photo in body.photos:
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


def _refused(exc: CheckViolation) -> Exception | None:
    """The database's answer to a report it refused, as the error the client sees."""
    name = exc.diag.constraint_name
    if name in (
        "construction_daily_reports_sequence_check",
        "construction_daily_reports_revision_check",
        "construction_daily_report_crew_report_check",
        "construction_daily_report_photos_report_check",
    ):
        return ConstructionRevisionConflictError("The report changed since it was read")
    if name == "construction_daily_reports_date_check":
        return ConstructionFutureDateError("The date is after today on the site")
    if name == "construction_daily_report_photos_image_check":
        return InvalidReferenceError("A photo is a document version with an image", field="photos")
    return None


async def put_report(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    report_date: date,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: DailyReportInput,
) -> DailyReportView:
    """The next revision of the report of a site date (decision 5)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.daily_report", key)
    fingerprint = request_fingerprint(f"{project_id}:{report_date.isoformat()}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        saved = stored.body.get("revision")
        view = (
            await load_report(conn, project_id, report_date, saved)
            if isinstance(saved, int)
            else None
        )
        if view is None:
            raise NotFoundError("Daily report not found", project_id=str(project_id))
        return view
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("A daily report needs a contract")
    if report_date > await site_today(conn, project_id):
        raise ConstructionFutureDateError("The date is after today on the site")
    current = await _latest(conn, project_id, report_date)
    if body.expected_revision != current:
        raise ConstructionRevisionConflictError(
            "The report changed since it was read", revision=current
        )
    await _check_references(conn, body)
    revision = current + 1
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_daily_reports (tenant_id, project_id, report_date, "
                "revision, weather, notes, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (business, project_id, report_date, revision, body.weather, body.notes, user_id),
            )
            for position, member in enumerate(body.crew, start=1):
                await conn.execute(
                    "insert into gba.construction_daily_report_crew (tenant_id, project_id, "
                    "report_date, revision, position, label, headcount, counterparty_id) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        project_id,
                        report_date,
                        revision,
                        position,
                        member.label,
                        member.headcount,
                        member.counterparty_id,
                    ),
                )
            for position, photo in enumerate(body.photos, start=1):
                await conn.execute(
                    "insert into gba.construction_daily_report_photos (tenant_id, project_id, "
                    "report_date, revision, position, document_id, document_revision) "
                    "values (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        project_id,
                        report_date,
                        revision,
                        position,
                        photo.document_id,
                        photo.revision,
                    ),
                )
    except UniqueViolation as exc:
        raise ConstructionRevisionConflictError("The report changed since it was read") from exc
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("The report names an unknown record", field="crew") from exc
    except CheckViolation as exc:
        mapped = _refused(exc)
        if mapped is None:
            raise
        raise mapped from exc
    view = await load_report(conn, project_id, report_date, revision)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"revision": revision})
    return view
