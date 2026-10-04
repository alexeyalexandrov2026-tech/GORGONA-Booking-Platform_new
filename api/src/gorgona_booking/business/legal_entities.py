"""Tenant-owned legal-entity identities and append-only draft revisions."""

import hashlib
import json
from uuid import UUID

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.legal_entity_contracts import (
    LegalEntityInput,
    LegalEntityList,
    LegalEntityView,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError


def request_hash(entity_id: UUID, body: LegalEntityInput) -> str:
    command = {"legal_entity_id": str(entity_id), **body.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()


async def load_legal_entity(
    conn: RuntimeConnection, business_id: UUID, entity_id: UUID, *, revision: int | None = None
) -> LegalEntityView | None:
    row = await (
        await conn.execute(
            "select e.code, v.legal_name, v.revision, v.created_at "
            "from gba.legal_entities e join gba.legal_entity_versions v "
            "on v.tenant_id = e.tenant_id and v.legal_entity_id = e.id "
            "where e.tenant_id = %s and e.id = %s "
            "and (%s::integer is null or v.revision = %s) "
            "order by v.revision desc limit 1",
            (business_id, entity_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    return LegalEntityView(
        business_id=business_id,
        legal_entity_id=entity_id,
        code=row[0],
        legal_name=row[1],
        revision=row[2],
        created_at=row[3],
    )


async def list_legal_entities(
    conn: RuntimeConnection, business_id: UUID, *, after: str | None, limit: int
) -> LegalEntityList:
    rows = await (
        await conn.execute(
            "select e.id, e.code, v.legal_name, v.revision, v.created_at "
            "from gba.legal_entities e join lateral "
            "(select legal_name, revision, created_at from gba.legal_entity_versions "
            "where tenant_id = e.tenant_id and legal_entity_id = e.id "
            "order by revision desc limit 1) v on true "
            "where e.tenant_id = %s and (%s::text is null or e.code > %s) "
            "order by e.code limit %s",
            (business_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        LegalEntityView(
            business_id=business_id,
            legal_entity_id=row[0],
            code=row[1],
            legal_name=row[2],
            revision=row[3],
            created_at=row[4],
        )
        for row in rows[:limit]
    )
    return LegalEntityList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].code if len(rows) > limit else None,
    )


async def save_legal_entity(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    entity_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: LegalEntityInput,
) -> LegalEntityView:
    """Caller holds the company structure lock before the membership share lock.

    Identity, revision, audit and receipt commit or roll back together. A caller's
    internal reference distinguishes records; equal names never merge legal entities.
    """
    scope = IdempotencyScope(business_id, actor, "business.legal_entity.save", key)
    fingerprint = request_hash(entity_id, body)
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("This key was already used with another entity command")
        return LegalEntityView.model_validate(previous.body)

    current = await load_legal_entity(conn, business_id, entity_id)
    revision = current.revision if current else 0
    if body.expected_revision != revision:
        raise ConflictError(
            "This legal entity changed. Reload it before saving.", revision=revision
        )
    if current is not None and current.code != body.code:
        raise InvalidReferenceError("The internal reference of an existing entity cannot change")
    if current is None:
        try:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.legal_entities (tenant_id, id, code, created_by) "
                    "values (%s, %s, %s, %s)",
                    (business_id, entity_id, body.code, user_id),
                )
        except UniqueViolation as exc:
            if exc.diag.constraint_name != "legal_entities_code_unique":
                raise
            raise ConflictError(
                "A legal entity with this internal reference already exists"
            ) from exc
    revision += 1
    await conn.execute(
        "insert into gba.legal_entity_versions "
        "(tenant_id, legal_entity_id, revision, legal_name, created_by) "
        "values (%s, %s, %s, %s, %s)",
        (business_id, entity_id, revision, body.legal_name, user_id),
    )
    result = await load_legal_entity(conn, business_id, entity_id)
    if result is None:
        raise RuntimeError("Legal entity insert did not produce a version")
    await conn.execute(
        "insert into gba.audit_events "
        "(tenant_id, actor, action, target_type, target_id, details, request_id) "
        "values (%s, %s, 'legal_entity.saved', 'legal_entity', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (business_id, actor, str(entity_id), Jsonb({"revision": revision, "code": body.code})),
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result
