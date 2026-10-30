"""O1 (package O, BUILD-01): construction projects and estimate versions (ADR-0035).

A project has one currency and a site time zone. Estimate versions and their lines are insert-only;
a version is proposed once (only the latest); totals are derived on read. The database rechecks the
sequence of versions, the proposal stamp and the currency, and gates writes on the module.
"""

import hashlib
import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import modules
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

PAGE = 50
MONEY_MAX = 1_000_000_000_000


class ConstructionNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class ConstructionRevisionConflictError(ConflictError):
    code = "CONSTRUCTION_REVISION_CONFLICT"


class ConstructionNumberTakenError(ConflictError):
    code = "CONSTRUCTION_NUMBER_TAKEN"


class ConstructionTimeZoneError(DomainError):
    code = "CONSTRUCTION_TIME_ZONE_UNKNOWN"


class ConstructionCurrencyFixedError(ConflictError):
    code = "CONSTRUCTION_CURRENCY_FIXED"


class ConstructionEstimateStaleError(ConflictError):
    code = "CONSTRUCTION_ESTIMATE_STALE"


class ConstructionContractExistsError(ConflictError):
    code = "CONSTRUCTION_CONTRACT_EXISTS"


class ConstructionCustomerFixedError(ConflictError):
    code = "CONSTRUCTION_CUSTOMER_FIXED"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectInput(Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    number: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    customer_id: UUID
    location_id: UUID
    site_address: str = Field(min_length=1, max_length=500)
    time_zone: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


LineKind = Literal["material", "labor", "equipment", "subcontract", "other"]


class LineInput(Strict):
    kind: LineKind
    description: str = Field(min_length=1, max_length=500)
    phase: str = Field(min_length=1, max_length=64)
    quantity: Decimal = Field(gt=0, le=Decimal("999999999.9999"), max_digits=13, decimal_places=4)
    unit: str = Field(min_length=1, max_length=16)
    unit_cost_minor: int = Field(ge=0, le=MONEY_MAX)
    unit_price_minor: int = Field(ge=0, le=MONEY_MAX)
    material_id: UUID | None = None


class EstimateInput(Strict):
    schema_version: Literal[1]
    based_on: int = Field(ge=0, le=100_000)
    note: str | None = Field(default=None, min_length=1, max_length=1000)
    lines: list[LineInput] = Field(min_length=1, max_length=500)


class ProposalInput(Strict):
    schema_version: Literal[1]


class ProjectView(BaseModel):
    project_id: UUID
    revision: int
    number: str
    name: str
    customer_id: UUID
    location_id: UUID
    site_address: str
    time_zone: str
    currency: str
    latest_version: int


class ProjectList(BaseModel):
    items: list[ProjectView]
    next_cursor: UUID | None = None


class LineView(BaseModel):
    position: int
    kind: str
    description: str
    phase: str
    quantity: Decimal
    unit: str
    unit_cost_minor: int
    unit_price_minor: int
    material_id: UUID | None
    cost_minor: int
    price_minor: int


class EstimateSummary(BaseModel):
    version: int
    based_on: int
    note: str | None
    proposed_at: datetime | None
    cost_total_minor: int
    price_total_minor: int


class EstimateView(EstimateSummary):
    project_id: UUID
    currency: str
    lines: list[LineView]


class EstimateList(BaseModel):
    items: list[EstimateSummary]


_SUMMARY = set(EstimateSummary.model_fields)


def amount(quantity: Decimal, unit_minor: int) -> int:
    """Quantity times a unit amount, rounded half up to a whole minor unit (decision 5)."""
    return int((quantity * unit_minor).quantize(Decimal(1), rounding=ROUND_HALF_UP))


async def require_construction(conn: RuntimeConnection, business: UUID) -> None:
    """Writes need an accepted module that this business enabled (ADR-0019, ADR-0035)."""
    current = modules.MODULES_BY_ID[CONSTRUCTION_MODULE]
    if not current.enableable or not at_least(current.readiness, modules.MINIMUM_READINESS):
        raise ConstructionNotReadyError(
            "Construction has not been accepted", module_id=CONSTRUCTION_MODULE
        )
    await require_module(conn, business, CONSTRUCTION_MODULE)
    for dependency in current.depends_on:
        if modules.MODULES_BY_ID[dependency].kind == modules.ModuleKind.OPTIONAL:
            await require_module(conn, business, dependency)


def request_fingerprint(subject: str, body: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            {"subject": subject, "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


async def latest_version(conn: RuntimeConnection, project_id: UUID) -> int:
    row = await (
        await conn.execute(
            "select coalesce(max(version), 0) from gba.construction_estimate_versions "
            "where project_id = %s",
            (project_id,),
        )
    ).fetchone()
    return int(row[0]) if row else 0


async def has_contract(conn: RuntimeConnection, project_id: UUID) -> bool:
    row = await (
        await conn.execute(
            "select 1 from gba.construction_contracts where project_id = %s", (project_id,)
        )
    ).fetchone()
    return row is not None


async def load_project(conn: RuntimeConnection, project_id: UUID) -> ProjectView | None:
    row = await (
        await conn.execute(
            "select revision, number, name, customer_id, location_id, site_address, time_zone, "
            "currency from gba.construction_projects where id = %s",
            (project_id,),
        )
    ).fetchone()
    if row is None:
        return None
    return ProjectView(
        project_id=project_id,
        revision=row[0],
        number=row[1],
        name=row[2],
        customer_id=row[3],
        location_id=row[4],
        site_address=row[5],
        time_zone=row[6],
        currency=row[7],
        latest_version=await latest_version(conn, project_id),
    )


async def list_projects(conn: RuntimeConnection, after: UUID | None = None) -> ProjectList:
    if after is None:
        cursor = await conn.execute(
            "select id from gba.construction_projects order by id limit %s", (PAGE + 1,)
        )
    else:
        cursor = await conn.execute(
            "select id from gba.construction_projects where id > %s order by id limit %s",
            (after, PAGE + 1),
        )
    rows = await cursor.fetchall()
    items = [await load_project(conn, row[0]) for row in rows[:PAGE]]
    views = [item for item in items if item is not None]
    more = len(rows) > PAGE and bool(views)
    return ProjectList(items=views, next_cursor=views[-1].project_id if more else None)


async def _known_zone(conn: RuntimeConnection, zone: str) -> bool:
    row = await (
        await conn.execute("select 1 from pg_catalog.pg_timezone_names where name = %s", (zone,))
    ).fetchone()
    return row is not None


async def _visible_location(conn: RuntimeConnection, location_id: UUID) -> bool:
    """A branch-limited caller names only its own branch (ADR-0035 decision 8)."""
    row = await (await conn.execute("select gba.current_location_id()")).fetchone()
    scope = row[0] if row else None
    if scope is not None and scope != location_id:
        return False
    found = await (
        await conn.execute("select 1 from gba.locations where id = %s", (location_id,))
    ).fetchone()
    return found is not None


async def save_project(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ProjectInput,
) -> ProjectView:
    """Replace a construction project whole, with its expected revision (decisions 1-2)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.project", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_project(conn, project_id)
        if view is None:
            raise NotFoundError("Project not found", project_id=str(project_id))
        return view
    if not await _known_zone(conn, body.time_zone):
        raise ConstructionTimeZoneError("Unknown time zone", time_zone=body.time_zone)
    if not await _visible_location(conn, body.location_id):
        raise InvalidReferenceError("Unknown branch", field="location_id")
    current = await (
        await conn.execute(
            "select revision, currency, customer_id from gba.construction_projects "
            "where id = %s for update",
            (project_id,),
        )
    ).fetchone()
    found = 0 if current is None else int(current[0])
    if found != body.expected_revision:
        raise ConstructionRevisionConflictError(
            "The project changed since it was read; reload it", revision=found
        )
    if (
        current is not None
        and current[1] != body.currency
        and await latest_version(conn, project_id)
    ):
        raise ConstructionCurrencyFixedError(
            "A project with an estimate keeps its currency", currency=current[1]
        )
    if (
        current is not None
        and current[2] != body.customer_id
        and await has_contract(conn, project_id)
    ):
        raise ConstructionCustomerFixedError("A project with a contract keeps its customer")
    values = (
        body.location_id,
        body.number,
        body.name,
        body.customer_id,
        body.site_address,
        body.time_zone,
        body.currency,
    )
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            if current is None:
                await conn.execute(
                    "insert into gba.construction_projects (tenant_id, id, location_id, number, "
                    "name, customer_id, site_address, time_zone, currency, revision, created_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (business, project_id, *values, user_id),
                )
            else:
                await conn.execute(
                    "update gba.construction_projects set location_id = %s, number = %s, "
                    "name = %s, customer_id = %s, site_address = %s, time_zone = %s, "
                    "currency = %s, revision = revision + 1, updated_at = clock_timestamp() "
                    "where id = %s",
                    (*values, project_id),
                )
    except UniqueViolation as exc:
        raise ConstructionNumberTakenError("Another project has this number") from exc
    except ForeignKeyViolation as exc:
        field = "currency" if "currency" in (exc.diag.constraint_name or "") else "customer_id"
        raise InvalidReferenceError("Unknown reference", field=field) from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "construction_projects_currency_check":
            raise ConstructionCurrencyFixedError(
                "A project with an estimate keeps its currency"
            ) from exc
        if exc.diag.constraint_name == "construction_projects_customer_check":
            raise ConstructionCustomerFixedError(
                "A project with a contract keeps its customer"
            ) from exc
        if exc.diag.constraint_name == "construction_projects_time_zone_check":
            raise ConstructionTimeZoneError("Unknown time zone") from exc
        raise
    view = await load_project(conn, project_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"project_id": str(project_id)})
    return view


async def lock_project(conn: RuntimeConnection, project_id: UUID) -> str:
    row = await (
        await conn.execute(
            "select currency from gba.construction_projects where id = %s for update",
            (project_id,),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Project not found", project_id=str(project_id))
    return str(row[0])


async def load_estimate(
    conn: RuntimeConnection, project_id: UUID, version: int
) -> EstimateView | None:
    head = await (
        await conn.execute(
            "select v.note, v.proposed_at, p.currency from gba.construction_estimate_versions v "
            "join gba.construction_projects p on p.tenant_id = v.tenant_id and p.id = v.project_id "
            "where v.project_id = %s and v.version = %s",
            (project_id, version),
        )
    ).fetchone()
    if head is None:
        return None
    rows = await (
        await conn.execute(
            "select position, kind, description, phase, quantity, unit, unit_cost_minor, "
            "unit_price_minor, material_id from gba.construction_estimate_lines "
            "where project_id = %s and version = %s order by position",
            (project_id, version),
        )
    ).fetchall()
    lines = [
        LineView(
            position=row[0],
            kind=row[1],
            description=row[2],
            phase=row[3],
            quantity=row[4],
            unit=row[5],
            unit_cost_minor=row[6],
            unit_price_minor=row[7],
            material_id=row[8],
            cost_minor=amount(row[4], row[6]),
            price_minor=amount(row[4], row[7]),
        )
        for row in rows
    ]
    return EstimateView(
        project_id=project_id,
        version=version,
        based_on=version - 1,
        note=head[0],
        proposed_at=head[1],
        currency=head[2],
        cost_total_minor=sum(item.cost_minor for item in lines),
        price_total_minor=sum(item.price_minor for item in lines),
        lines=lines,
    )


async def list_estimates(conn: RuntimeConnection, project_id: UUID) -> EstimateList:
    if await load_project(conn, project_id) is None:
        raise NotFoundError("Project not found", project_id=str(project_id))
    rows = await (
        await conn.execute(
            "select version from gba.construction_estimate_versions where project_id = %s "
            "order by version",
            (project_id,),
        )
    ).fetchall()
    items: list[EstimateSummary] = []
    for row in rows:
        view = await load_estimate(conn, project_id, row[0])
        if view is not None:
            items.append(EstimateSummary.model_validate(view.model_dump(include=_SUMMARY)))
    return EstimateList(items=items)


async def save_estimate(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: EstimateInput,
) -> EstimateView:
    """Add the next estimate version on the latest one the client read (decisions 3-4)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.estimate", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored_estimate(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    if await has_contract(conn, project_id):
        raise ConstructionContractExistsError(
            "The project has a contract; change its scope with a change order"
        )
    latest = await latest_version(conn, project_id)
    if body.based_on != latest:
        raise ConstructionEstimateStaleError(
            "The estimate changed since it was read; reload it", latest_version=latest
        )
    version = latest + 1
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_estimate_versions (tenant_id, project_id, version, "
                "note, created_by) values (%s, %s, %s, %s, %s)",
                (business, project_id, version, body.note, user_id),
            )
            for position, item in enumerate(body.lines, start=1):
                await conn.execute(
                    "insert into gba.construction_estimate_lines (tenant_id, project_id, version, "
                    "position, kind, description, phase, quantity, unit, unit_cost_minor, "
                    "unit_price_minor, material_id) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        project_id,
                        version,
                        position,
                        item.kind,
                        item.description,
                        item.phase,
                        item.quantity,
                        item.unit,
                        item.unit_cost_minor,
                        item.unit_price_minor,
                        item.material_id,
                    ),
                )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown material", field="material_id") from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "construction_estimate_versions_contract_check":
            raise ConstructionContractExistsError("The project has a contract") from exc
        raise
    view = await load_estimate(conn, project_id, version)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"version": version})
    return view


async def _stored_estimate(
    conn: RuntimeConnection, project_id: UUID, body: dict[str, object]
) -> EstimateView:
    version = body.get("version")
    view = await load_estimate(conn, project_id, int(version)) if isinstance(version, int) else None
    if view is None:
        raise NotFoundError("Estimate not found", project_id=str(project_id))
    return view


async def propose(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    version: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ProposalInput,
) -> EstimateView:
    """Stamp the latest version as the proposal sent to the customer, once (decision 5)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.proposal", key)
    fingerprint = request_fingerprint(f"{project_id}:{version}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _stored_estimate(conn, project_id, stored.body)
    await lock_project(conn, project_id)
    current = await load_estimate(conn, project_id, version)
    if current is None:
        raise NotFoundError("Estimate not found", project_id=str(project_id), version=version)
    latest = await latest_version(conn, project_id)
    if version != latest:
        raise ConstructionEstimateStaleError(
            "Only the latest estimate version can be proposed", latest_version=latest
        )
    if current.proposed_at is None:
        await conn.execute(
            "update gba.construction_estimate_versions set proposed_at = clock_timestamp(), "
            "proposed_by = %s where project_id = %s and version = %s",
            (user_id, project_id, version),
        )
    view = await load_estimate(conn, project_id, version)
    assert view is not None  # noqa: S101 - read above
    await idempotency.complete(conn, scope, 200, {"version": version})
    return view
