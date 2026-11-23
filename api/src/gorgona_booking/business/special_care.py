"""SPECIAL-02 (ADR-0043): Consent-gated Healthcare, Veterinary, and Social Care workflows."""

from datetime import date
from typing import Any, Literal
from uuid import UUID

from psycopg import errors
from pydantic import AwareDatetime, Field, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError

CARE_MODULE = "clinical_care"

SubjectKind = Literal["human_patient", "animal_patient", "social_care_recipient"]
ConsentScope = Literal["care_records", "procedures", "medication", "sharing"]
ConsentStatus = Literal["active", "revoked"]
PlanStatus = Literal["active", "completed", "cancelled"]


class CareNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class CareConsentRequiredError(ConflictError):
    code = "CARE_CONSENT_REQUIRED"


class CareStateError(ConflictError):
    code = "CARE_STATE_INVALID"


def _check_ready() -> None:
    mod = modules.MODULES_BY_ID[CARE_MODULE]
    if not mod.enableable or not at_least(mod.readiness, modules.MINIMUM_READINESS):
        raise CareNotReadyError(
            "Clinical care module is not enabled for production writes",
            module_id=CARE_MODULE,
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


class CareSubjectInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    guardian_counterparty_id: UUID
    subject_kind: SubjectKind
    code: str
    display_name: str
    species_or_profile: str | None = None
    allergies_summary: str | None = None

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_line(value, 200)


class CareSubjectView(Strict):
    schema_version: Literal[1] = 1
    subject_id: UUID
    location_id: UUID
    guardian_counterparty_id: UUID
    subject_kind: SubjectKind
    code: str
    display_name: str
    species_or_profile: str | None
    allergies_summary: str | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class CareConsentInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    subject_id: UUID
    scope: ConsentScope
    status: ConsentStatus = "active"
    granted_by_name: str

    @field_validator("granted_by_name")
    @classmethod
    def valid_grantor(cls, value: str) -> str:
        return _clean_line(value, 200)


class CareConsentView(Strict):
    schema_version: Literal[1] = 1
    consent_id: UUID
    location_id: UUID
    subject_id: UUID
    scope: ConsentScope
    status: ConsentStatus
    granted_by_name: str
    revoked_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class CarePlanInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    subject_id: UUID
    consent_id: UUID
    title: str
    status: PlanStatus = "active"

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_line(value, 200)


class CarePlanView(Strict):
    schema_version: Literal[1] = 1
    plan_id: UUID
    location_id: UUID
    subject_id: UUID
    consent_id: UUID
    title: str
    status: PlanStatus
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class CareEncounterInput(Versioned):
    location_id: UUID
    subject_id: UUID
    consent_id: UUID
    plan_id: UUID | None = None
    encounter_date: date
    summary: str
    clinical_notes: str

    @field_validator("summary")
    @classmethod
    def valid_sum(cls, value: str) -> str:
        return _clean_line(value, 300)

    @field_validator("clinical_notes")
    @classmethod
    def valid_notes(cls, value: str) -> str:
        clean = value.strip()
        if not clean or len(clean) > 2000:
            raise ValueError("Clinical notes must be 1..2000 characters")
        return clean


class CareEncounterView(Strict):
    schema_version: Literal[1] = 1
    encounter_id: UUID
    location_id: UUID
    subject_id: UUID
    consent_id: UUID
    plan_id: UUID | None
    encounter_date: date
    summary: str
    # Redacted (None) whenever the governing consent has been revoked
    clinical_notes: str | None
    consent_active: bool
    recorded_by: UUID
    recorded_at: AwareDatetime


class CareSubjectList(Strict):
    schema_version: Literal[1] = 1
    items: list[CareSubjectView]


class CareConsentList(Strict):
    schema_version: Literal[1] = 1
    items: list[CareConsentView]


class CareEncounterList(Strict):
    schema_version: Literal[1] = 1
    items: list[CareEncounterView]


def _subject_view(r: tuple[Any, ...]) -> CareSubjectView:
    return CareSubjectView(
        subject_id=r[0],
        location_id=r[1],
        guardian_counterparty_id=r[2],
        subject_kind=r[3],
        code=str(r[4]),
        display_name=str(r[5]),
        species_or_profile=r[6],
        allergies_summary=r[7],
        revision=int(r[8]),
        recorded_by=r[9],
        recorded_at=r[10],
    )


def _consent_view(r: tuple[Any, ...]) -> CareConsentView:
    return CareConsentView(
        consent_id=r[0],
        location_id=r[1],
        subject_id=r[2],
        scope=r[3],
        status=r[4],
        granted_by_name=str(r[5]),
        revoked_at=r[6],
        revision=int(r[7]),
        recorded_by=r[8],
        recorded_at=r[9],
    )


def _plan_view(r: tuple[Any, ...]) -> CarePlanView:
    return CarePlanView(
        plan_id=r[0],
        location_id=r[1],
        subject_id=r[2],
        consent_id=r[3],
        title=str(r[4]),
        status=r[5],
        revision=int(r[6]),
        recorded_by=r[7],
        recorded_at=r[8],
    )


def _encounter_view(r: tuple[Any, ...]) -> CareEncounterView:
    active = str(r[8]) == "active"
    return CareEncounterView(
        encounter_id=r[0],
        location_id=r[1],
        subject_id=r[2],
        consent_id=r[3],
        plan_id=r[4],
        encounter_date=r[5],
        summary=str(r[6]),
        clinical_notes=str(r[7]) if active else None,
        consent_active=active,
        recorded_by=r[9],
        recorded_at=r[10],
    )


async def list_subjects(conn: RuntimeConnection, business: UUID) -> CareSubjectList:
    rows = await (
        await conn.execute(
            "select id, location_id, guardian_counterparty_id, subject_kind, code, "
            "display_name, species_or_profile, allergies_summary, revision, recorded_by, "
            "recorded_at from gba.care_subjects where tenant_id = %s order by code",
            (business,),
        )
    ).fetchall()
    return CareSubjectList(items=[_subject_view(r) for r in rows])


async def list_consents(conn: RuntimeConnection, business: UUID) -> CareConsentList:
    rows = await (
        await conn.execute(
            "select id, location_id, subject_id, scope, status, granted_by_name, revoked_at, "
            "revision, recorded_by, recorded_at from gba.care_consents "
            "where tenant_id = %s order by recorded_at desc, id desc",
            (business,),
        )
    ).fetchall()
    return CareConsentList(items=[_consent_view(r) for r in rows])


async def save_subject(
    conn: RuntimeConnection,
    business: UUID,
    subject_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CareSubjectInput,
) -> CareSubjectView:
    _check_ready()
    await require_module(conn, business, CARE_MODULE)
    scope = IdempotencyScope(business, actor, "care.subject.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"subject_id": str(subject_id), **body.model_dump(mode="json")}),
        CareSubjectView,
    )
    if replay is not None:
        return replay

    async with module_writes(CARE_MODULE):
        existing = await (
            await conn.execute(
                "select revision from gba.care_subjects where tenant_id = %s and id = %s "
                "for update",
                (business, subject_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise CareStateError("Care subject does not exist yet")
                await conn.execute(
                    "insert into gba.care_subjects ("
                    "id, tenant_id, location_id, guardian_counterparty_id, subject_kind, code, "
                    "display_name, species_or_profile, allergies_summary, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        subject_id,
                        business,
                        body.location_id,
                        body.guardian_counterparty_id,
                        body.subject_kind,
                        body.code,
                        body.display_name,
                        body.species_or_profile,
                        body.allergies_summary,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise CareStateError("Care subject revision mismatch")
                await conn.execute(
                    "update gba.care_subjects set display_name = %s, species_or_profile = %s, "
                    "allergies_summary = %s, revision = revision + 1, recorded_by = %s, "
                    "recorded_at = now() where tenant_id = %s and id = %s",
                    (
                        body.display_name,
                        body.species_or_profile,
                        body.allergies_summary,
                        user_id,
                        business,
                        subject_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise CareStateError("Care subject code already exists") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced location or guardian not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, guardian_counterparty_id, subject_kind, code, "
                "display_name, species_or_profile, allergies_summary, revision, recorded_by, "
                "recorded_at from gba.care_subjects where tenant_id = %s and id = %s",
                (business, subject_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _subject_view(row)
        await commands.complete(conn, scope, view)
        return view


async def save_consent(
    conn: RuntimeConnection,
    business: UUID,
    consent_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CareConsentInput,
) -> CareConsentView:
    _check_ready()
    await require_module(conn, business, CARE_MODULE)
    scope = IdempotencyScope(business, actor, "care.consent.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"consent_id": str(consent_id), **body.model_dump(mode="json")}),
        CareConsentView,
    )
    if replay is not None:
        return replay

    async with module_writes(CARE_MODULE):
        existing = await (
            await conn.execute(
                "select revision, status from gba.care_consents where tenant_id = %s and id = %s "
                "for update",
                (business, consent_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise CareStateError("Care consent does not exist yet")
                await conn.execute(
                    "insert into gba.care_consents ("
                    "id, tenant_id, location_id, subject_id, scope, status, granted_by_name, "
                    "revoked_at, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, "
                    "case when %s = 'revoked' then now() else null end, 1, %s)",
                    (
                        consent_id,
                        business,
                        body.location_id,
                        body.subject_id,
                        body.scope,
                        body.status,
                        body.granted_by_name,
                        body.status,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise CareStateError("Care consent revision mismatch")
                if str(existing[1]) == "revoked":
                    raise CareStateError("Revoked care consent cannot be reactivated")
                await conn.execute(
                    "update gba.care_consents set status = %s, "
                    "revoked_at = case when %s = 'revoked' then now() else null end, "
                    "revision = revision + 1, recorded_by = %s, recorded_at = now() "
                    "where tenant_id = %s and id = %s",
                    (body.status, body.status, user_id, business, consent_id),
                )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced care subject not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, subject_id, scope, status, granted_by_name, revoked_at, "
                "revision, recorded_by, recorded_at from gba.care_consents "
                "where tenant_id = %s and id = %s",
                (business, consent_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _consent_view(row)
        await commands.complete(conn, scope, view)
        return view


async def _require_active_consent(
    conn: RuntimeConnection,
    business: UUID,
    location_id: UUID,
    subject_id: UUID,
    consent_id: UUID,
) -> None:
    c = await (
        await conn.execute(
            "select status from gba.care_consents "
            "where tenant_id = %s and location_id = %s and subject_id = %s and id = %s for share",
            (business, location_id, subject_id, consent_id),
        )
    ).fetchone()
    if c is None or str(c[0]) != "active":
        raise CareConsentRequiredError(
            "An active, unrevoked consent is required for clinical or care records"
        )


async def save_plan(
    conn: RuntimeConnection,
    business: UUID,
    plan_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CarePlanInput,
) -> CarePlanView:
    _check_ready()
    await require_module(conn, business, CARE_MODULE)
    scope = IdempotencyScope(business, actor, "care.plan.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"plan_id": str(plan_id), **body.model_dump(mode="json")}),
        CarePlanView,
    )
    if replay is not None:
        return replay

    await _require_active_consent(
        conn, business, body.location_id, body.subject_id, body.consent_id
    )
    async with module_writes(CARE_MODULE):
        existing = await (
            await conn.execute(
                "select revision from gba.care_plans where tenant_id = %s and id = %s for update",
                (business, plan_id),
            )
        ).fetchone()
        if existing is None:
            if body.expected_revision != 0:
                raise CareStateError("Care plan does not exist yet")
            await conn.execute(
                "insert into gba.care_plans ("
                "id, tenant_id, location_id, subject_id, consent_id, title, status, revision, "
                "recorded_by) values (%s, %s, %s, %s, %s, %s, %s, 1, %s)",
                (
                    plan_id,
                    business,
                    body.location_id,
                    body.subject_id,
                    body.consent_id,
                    body.title,
                    body.status,
                    user_id,
                ),
            )
        else:
            if body.expected_revision != int(existing[0]):
                raise CareStateError("Care plan revision mismatch")
            await conn.execute(
                "update gba.care_plans set title = %s, status = %s, revision = revision + 1, "
                "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
                (body.title, body.status, user_id, business, plan_id),
            )
        row = await (
            await conn.execute(
                "select id, location_id, subject_id, consent_id, title, status, revision, "
                "recorded_by, recorded_at from gba.care_plans where tenant_id = %s and id = %s",
                (business, plan_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _plan_view(row)
        await commands.complete(conn, scope, view)
        return view


async def record_encounter(
    conn: RuntimeConnection,
    business: UUID,
    encounter_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CareEncounterInput,
) -> CareEncounterView:
    _check_ready()
    await require_module(conn, business, CARE_MODULE)
    scope = IdempotencyScope(business, actor, "care.encounter.record", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"encounter_id": str(encounter_id), **body.model_dump(mode="json")}),
        CareEncounterView,
    )
    if replay is not None:
        return replay

    await _require_active_consent(
        conn, business, body.location_id, body.subject_id, body.consent_id
    )
    async with module_writes(CARE_MODULE):
        try:
            await conn.execute(
                "insert into gba.care_encounters ("
                "id, tenant_id, location_id, subject_id, consent_id, plan_id, encounter_date, "
                "summary, clinical_notes, recorded_by"
                ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    encounter_id,
                    business,
                    body.location_id,
                    body.subject_id,
                    body.consent_id,
                    body.plan_id,
                    body.encounter_date,
                    body.summary,
                    body.clinical_notes,
                    user_id,
                ),
            )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced care plan not found") from exc

        row = await (
            await conn.execute(
                "select e.id, e.location_id, e.subject_id, e.consent_id, e.plan_id, "
                "e.encounter_date, e.summary, e.clinical_notes, c.status, e.recorded_by, "
                "e.recorded_at from gba.care_encounters e "
                "join gba.care_consents c on c.tenant_id = e.tenant_id and c.id = e.consent_id "
                "where e.tenant_id = %s and e.id = %s",
                (business, encounter_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _encounter_view(row)
        await commands.complete(conn, scope, view)
        return view


async def list_encounters(
    conn: RuntimeConnection,
    business: UUID,
    *,
    subject_id: UUID | None = None,
) -> CareEncounterList:
    await require_module(conn, business, CARE_MODULE)
    rows = await (
        await conn.execute(
            "select e.id, e.location_id, e.subject_id, e.consent_id, e.plan_id, "
            "e.encounter_date, e.summary, e.clinical_notes, c.status, e.recorded_by, "
            "e.recorded_at from gba.care_encounters e "
            "join gba.care_consents c on c.tenant_id = e.tenant_id and c.id = e.consent_id "
            "where e.tenant_id = %s and (%s::uuid is null or e.subject_id = %s) "
            "order by e.encounter_date desc, e.id",
            (business, subject_id, subject_id),
        )
    ).fetchall()
    return CareEncounterList(items=[_encounter_view(r) for r in rows])
