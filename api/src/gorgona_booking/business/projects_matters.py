"""PRO-01 Slice 1 (ADR-0038): legal matters, projects, conflict checks, and ethical-wall ACL."""

import re
from datetime import UTC, date, datetime
from typing import Literal, Self
from uuid import UUID, uuid7

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

PROJECTS_MODULE = "projects"

MatterKind = Literal["legal_case", "project", "recurring_engagement"]
MatterStatus = Literal["intake", "conflict_check", "active", "on_hold", "closed", "cancelled"]
MatterAccessMode = Literal["branch", "restricted"]
MatterRole = Literal["lead", "contributor", "viewer", "billing"]
ConflictDecision = Literal["clear", "waived", "blocked"]

_MAX_REVISION = 2_147_483_647
_SINGLE_LINE_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_MULTILINE_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class ProjectsNotReadyError(ConflictError):
    code = "PROJECTS_NOT_READY"


class ProjectsRevisionError(ConflictError):
    code = "PROJECTS_REVISION_CONFLICT"


class ProjectsStateError(ConflictError):
    code = "PROJECTS_STATE_INVALID"


class ProjectsConflictGateError(ConflictError):
    code = "PROJECTS_CONFLICT_CHECK_REQUIRED"


class ProjectsAclError(ConflictError):
    code = "PROJECTS_ACL_CONFLICT"


def _clean_single_line(value: str, max_len: int) -> str:
    if _SINGLE_LINE_CTRL.search(value):
        raise ValueError("Control characters are not allowed")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_len:
        raise ValueError(f"Enter between 1 and {max_len} characters")
    return cleaned


def _clean_multiline(value: str, max_len: int) -> str:
    if _MULTILINE_CTRL.search(value):
        raise ValueError("Control characters are not allowed")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_len:
        raise ValueError(f"Enter between 1 and {max_len} characters")
    return cleaned


class MatterInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    location_id: UUID
    code: str
    title: str
    description: str | None = None
    kind: MatterKind
    status: MatterStatus
    access_mode: MatterAccessMode = "branch"
    client_counterparty_id: UUID
    currency: str
    budget_minor: StrictInt | None = Field(default=None, ge=0)
    opened_on: date
    due_on: date | None = None

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_single_line(value, 40)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_single_line(value, 200)

    @field_validator("description")
    @classmethod
    def valid_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_multiline(value, 4000)

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        cleaned = value.strip()
        if not _CURRENCY_RE.match(cleaned):
            raise ValueError("Currency must be a three-letter uppercase ISO code")
        return cleaned

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        if self.due_on is not None and self.due_on < self.opened_on:
            raise ValueError("Due date cannot precede opened date")
        return self


class MatterView(Strict):
    schema_version: Literal[1] = 1
    matter_id: UUID
    location_id: UUID
    code: str
    title: str
    description: str | None
    kind: MatterKind
    status: MatterStatus
    access_mode: MatterAccessMode
    client_counterparty_id: UUID
    currency: str
    budget_minor: int | None
    opened_on: date
    due_on: date | None
    closed_at: AwareDatetime | None
    revision: int
    created_by: UUID
    recorded_by: UUID
    recorded_at: AwareDatetime


class MatterList(Strict):
    schema_version: Literal[1] = 1
    items: list[MatterView]
    next_after: UUID | None = None


class MatterRevisionView(Strict):
    schema_version: Literal[1] = 1
    matter_id: UUID
    revision: int
    location_id: UUID
    code: str
    title: str
    description: str | None
    kind: MatterKind
    status: MatterStatus
    access_mode: MatterAccessMode
    client_counterparty_id: UUID
    currency: str
    budget_minor: int | None
    opened_on: date
    due_on: date | None
    closed_at: AwareDatetime | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class MatterRevisionList(Strict):
    schema_version: Literal[1] = 1
    items: list[MatterRevisionView]


class ConflictCheckInput(Versioned):
    checked_parties: str
    decision: ConflictDecision
    rationale: str

    @field_validator("checked_parties", "rationale")
    @classmethod
    def valid_text(cls, value: str) -> str:
        return _clean_multiline(value, 2000)


class ConflictCheckView(Strict):
    schema_version: Literal[1] = 1
    conflict_check_id: UUID
    matter_id: UUID
    location_id: UUID
    checked_parties: str
    decision: ConflictDecision
    rationale: str
    decided_by: UUID
    decided_at: AwareDatetime


class ConflictCheckList(Strict):
    schema_version: Literal[1] = 1
    items: list[ConflictCheckView]


class MatterMemberInput(Versioned):
    user_id: UUID
    matter_role: MatterRole


class MatterMemberView(Strict):
    schema_version: Literal[1] = 1
    member_id: UUID
    matter_id: UUID
    location_id: UUID
    user_id: UUID
    matter_role: MatterRole
    granted_by: UUID
    granted_at: AwareDatetime
    revoked_by: UUID | None
    revoked_at: AwareDatetime | None


class MatterMemberList(Strict):
    schema_version: Literal[1] = 1
    items: list[MatterMemberView]


class _MatterReceipt(Strict):
    matter_id: UUID


class _ConflictCheckReceipt(Strict):
    conflict_check_id: UUID


class _MatterMemberReceipt(Strict):
    member_id: UUID


_SELECT_MATTER = """
select id as matter_id, location_id, code, title, description, kind, status,
       access_mode, client_counterparty_id, currency, budget_minor, opened_on,
       due_on, closed_at, revision, created_by, recorded_by, recorded_at
from gba.project_matters
where tenant_id = %s and id = %s
"""

_SELECT_CONFLICT_CHECK = """
select id as conflict_check_id, matter_id, location_id, checked_parties,
       decision, rationale, decided_by, decided_at
from gba.project_conflict_checks
where tenant_id = %s and id = %s
"""

_SELECT_MEMBER = """
select id as member_id, matter_id, location_id, user_id, matter_role,
       granted_by, granted_at, revoked_by, revoked_at
from gba.project_matter_members
where tenant_id = %s and id = %s
"""


def _check_ready() -> None:
    if not modules.MODULES_BY_ID[PROJECTS_MODULE].enableable:
        raise ProjectsNotReadyError(
            "The projects module is not ready", details={"module_id": PROJECTS_MODULE}
        )


async def _ensure_location_exists(
    conn: RuntimeConnection, business: UUID, location_id: UUID
) -> None:
    found = await (
        await conn.execute(
            "select 1 from gba.locations where tenant_id = %s and id = %s",
            (business, location_id),
        )
    ).fetchone()
    if found is None:
        raise InvalidReferenceError("Unknown branch", field="location_id")


async def _require_matter_visible(
    conn: RuntimeConnection, business: UUID, matter_id: UUID, *, for_update: bool = False
) -> tuple[UUID, str, str, str]:
    sql = (
        "select location_id, kind, status, access_mode from gba.project_matters "
        "where tenant_id = %s and id = %s for update"
        if for_update
        else "select location_id, kind, status, access_mode from gba.project_matters "
        "where tenant_id = %s and id = %s"
    )
    row = await (await conn.execute(sql, (business, matter_id))).fetchone()
    if row is None:
        raise NotFoundError("Project matter not found")
    return (UUID(str(row[0])), str(row[1]), str(row[2]), str(row[3]))


async def _require_lead_if_restricted(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    access_mode: str,
    user_id: UUID,
) -> None:
    if access_mode != "restricted":
        return
    lead = await (
        await conn.execute(
            "select 1 from gba.project_matter_members "
            "where tenant_id = %s and matter_id = %s and user_id = %s "
            "and matter_role = 'lead' and revoked_at is null",
            (business, matter_id, user_id),
        )
    ).fetchone()
    if lead is None:
        raise PermissionDeniedError("Only an active matter lead may manage a restricted matter")


async def list_matters(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    kind: MatterKind | None = None,
    status: MatterStatus | None = None,
    after: UUID | None = None,
    limit: int = 50,
) -> MatterList:
    async with conn.cursor(row_factory=class_row(MatterView)) as cur:
        await cur.execute(
            "select id as matter_id, location_id, code, title, description, kind, status, "
            "access_mode, client_counterparty_id, currency, budget_minor, opened_on, "
            "due_on, closed_at, revision, created_by, recorded_by, recorded_at "
            "from gba.project_matters "
            "where tenant_id = %s "
            "and (%s::uuid is null or location_id = %s::uuid) "
            "and (%s::text is null or kind = %s::text) "
            "and (%s::text is null or status = %s::text) "
            "and (%s::uuid is null or id > %s::uuid) "
            "order by id limit %s",
            (
                business,
                location_id,
                location_id,
                kind,
                kind,
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
    return MatterList(items=items, next_after=items[-1].matter_id if has_more else None)


async def get_matter(conn: RuntimeConnection, business: UUID, matter_id: UUID) -> MatterView:
    async with conn.cursor(row_factory=class_row(MatterView)) as cur:
        await cur.execute(_SELECT_MATTER, (business, matter_id))
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Project matter not found")
    return found


async def list_matter_revisions(
    conn: RuntimeConnection, business: UUID, matter_id: UUID
) -> MatterRevisionList:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(MatterRevisionView)) as cur:
        await cur.execute(
            "select matter_id, revision, location_id, code, title, description, kind, status, "
            "access_mode, client_counterparty_id, currency, budget_minor, opened_on, "
            "due_on, closed_at, recorded_by, recorded_at "
            "from gba.project_matter_revisions "
            "where tenant_id = %s and matter_id = %s order by revision",
            (business, matter_id),
        )
        rows = await cur.fetchall()
    return MatterRevisionList(items=rows)


async def save_matter(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: MatterInput,
) -> MatterView:
    if location_scope is not None and body.location_id != location_scope:
        raise PermissionDeniedError("You can only manage matters in your assigned branch")
    scope = IdempotencyScope(business, actor, "projects.matter.save", key)
    fingerprint = commands.fingerprint(
        {"matter_id": str(matter_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _MatterReceipt)
    if receipt is not None:
        return await get_matter(conn, business, receipt.matter_id)

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    await _ensure_location_exists(conn, business, body.location_id)

    async with module_writes(PROJECTS_MODULE):
        existing = await (
            await conn.execute(
                "select location_id, kind, status, access_mode, currency, closed_at, revision "
                "from gba.project_matters where tenant_id = %s and id = %s for update",
                (business, matter_id),
            )
        ).fetchone()
        if existing is None:
            if body.expected_revision != 0:
                raise NotFoundError("Project matter not found")
            if body.kind == "legal_case" and body.status not in ("intake", "conflict_check"):
                raise ProjectsConflictGateError(
                    "A legal case must start in intake or conflict_check until conflict clearance"
                )
            next_rev = 1
            closed_at: datetime | None = (
                datetime.now(tz=UTC) if body.status in ("closed", "cancelled") else None
            )
            try:
                await conn.execute(
                    "insert into gba.project_matters "
                    "(tenant_id, id, location_id, code, title, description, kind, status, "
                    "access_mode, client_counterparty_id, currency, budget_minor, opened_on, "
                    "due_on, closed_at, revision, created_by, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, %s, 1, %s, %s)",
                    (
                        business,
                        matter_id,
                        body.location_id,
                        body.code,
                        body.title,
                        body.description,
                        body.kind,
                        body.status,
                        body.access_mode,
                        body.client_counterparty_id,
                        body.currency,
                        body.budget_minor,
                        body.opened_on,
                        body.due_on,
                        closed_at,
                        user_id,
                        user_id,
                    ),
                )
            except errors.UniqueViolation as exc:
                raise ProjectsRevisionError(
                    "Project matter identifier or code is already in use",
                    details={"code": body.code},
                ) from exc
            except errors.ForeignKeyViolation as exc:
                if exc.diag.constraint_name == "project_matters_client_fk":
                    raise InvalidReferenceError(
                        "Unknown client counterparty", field="client_counterparty_id"
                    ) from exc
                raise
            if body.access_mode == "restricted":
                await conn.execute(
                    "insert into gba.project_matter_members "
                    "(tenant_id, id, location_id, matter_id, user_id, matter_role, granted_by) "
                    "values (%s, %s, %s, %s, %s, 'lead', %s)",
                    (business, uuid7(), body.location_id, matter_id, user_id, user_id),
                )
        else:
            (
                existing_loc,
                existing_kind,
                existing_status,
                existing_access,
                existing_currency,
                existing_closed_at,
                current_rev,
            ) = existing
            await _require_lead_if_restricted(
                conn, business, matter_id, str(existing_access), user_id
            )
            if body.expected_revision != int(current_rev):
                raise ProjectsRevisionError(
                    "Project matter has changed", details={"revision": int(current_rev)}
                )
            if UUID(str(existing_loc)) != body.location_id:
                raise InvalidReferenceError(
                    "A project matter cannot move to another branch", field="location_id"
                )
            if str(existing_kind) != body.kind:
                raise ProjectsStateError("Project matter kind cannot change")
            if str(existing_currency) != body.currency:
                raise ProjectsStateError("Project matter currency cannot change")
            if str(existing_status) in ("closed", "cancelled") and body.status != str(
                existing_status
            ):
                raise ProjectsStateError("Closed or cancelled matters cannot reopen")
            if (
                body.kind == "legal_case"
                and body.status == "active"
                and str(existing_status) != "active"
            ):
                latest = await (
                    await conn.execute(
                        "select decision from gba.project_conflict_checks "
                        "where tenant_id = %s and matter_id = %s "
                        "order by decided_at desc, id desc limit 1",
                        (business, matter_id),
                    )
                ).fetchone()
                if latest is None or str(latest[0]) not in ("clear", "waived"):
                    raise ProjectsConflictGateError(
                        "Legal case requires a clear or waived conflict check before activation"
                    )
            if str(existing_access) == "branch" and body.access_mode == "restricted":
                existing_actor_member = await (
                    await conn.execute(
                        "select id, matter_role from gba.project_matter_members "
                        "where tenant_id = %s and matter_id = %s and user_id = %s "
                        "and revoked_at is null for update",
                        (business, matter_id, user_id),
                    )
                ).fetchone()
                if existing_actor_member is None:
                    await conn.execute(
                        "insert into gba.project_matter_members "
                        "(tenant_id, id, location_id, matter_id, user_id, matter_role, granted_by) "
                        "values (%s, %s, %s, %s, %s, 'lead', %s)",
                        (business, uuid7(), body.location_id, matter_id, user_id, user_id),
                    )
                elif str(existing_actor_member[1]) != "lead":
                    await conn.execute(
                        "update gba.project_matter_members set matter_role = 'lead' "
                        "where tenant_id = %s and id = %s",
                        (business, existing_actor_member[0]),
                    )
            next_rev = int(current_rev) + 1
            if body.status in ("closed", "cancelled"):
                closed_at = existing_closed_at or datetime.now(tz=UTC)
            else:
                closed_at = None
            try:
                await conn.execute(
                    "update gba.project_matters "
                    "set code = %s, title = %s, description = %s, status = %s, "
                    "access_mode = %s, client_counterparty_id = %s, budget_minor = %s, "
                    "opened_on = %s, due_on = %s, closed_at = %s, revision = %s, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.code,
                        body.title,
                        body.description,
                        body.status,
                        body.access_mode,
                        body.client_counterparty_id,
                        body.budget_minor,
                        body.opened_on,
                        body.due_on,
                        closed_at,
                        next_rev,
                        user_id,
                        business,
                        matter_id,
                    ),
                )
            except errors.UniqueViolation as exc:
                raise ProjectsRevisionError(
                    "Project matter code is already in use in this branch",
                    details={"code": body.code},
                ) from exc
            except errors.ForeignKeyViolation as exc:
                if exc.diag.constraint_name == "project_matters_client_fk":
                    raise InvalidReferenceError(
                        "Unknown client counterparty", field="client_counterparty_id"
                    ) from exc
                raise

        await conn.execute(
            "insert into gba.project_matter_revisions "
            "(tenant_id, matter_id, revision, location_id, code, title, description, kind, "
            "status, access_mode, client_counterparty_id, currency, budget_minor, opened_on, "
            "due_on, closed_at, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                matter_id,
                next_rev,
                body.location_id,
                body.code,
                body.title,
                body.description,
                body.kind,
                body.status,
                body.access_mode,
                body.client_counterparty_id,
                body.currency,
                body.budget_minor,
                body.opened_on,
                body.due_on,
                closed_at,
                user_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.matter.saved",
        "project_matter",
        str(matter_id),
        {"revision": next_rev, "status": body.status, "access_mode": body.access_mode},
    )
    await commands.complete(conn, scope, _MatterReceipt(matter_id=matter_id))
    return await get_matter(conn, business, matter_id)


async def list_conflict_checks(
    conn: RuntimeConnection, business: UUID, matter_id: UUID
) -> ConflictCheckList:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(ConflictCheckView)) as cur:
        await cur.execute(
            "select id as conflict_check_id, matter_id, location_id, checked_parties, "
            "decision, rationale, decided_by, decided_at "
            "from gba.project_conflict_checks "
            "where tenant_id = %s and matter_id = %s order by decided_at desc, id desc",
            (business, matter_id),
        )
        rows = await cur.fetchall()
    return ConflictCheckList(items=rows)


async def record_conflict_check(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ConflictCheckInput,
) -> ConflictCheckView:
    scope = IdempotencyScope(business, actor, "projects.conflict_check.record", key)
    fingerprint = commands.fingerprint(
        {"matter_id": str(matter_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _ConflictCheckReceipt)
    if receipt is not None:
        async with conn.cursor(row_factory=class_row(ConflictCheckView)) as cur:
            await cur.execute(_SELECT_CONFLICT_CHECK, (business, receipt.conflict_check_id))
            found = await cur.fetchone()
        if found is None:
            raise NotFoundError("Conflict check not found")
        return found

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_lead_if_restricted(conn, business, matter_id, access_mode, user_id)
    if status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot record a conflict check on a closed or cancelled matter")

    check_id = uuid7()
    async with module_writes(PROJECTS_MODULE):
        await conn.execute(
            "insert into gba.project_conflict_checks "
            "(tenant_id, id, location_id, matter_id, checked_parties, decision, "
            "rationale, decided_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                check_id,
                matter_loc,
                matter_id,
                body.checked_parties,
                body.decision,
                body.rationale,
                user_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.conflict_check.recorded",
        "project_conflict_check",
        str(check_id),
        {"matter_id": str(matter_id), "decision": body.decision},
    )
    await commands.complete(conn, scope, _ConflictCheckReceipt(conflict_check_id=check_id))
    async with conn.cursor(row_factory=class_row(ConflictCheckView)) as cur:
        await cur.execute(_SELECT_CONFLICT_CHECK, (business, check_id))
        created = await cur.fetchone()
    if created is None:
        raise NotFoundError("Conflict check not found")
    return created


async def list_matter_members(
    conn: RuntimeConnection, business: UUID, matter_id: UUID
) -> MatterMemberList:
    await _require_matter_visible(conn, business, matter_id)
    async with conn.cursor(row_factory=class_row(MatterMemberView)) as cur:
        await cur.execute(
            "select id as member_id, matter_id, location_id, user_id, matter_role, "
            "granted_by, granted_at, revoked_by, revoked_at "
            "from gba.project_matter_members "
            "where tenant_id = %s and matter_id = %s order by granted_at, id",
            (business, matter_id),
        )
        rows = await cur.fetchall()
    return MatterMemberList(items=rows)


async def grant_matter_member(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MatterMemberInput,
) -> MatterMemberView:
    scope = IdempotencyScope(business, actor, "projects.member.grant", key)
    fingerprint = commands.fingerprint(
        {"matter_id": str(matter_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _MatterMemberReceipt)
    if receipt is not None:
        await _require_matter_visible(conn, business, matter_id)
        async with conn.cursor(row_factory=class_row(MatterMemberView)) as cur:
            await cur.execute(_SELECT_MEMBER, (business, receipt.member_id))
            found = await cur.fetchone()
        if found is None:
            raise NotFoundError("Matter member not found")
        return found

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    matter_loc, _kind, status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_lead_if_restricted(conn, business, matter_id, access_mode, user_id)
    if status in ("closed", "cancelled"):
        raise ProjectsStateError("Cannot grant access on a closed or cancelled matter")

    target_membership = await (
        await conn.execute(
            "select location_id from gba.memberships "
            "where tenant_id = %s and user_id = %s and status = 'active'",
            (business, body.user_id),
        )
    ).fetchone()
    if target_membership is None:
        raise InvalidReferenceError(
            "User is not an active member of this business", field="user_id"
        )
    if target_membership[0] is not None and UUID(str(target_membership[0])) != matter_loc:
        raise InvalidReferenceError(
            "User membership is scoped to a different branch", field="user_id"
        )

    async with module_writes(PROJECTS_MODULE):
        existing_active = await (
            await conn.execute(
                "select id, matter_role from gba.project_matter_members "
                "where tenant_id = %s and matter_id = %s and user_id = %s "
                "and revoked_at is null for update",
                (business, matter_id, body.user_id),
            )
        ).fetchone()
        if existing_active is not None:
            member_id = UUID(str(existing_active[0]))
            old_role = str(existing_active[1])
            if access_mode == "restricted" and old_role == "lead" and body.matter_role != "lead":
                other_leads = await (
                    await conn.execute(
                        "select count(*) from gba.project_matter_members "
                        "where tenant_id = %s and matter_id = %s and matter_role = 'lead' "
                        "and revoked_at is null and id <> %s",
                        (business, matter_id, member_id),
                    )
                ).fetchone()
                if other_leads is None or int(other_leads[0]) < 1:
                    raise ProjectsAclError(
                        "A restricted matter must retain at least one active lead member"
                    )
            await conn.execute(
                "update gba.project_matter_members set matter_role = %s "
                "where tenant_id = %s and id = %s",
                (body.matter_role, business, member_id),
            )
        else:
            member_id = uuid7()
            await conn.execute(
                "insert into gba.project_matter_members "
                "(tenant_id, id, location_id, matter_id, user_id, matter_role, granted_by) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    member_id,
                    matter_loc,
                    matter_id,
                    body.user_id,
                    body.matter_role,
                    user_id,
                ),
            )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.member.granted",
        "project_matter_member",
        str(member_id),
        {"matter_id": str(matter_id), "user_id": str(body.user_id), "role": body.matter_role},
    )
    await commands.complete(conn, scope, _MatterMemberReceipt(member_id=member_id))
    async with conn.cursor(row_factory=class_row(MatterMemberView)) as cur:
        await cur.execute(_SELECT_MEMBER, (business, member_id))
        saved = await cur.fetchone()
    if saved is None:
        raise NotFoundError("Matter member not found")
    return saved


async def revoke_matter_member(
    conn: RuntimeConnection,
    business: UUID,
    matter_id: UUID,
    member_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
) -> MatterMemberView:
    scope = IdempotencyScope(business, actor, "projects.member.revoke", key)
    fingerprint = commands.fingerprint({"matter_id": str(matter_id), "member_id": str(member_id)})
    receipt = await commands.claim(conn, scope, fingerprint, _MatterMemberReceipt)
    if receipt is not None:
        await _require_matter_visible(conn, business, matter_id)
        async with conn.cursor(row_factory=class_row(MatterMemberView)) as cur:
            await cur.execute(_SELECT_MEMBER, (business, receipt.member_id))
            found = await cur.fetchone()
        if found is None:
            raise NotFoundError("Matter member not found")
        return found

    _check_ready()
    await require_module(conn, business, PROJECTS_MODULE)
    _loc, _kind, _status, access_mode = await _require_matter_visible(
        conn, business, matter_id, for_update=True
    )
    await _require_lead_if_restricted(conn, business, matter_id, access_mode, user_id)

    async with module_writes(PROJECTS_MODULE):
        row = await (
            await conn.execute(
                "select matter_role, revoked_at, user_id from gba.project_matter_members "
                "where tenant_id = %s and matter_id = %s and id = %s for update",
                (business, matter_id, member_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Matter member not found")
        member_role, revoked_at, target_user_id = str(row[0]), row[1], UUID(str(row[2]))
        if revoked_at is not None:
            raise ProjectsStateError("Matter member access is already revoked")
        if access_mode == "restricted" and member_role == "lead":
            other_leads = await (
                await conn.execute(
                    "select count(*) from gba.project_matter_members "
                    "where tenant_id = %s and matter_id = %s and matter_role = 'lead' "
                    "and revoked_at is null and id <> %s",
                    (business, matter_id, member_id),
                )
            ).fetchone()
            if other_leads is None or int(other_leads[0]) < 1:
                raise ProjectsAclError(
                    "A restricted matter must retain at least one active lead member"
                )
        await conn.execute(
            "update gba.project_matter_members "
            "set revoked_by = %s, revoked_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (user_id, business, member_id),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "projects.member.revoked",
        "project_matter_member",
        str(member_id),
        {"matter_id": str(matter_id), "user_id": str(target_user_id)},
    )
    await commands.complete(conn, scope, _MatterMemberReceipt(member_id=member_id))
    async with conn.cursor(row_factory=class_row(MatterMemberView)) as cur:
        await cur.execute(_SELECT_MEMBER, (business, member_id))
        revoked = await cur.fetchone()
    if revoked is None:
        raise NotFoundError("Matter member not found")
    return revoked
