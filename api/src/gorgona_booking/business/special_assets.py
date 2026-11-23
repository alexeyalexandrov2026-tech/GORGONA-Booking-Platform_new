"""SPECIAL-03 (ADR-0044): Assets, inspections, work orders and safety incidents."""

from datetime import date
from decimal import Decimal
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
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

ASSETS_MODULE = "assets"

AssetDomain = Literal[
    "agriculture_plot",
    "utility_infrastructure",
    "mining_equipment",
    "security_post",
    "facility_system",
    "environmental_site",
]
AssetStatus = Literal["active", "maintenance", "out_of_service", "decommissioned"]
InspectionKind = Literal["safety", "environmental", "patrol", "meter_reading", "preventive"]
InspectionOutcome = Literal["passed", "attention_required", "failed"]
WorkKind = Literal[
    "preventive",
    "corrective",
    "cleaning",
    "patrol_response",
    "waste_collection",
    "remediation",
]
PriorityLevel = Literal["low", "normal", "high", "critical"]
WorkStatus = Literal["open", "in_progress", "completed", "cancelled"]
IncidentKind = Literal[
    "safety_hazard",
    "environmental_spill",
    "security_breach",
    "utility_outage",
    "equipment_failure",
]
IncidentSeverity = Literal["low", "medium", "high", "critical"]
IncidentStatus = Literal["open", "contained", "resolved"]


class AssetsNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class AssetStateError(ConflictError):
    code = "ASSET_STATE_INVALID"


class AssetCriticalIncidentError(ConflictError):
    code = "ASSET_CRITICAL_INCIDENT_OPEN"


def _check_ready() -> None:
    mod = modules.MODULES_BY_ID[ASSETS_MODULE]
    if not mod.enableable or not at_least(mod.readiness, modules.MINIMUM_READINESS):
        raise AssetsNotReadyError(
            "Assets module is not enabled for production writes",
            module_id=ASSETS_MODULE,
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


class ManagedAssetInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    owner_counterparty_id: UUID | None = None
    asset_domain: AssetDomain
    code: str
    name: str
    status: AssetStatus = "active"
    serial_or_parcel: str = ""
    next_inspection_due: date | None = None

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_line(value, 200)

    @field_validator("serial_or_parcel")
    @classmethod
    def valid_serial(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) > 120 or "\n" in clean or "\r" in clean:
            raise ValueError("Serial or parcel must be single-line up to 120 chars")
        return clean


class ManagedAssetView(Strict):
    schema_version: Literal[1] = 1
    asset_id: UUID
    location_id: UUID
    owner_counterparty_id: UUID | None
    asset_domain: AssetDomain
    code: str
    name: str
    status: AssetStatus
    serial_or_parcel: str
    next_inspection_due: date | None
    revision: int
    recorded_by: UUID
    updated_at: AwareDatetime


class ManagedAssetList(Strict):
    schema_version: Literal[1] = 1
    items: list[ManagedAssetView]


class AssetInspectionInput(Versioned):
    location_id: UUID
    asset_id: UUID
    inspection_kind: InspectionKind
    outcome: InspectionOutcome
    meter_reading: Decimal | None = Field(default=None, ge=Decimal("0"))
    notes: str = ""

    @field_validator("notes")
    @classmethod
    def valid_notes(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) > 2000:
            raise ValueError("Inspection notes must be <= 2000 characters")
        return clean


class AssetInspectionView(Strict):
    schema_version: Literal[1] = 1
    inspection_id: UUID
    location_id: UUID
    asset_id: UUID
    inspection_kind: InspectionKind
    outcome: InspectionOutcome
    meter_reading: Decimal | None
    notes: str
    inspected_at: AwareDatetime
    recorded_by: UUID


class AssetInspectionList(Strict):
    schema_version: Literal[1] = 1
    items: list[AssetInspectionView]


class AssetWorkOrderInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    asset_id: UUID
    inspection_id: UUID | None = None
    work_kind: WorkKind
    priority: PriorityLevel = "normal"
    status: WorkStatus = "open"
    summary: str
    completion_notes: str = ""
    due_at: AwareDatetime | None = None

    @field_validator("summary")
    @classmethod
    def valid_summary(cls, value: str) -> str:
        return _clean_line(value, 300)

    @field_validator("completion_notes")
    @classmethod
    def valid_notes(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) > 2000:
            raise ValueError("Completion notes must be <= 2000 characters")
        return clean


class AssetWorkOrderView(Strict):
    schema_version: Literal[1] = 1
    work_order_id: UUID
    location_id: UUID
    asset_id: UUID
    inspection_id: UUID | None
    work_kind: WorkKind
    priority: PriorityLevel
    status: WorkStatus
    summary: str
    completion_notes: str
    due_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    updated_at: AwareDatetime


class AssetWorkOrderList(Strict):
    schema_version: Literal[1] = 1
    items: list[AssetWorkOrderView]


class AssetIncidentInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    asset_id: UUID
    incident_kind: IncidentKind
    severity: IncidentSeverity
    status: IncidentStatus = "open"
    description: str
    resolution_summary: str = ""

    @field_validator("description")
    @classmethod
    def valid_desc(cls, value: str) -> str:
        clean = value.strip()
        if not clean or len(clean) > 2000:
            raise ValueError("Incident description must be 1..2000 characters")
        return clean

    @field_validator("resolution_summary")
    @classmethod
    def valid_res(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) > 2000:
            raise ValueError("Resolution summary must be <= 2000 characters")
        return clean


class AssetIncidentView(Strict):
    schema_version: Literal[1] = 1
    incident_id: UUID
    location_id: UUID
    asset_id: UUID
    incident_kind: IncidentKind
    severity: IncidentSeverity
    status: IncidentStatus
    description: str
    resolution_summary: str
    occurred_at: AwareDatetime
    resolved_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    updated_at: AwareDatetime


class AssetIncidentList(Strict):
    schema_version: Literal[1] = 1
    items: list[AssetIncidentView]


def _asset_view(r: tuple[Any, ...]) -> ManagedAssetView:
    return ManagedAssetView(
        asset_id=r[0],
        location_id=r[1],
        owner_counterparty_id=r[2],
        asset_domain=r[3],
        code=str(r[4]),
        name=str(r[5]),
        status=r[6],
        serial_or_parcel=str(r[7]),
        next_inspection_due=r[8],
        revision=int(r[9]),
        recorded_by=r[10],
        updated_at=r[11],
    )


def _inspection_view(r: tuple[Any, ...]) -> AssetInspectionView:
    return AssetInspectionView(
        inspection_id=r[0],
        location_id=r[1],
        asset_id=r[2],
        inspection_kind=r[3],
        outcome=r[4],
        meter_reading=r[5],
        notes=str(r[6]),
        inspected_at=r[7],
        recorded_by=r[8],
    )


def _work_order_view(r: tuple[Any, ...]) -> AssetWorkOrderView:
    return AssetWorkOrderView(
        work_order_id=r[0],
        location_id=r[1],
        asset_id=r[2],
        inspection_id=r[3],
        work_kind=r[4],
        priority=r[5],
        status=r[6],
        summary=str(r[7]),
        completion_notes=str(r[8]),
        due_at=r[9],
        completed_at=r[10],
        revision=int(r[11]),
        recorded_by=r[12],
        updated_at=r[13],
    )


def _incident_view(r: tuple[Any, ...]) -> AssetIncidentView:
    return AssetIncidentView(
        incident_id=r[0],
        location_id=r[1],
        asset_id=r[2],
        incident_kind=r[3],
        severity=r[4],
        status=r[5],
        description=str(r[6]),
        resolution_summary=str(r[7]),
        occurred_at=r[8],
        resolved_at=r[9],
        revision=int(r[10]),
        recorded_by=r[11],
        updated_at=r[12],
    )


async def list_assets(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
) -> ManagedAssetList:
    if location_id is not None:
        rows = await (
            await conn.execute(
                "select id, location_id, owner_counterparty_id, asset_domain, code, name, "
                "status, serial_or_parcel, next_inspection_due, revision, recorded_by, "
                "updated_at from gba.managed_assets "
                "where tenant_id = %s and location_id = %s order by code",
                (business, location_id),
            )
        ).fetchall()
    else:
        rows = await (
            await conn.execute(
                "select id, location_id, owner_counterparty_id, asset_domain, code, name, "
                "status, serial_or_parcel, next_inspection_due, revision, recorded_by, "
                "updated_at from gba.managed_assets "
                "where tenant_id = %s order by code",
                (business,),
            )
        ).fetchall()
    return ManagedAssetList(items=[_asset_view(r) for r in rows])


async def save_asset(
    conn: RuntimeConnection,
    business: UUID,
    asset_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ManagedAssetInput,
) -> ManagedAssetView:
    _check_ready()
    await require_module(conn, business, ASSETS_MODULE)
    scope = IdempotencyScope(business, actor, "assets.asset.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"asset_id": str(asset_id), **body.model_dump(mode="json")}),
        ManagedAssetView,
    )
    if replay is not None:
        return replay

    async with module_writes(ASSETS_MODULE):
        existing = await (
            await conn.execute(
                "select revision, status from gba.managed_assets "
                "where tenant_id = %s and id = %s for update",
                (business, asset_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise AssetStateError("Managed asset does not exist yet")
                await conn.execute(
                    "insert into gba.managed_assets ("
                    "id, tenant_id, location_id, owner_counterparty_id, asset_domain, code, "
                    "name, status, serial_or_parcel, next_inspection_due, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        asset_id,
                        business,
                        body.location_id,
                        body.owner_counterparty_id,
                        body.asset_domain,
                        body.code,
                        body.name,
                        body.status,
                        body.serial_or_parcel,
                        body.next_inspection_due,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise AssetStateError("Managed asset revision mismatch")
                if body.status == "active":
                    open_crit = await (
                        await conn.execute(
                            "select 1 from gba.asset_safety_incidents "
                            "where tenant_id = %s and asset_id = %s "
                            "and severity = 'critical' and status = 'open' limit 1",
                            (business, asset_id),
                        )
                    ).fetchone()
                    if open_crit is not None:
                        raise AssetCriticalIncidentError(
                            "Cannot return asset to active while a critical incident is open"
                        )
                await conn.execute(
                    "update gba.managed_assets set owner_counterparty_id = %s, name = %s, "
                    "status = %s, serial_or_parcel = %s, next_inspection_due = %s, "
                    "revision = revision + 1, recorded_by = %s, updated_at = now() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.owner_counterparty_id,
                        body.name,
                        body.status,
                        body.serial_or_parcel,
                        body.next_inspection_due,
                        user_id,
                        business,
                        asset_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise AssetStateError("Managed asset code already exists in branch") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced location or owner not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, owner_counterparty_id, asset_domain, code, name, "
                "status, serial_or_parcel, next_inspection_due, revision, recorded_by, "
                "updated_at from gba.managed_assets where tenant_id = %s and id = %s",
                (business, asset_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _asset_view(row)
        await commands.complete(conn, scope, view)
        return view


async def list_inspections(
    conn: RuntimeConnection,
    business: UUID,
    *,
    asset_id: UUID | None = None,
) -> AssetInspectionList:
    if asset_id is not None:
        rows = await (
            await conn.execute(
                "select id, location_id, asset_id, inspection_kind, outcome, meter_reading, "
                "notes, inspected_at, recorded_by from gba.asset_inspections "
                "where tenant_id = %s and asset_id = %s order by inspected_at desc, id desc",
                (business, asset_id),
            )
        ).fetchall()
    else:
        rows = await (
            await conn.execute(
                "select id, location_id, asset_id, inspection_kind, outcome, meter_reading, "
                "notes, inspected_at, recorded_by from gba.asset_inspections "
                "where tenant_id = %s order by inspected_at desc, id desc",
                (business,),
            )
        ).fetchall()
    return AssetInspectionList(items=[_inspection_view(r) for r in rows])


async def record_inspection(
    conn: RuntimeConnection,
    business: UUID,
    inspection_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AssetInspectionInput,
) -> AssetInspectionView:
    _check_ready()
    await require_module(conn, business, ASSETS_MODULE)
    scope = IdempotencyScope(business, actor, "assets.inspection.record", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"inspection_id": str(inspection_id), **body.model_dump(mode="json")}),
        AssetInspectionView,
    )
    if replay is not None:
        return replay

    async with module_writes(ASSETS_MODULE):
        asset_row = await (
            await conn.execute(
                "select status from gba.managed_assets "
                "where tenant_id = %s and location_id = %s and id = %s",
                (business, body.location_id, body.asset_id),
            )
        ).fetchone()
        if asset_row is None:
            raise NotFoundError("Managed asset not found in branch")
        try:
            await conn.execute(
                "insert into gba.asset_inspections ("
                "id, tenant_id, location_id, asset_id, inspection_kind, outcome, "
                "meter_reading, notes, recorded_by"
                ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    inspection_id,
                    business,
                    body.location_id,
                    body.asset_id,
                    body.inspection_kind,
                    body.outcome,
                    body.meter_reading,
                    body.notes,
                    user_id,
                ),
            )
        except errors.UniqueViolation as exc:
            raise AssetStateError("Inspection record already exists") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced asset not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, asset_id, inspection_kind, outcome, meter_reading, "
                "notes, inspected_at, recorded_by from gba.asset_inspections "
                "where tenant_id = %s and id = %s",
                (business, inspection_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _inspection_view(row)
        await commands.complete(conn, scope, view)
        return view


async def list_work_orders(
    conn: RuntimeConnection,
    business: UUID,
    *,
    asset_id: UUID | None = None,
) -> AssetWorkOrderList:
    if asset_id is not None:
        rows = await (
            await conn.execute(
                "select id, location_id, asset_id, inspection_id, work_kind, priority, status, "
                "summary, completion_notes, due_at, completed_at, revision, recorded_by, "
                "updated_at from gba.asset_work_orders "
                "where tenant_id = %s and asset_id = %s order by created_at desc, id desc",
                (business, asset_id),
            )
        ).fetchall()
    else:
        rows = await (
            await conn.execute(
                "select id, location_id, asset_id, inspection_id, work_kind, priority, status, "
                "summary, completion_notes, due_at, completed_at, revision, recorded_by, "
                "updated_at from gba.asset_work_orders "
                "where tenant_id = %s order by created_at desc, id desc",
                (business,),
            )
        ).fetchall()
    return AssetWorkOrderList(items=[_work_order_view(r) for r in rows])


async def save_work_order(
    conn: RuntimeConnection,
    business: UUID,
    work_order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AssetWorkOrderInput,
) -> AssetWorkOrderView:
    _check_ready()
    await require_module(conn, business, ASSETS_MODULE)
    scope = IdempotencyScope(business, actor, "assets.work_order.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"work_order_id": str(work_order_id), **body.model_dump(mode="json")}),
        AssetWorkOrderView,
    )
    if replay is not None:
        return replay

    async with module_writes(ASSETS_MODULE):
        asset_row = await (
            await conn.execute(
                "select status from gba.managed_assets "
                "where tenant_id = %s and location_id = %s and id = %s for share",
                (business, body.location_id, body.asset_id),
            )
        ).fetchone()
        if asset_row is None:
            raise NotFoundError("Managed asset not found in branch")

        existing = await (
            await conn.execute(
                "select revision, status from gba.asset_work_orders "
                "where tenant_id = %s and id = %s for update",
                (business, work_order_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise AssetStateError("Work order does not exist yet")
                if str(asset_row[0]) == "decommissioned" and body.status in ("open", "in_progress"):
                    raise AssetStateError("Cannot open work order on a decommissioned asset")
                await conn.execute(
                    "insert into gba.asset_work_orders ("
                    "id, tenant_id, location_id, asset_id, inspection_id, work_kind, priority, "
                    "status, summary, completion_notes, due_at, completed_at, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "case when %s = 'completed' then now() else null end, 1, %s)",
                    (
                        work_order_id,
                        business,
                        body.location_id,
                        body.asset_id,
                        body.inspection_id,
                        body.work_kind,
                        body.priority,
                        body.status,
                        body.summary,
                        body.completion_notes,
                        body.due_at,
                        body.status,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise AssetStateError("Work order revision mismatch")
                if str(existing[1]) in ("completed", "cancelled"):
                    raise AssetStateError("Terminal work order cannot be modified")
                await conn.execute(
                    "update gba.asset_work_orders set priority = %s, status = %s, summary = %s, "
                    "completion_notes = %s, due_at = %s, "
                    "completed_at = case when %s = 'completed' then now() else null end, "
                    "revision = revision + 1, recorded_by = %s, updated_at = now() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.priority,
                        body.status,
                        body.summary,
                        body.completion_notes,
                        body.due_at,
                        body.status,
                        user_id,
                        business,
                        work_order_id,
                    ),
                )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced asset or inspection not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, asset_id, inspection_id, work_kind, priority, status, "
                "summary, completion_notes, due_at, completed_at, revision, recorded_by, "
                "updated_at from gba.asset_work_orders where tenant_id = %s and id = %s",
                (business, work_order_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _work_order_view(row)
        await commands.complete(conn, scope, view)
        return view


async def list_incidents(
    conn: RuntimeConnection,
    business: UUID,
    *,
    asset_id: UUID | None = None,
) -> AssetIncidentList:
    if asset_id is not None:
        rows = await (
            await conn.execute(
                "select id, location_id, asset_id, incident_kind, severity, status, description, "
                "resolution_summary, occurred_at, resolved_at, revision, recorded_by, updated_at "
                "from gba.asset_safety_incidents "
                "where tenant_id = %s and asset_id = %s order by occurred_at desc, id desc",
                (business, asset_id),
            )
        ).fetchall()
    else:
        rows = await (
            await conn.execute(
                "select id, location_id, asset_id, incident_kind, severity, status, description, "
                "resolution_summary, occurred_at, resolved_at, revision, recorded_by, updated_at "
                "from gba.asset_safety_incidents "
                "where tenant_id = %s order by occurred_at desc, id desc",
                (business,),
            )
        ).fetchall()
    return AssetIncidentList(items=[_incident_view(r) for r in rows])


async def save_incident(
    conn: RuntimeConnection,
    business: UUID,
    incident_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AssetIncidentInput,
) -> AssetIncidentView:
    _check_ready()
    await require_module(conn, business, ASSETS_MODULE)
    scope = IdempotencyScope(business, actor, "assets.incident.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"incident_id": str(incident_id), **body.model_dump(mode="json")}),
        AssetIncidentView,
    )
    if replay is not None:
        return replay

    async with module_writes(ASSETS_MODULE):
        asset_row = await (
            await conn.execute(
                "select status from gba.managed_assets "
                "where tenant_id = %s and location_id = %s and id = %s for update",
                (business, body.location_id, body.asset_id),
            )
        ).fetchone()
        if asset_row is None:
            raise NotFoundError("Managed asset not found in branch")

        existing = await (
            await conn.execute(
                "select revision, status from gba.asset_safety_incidents "
                "where tenant_id = %s and id = %s for update",
                (business, incident_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise AssetStateError("Incident does not exist yet")
                await conn.execute(
                    "insert into gba.asset_safety_incidents ("
                    "id, tenant_id, location_id, asset_id, incident_kind, severity, status, "
                    "description, resolution_summary, resolved_at, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "case when %s = 'resolved' then now() else null end, 1, %s)",
                    (
                        incident_id,
                        business,
                        body.location_id,
                        body.asset_id,
                        body.incident_kind,
                        body.severity,
                        body.status,
                        body.description,
                        body.resolution_summary,
                        body.status,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise AssetStateError("Incident revision mismatch")
                if str(existing[1]) == "resolved":
                    raise AssetStateError("Resolved incident cannot be reopened")
                await conn.execute(
                    "update gba.asset_safety_incidents set severity = %s, status = %s, "
                    "description = %s, resolution_summary = %s, "
                    "resolved_at = case when %s = 'resolved' then now() else null end, "
                    "revision = revision + 1, recorded_by = %s, updated_at = now() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.severity,
                        body.status,
                        body.description,
                        body.resolution_summary,
                        body.status,
                        user_id,
                        business,
                        incident_id,
                    ),
                )

            if (
                body.severity == "critical"
                and body.status == "open"
                and str(asset_row[0]) == "active"
            ):
                await conn.execute(
                    "update gba.managed_assets set status = 'out_of_service', "
                    "revision = revision + 1, recorded_by = %s, updated_at = now() "
                    "where tenant_id = %s and id = %s",
                    (user_id, business, body.asset_id),
                )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced asset not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, asset_id, incident_kind, severity, status, description, "
                "resolution_summary, occurred_at, resolved_at, revision, recorded_by, updated_at "
                "from gba.asset_safety_incidents where tenant_id = %s and id = %s",
                (business, incident_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _incident_view(row)
        await commands.complete(conn, scope, view)
        return view
