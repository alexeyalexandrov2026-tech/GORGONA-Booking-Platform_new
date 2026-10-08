"""Permanent reference-only command outcomes shared by H documents and settlements.

A command claims its key under the ledger lock, replays a committed reference after
the ordinary receipt expired and cannot commit once its key was cancelled. Receipts
hold hashes and identifiers only, never a financial body.
"""

from collections.abc import Awaitable, Callable
from typing import Literal, NamedTuple
from uuid import UUID

from psycopg.errors import SerializationFailure
from pydantic import BaseModel

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import commands, ledger
from gorgona_booking.business.financial_contracts import (
    FinancialCommandKind,
    FinancialCommandReference,
    FinancialCommandStatus,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DatabaseUnavailableError, InvalidReferenceError


class FinancialCommandCancelledError(ConflictError):
    code = "FINANCIAL_COMMAND_CANCELLED"


class Reference(NamedTuple):
    """The immutable row a command produced: a document version or settlement event."""

    book_id: UUID
    subject_id: UUID
    revision: int


class _Family(NamedTuple):
    receipts: Literal["financial_command_receipts", "settlement_command_receipts"]
    subject: Literal["document_id", "settlement_id"]
    revision: Literal["revision", "sequence"]
    target: str


_DOCUMENTS = _Family("financial_command_receipts", "document_id", "revision", "financial_document")
_SETTLEMENTS = _Family(
    "settlement_command_receipts", "settlement_id", "sequence", "settlement_document"
)
_FAMILIES: dict[FinancialCommandKind, _Family] = {
    "invoice_draft": _DOCUMENTS,
    "invoice_issue": _DOCUMENTS,
    "accrual_draft": _DOCUMENTS,
    "accrual_issue": _DOCUMENTS,
    "credit_draft": _DOCUMENTS,
    "credit_issue": _DOCUMENTS,
    "settlement_prepare": _SETTLEMENTS,
    "settlement_approve": _SETTLEMENTS,
    "settlement_reserve": _SETTLEMENTS,
    "settlement_sent": _SETTLEMENTS,
    "settlement_confirm": _SETTLEMENTS,
    "settlement_release": _SETTLEMENTS,
    "settlement_cancel": _SETTLEMENTS,
    "settlement_payment_void": _SETTLEMENTS,
    "settlement_payment_correct": _SETTLEMENTS,
}
_KEY = " where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s"


def scope(
    business: UUID, actor: str, operation: FinancialCommandKind, key: str
) -> IdempotencyScope:
    return IdempotencyScope(business, actor, "business.finance." + operation, key)


async def lock(conn: RuntimeConnection, business: UUID) -> None:
    try:
        await conn.execute("select gba.lock_ledger(%s)", (business,))
    except SerializationFailure as exc:
        raise DatabaseUnavailableError(
            "Financial writes require read committed transactions"
        ) from exc


async def _stored(
    conn: RuntimeConnection,
    family: _Family,
    business: UUID,
    actor: str,
    operation: FinancialCommandKind,
    key: str,
) -> tuple[str, Reference] | None:
    row = await (
        await conn.execute(
            "select request_hash,book_id,"  # noqa: S608 - fixed finite identifiers
            + family.subject
            + ","
            + family.revision
            + " from gba."
            + family.receipts
            + _KEY,
            (business, actor, operation, key),
        )
    ).fetchone()
    return None if row is None else (row[0], Reference(row[1], row[2], row[3]))


async def claim[T: BaseModel](
    conn: RuntimeConnection,
    *,
    business: UUID,
    actor: str,
    operation: FinancialCommandKind,
    key: str,
    request_hash: str,
    model: type[T],
    receipt: Callable[[Reference], T],
) -> Reference | None:
    """None when this call owns the key; the committed reference on a replay."""
    await lock(conn, business)
    cancelled = await (
        await conn.execute(
            "select 1 from gba.financial_command_cancellations" + _KEY,  # noqa: S608
            (business, actor, operation, key),
        )
    ).fetchone()
    if cancelled:
        raise FinancialCommandCancelledError("This unresolved financial command was cancelled")
    stored = await _stored(conn, _FAMILIES[operation], business, actor, operation, key)
    if stored is not None and stored[0] != request_hash:
        raise IdempotencyKeyReusedError("This key was already used with another financial command")
    target = scope(business, actor, operation, key)
    cached = await commands.claim(conn, target, request_hash, model)
    if stored is None:
        if cached is not None:
            raise DatabaseUnavailableError("The financial command outcome is incomplete")
        return None
    permanent = receipt(stored[1])
    if cached is not None and cached != permanent:
        raise DatabaseUnavailableError("The financial command references disagree")
    if cached is None:
        await commands.complete(conn, target, permanent)
    return stored[1]


async def complete(
    conn: RuntimeConnection,
    *,
    business: UUID,
    actor: str,
    user: UUID,
    operation: FinancialCommandKind,
    key: str,
    request_hash: str,
    reference: Reference,
    receipt: BaseModel,
    flush: Callable[[RuntimeConnection], Awaitable[None]],
) -> None:
    """Write the permanent receipt after SQL rechecked the complete effect."""
    family = _FAMILIES[operation]
    await flush(conn)
    await conn.execute(
        "insert into gba."  # noqa: S608 - fixed finite identifiers
        + family.receipts
        + " (tenant_id,actor_key,operation,idempotency_key,request_hash,book_id,"
        + family.subject
        + ","
        + family.revision
        + ",created_by) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            business,
            actor,
            operation,
            key,
            request_hash,
            reference.book_id,
            reference.subject_id,
            reference.revision,
            user,
        ),
    )
    await flush(conn)
    await commands.audit(
        conn,
        business,
        actor,
        "finance." + operation,
        family.target,
        str(reference.subject_id),
        {"book_id": str(reference.book_id), family.revision: reference.revision},
    )
    await commands.complete(conn, scope(business, actor, operation, key), receipt)


async def resolve_command(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    actor: str,
    key: str,
    body: FinancialCommandReference,
) -> FinancialCommandStatus:
    await lock(conn, business_id)
    # Validate the bounded key even when no ordinary receipt is retained.
    scope(business_id, actor, body.operation, key)
    expected = Reference(body.book_id, body.subject_id, body.revision)
    state: Literal["committed", "unresolved", "cancelled"] = "unresolved"
    stored = await _stored(conn, _FAMILIES[body.operation], business_id, actor, body.operation, key)
    found = None if stored is None else stored[1]
    if found is not None:
        state = "committed"
    else:
        row = await (
            await conn.execute(
                "select book_id,document_id,revision "
                "from gba.financial_command_cancellations" + _KEY,
                (business_id, actor, body.operation, key),
            )
        ).fetchone()
        if row is not None:
            found, state = Reference(row[0], row[1], row[2]), "cancelled"
    if found is not None and found != expected:
        raise InvalidReferenceError("This outcome belongs to another financial reference")
    return FinancialCommandStatus(
        business_id=business_id, key=key, operation=body.operation, state=state
    )


async def cancel_command(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: FinancialCommandReference,
) -> FinancialCommandStatus:
    result = await resolve_command(conn, business_id=business_id, actor=actor, key=key, body=body)
    if result.state != "unresolved":
        return result
    await ledger.require_book(conn, business_id, body.book_id)
    await conn.execute(
        "insert into gba.financial_command_cancellations "
        "(tenant_id,actor_key,operation,idempotency_key,book_id,document_id,revision,cancelled_by) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            business_id,
            actor,
            body.operation,
            key,
            body.book_id,
            body.subject_id,
            body.revision,
            user_id,
        ),
    )
    await commands.audit(
        conn,
        business_id,
        actor,
        "finance.command_cancelled",
        "financial_command",
        key,
        {"book_id": str(body.book_id), "operation": body.operation},
    )
    return result.model_copy(update={"state": "cancelled"})
