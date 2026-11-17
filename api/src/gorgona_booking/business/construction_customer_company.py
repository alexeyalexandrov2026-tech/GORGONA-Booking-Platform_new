"""O-09: versioned project-to-customer-company association."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation
from pydantic import BaseModel, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.construction import (
    ConstructionRevisionConflictError,
    Strict,
    lock_project,
    request_fingerprint,
    require_construction,
)
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError


class CustomerCompanyInput(Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_646)
    expected_customer_generation: int = Field(ge=1)
    company_id: UUID | None


class CustomerCompanyVersion(BaseModel):
    revision: int
    customer_id: UUID
    company_id: UUID | None
    recorded_at: datetime


class CustomerCompanyView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    customer_id: UUID
    customer_generation: int
    revision: int
    company_id: UUID | None
    versions: list[CustomerCompanyVersion]


async def load_customer_company(conn: RuntimeConnection, project_id: UUID) -> CustomerCompanyView:
    rows = await (
        await conn.execute(
            "select p.customer_id, p.customer_generation, b.revision, b.customer_id, "
            "b.customer_generation, b.company_id, b.created_at "
            "from gba.construction_projects p left join gba.construction_customer_companies b "
            "on (p.tenant_id, p.id) = (b.tenant_id, b.project_id) "
            "where p.id=%s order by b.revision",
            (project_id,),
        )
    ).fetchall()
    if not rows:
        raise NotFoundError("Project not found", project_id=str(project_id))
    customer_id, generation, revision, _, binding_generation, company, _ = rows[-1]
    return CustomerCompanyView(
        project_id=project_id,
        customer_id=customer_id,
        customer_generation=generation,
        revision=revision or 0,
        company_id=company if binding_generation == generation else None,
        versions=[
            CustomerCompanyVersion(
                revision=row[2], customer_id=row[3], company_id=row[5], recorded_at=row[6]
            )
            for row in rows
            if row[2] is not None
        ],
    )


async def save_customer_company(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CustomerCompanyInput,
) -> CustomerCompanyView:
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.customer_company", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_customer_company(conn, project_id)
    await lock_project(conn, project_id)
    current = await load_customer_company(conn, project_id)
    if (
        body.expected_revision != current.revision
        or body.expected_customer_generation != current.customer_generation
    ):
        raise ConstructionRevisionConflictError(
            "The customer assignment or company link changed since it was read",
            revision=current.revision,
            customer_generation=current.customer_generation,
        )
    if body.company_id == business:
        raise InvalidReferenceError("The customer company must be separate", field="company_id")
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_customer_companies "
                "(tenant_id, project_id, revision, customer_id, customer_generation, "
                "company_id, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    project_id,
                    current.revision + 1,
                    current.customer_id,
                    current.customer_generation,
                    body.company_id,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Customer company not found", field="company_id") from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name in {
            "construction_customer_company_current",
            "construction_customer_company_revision",
        }:
            raise ConstructionRevisionConflictError("The customer company changed") from exc
        raise
    await idempotency.complete(conn, scope, 200, {"project_id": str(project_id)})
    return await load_customer_company(conn, project_id)
