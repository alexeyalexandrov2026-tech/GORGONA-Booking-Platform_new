"""PRO-01 Slice 3 (ADR-0038): versioned billable time tracking and recurring service schedules."""

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID, uuid7

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.projects_matters import (
    PROJECTS_MODULE,
    ProjectsRevisionError,
    ProjectsStateError,
    _check_ready,
    _clean_multiline,
    _clean_single_line,
    _require_lead_if_restricted,
    _require_matter_visible,
)
from gorgona_booking.business.projects_work import _require_writer_if_restricted
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError

TimeEntryStatus = Literal["draft", "submitted", "approved", "billed", "rejected"]
TimeDecision = Literal["approve", "reject"]
RecurringCadence = Literal["weekly", "biweekly", "monthly", "quarterly"]
RecurringStatus = Literal["active", "paused", "ended"]
RunBillingStatus = Literal["unbilled", "billed"]

_MAX_REVISION = 2_147_483_647


def compute_time_amount_minor(
    *, duration_minutes: int, hourly_rate_minor: int, billable: bool
) -> int:
    if not billable:
        return 0
    raw = (Decimal(duration_minutes) * Decimal(hourly_rate_minor)) / Decimal(60)
    return int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def advance_period(start: date, cadence: RecurringCadence) -> tuple[date, date]:
    """Return (period_end_inclusive, next_run_date) for one cycle starting on `start`."""
    if cadence == "weekly":
        nxt = start + timedelta(days=7)
        return nxt - timedelta(days=1), nxt
    if cadence == "biweekly":
        nxt = start + timedelta(days=14)
        return nxt - timedelta(days=1), nxt
    months = 1 if cadence == "monthly" else 3
    total_months = (start.month - 1) + months
    year = start.year + total_months // 12
    month = (total_months % 12) + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    nxt = date(year, month, day)
    return nxt - timedelta(days=1), nxt


class TimeEntryInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    stage_id: UUID | None = None
    task_id: UUID | None = None
    work_date: date
    duration_minutes: StrictInt = Field(ge=1, le=1440)
    hourly_rate_minor: StrictInt = Field(ge=0)
    billable: bool = True
    description: str
    submit: bool = False

    @field_validator("description")
    @classmethod
    def valid_description(cls, value: str) -> str:
        return _clean_multiline(value, 2000)


class TimeEntryDecisionInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION - 1)
    decision: TimeDecision


class TimeEntryView(Strict):
    schema_version: Literal[1] = 1
    time_entry_id: UUID
    matter_id: UUID
    location_id: UUID
    stage_id: UUID | None
    task_id: UUID | None
    staff_user_id: UUID
    work_date: date
    duration_minutes: int
    hourly_rate_minor: int
    currency: str
    billable: bool
    amount_minor: int
    description: str
    status: TimeEntryStatus
    decided_by: UUID | None
    decided_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class TimeEntryList(Strict):
    schema_version: Literal[1] = 1
    items: list[TimeEntryView]
    next_after: UUID | None = None


class TimeEntryRevisionView(Strict):
    schema_version: Literal[1] = 1
    time_entry_id: UUID
    revision: int
    matter_id: UUID
    location_id: UUID
    stage_id: UUID | None
    task_id: UUID | None
    staff_user_id: UUID
    work_date: date
    duration_minutes: int
    hourly_rate_minor: int
    currency: str
    billable: bool
    amount_minor: int
    description: str
    status: TimeEntryStatus
    decided_by: UUID | None
    decided_at: AwareDatetime | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class TimeEntryRevisionList(Strict):
    schema_version: Literal[1] = 1
    items: list[TimeEntryRevisionView]


class RecurringScheduleInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    title: str
    task_template_title: str
    task_template_description: str | None = None
    default_assignee_user_id: UUID | None = None
    cadence: RecurringCadence
    next_run_date: date
    fixed_fee_minor: StrictInt = Field(ge=0)
    status: RecurringStatus = "active"

    @field_validator("title", "task_template_title")
    @classmethod
    def valid_line(cls, value: str) -> str:
        return _clean_single_line(value, 200)

    @field_validator("task_template_description")
    @classmethod
    def valid_desc(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_multiline(value, 4000)


class RecurringScheduleView(Strict):
    schema_version: Literal[1] = 1
    schedule_id: UUID
    matter_id: UUID
    location_id: UUID
    title: str
    task_template_title: str
    task_template_description: str | None
    default_assignee_user_id: UUID | None
    cadence: RecurringCadence
    next_run_date: date
    fixed_fee_minor: int
    currency: str
    status: RecurringStatus
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class RecurringScheduleList(Strict):
    schema_version: Literal[1] = 1
    items: list[RecurringScheduleView]


class RecurringRunTriggerInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION - 1)


class RecurringRunView(Strict):
    schema_version: Literal[1] = 1
    run_id: UUID
    matter_id: UUID
    location_id: UUID
    schedule_id: UUID
    period_start: date
    period_end: date
    task_id: UUID
    fee_minor: int
    currency: str
    billing_status: RunBillingStatus
    recorded_by: UUID
    recorded_at: AwareDatetime


class RecurringRunList(Strict):
    schema_version: Literal[1] = 1
    items: list[RecurringRunView]


class _TimeReceipt(Strict):
    time_entry_id: UUID


class _ScheduleReceipt(Strict):
    schedule_id: UUID


class _RunReceipt(Strict):
    run_id: UUID


_SELECT_TIME = """
select id as time_entry_id, matter_id, location_id, stage_id, task_id, staff_user_id,
       work_date, duration_minutes, hourly_rate_minor, currency, billable, amount_minor,
       description, status, decided_by, decided_at, revision, recorded_by, recorded_at
from gba.project_time_entries
where tenant_id = %s and id = %s
"""

_SELECT_SCHEDULE = """
select id as schedule_id, matter_id, location_id, title, task_template_title,
       task_template_description, default_assignee_user_id, cadence, next_run_date,
       fixed_fee_minor, currency, status, revision, recorded_by, recorded_at
from gba.project_recurring_schedules
where tenant_id = %s and id = %s
"""

_SELECT_RUN = """
select id as run_id, matter_id, location_id, schedule_id, period_start, period_end,
       task_id, fee_minor, currency, billing_status, recorded_by, recorded_at
from gba.project_recurring_runs
where tenant_id = %s and id = %s
"""


async def _matter_currency(conn: RuntimeConnection, business: UUID, matter_id: UUID) -> str:
    row = await (
        await conn.execute(
            "select currency from gba.project_matters where tenant_id = %s and id = %s",
            (business, matter_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Project matter not found")
    return str(row[0])


async def list_time_entries(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    *,
    status: TimeEntryStatus | None = None,
    after: UUID | None = None,
    limit: int = 50,
) -> TimeEntryList:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(TimeEntryView)) as cur:
        await cur.execute(
            "select id as time_entry_id, matter_id, location_id, stage_id, task_id, "
            "staff_user_id, work_date, duration_minutes, hourly_rate_minor, currency, "
            "billable, amount_minor, description, status, decided_by, decided_at, "
            "revision, recorded_by, recorded_at "
            "from gba.project_time_entries "
            "where tenant_id = %s and matter_id = %s "
            "and (%s::text is null or status = %s::text) "
            "and (%s::uuid is null or id > %s::uuid) "
            "order by id limit %s",
            (business, matter_id, status, status, after, after, limit + 1),
        )
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    items = rows[:limit]
    return TimeEntryList(items=items, next_after=items[-1].time_entry_id if has_more else None)


async def get_time_entry(
    conn: RuntimeConnection, business: UUID, matter_id: UUID, time_entry_id: UUID
) -> TimeEntryView:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(TimeEntryView)) as cur:
        await cur.execute(_SELECT_TIME, (business, time_entry_id))
        found = await cur.fetchone()
    if found is None or found.matter_id != matter_id:
        raise NotFoundError("Time entry not found")
    return found


async def list_time_entry_revisions(
    conn: RuntimeConnection, business: UUID, matter_id: UUID, time_entry_id: UUID
) -> TimeEntryRevisionList:
    await get_time_entry(conn, business, matter_id, time_entry_id)
    async with conn.cursor(row_factory=class_row(TimeEntryRevisionView)) as cur:
        await cur.execute(
            "select time_entry_id, revision, matter_id, location_id, stage_id, task_id, "
            "staff_user_id, work_date, duration_minutes, hourly_rate_minor, currency, "
            "billable, amount_minor, description, status, decided_by, decided_at, "
            "recorded_by, recorded_at "
            "from gba.project_time_entry_revisions "
            "where tenant_id = %s and time_entry_id = %s order by revision",
            (business, time_entry_id),
        )
        rows = await cur.fetchall()
    return TimeEntryRevisionList(items=rows)


async def save_time_entry(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    time_entry_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: TimeEntryInput,
) -> TimeEntryView:
    scope = IdempotencyScope(business, actor, "projects.time.save", key)
    fingerprint = commands.fingerprint(
        {
            "matter_id": str(matter_id),
            "time_entry_id": str(time_entry_id),
            "body": body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _TimeReceipt)
    if receipt is not None:
        return await get_time_entry(conn, business, matter_id, receipt.time_entry_id)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_writer_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot record time on a closed or cancelled matter")

    currency = await _matter_currency(conn, business, matter_id)
    amount_minor = compute_time_amount_minor(
        duration_minutes=body.duration_minutes,
        hourly_rate_minor=body.hourly_rate_minor,
        billable=body.billable,
    )
    target_status: TimeEntryStatus = "submitted" if body.submit else "draft"

    async with module_writes(PROJECTS_MODULE):
        existing = await (
            await conn.execute(
                "select matter_id, staff_user_id, status, revision from gba.project_time_entries "
                "where tenant_id = %s and id = %s for update",
                (business, time_entry_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise NotFoundError("Time entry not found")
                next_rev = 1
                staff_uid = user_id
                await conn.execute(
                    "insert into gba.project_time_entries "
                    "(tenant_id, id, location_id, matter_id, stage_id, task_id, staff_user_id, "
                    "work_date, duration_minutes, hourly_rate_minor, currency, billable, "
                    "amount_minor, description, status, revision, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        business,
                        time_entry_id,
                        matter_loc,
                        matter_id,
                        body.stage_id,
                        body.task_id,
                        staff_uid,
                        body.work_date,
                        body.duration_minutes,
                        body.hourly_rate_minor,
                        currency,
                        body.billable,
                        amount_minor,
                        body.description,
                        target_status,
                        user_id,
                    ),
                )
            else:
                ex_matter, ex_staff, ex_status, cur_rev = existing
                if UUID(str(ex_matter)) != matter_id:
                    raise NotFoundError("Time entry not found")
                if body.expected_revision != int(cur_rev):
                    raise ProjectsRevisionError(
                        "Time entry has changed", details={"revision": int(cur_rev)}
                    )
                if str(ex_status) in ("approved", "billed"):
                    raise ProjectsStateError("Approved or billed time entries cannot be edited")
                next_rev = int(cur_rev) + 1
                staff_uid = UUID(str(ex_staff))
                await conn.execute(
                    "update gba.project_time_entries "
                    "set stage_id = %s, task_id = %s, work_date = %s, duration_minutes = %s, "
                    "hourly_rate_minor = %s, billable = %s, amount_minor = %s, description = %s, "
                    "status = %s, decided_by = null, decided_at = null, revision = %s, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.stage_id,
                        body.task_id,
                        body.work_date,
                        body.duration_minutes,
                        body.hourly_rate_minor,
                        body.billable,
                        amount_minor,
                        body.description,
                        target_status,
                        next_rev,
                        user_id,
                        business,
                        time_entry_id,
                    ),
                )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Unknown stage or task for this matter") from exc

        await conn.execute(
            "insert into gba.project_time_entry_revisions "
            "(tenant_id, time_entry_id, revision, location_id, matter_id, stage_id, task_id, "
            "staff_user_id, work_date, duration_minutes, hourly_rate_minor, currency, billable, "
            "amount_minor, description, status, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                time_entry_id,
                next_rev,
                matter_loc,
                matter_id,
                body.stage_id,
                body.task_id,
                staff_uid,
                body.work_date,
                body.duration_minutes,
                body.hourly_rate_minor,
                currency,
                body.billable,
                amount_minor,
                body.description,
                target_status,
                user_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.time.saved",
        "project_time_entry",
        str(time_entry_id),
        {"matter_id": str(matter_id), "revision": next_rev, "status": target_status},
    )
    await commands.complete(conn, scope, _TimeReceipt(time_entry_id=time_entry_id))
    return await get_time_entry(conn, business, matter_id, time_entry_id)


async def decide_time_entry(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    time_entry_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: TimeEntryDecisionInput,
) -> TimeEntryView:
    scope = IdempotencyScope(business, actor, "projects.time.decide", key)
    fingerprint = commands.fingerprint(
        {
            "matter_id": str(matter_id),
            "time_entry_id": str(time_entry_id),
            "body": body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _TimeReceipt)
    if receipt is not None:
        return await get_time_entry(conn, business, matter_id, receipt.time_entry_id)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_lead_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot decide time entries on a closed or cancelled matter")

    target_status: TimeEntryStatus = "approved" if body.decision == "approve" else "rejected"
    decided_at = datetime.now(tz=UTC)

    async with module_writes(PROJECTS_MODULE):
        row = await (
            await conn.execute(
                "select matter_id, stage_id, task_id, staff_user_id, work_date, duration_minutes, "
                "hourly_rate_minor, currency, billable, amount_minor, "
                "description, status, revision "
                "from gba.project_time_entries where tenant_id = %s and id = %s for update",
                (business, time_entry_id),
            )
        ).fetchone()
        if row is None or UUID(str(row[0])) != matter_id:
            raise NotFoundError("Time entry not found")
        cur_status, cur_rev = str(row[11]), int(row[12])
        if body.expected_revision != cur_rev:
            raise ProjectsRevisionError("Time entry has changed", details={"revision": cur_rev})
        if cur_status != "submitted":
            raise ProjectsStateError("Only submitted time entries can be approved or rejected")
        next_rev = cur_rev + 1
        await conn.execute(
            "update gba.project_time_entries "
            "set status = %s, decided_by = %s, decided_at = %s, revision = %s, "
            "recorded_by = %s, recorded_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (target_status, user_id, decided_at, next_rev, user_id, business, time_entry_id),
        )
        await conn.execute(
            "insert into gba.project_time_entry_revisions "
            "(tenant_id, time_entry_id, revision, location_id, matter_id, stage_id, task_id, "
            "staff_user_id, work_date, duration_minutes, hourly_rate_minor, currency, billable, "
            "amount_minor, description, status, decided_by, decided_at, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                time_entry_id,
                next_rev,
                matter_loc,
                matter_id,
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                target_status,
                user_id,
                decided_at,
                user_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.time.decided",
        "project_time_entry",
        str(time_entry_id),
        {"matter_id": str(matter_id), "status": target_status, "revision": next_rev},
    )
    await commands.complete(conn, scope, _TimeReceipt(time_entry_id=time_entry_id))
    return await get_time_entry(conn, business, matter_id, time_entry_id)


async def list_recurring_schedules(
    conn: RuntimeConnection, business: UUID, matter_id: UUID
) -> RecurringScheduleList:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(RecurringScheduleView)) as cur:
        await cur.execute(
            "select id as schedule_id, matter_id, location_id, title, task_template_title, "
            "task_template_description, default_assignee_user_id, cadence, next_run_date, "
            "fixed_fee_minor, currency, status, revision, recorded_by, recorded_at "
            "from gba.project_recurring_schedules "
            "where tenant_id = %s and matter_id = %s order by id",
            (business, matter_id),
        )
        rows = await cur.fetchall()
    return RecurringScheduleList(items=rows)


async def get_recurring_schedule(
    conn: RuntimeConnection, business: UUID, matter_id: UUID, schedule_id: UUID
) -> RecurringScheduleView:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(RecurringScheduleView)) as cur:
        await cur.execute(_SELECT_SCHEDULE, (business, schedule_id))
        found = await cur.fetchone()
    if found is None or found.matter_id != matter_id:
        raise NotFoundError("Recurring schedule not found")
    return found


async def save_recurring_schedule(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    schedule_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RecurringScheduleInput,
) -> RecurringScheduleView:
    scope = IdempotencyScope(business, actor, "projects.recurring.save", key)
    fingerprint = commands.fingerprint(
        {
            "matter_id": str(matter_id),
            "schedule_id": str(schedule_id),
            "body": body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _ScheduleReceipt)
    if receipt is not None:
        return await get_recurring_schedule(conn, business, matter_id, receipt.schedule_id)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_lead_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError(
            "Cannot manage recurring schedules on a closed or cancelled matter"
        )

    if body.default_assignee_user_id is not None:
        mem = await (
            await conn.execute(
                "select location_id from gba.memberships "
                "where tenant_id = %s and user_id = %s and status = 'active'",
                (business, body.default_assignee_user_id),
            )
        ).fetchone()
        if mem is None or (mem[0] is not None and UUID(str(mem[0])) != matter_loc):
            raise InvalidReferenceError(
                "Default assignee must be an active member in this branch",
                field="default_assignee_user_id",
            )
        if access_mode == "restricted":
            acl = await (
                await conn.execute(
                    "select 1 from gba.project_matter_members "
                    "where tenant_id = %s and matter_id = %s and user_id = %s "
                    "and revoked_at is null",
                    (business, matter_id, body.default_assignee_user_id),
                )
            ).fetchone()
            if acl is None:
                raise InvalidReferenceError(
                    "Default assignee must be an active member of this restricted matter",
                    field="default_assignee_user_id",
                )

    currency = await _matter_currency(conn, business, matter_id)

    async with module_writes(PROJECTS_MODULE):
        existing = await (
            await conn.execute(
                "select matter_id, status, revision from gba.project_recurring_schedules "
                "where tenant_id = %s and id = %s for update",
                (business, schedule_id),
            )
        ).fetchone()
        if existing is None:
            if body.expected_revision != 0:
                raise NotFoundError("Recurring schedule not found")
            next_rev = 1
            await conn.execute(
                "insert into gba.project_recurring_schedules "
                "(tenant_id, id, location_id, matter_id, title, task_template_title, "
                "task_template_description, default_assignee_user_id, cadence, next_run_date, "
                "fixed_fee_minor, currency, status, revision, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                (
                    business,
                    schedule_id,
                    matter_loc,
                    matter_id,
                    body.title,
                    body.task_template_title,
                    body.task_template_description,
                    body.default_assignee_user_id,
                    body.cadence,
                    body.next_run_date,
                    body.fixed_fee_minor,
                    currency,
                    body.status,
                    user_id,
                ),
            )
        else:
            ex_matter, ex_status, cur_rev = existing
            if UUID(str(ex_matter)) != matter_id:
                raise NotFoundError("Recurring schedule not found")
            if body.expected_revision != int(cur_rev):
                raise ProjectsRevisionError(
                    "Recurring schedule has changed", details={"revision": int(cur_rev)}
                )
            if str(ex_status) == "ended" and body.status != "ended":
                raise ProjectsStateError("Ended recurring schedule cannot resume")
            next_rev = int(cur_rev) + 1
            await conn.execute(
                "update gba.project_recurring_schedules "
                "set title = %s, task_template_title = %s, task_template_description = %s, "
                "default_assignee_user_id = %s, cadence = %s, next_run_date = %s, "
                "fixed_fee_minor = %s, status = %s, revision = %s, recorded_by = %s, "
                "recorded_at = clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (
                    body.title,
                    body.task_template_title,
                    body.task_template_description,
                    body.default_assignee_user_id,
                    body.cadence,
                    body.next_run_date,
                    body.fixed_fee_minor,
                    body.status,
                    next_rev,
                    user_id,
                    business,
                    schedule_id,
                ),
            )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.recurring.saved",
        "project_recurring_schedule",
        str(schedule_id),
        {"matter_id": str(matter_id), "revision": next_rev, "status": body.status},
    )
    await commands.complete(conn, scope, _ScheduleReceipt(schedule_id=schedule_id))
    return await get_recurring_schedule(conn, business, matter_id, schedule_id)


async def list_recurring_runs(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    *,
    schedule_id: UUID | None = None,
) -> RecurringRunList:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(RecurringRunView)) as cur:
        await cur.execute(
            "select id as run_id, matter_id, location_id, schedule_id, period_start, "
            "period_end, task_id, fee_minor, currency, billing_status, recorded_by, recorded_at "
            "from gba.project_recurring_runs "
            "where tenant_id = %s and matter_id = %s "
            "and (%s::uuid is null or schedule_id = %s::uuid) "
            "order by period_start desc, id desc",
            (business, matter_id, schedule_id, schedule_id),
        )
        rows = await cur.fetchall()
    return RecurringRunList(items=rows)


async def materialize_recurring_run(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    schedule_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RecurringRunTriggerInput,
) -> RecurringRunView:
    scope = IdempotencyScope(business, actor, "projects.recurring.run", key)
    fingerprint = commands.fingerprint(
        {
            "matter_id": str(matter_id),
            "schedule_id": str(schedule_id),
            "expected_revision": body.expected_revision,
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _RunReceipt)
    if receipt is not None:
        await _require_matter_visible(conn, business, matter_id)
        async with conn.cursor(row_factory=class_row(RecurringRunView)) as cur:
            await cur.execute(_SELECT_RUN, (business, receipt.run_id))
            found = await cur.fetchone()
        if found is None or found.matter_id != matter_id:
            raise NotFoundError("Recurring run not found")
        return found

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_lead_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot run recurring schedules on a closed or cancelled matter")

    async with module_writes(PROJECTS_MODULE):
        sched = await (
            await conn.execute(
                "select matter_id, task_template_title, task_template_description, "
                "default_assignee_user_id, cadence, next_run_date, fixed_fee_minor, "
                "currency, status, revision "
                "from gba.project_recurring_schedules "
                "where tenant_id = %s and id = %s for update",
                (business, schedule_id),
            )
        ).fetchone()
        if sched is None or UUID(str(sched[0])) != matter_id:
            raise NotFoundError("Recurring schedule not found")
        (
            _sm,
            tpl_title,
            tpl_desc,
            assignee_uid,
            cadence_str,
            period_start,
            fee_minor,
            currency,
            sched_status,
            cur_rev,
        ) = sched
        if body.expected_revision != int(cur_rev):
            raise ProjectsRevisionError(
                "Recurring schedule has changed", details={"revision": int(cur_rev)}
            )
        if str(sched_status) != "active":
            raise ProjectsStateError("Only active recurring schedules can be materialized")

        period_end, next_run = advance_period(period_start, cadence_str)
        task_id = uuid7()
        run_id = uuid7()
        cycle_title = f"{tpl_title} ({period_start.isoformat()}..{period_end.isoformat()})"[:200]
        await conn.execute(
            "insert into gba.project_tasks "
            "(tenant_id, id, location_id, matter_id, title, description, assignee_user_id, "
            "priority, status, due_on, revision, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, 'normal', 'todo', %s, 1, %s)",
            (
                business,
                task_id,
                matter_loc,
                matter_id,
                cycle_title,
                tpl_desc,
                assignee_uid,
                period_end,
                user_id,
            ),
        )
        try:
            await conn.execute(
                "insert into gba.project_recurring_runs "
                "(tenant_id, id, location_id, matter_id, schedule_id, period_start, period_end, "
                "task_id, fee_minor, currency, billing_status, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'unbilled', %s)",
                (
                    business,
                    run_id,
                    matter_loc,
                    matter_id,
                    schedule_id,
                    period_start,
                    period_end,
                    task_id,
                    fee_minor,
                    currency,
                    user_id,
                ),
            )
        except errors.UniqueViolation as exc:
            raise ProjectsRevisionError(
                "This recurring period has already been materialized"
            ) from exc

        await conn.execute(
            "update gba.project_recurring_schedules "
            "set next_run_date = %s, revision = %s, recorded_by = %s, "
            "recorded_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (next_run, int(cur_rev) + 1, user_id, business, schedule_id),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.recurring.run_created",
        "project_recurring_run",
        str(run_id),
        {
            "matter_id": str(matter_id),
            "schedule_id": str(schedule_id),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "task_id": str(task_id),
        },
    )
    await commands.complete(conn, scope, _RunReceipt(run_id=run_id))
    async with conn.cursor(row_factory=class_row(RecurringRunView)) as cur:
        await cur.execute(_SELECT_RUN, (business, run_id))
        created = await cur.fetchone()
    if created is None:
        raise NotFoundError("Recurring run not found")
    return created
