"""PRO-01 Slice 2 (ADR-0038): stages, tasks, DAG dependencies, matter files, and ACL search."""

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.file_validation import ValidatedFile
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
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

StageStatus = Literal["open", "submitted", "accepted", "rejected"]
StageDecision = Literal["accept", "reject"]
TaskPriority = Literal["low", "normal", "high", "urgent"]
TaskStatus = Literal["todo", "in_progress", "blocked", "done", "cancelled"]
FileCategory = Literal["pleading", "contract", "evidence", "deliverable", "correspondence", "other"]

_MAX_REVISION = 2_147_483_647


class ProjectsDependencyError(ConflictError):
    code = "PROJECTS_DEPENDENCY_CYCLE"


class StageInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    stage_no: StrictInt = Field(ge=1, le=1000)
    title: str
    description: str | None = None
    due_on: date | None = None
    fixed_fee_minor: StrictInt | None = Field(default=None, ge=0)
    deliverable_summary: str | None = None

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_single_line(value, 200)

    @field_validator("description", "deliverable_summary")
    @classmethod
    def valid_opt_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_multiline(value, 4000)


class StageSubmitInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION - 1)
    deliverable_summary: str

    @field_validator("deliverable_summary")
    @classmethod
    def valid_summary(cls, value: str) -> str:
        return _clean_multiline(value, 4000)


class StageDecisionInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION - 1)
    decision: StageDecision


class StageView(Strict):
    schema_version: Literal[1] = 1
    stage_id: UUID
    matter_id: UUID
    location_id: UUID
    stage_no: int
    title: str
    description: str | None
    due_on: date | None
    fixed_fee_minor: int | None
    deliverable_summary: str | None
    deliverable_revision: int
    status: StageStatus
    decided_by: UUID | None
    decided_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class StageList(Strict):
    schema_version: Literal[1] = 1
    items: list[StageView]


class TaskInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    stage_id: UUID | None = None
    title: str
    description: str | None = None
    assignee_user_id: UUID | None = None
    priority: TaskPriority = "normal"
    status: TaskStatus = "todo"
    due_on: date | None = None

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_single_line(value, 200)

    @field_validator("description")
    @classmethod
    def valid_desc(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_multiline(value, 4000)


class TaskView(Strict):
    schema_version: Literal[1] = 1
    task_id: UUID
    matter_id: UUID
    location_id: UUID
    stage_id: UUID | None
    title: str
    description: str | None
    assignee_user_id: UUID | None
    priority: TaskPriority
    status: TaskStatus
    due_on: date | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class TaskList(Strict):
    schema_version: Literal[1] = 1
    items: list[TaskView]
    next_after: UUID | None = None


class TaskDependencyInput(Versioned):
    depends_on_task_id: UUID


class TaskDependencyView(Strict):
    schema_version: Literal[1] = 1
    matter_id: UUID
    task_id: UUID
    depends_on_task_id: UUID
    recorded_by: UUID
    recorded_at: AwareDatetime


class TaskDependencyList(Strict):
    schema_version: Literal[1] = 1
    items: list[TaskDependencyView]


class MatterFileView(Strict):
    schema_version: Literal[1] = 1
    file_id: UUID
    matter_id: UUID
    location_id: UUID
    stage_id: UUID | None
    task_id: UUID | None
    linked_document_id: UUID | None
    category: FileCategory
    title: str
    file_name: str
    media_type: Literal["application/pdf", "image/png", "image/jpeg"]
    byte_size: int
    sha256: str
    uploaded_by: UUID
    uploaded_at: AwareDatetime


class MatterFileList(Strict):
    schema_version: Literal[1] = 1
    items: list[MatterFileView]


class SearchHit(Strict):
    entity_type: Literal["matter", "stage", "task", "file"]
    entity_id: UUID
    matter_id: UUID
    title: str
    subtitle: str | None = None


class ProjectSearchResult(Strict):
    schema_version: Literal[1] = 1
    query: str
    matters: list[SearchHit]
    stages: list[SearchHit]
    tasks: list[SearchHit]
    files: list[SearchHit]


class _StageReceipt(Strict):
    stage_id: UUID


class _TaskReceipt(Strict):
    task_id: UUID


class _DepReceipt(Strict):
    task_id: UUID
    depends_on_task_id: UUID


class _FileReceipt(Strict):
    file_id: UUID


_SELECT_STAGE = """
select id as stage_id, matter_id, location_id, stage_no, title, description, due_on,
       fixed_fee_minor, deliverable_summary, deliverable_revision, status, decided_by,
       decided_at, revision, recorded_by, recorded_at
from gba.project_stages
where tenant_id = %s and id = %s
"""

_SELECT_TASK = """
select id as task_id, matter_id, location_id, stage_id, title, description,
       assignee_user_id, priority, status, due_on, revision, recorded_by, recorded_at
from gba.project_tasks
where tenant_id = %s and id = %s
"""

_SELECT_FILE = """
select id as file_id, matter_id, location_id, stage_id, task_id, linked_document_id,
       category, title, file_name, media_type, byte_size, sha256, uploaded_by, uploaded_at
from gba.project_matter_files
where tenant_id = %s and id = %s
"""


async def _require_writer_if_restricted(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    access_mode: str,
    user_id: UUID,
) -> None:
    if access_mode != "restricted":
        return
    row = await (
        await conn.execute(
            "select matter_role from gba.project_matter_members "
            "where tenant_id = %s and matter_id = %s and user_id = %s and revoked_at is null",
            (business, matter_id, user_id),
        )
    ).fetchone()
    if row is None or str(row[0]) == "viewer":
        raise PermissionDeniedError("Viewers have read-only access to a restricted matter")


def _escape_like(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def list_stages(conn: RuntimeConnection, business: UUID, matter_id: UUID) -> StageList:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(StageView)) as cur:
        await cur.execute(
            "select id as stage_id, matter_id, location_id, stage_no, title, description, "
            "due_on, fixed_fee_minor, deliverable_summary, deliverable_revision, status, "
            "decided_by, decided_at, revision, recorded_by, recorded_at "
            "from gba.project_stages where tenant_id = %s and matter_id = %s "
            "order by stage_no, id",
            (business, matter_id),
        )
        rows = await cur.fetchall()
    return StageList(items=rows)


async def get_stage(
    conn: RuntimeConnection, business: UUID, matter_id: UUID, stage_id: UUID
) -> StageView:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(StageView)) as cur:
        await cur.execute(_SELECT_STAGE, (business, stage_id))
        found = await cur.fetchone()
    if found is None or found.matter_id != matter_id:
        raise NotFoundError("Project stage not found")
    return found


async def save_stage(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    stage_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: StageInput,
) -> StageView:
    scope = IdempotencyScope(business, actor, "projects.stage.save", key)
    fingerprint = commands.fingerprint(
        {
            "matter_id": str(matter_id),
            "stage_id": str(stage_id),
            "body": body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _StageReceipt)
    if receipt is not None:
        return await get_stage(conn, business, matter_id, receipt.stage_id)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_lead_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot modify stages of a closed or cancelled matter")

    async with module_writes(PROJECTS_MODULE):
        existing = await (
            await conn.execute(
                "select matter_id, stage_no, status, revision from gba.project_stages "
                "where tenant_id = %s and id = %s for update",
                (business, stage_id),
            )
        ).fetchone()
        if existing is None:
            if body.expected_revision != 0:
                raise NotFoundError("Project stage not found")
            next_rev = 1
            try:
                await conn.execute(
                    "insert into gba.project_stages "
                    "(tenant_id, id, location_id, matter_id, stage_no, title, description, "
                    "due_on, fixed_fee_minor, deliverable_summary, deliverable_revision, "
                    "status, revision, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 'open', 1, %s)",
                    (
                        business,
                        stage_id,
                        matter_loc,
                        matter_id,
                        body.stage_no,
                        body.title,
                        body.description,
                        body.due_on,
                        body.fixed_fee_minor,
                        body.deliverable_summary,
                        user_id,
                    ),
                )
            except errors.UniqueViolation as exc:
                raise ProjectsRevisionError(
                    "Stage number or identifier is already used on this matter",
                    details={"stage_no": body.stage_no},
                ) from exc
        else:
            ex_matter, ex_no, ex_status, cur_rev = existing
            if UUID(str(ex_matter)) != matter_id:
                raise NotFoundError("Project stage not found")
            if body.expected_revision != int(cur_rev):
                raise ProjectsRevisionError(
                    "Project stage has changed", details={"revision": int(cur_rev)}
                )
            if int(ex_no) != body.stage_no:
                raise ProjectsStateError("Stage number cannot change")
            if str(ex_status) == "accepted":
                raise ProjectsStateError("Accepted stages cannot be edited")
            next_rev = int(cur_rev) + 1
            await conn.execute(
                "update gba.project_stages "
                "set title = %s, description = %s, due_on = %s, fixed_fee_minor = %s, "
                "deliverable_summary = %s, revision = %s, recorded_by = %s, "
                "recorded_at = clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (
                    body.title,
                    body.description,
                    body.due_on,
                    body.fixed_fee_minor,
                    body.deliverable_summary,
                    next_rev,
                    user_id,
                    business,
                    stage_id,
                ),
            )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.stage.saved",
        "project_stage",
        str(stage_id),
        {"matter_id": str(matter_id), "revision": next_rev},
    )
    await commands.complete(conn, scope, _StageReceipt(stage_id=stage_id))
    return await get_stage(conn, business, matter_id, stage_id)


async def submit_stage_deliverable(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    stage_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: StageSubmitInput,
) -> StageView:
    scope = IdempotencyScope(business, actor, "projects.stage.submit", key)
    fingerprint = commands.fingerprint(
        {
            "matter_id": str(matter_id),
            "stage_id": str(stage_id),
            "body": body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _StageReceipt)
    if receipt is not None:
        return await get_stage(conn, business, matter_id, receipt.stage_id)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    _loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_writer_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot submit deliverables on a closed or cancelled matter")

    async with module_writes(PROJECTS_MODULE):
        row = await (
            await conn.execute(
                "select matter_id, status, revision, deliverable_revision from gba.project_stages "
                "where tenant_id = %s and id = %s for update",
                (business, stage_id),
            )
        ).fetchone()
        if row is None or UUID(str(row[0])) != matter_id:
            raise NotFoundError("Project stage not found")
        cur_status, cur_rev, cur_deliv = str(row[1]), int(row[2]), int(row[3])
        if body.expected_revision != cur_rev:
            raise ProjectsRevisionError("Project stage has changed", details={"revision": cur_rev})
        if cur_status not in ("open", "rejected"):
            raise ProjectsStateError("Only open or rejected stages can be submitted")
        await conn.execute(
            "update gba.project_stages "
            "set deliverable_summary = %s, deliverable_revision = %s, status = 'submitted', "
            "decided_by = null, decided_at = null, revision = %s, recorded_by = %s, "
            "recorded_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (
                body.deliverable_summary,
                cur_deliv + 1,
                cur_rev + 1,
                user_id,
                business,
                stage_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.stage.submitted",
        "project_stage",
        str(stage_id),
        {"matter_id": str(matter_id), "deliverable_revision": cur_deliv + 1},
    )
    await commands.complete(conn, scope, _StageReceipt(stage_id=stage_id))
    return await get_stage(conn, business, matter_id, stage_id)


async def decide_stage(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    stage_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: StageDecisionInput,
) -> StageView:
    scope = IdempotencyScope(business, actor, "projects.stage.decide", key)
    fingerprint = commands.fingerprint(
        {
            "matter_id": str(matter_id),
            "stage_id": str(stage_id),
            "body": body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _StageReceipt)
    if receipt is not None:
        return await get_stage(conn, business, matter_id, receipt.stage_id)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    _loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_lead_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot decide stages on a closed or cancelled matter")

    target_status: StageStatus = "accepted" if body.decision == "accept" else "rejected"
    async with module_writes(PROJECTS_MODULE):
        row = await (
            await conn.execute(
                "select matter_id, status, revision from gba.project_stages "
                "where tenant_id = %s and id = %s for update",
                (business, stage_id),
            )
        ).fetchone()
        if row is None or UUID(str(row[0])) != matter_id:
            raise NotFoundError("Project stage not found")
        cur_status, cur_rev = str(row[1]), int(row[2])
        if body.expected_revision != cur_rev:
            raise ProjectsRevisionError("Project stage has changed", details={"revision": cur_rev})
        if cur_status != "submitted":
            raise ProjectsStateError("Only submitted stages can be accepted or rejected")
        await conn.execute(
            "update gba.project_stages "
            "set status = %s, decided_by = %s, decided_at = %s, revision = %s, "
            "recorded_by = %s, recorded_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (
                target_status,
                user_id,
                datetime.now(tz=UTC),
                cur_rev + 1,
                user_id,
                business,
                stage_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.stage.decided",
        "project_stage",
        str(stage_id),
        {"matter_id": str(matter_id), "status": target_status},
    )
    await commands.complete(conn, scope, _StageReceipt(stage_id=stage_id))
    return await get_stage(conn, business, matter_id, stage_id)


async def list_tasks(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    *,
    stage_id: UUID | None = None,
    status: TaskStatus | None = None,
    after: UUID | None = None,
    limit: int = 50,
) -> TaskList:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(TaskView)) as cur:
        await cur.execute(
            "select id as task_id, matter_id, location_id, stage_id, title, description, "
            "assignee_user_id, priority, status, due_on, revision, recorded_by, recorded_at "
            "from gba.project_tasks "
            "where tenant_id = %s and matter_id = %s "
            "and (%s::uuid is null or stage_id = %s::uuid) "
            "and (%s::text is null or status = %s::text) "
            "and (%s::uuid is null or id > %s::uuid) "
            "order by id limit %s",
            (
                business,
                matter_id,
                stage_id,
                stage_id,
                status,
                status,
                after,
                after,
                limit + 1,
            ),
        )
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    items = rows[:limit]
    return TaskList(items=items, next_after=items[-1].task_id if has_more else None)


async def get_task(
    conn: RuntimeConnection, business: UUID, matter_id: UUID, task_id: UUID
) -> TaskView:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(TaskView)) as cur:
        await cur.execute(_SELECT_TASK, (business, task_id))
        found = await cur.fetchone()
    if found is None or found.matter_id != matter_id:
        raise NotFoundError("Project task not found")
    return found


async def save_task(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    task_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: TaskInput,
) -> TaskView:
    scope = IdempotencyScope(business, actor, "projects.task.save", key)
    fingerprint = commands.fingerprint(
        {"matter_id": str(matter_id), "task_id": str(task_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _TaskReceipt)
    if receipt is not None:
        return await get_task(conn, business, matter_id, receipt.task_id)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_writer_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot modify tasks of a closed or cancelled matter")

    if body.assignee_user_id is not None:
        mem = await (
            await conn.execute(
                "select location_id from gba.memberships "
                "where tenant_id = %s and user_id = %s and status = 'active'",
                (business, body.assignee_user_id),
            )
        ).fetchone()
        if mem is None:
            raise InvalidReferenceError(
                "Assignee is not an active member of this business", field="assignee_user_id"
            )
        if mem[0] is not None and UUID(str(mem[0])) != matter_loc:
            raise InvalidReferenceError(
                "Assignee belongs to another branch", field="assignee_user_id"
            )
        if access_mode == "restricted":
            acl = await (
                await conn.execute(
                    "select 1 from gba.project_matter_members "
                    "where tenant_id = %s and matter_id = %s and user_id = %s "
                    "and revoked_at is null",
                    (business, matter_id, body.assignee_user_id),
                )
            ).fetchone()
            if acl is None:
                raise InvalidReferenceError(
                    "Assignee must be an active member of this restricted matter",
                    field="assignee_user_id",
                )

    async with module_writes(PROJECTS_MODULE):
        existing = await (
            await conn.execute(
                "select matter_id, revision from gba.project_tasks "
                "where tenant_id = %s and id = %s for update",
                (business, task_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise NotFoundError("Project task not found")
                next_rev = 1
                await conn.execute(
                    "insert into gba.project_tasks "
                    "(tenant_id, id, location_id, matter_id, stage_id, title, description, "
                    "assignee_user_id, priority, status, due_on, revision, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        business,
                        task_id,
                        matter_loc,
                        matter_id,
                        body.stage_id,
                        body.title,
                        body.description,
                        body.assignee_user_id,
                        body.priority,
                        body.status,
                        body.due_on,
                        user_id,
                    ),
                )
            else:
                ex_matter, cur_rev = existing
                if UUID(str(ex_matter)) != matter_id:
                    raise NotFoundError("Project task not found")
                if body.expected_revision != int(cur_rev):
                    raise ProjectsRevisionError(
                        "Project task has changed", details={"revision": int(cur_rev)}
                    )
                next_rev = int(cur_rev) + 1
                await conn.execute(
                    "update gba.project_tasks "
                    "set stage_id = %s, title = %s, description = %s, assignee_user_id = %s, "
                    "priority = %s, status = %s, due_on = %s, revision = %s, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.stage_id,
                        body.title,
                        body.description,
                        body.assignee_user_id,
                        body.priority,
                        body.status,
                        body.due_on,
                        next_rev,
                        user_id,
                        business,
                        task_id,
                    ),
                )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Unknown stage for this matter", field="stage_id") from exc

    await commands.audit(
        conn,
        business,
        actor,
        "projects.task.saved",
        "project_task",
        str(task_id),
        {"matter_id": str(matter_id), "status": body.status, "revision": next_rev},
    )
    await commands.complete(conn, scope, _TaskReceipt(task_id=task_id))
    return await get_task(conn, business, matter_id, task_id)


async def list_task_dependencies(
    conn: RuntimeConnection, business: UUID, matter_id: UUID, task_id: UUID
) -> TaskDependencyList:
    await get_task(conn, business, matter_id, task_id)
    async with conn.cursor(row_factory=class_row(TaskDependencyView)) as cur:
        await cur.execute(
            "select matter_id, task_id, depends_on_task_id, recorded_by, recorded_at "
            "from gba.project_task_dependencies "
            "where tenant_id = %s and matter_id = %s and task_id = %s "
            "order by depends_on_task_id",
            (business, matter_id, task_id),
        )
        rows = await cur.fetchall()
    return TaskDependencyList(items=rows)


async def add_task_dependency(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    task_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: TaskDependencyInput,
) -> TaskDependencyView:
    scope = IdempotencyScope(business, actor, "projects.task_dependency.add", key)
    fingerprint = commands.fingerprint(
        {
            "matter_id": str(matter_id),
            "task_id": str(task_id),
            "depends_on": str(body.depends_on_task_id),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _DepReceipt)
    if receipt is not None:
        await _require_matter_visible(conn, business, matter_id)
        async with conn.cursor(row_factory=class_row(TaskDependencyView)) as cur:
            await cur.execute(
                "select matter_id, task_id, depends_on_task_id, recorded_by, recorded_at "
                "from gba.project_task_dependencies "
                "where tenant_id = %s and task_id = %s and depends_on_task_id = %s",
                (business, receipt.task_id, receipt.depends_on_task_id),
            )
            found = await cur.fetchone()
        if found is None:
            raise NotFoundError("Task dependency not found")
        return found

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_writer_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot add task dependencies on a closed or cancelled matter")
    if task_id == body.depends_on_task_id:
        raise ProjectsDependencyError("A task cannot depend on itself")

    async with module_writes(PROJECTS_MODULE):
        try:
            await conn.execute(
                "insert into gba.project_task_dependencies "
                "(tenant_id, location_id, matter_id, task_id, depends_on_task_id, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s)",
                (business, matter_loc, matter_id, task_id, body.depends_on_task_id, user_id),
            )
        except errors.UniqueViolation as exc:
            raise ProjectsRevisionError("This task dependency already exists") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Both tasks must belong to this matter", field="depends_on_task_id"
            ) from exc
        except errors.CheckViolation as exc:
            raise ProjectsDependencyError("Adding this dependency creates a cycle") from exc

    await commands.audit(
        conn,
        business,
        actor,
        "projects.task_dependency.added",
        "project_task",
        str(task_id),
        {"matter_id": str(matter_id), "depends_on_task_id": str(body.depends_on_task_id)},
    )
    await commands.complete(
        conn, scope, _DepReceipt(task_id=task_id, depends_on_task_id=body.depends_on_task_id)
    )
    async with conn.cursor(row_factory=class_row(TaskDependencyView)) as cur:
        await cur.execute(
            "select matter_id, task_id, depends_on_task_id, recorded_by, recorded_at "
            "from gba.project_task_dependencies "
            "where tenant_id = %s and task_id = %s and depends_on_task_id = %s",
            (business, task_id, body.depends_on_task_id),
        )
        created = await cur.fetchone()
    if created is None:
        raise NotFoundError("Task dependency not found")
    return created


async def list_matter_files(
    conn: RuntimeConnection, business: UUID, matter_id: UUID
) -> MatterFileList:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(MatterFileView)) as cur:
        await cur.execute(
            "select id as file_id, matter_id, location_id, stage_id, task_id, "
            "linked_document_id, category, title, file_name, media_type, byte_size, "
            "sha256, uploaded_by, uploaded_at "
            "from gba.project_matter_files "
            "where tenant_id = %s and matter_id = %s order by uploaded_at desc, id desc",
            (business, matter_id),
        )
        rows = await cur.fetchall()
    return MatterFileList(items=rows)


async def get_matter_file_content(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    file_id: UUID,
    *,
    actor: str,
) -> tuple[MatterFileView, bytes]:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(MatterFileView)) as cur:
        await cur.execute(_SELECT_FILE, (business, file_id))
        meta = await cur.fetchone()
    if meta is None or meta.matter_id != matter_id:
        raise NotFoundError("Matter file not found")
    row = await (
        await conn.execute(
            "select content from gba.project_matter_files "
            "where tenant_id = %s and matter_id = %s and id = %s",
            (business, matter_id, file_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Matter file not found")
    await commands.audit(
        conn,
        business,
        actor,
        "projects.file.downloaded",
        "project_matter_file",
        str(file_id),
        {"matter_id": str(matter_id), "sha256": meta.sha256},
    )
    return meta, bytes(row[0])


async def upload_matter_file(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    file_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    title: str,
    category: FileCategory,
    stage_id: UUID | None,
    task_id: UUID | None,
    linked_document_id: UUID | None,
    validated: ValidatedFile,
    content: bytes,
) -> MatterFileView:
    cleaned_title = _clean_single_line(title, 200)
    scope = IdempotencyScope(business, actor, "projects.file.upload", key)
    fingerprint = commands.fingerprint(
        {
            "matter_id": str(matter_id),
            "file_id": str(file_id),
            "title": cleaned_title,
            "category": category,
            "stage_id": str(stage_id) if stage_id else None,
            "task_id": str(task_id) if task_id else None,
            "linked_document_id": str(linked_document_id) if linked_document_id else None,
            "sha256": validated.sha256,
            "file_name": validated.file_name,
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _FileReceipt)
    if receipt is not None:
        await _require_matter_visible(conn, business, matter_id)
        async with conn.cursor(row_factory=class_row(MatterFileView)) as cur:
            await cur.execute(_SELECT_FILE, (business, receipt.file_id))
            found = await cur.fetchone()
        if found is None or found.matter_id != matter_id:
            raise NotFoundError("Matter file not found")
        return found

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, matter_status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_writer_if_restricted(conn, business, matter_id, access_mode, user_id)
    if matter_status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot upload files to a closed or cancelled matter")

    async with module_writes(PROJECTS_MODULE):
        try:
            await conn.execute(
                "insert into gba.project_matter_files "
                "(tenant_id, id, location_id, matter_id, stage_id, task_id, linked_document_id, "
                "category, title, file_name, media_type, byte_size, sha256, content, uploaded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    file_id,
                    matter_loc,
                    matter_id,
                    stage_id,
                    task_id,
                    linked_document_id,
                    category,
                    cleaned_title,
                    validated.file_name,
                    validated.media_type,
                    validated.size_bytes,
                    validated.sha256,
                    content,
                    user_id,
                ),
            )
        except errors.UniqueViolation as exc:
            raise ProjectsRevisionError("This matter file identifier already exists") from exc
        except errors.ForeignKeyViolation as exc:
            if exc.diag.constraint_name == "project_matter_files_document_fk":
                raise InvalidReferenceError(
                    "Unknown linked document", field="linked_document_id"
                ) from exc
            raise InvalidReferenceError("Unknown stage or task for this matter") from exc

    await commands.audit(
        conn,
        business,
        actor,
        "projects.file.uploaded",
        "project_matter_file",
        str(file_id),
        {"matter_id": str(matter_id), "sha256": validated.sha256, "category": category},
    )
    await commands.complete(conn, scope, _FileReceipt(file_id=file_id))
    async with conn.cursor(row_factory=class_row(MatterFileView)) as cur:
        await cur.execute(_SELECT_FILE, (business, file_id))
        saved = await cur.fetchone()
    if saved is None:
        raise NotFoundError("Matter file not found")
    return saved


async def search_projects(
    conn: RuntimeConnection,
    business: UUID,
    *,
    query: str,
    limit: int = 25,
) -> ProjectSearchResult:
    cleaned = _clean_single_line(query, 200)
    pattern = _escape_like(cleaned)

    m_rows = await (
        await conn.execute(
            "select id, code, title from gba.project_matters "
            "where tenant_id = %s "
            "and (code ilike %s escape '\\' or title ilike %s escape '\\' "
            "or coalesce(description, '') ilike %s escape '\\') "
            "order by id limit %s",
            (business, pattern, pattern, pattern, limit),
        )
    ).fetchall()
    s_rows = await (
        await conn.execute(
            "select id, matter_id, title, status from gba.project_stages "
            "where tenant_id = %s "
            "and (title ilike %s escape '\\' or coalesce(description, '') ilike %s escape '\\' "
            "or coalesce(deliverable_summary, '') ilike %s escape '\\') "
            "order by id limit %s",
            (business, pattern, pattern, pattern, limit),
        )
    ).fetchall()
    t_rows = await (
        await conn.execute(
            "select id, matter_id, title, status from gba.project_tasks "
            "where tenant_id = %s "
            "and (title ilike %s escape '\\' or coalesce(description, '') ilike %s escape '\\') "
            "order by id limit %s",
            (business, pattern, pattern, limit),
        )
    ).fetchall()
    f_rows = await (
        await conn.execute(
            "select id, matter_id, title, file_name from gba.project_matter_files "
            "where tenant_id = %s "
            "and (title ilike %s escape '\\' or file_name ilike %s escape '\\') "
            "order by id limit %s",
            (business, pattern, pattern, limit),
        )
    ).fetchall()

    return ProjectSearchResult(
        query=cleaned,
        matters=[
            SearchHit(
                entity_type="matter",
                entity_id=UUID(str(r[0])),
                matter_id=UUID(str(r[0])),
                title=str(r[2]),
                subtitle=str(r[1]),
            )
            for r in m_rows
        ],
        stages=[
            SearchHit(
                entity_type="stage",
                entity_id=UUID(str(r[0])),
                matter_id=UUID(str(r[1])),
                title=str(r[2]),
                subtitle=str(r[3]),
            )
            for r in s_rows
        ],
        tasks=[
            SearchHit(
                entity_type="task",
                entity_id=UUID(str(r[0])),
                matter_id=UUID(str(r[1])),
                title=str(r[2]),
                subtitle=str(r[3]),
            )
            for r in t_rows
        ],
        files=[
            SearchHit(
                entity_type="file",
                entity_id=UUID(str(r[0])),
                matter_id=UUID(str(r[1])),
                title=str(r[2]),
                subtitle=str(r[3]),
            )
            for r in f_rows
        ],
    )
