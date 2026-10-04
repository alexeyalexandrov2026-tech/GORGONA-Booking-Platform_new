"""Shared helpers for idempotent, audited business commands (ADR-0019).

A command claims its key, replays a stored result for the same body, refuses the
key for another body, and writes its audit event in the caller's transaction. The
older stage-1 modules keep their own copies until they are moved here.
"""

import hashlib
import json
from collections.abc import Mapping
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.db.pool import RuntimeConnection


def fingerprint(command: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()


async def claim[T: BaseModel](
    conn: RuntimeConnection, scope: IdempotencyScope, request_hash: str, model: type[T]
) -> T | None:
    """None when this call owns the key; the stored result when it is a replay."""
    previous = await idempotency.claim(conn, scope, request_hash)
    if previous is None:
        return None
    if previous.request_hash != request_hash:
        raise IdempotencyKeyReusedError("This key was already used with another command")
    return model.model_validate(previous.body)


async def complete(conn: RuntimeConnection, scope: IdempotencyScope, result: BaseModel) -> None:
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))


async def audit(
    conn: RuntimeConnection,
    business_id: UUID,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    details: Mapping[str, object],
) -> None:
    await conn.execute(
        "insert into gba.audit_events "
        "(tenant_id, actor, action, target_type, target_id, details, request_id) "
        "values (%s, %s, %s, %s, %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (business_id, actor, action, target_type, target_id, Jsonb(dict(details))),
    )
