"""SPECIAL-04 (ADR-0045): Staffing, advisory, organizations and public administration."""

from datetime import date
from typing import Any, Literal
from uuid import UUID

from psycopg import errors
from pydantic import AwareDatetime, Field, field_validator, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

CIVIC_MODULE = "public_civic"

ProgramDomain = Literal[
    "advisory_engagement",
    "staffing_requisition",
    "membership_program",
    "public_service_program",
]
ProgramStatus = Literal["active", "paused", "closed"]
CaseStatus = Literal["submitted", "in_review", "approved", "rejected", "closed"]
AllocationKind = Literal[
    "staffing_placement",
    "advisory_mandate",
    "membership_award",
    "grant_award",
    "public_permit",
]
AllocationStatus = Literal["active", "suspended", "revoked", "expired"]
AuditEventKind = Literal[
    "compliance_check",
    "conflict_disclosure",
    "review_note",
    "public_notice",
    "appeal_logged",
]


class CivicNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class CivicStateError(ConflictError):
    code = "CIVIC_STATE_INVALID"


class CivicDualReviewError(ConflictError):
    code = "CIVIC_DUAL_REVIEW_REQUIRED"


class CivicCaseNotApprovedError(ConflictError):
    code = "CIVIC_CASE_NOT_APPROVED"


def _check_ready() -> None:
    mod = modules.MODULES_BY_ID[CIVIC_MODULE]
    if not mod.enableable or not at_least(mod.readiness, modules.MINIMUM_READINESS):
        raise CivicNotReadyError(
            "Public/civic module is not enabled for production writes",
            module_id=CIVIC_MODULE,
        )


def _clean_code(value: str) -> str:
    clean = value.strip().upper()
    if len(clean) < 2 or len(clean) > 64:
        raise ValueError("Code must be 2..64 characters")
    if not clean[0].isalnum() or not all(c.isalnum() or c in "_-" for c in clean):
        raise ValueError("Code must use uppercase alphanumeric, _ or -")
    return clean


def _clean_line(value: str, max_len: int) -> str:
    clean = value.strip()
    if not clean or len(clean) > max_len or "\n" in clean or "\r" in clean:
        raise ValueError(f"Expected non-empty single-line text up to {max_len} chars")
    return clean


class CivicProgramInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    program_domain: ProgramDomain
    code: str
    title: str
    status: ProgramStatus = "active"
    requires_dual_review: bool = False

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_line(value, 200)


class CivicProgramView(Strict):
    schema_version: Literal[1] = 1
    program_id: UUID
    location_id: UUID
    program_domain: ProgramDomain
    code: str
    title: str
    status: ProgramStatus
    requires_dual_review: bool
    revision: int
    recorded_by: UUID
    updated_at: AwareDatetime


class CivicProgramList(Strict):
    schema_version: Literal[1] = 1
    items: list[CivicProgramView]


class CivicCaseInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    program_id: UUID
    subject_counterparty_id: UUID
    case_number: str
    status: CaseStatus = "submitted"
    summary: str
    decision_notes: str = ""

    @field_validator("case_number")
    @classmethod
    def valid_num(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("summary")
    @classmethod
    def valid_sum(cls, value: str) -> str:
        return _clean_line(value, 300)

    @field_validator("decision_notes")
    @classmethod
    def valid_notes(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) > 2000:
            raise ValueError("Decision notes must be <= 2000 characters")
        return clean


class CivicCaseView(Strict):
    schema_version: Literal[1] = 1
    case_id: UUID
    location_id: UUID
    program_id: UUID
    subject_counterparty_id: UUID
    case_number: str
    status: CaseStatus
    summary: str
    decision_notes: str
    submitted_by: UUID
    decided_by: UUID | None
    decided_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    updated_at: AwareDatetime


class CivicCaseList(Strict):
    schema_version: Literal[1] = 1
    items: list[CivicCaseView]


class CivicAllocationInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    case_id: UUID
    allocation_kind: AllocationKind
    reference_code: str
    status: AllocationStatus = "active"
    effective_from: date
    effective_until: date | None = None

    @field_validator("reference_code")
    @classmethod
    def valid_ref(cls, value: str) -> str:
        return _clean_code(value)

    @model_validator(mode="after")
    def valid_dates(self) -> CivicAllocationInput:
        if self.effective_until is not None and self.effective_until < self.effective_from:
            raise ValueError("effective_until must be on or after effective_from")
        return self


class CivicAllocationView(Strict):
    schema_version: Literal[1] = 1
    allocation_id: UUID
    location_id: UUID
    case_id: UUID
    allocation_kind: AllocationKind
    reference_code: str
    status: AllocationStatus
    effective_from: date
    effective_until: date | None
    revision: int
    recorded_by: UUID
    updated_at: AwareDatetime


class CivicAllocationList(Strict):
    schema_version: Literal[1] = 1
    items: list[CivicAllocationView]


class CivicAuditEventInput(Versioned):
    location_id: UUID
    case_id: UUID
    event_kind: AuditEventKind
    details: str

    @field_validator("details")
    @classmethod
    def valid_details(cls, value: str) -> str:
        clean = value.strip()
        if not clean or len(clean) > 2000:
            raise ValueError("Event details must be 1..2000 characters")
        return clean


class CivicAuditEventView(Strict):
    schema_version: Literal[1] = 1
    event_id: UUID
    location_id: UUID
    case_id: UUID
    event_kind: AuditEventKind
    details: str
    recorded_by: UUID
    created_at: AwareDatetime


class CivicAuditEventList(Strict):
    schema_version: Literal[1] = 1
    items: list[CivicAuditEventView]


def _program_view(r: tuple[Any, ...]) -> CivicProgramView:
    return CivicProgramView(
        program_id=r[0],
        location_id=r[1],
        program_domain=r[2],
        code=str(r[3]),
        title=str(r[4]),
        status=r[5],
        requires_dual_review=bool(r[6]),
        revision=int(r[7]),
        recorded_by=r[8],
        updated_at=r[9],
    )


def _case_view(r: tuple[Any, ...]) -> CivicCaseView:
    return CivicCaseView(
        case_id=r[0],
        location_id=r[1],
        program_id=r[2],
        subject_counterparty_id=r[3],
        case_number=str(r[4]),
        status=r[5],
        summary=str(r[6]),
        decision_notes=str(r[7]),
        submitted_by=r[8],
        decided_by=r[9],
        decided_at=r[10],
        revision=int(r[11]),
        recorded_by=r[12],
        updated_at=r[13],
    )


def _allocation_view(r: tuple[Any, ...]) -> CivicAllocationView:
    return CivicAllocationView(
        allocation_id=r[0],
        location_id=r[1],
        case_id=r[2],
        allocation_kind=r[3],
        reference_code=str(r[4]),
        status=r[5],
        effective_from=r[6],
        effective_until=r[7],
        revision=int(r[8]),
        recorded_by=r[9],
        updated_at=r[10],
    )


def _event_view(r: tuple[Any, ...]) -> CivicAuditEventView:
    return CivicAuditEventView(
        event_id=r[0],
        location_id=r[1],
        case_id=r[2],
        event_kind=r[3],
        details=str(r[4]),
        recorded_by=r[5],
        created_at=r[6],
    )


async def list_programs(conn: RuntimeConnection, business: UUID) -> CivicProgramList:
    rows = await (
        await conn.execute(
            "select id, location_id, program_domain, code, title, status, "
            "requires_dual_review, revision, recorded_by, updated_at "
            "from gba.civic_programs where tenant_id = %s order by code",
            (business,),
        )
    ).fetchall()
    return CivicProgramList(items=[_program_view(r) for r in rows])


async def save_program(
    conn: RuntimeConnection,
    business: UUID,
    program_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CivicProgramInput,
) -> CivicProgramView:
    _check_ready()
    await require_module(conn, business, CIVIC_MODULE)
    scope = IdempotencyScope(business, actor, "civic.program.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"program_id": str(program_id), **body.model_dump(mode="json")}),
        CivicProgramView,
    )
    if replay is not None:
        return replay

    async with module_writes(CIVIC_MODULE):
        existing = await (
            await conn.execute(
                "select revision from gba.civic_programs where tenant_id = %s and id = %s "
                "for update",
                (business, program_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise CivicStateError("Civic program does not exist yet")
                await conn.execute(
                    "insert into gba.civic_programs ("
                    "id, tenant_id, location_id, program_domain, code, title, status, "
                    "requires_dual_review, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        program_id,
                        business,
                        body.location_id,
                        body.program_domain,
                        body.code,
                        body.title,
                        body.status,
                        body.requires_dual_review,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise CivicStateError("Civic program revision mismatch")
                await conn.execute(
                    "update gba.civic_programs set title = %s, status = %s, "
                    "requires_dual_review = %s, revision = revision + 1, "
                    "recorded_by = %s, updated_at = now() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.title,
                        body.status,
                        body.requires_dual_review,
                        user_id,
                        business,
                        program_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise CivicStateError("Program code already exists in branch") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced location not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, program_domain, code, title, status, "
                "requires_dual_review, revision, recorded_by, updated_at "
                "from gba.civic_programs where tenant_id = %s and id = %s",
                (business, program_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _program_view(row)
        await commands.complete(conn, scope, view)
        return view


async def list_cases(
    conn: RuntimeConnection,
    business: UUID,
    *,
    program_id: UUID | None = None,
) -> CivicCaseList:
    if program_id is not None:
        rows = await (
            await conn.execute(
                "select id, location_id, program_id, subject_counterparty_id, case_number, "
                "status, summary, decision_notes, submitted_by, decided_by, decided_at, "
                "revision, recorded_by, updated_at from gba.civic_cases "
                "where tenant_id = %s and program_id = %s order by created_at desc, id desc",
                (business, program_id),
            )
        ).fetchall()
    else:
        rows = await (
            await conn.execute(
                "select id, location_id, program_id, subject_counterparty_id, case_number, "
                "status, summary, decision_notes, submitted_by, decided_by, decided_at, "
                "revision, recorded_by, updated_at from gba.civic_cases "
                "where tenant_id = %s order by created_at desc, id desc",
                (business,),
            )
        ).fetchall()
    return CivicCaseList(items=[_case_view(r) for r in rows])


async def save_case(
    conn: RuntimeConnection,
    business: UUID,
    case_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CivicCaseInput,
) -> CivicCaseView:
    _check_ready()
    await require_module(conn, business, CIVIC_MODULE)
    scope = IdempotencyScope(business, actor, "civic.case.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"case_id": str(case_id), **body.model_dump(mode="json")}),
        CivicCaseView,
    )
    if replay is not None:
        return replay

    async with module_writes(CIVIC_MODULE):
        prog = await (
            await conn.execute(
                "select status, requires_dual_review from gba.civic_programs "
                "where tenant_id = %s and location_id = %s and id = %s for share",
                (business, body.location_id, body.program_id),
            )
        ).fetchone()
        if prog is None:
            raise NotFoundError("Civic program not found in branch")
        prog_status, dual_review = str(prog[0]), bool(prog[1])

        existing = await (
            await conn.execute(
                "select revision, status, submitted_by from gba.civic_cases "
                "where tenant_id = %s and id = %s for update",
                (business, case_id),
            )
        ).fetchone()
        is_decision = body.status in ("approved", "rejected")
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise CivicStateError("Civic case does not exist yet")
                if prog_status == "closed":
                    raise CivicStateError("Cannot open a case under a closed program")
                if dual_review and body.status == "approved":
                    raise CivicDualReviewError(
                        "Dual-review program requires a second reviewer to approve a case"
                    )
                await conn.execute(
                    "insert into gba.civic_cases ("
                    "id, tenant_id, location_id, program_id, subject_counterparty_id, "
                    "case_number, status, summary, decision_notes, submitted_by, "
                    "decided_by, decided_at, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "case when %s then %s else null end, "
                    "case when %s then now() else null end, 1, %s)",
                    (
                        case_id,
                        business,
                        body.location_id,
                        body.program_id,
                        body.subject_counterparty_id,
                        body.case_number,
                        body.status,
                        body.summary,
                        body.decision_notes,
                        user_id,
                        is_decision,
                        user_id,
                        is_decision,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise CivicStateError("Civic case revision mismatch")
                prev_status, submitted_by = str(existing[1]), existing[2]
                if prev_status in ("rejected", "closed"):
                    raise CivicStateError("Terminal case cannot be modified")
                if dual_review and body.status == "approved" and user_id == submitted_by:
                    raise CivicDualReviewError(
                        "Submitter cannot self-approve a case in a dual-review program"
                    )
                await conn.execute(
                    "update gba.civic_cases set status = %s, summary = %s, decision_notes = %s, "
                    "decided_by = case when %s then %s else decided_by end, "
                    "decided_at = case when %s then now() else decided_at end, "
                    "revision = revision + 1, recorded_by = %s, updated_at = now() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.status,
                        body.summary,
                        body.decision_notes,
                        is_decision,
                        user_id,
                        is_decision,
                        user_id,
                        business,
                        case_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise CivicStateError("Case number already exists in branch") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced program or subject not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, program_id, subject_counterparty_id, case_number, "
                "status, summary, decision_notes, submitted_by, decided_by, decided_at, "
                "revision, recorded_by, updated_at from gba.civic_cases "
                "where tenant_id = %s and id = %s",
                (business, case_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _case_view(row)
        await commands.complete(conn, scope, view)
        return view


async def list_allocations(
    conn: RuntimeConnection,
    business: UUID,
    *,
    case_id: UUID | None = None,
) -> CivicAllocationList:
    if case_id is not None:
        rows = await (
            await conn.execute(
                "select id, location_id, case_id, allocation_kind, reference_code, status, "
                "effective_from, effective_until, revision, recorded_by, updated_at "
                "from gba.civic_allocations "
                "where tenant_id = %s and case_id = %s order by effective_from desc, id desc",
                (business, case_id),
            )
        ).fetchall()
    else:
        rows = await (
            await conn.execute(
                "select id, location_id, case_id, allocation_kind, reference_code, status, "
                "effective_from, effective_until, revision, recorded_by, updated_at "
                "from gba.civic_allocations "
                "where tenant_id = %s order by effective_from desc, id desc",
                (business,),
            )
        ).fetchall()
    return CivicAllocationList(items=[_allocation_view(r) for r in rows])


async def save_allocation(
    conn: RuntimeConnection,
    business: UUID,
    allocation_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CivicAllocationInput,
) -> CivicAllocationView:
    _check_ready()
    await require_module(conn, business, CIVIC_MODULE)
    scope = IdempotencyScope(business, actor, "civic.allocation.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"allocation_id": str(allocation_id), **body.model_dump(mode="json")}),
        CivicAllocationView,
    )
    if replay is not None:
        return replay

    async with module_writes(CIVIC_MODULE):
        case_row = await (
            await conn.execute(
                "select status from gba.civic_cases "
                "where tenant_id = %s and location_id = %s and id = %s for share",
                (business, body.location_id, body.case_id),
            )
        ).fetchone()
        if case_row is None:
            raise NotFoundError("Civic case not found in branch")

        existing = await (
            await conn.execute(
                "select revision from gba.civic_allocations "
                "where tenant_id = %s and id = %s for update",
                (business, allocation_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise CivicStateError("Allocation does not exist yet")
                if str(case_row[0]) != "approved":
                    raise CivicCaseNotApprovedError(
                        "Cannot issue allocation until parent case is approved"
                    )
                await conn.execute(
                    "insert into gba.civic_allocations ("
                    "id, tenant_id, location_id, case_id, allocation_kind, reference_code, "
                    "status, effective_from, effective_until, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        allocation_id,
                        business,
                        body.location_id,
                        body.case_id,
                        body.allocation_kind,
                        body.reference_code,
                        body.status,
                        body.effective_from,
                        body.effective_until,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise CivicStateError("Allocation revision mismatch")
                await conn.execute(
                    "update gba.civic_allocations set status = %s, effective_until = %s, "
                    "revision = revision + 1, recorded_by = %s, updated_at = now() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.status,
                        body.effective_until,
                        user_id,
                        business,
                        allocation_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise CivicStateError("Allocation reference code already exists in branch") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced case not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, case_id, allocation_kind, reference_code, status, "
                "effective_from, effective_until, revision, recorded_by, updated_at "
                "from gba.civic_allocations where tenant_id = %s and id = %s",
                (business, allocation_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _allocation_view(row)
        await commands.complete(conn, scope, view)
        return view


async def list_audit_events(
    conn: RuntimeConnection,
    business: UUID,
    *,
    case_id: UUID | None = None,
) -> CivicAuditEventList:
    if case_id is not None:
        rows = await (
            await conn.execute(
                "select id, location_id, case_id, event_kind, details, recorded_by, created_at "
                "from gba.civic_audit_events "
                "where tenant_id = %s and case_id = %s order by created_at desc, id desc",
                (business, case_id),
            )
        ).fetchall()
    else:
        rows = await (
            await conn.execute(
                "select id, location_id, case_id, event_kind, details, recorded_by, created_at "
                "from gba.civic_audit_events "
                "where tenant_id = %s order by created_at desc, id desc",
                (business,),
            )
        ).fetchall()
    return CivicAuditEventList(items=[_event_view(r) for r in rows])


async def record_audit_event(
    conn: RuntimeConnection,
    business: UUID,
    event_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CivicAuditEventInput,
) -> CivicAuditEventView:
    _check_ready()
    await require_module(conn, business, CIVIC_MODULE)
    scope = IdempotencyScope(business, actor, "civic.audit_event.record", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"event_id": str(event_id), **body.model_dump(mode="json")}),
        CivicAuditEventView,
    )
    if replay is not None:
        return replay

    async with module_writes(CIVIC_MODULE):
        case_row = await (
            await conn.execute(
                "select 1 from gba.civic_cases "
                "where tenant_id = %s and location_id = %s and id = %s",
                (business, body.location_id, body.case_id),
            )
        ).fetchone()
        if case_row is None:
            raise NotFoundError("Civic case not found in branch")
        try:
            await conn.execute(
                "insert into gba.civic_audit_events ("
                "id, tenant_id, location_id, case_id, event_kind, details, recorded_by"
                ") values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    event_id,
                    business,
                    body.location_id,
                    body.case_id,
                    body.event_kind,
                    body.details,
                    user_id,
                ),
            )
        except errors.UniqueViolation as exc:
            raise CivicStateError("Audit event already exists") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced case not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, case_id, event_kind, details, recorded_by, created_at "
                "from gba.civic_audit_events where tenant_id = %s and id = %s",
                (business, event_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _event_view(row)
        await commands.complete(conn, scope, view)
        return view
