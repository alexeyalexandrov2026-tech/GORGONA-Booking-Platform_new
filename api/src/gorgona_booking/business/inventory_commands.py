"""J5: settling an inventory command whose answer was lost, by its idempotency key.

Resolving reads the caller's own receipt for the key and says whether the command took
effect. Cancelling an unresolved command stores a cancellation in place of the receipt, so
a late copy of the command is refused as a reused key and changes nothing. It follows the
workforce desk: no table of its own, a daily limit of discards per person, identifiers only
in the reference and in the audit.
"""

import hashlib
from typing import Any
from uuid import UUID

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands
from gorgona_booking.business.inventory_contracts import (
    CancelledCommand,
    CommandReference,
    CommandState,
    CommandStatus,
    InventoryReceipt,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError, DomainError, InvalidReferenceError

_CANCELLED_STATUS = 410
# Discarded commands one person may leave in one business within 24 hours.
DISCARD_LIMIT = 20
_AUDIT_TARGET_LIMIT = 200


class InventoryDiscardsError(DomainError):
    code = "TOO_MANY_DISCARDED_COMMANDS"


def _scope(business: UUID, actor: str, body: CommandReference, key: str) -> IdempotencyScope:
    # The same operations the commands themselves claim their keys under.
    return IdempotencyScope(business, actor, "inventory." + body.operation, key)


def _state(status: int, stored: dict[str, Any], body: CommandReference) -> CommandState:
    if status == _CANCELLED_STATUS:
        cancelled = CancelledCommand.model_validate(stored)
        found = (cancelled.subject_id, cancelled.revision)
    else:
        receipt = InventoryReceipt.model_validate(stored)
        found = (receipt.subject_id, receipt.revision)
    if found != (body.subject_id, body.revision):
        raise InvalidReferenceError("This outcome belongs to another inventory reference")
    return "cancelled" if status == _CANCELLED_STATUS else "committed"


async def resolve_command(
    conn: RuntimeConnection, business: UUID, actor: str, key: str, body: CommandReference
) -> CommandStatus:
    scope = _scope(business, actor, body, key)
    # An expired receipt still records what happened; only a later claim may reuse it.
    row = await (
        await conn.execute(
            "select response_status,response_body from gba.idempotency_keys "
            "where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s",
            (business, actor, scope.operation, key),
        )
    ).fetchone()
    state: CommandState = "unresolved"
    if row is not None and row[0] is not None:
        state = _state(row[0], row[1], body)
    return CommandStatus(business_id=business, key=key, operation=body.operation, state=state)


async def cancel_command(
    conn: RuntimeConnection, business: UUID, actor: str, key: str, body: CommandReference
) -> CommandStatus:
    current = await resolve_command(conn, business, actor, key, body)
    if current.state != "unresolved":
        return current
    isolation = await (await conn.execute("show transaction_isolation")).fetchone()
    if isolation is None or isolation[0] != "read committed":
        raise DatabaseUnavailableError(
            "Discarding a new command requires read committed transactions"
        )
    # Lock order: the person's discard counter, then the receipt. Real commands never take
    # this lock. A savepoint removes a new receipt if the limit refuses its cancellation.
    async with conn.transaction():
        await conn.execute(
            "select pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(%s,0))",
            (f"gba:inventory-discards:{business}:{actor}",),
        )
        scope = _scope(business, actor, body, key)
        marker = CancelledCommand(**body.model_dump())
        # A real command that is still running is waited for, and its outcome reported.
        previous = await idempotency.claim(
            conn, scope, commands.fingerprint(marker.model_dump(mode="json"))
        )
        if previous is not None:
            return current.model_copy(
                update={"state": _state(previous.status_code, previous.body, body)}
            )
        discarded = await (
            await conn.execute(
                "select count(*) from gba.idempotency_keys where tenant_id=%s and actor_key=%s "
                "and operation like 'inventory.%%' and response_status=%s "
                "and created_at>now()-interval '24 hours'",
                (business, actor, _CANCELLED_STATUS),
            )
        ).fetchone()
        if discarded is not None and discarded[0] >= DISCARD_LIMIT:
            raise InventoryDiscardsError(
                "Too many actions were discarded today; check the result instead or try later"
            )
        await idempotency.complete(conn, scope, _CANCELLED_STATUS, marker.model_dump(mode="json"))
        await commands.audit(
            conn,
            business,
            actor,
            "inventory.command_cancelled",
            "inventory_command",
            # A key may be longer than an audit target; then its digest names it.
            key
            if len(key) <= _AUDIT_TARGET_LIMIT
            else "sha256:" + hashlib.sha256(key.encode()).hexdigest(),
            {"operation": body.operation, "revision": body.revision},
        )
        return current.model_copy(update={"state": "cancelled"})
