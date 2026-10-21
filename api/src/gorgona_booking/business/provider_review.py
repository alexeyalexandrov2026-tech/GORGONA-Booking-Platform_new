"""K4b: why a provider operation needs review, what waits for attention, acknowledgements.

Reads name stored facts only: never a raw body, signature, secret reference or verification
config. An acknowledgement (owner decision 2, 2026-10-18) records that a finance user handled a
decision without an operation; it changes no money and no decision (migration 0053).
"""

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg

from gorgona_booking.business import ledger, settlements
from gorgona_booking.business.financial_documents import require_workflow
from gorgona_booking.business.ledger_contracts import to_minor
from gorgona_booking.business.provider_payments import (
    ProviderLinkMismatchError,
    ProviderOperationLinkedError,
    load_operation,
    observed,
)
from gorgona_booking.business.settlement_contracts import (
    ProviderAcknowledgeInput,
    ProviderAcknowledgementResult,
    ProviderAcknowledgementView,
    ProviderAttentionItem,
    ProviderAttentionList,
    ProviderDecisionView,
    ProviderDeliveryDifference,
    ProviderDeliveryView,
    ProviderEventView,
    ProviderLinkCandidate,
    ProviderLinkInput,
    ProviderLinkResult,
    ProviderLinkView,
    ProviderOperationDetail,
    ProviderOperationSummary,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.errors import ConflictError, DatabaseUnavailableError, NotFoundError


class ProviderAttentionAcknowledgedError(ConflictError):
    code = "PROVIDER_ATTENTION_ACKNOWLEDGED"


class ProviderAttentionNotNeededError(ConflictError):
    code = "PROVIDER_ATTENTION_NOT_NEEDED"


def link_refusal_reason(exc: psycopg.errors.CheckViolation) -> str:
    """K5r (review R9): name the 0058 admission gate, which a link can meet in a race."""
    return "not_admitted" if "admitted connection" in str(exc) else "facts"


# The attested events of one operation: mapped to it by their facts, or decided as it.
_EVENTS = (
    "select e.id,e.facts->>'event_type',(e.facts->>'created')::bigint,e.facts,"
    "d.outcome,d.reason,d.decided_at from gba.provider_event_inbox e "
    "left join gba.provider_event_decisions d on d.tenant_id=e.tenant_id and d.event_id=e.id "
    "where e.tenant_id=%s and e.connection_id=%s and exists(select 1 "
    "from gba.provider_event_attestations a where a.tenant_id=e.tenant_id and a.event_id=e.id) "
    # K5r (review R1): the 0061 stored operation key and its index find this operation's events.
    "and ((e.operation_kind=%s and e.operation_object_id=%s) or d.operation_id=%s) "
    "order by (e.facts->>'created')::bigint,e.id"
)
_DELIVERIES = (
    "select event_id,delivery_sha256,facts,matches_original,received_at "
    "from gba.provider_event_deliveries where tenant_id=%s and event_id=any(%s) "
    "order by received_at,delivery_sha256"
)
# An attested event of the book without a decision, or decided without an operation.
_ATTENTION = (
    "select e.id,e.connection_id,e.facts->>'event_type',(e.facts->>'created')::bigint,d.reason,"
    "k.note,k.created_by,k.created_at,e.facts->'resource'->>'id' from gba.provider_event_inbox e "
    "join gba.provider_receipt_connections c on c.tenant_id=e.tenant_id and c.id=e.connection_id "
    "left join gba.provider_event_decisions d on d.tenant_id=e.tenant_id and d.event_id=e.id "
    "left join gba.provider_event_acknowledgements k "
    "on k.tenant_id=e.tenant_id and k.event_id=e.id "
    "where e.tenant_id=%s and c.book_id=%s and exists(select 1 "
    "from gba.provider_event_attestations a where a.tenant_id=e.tenant_id and a.event_id=e.id) "
    "and (d.event_id is null or d.operation_id is null) "
)


def _flat(facts: dict[str, Any]) -> dict[str, Any]:
    flat = {key: value for key, value in facts.items() if key != "resource"}
    flat.update({f"resource.{key}": value for key, value in facts.get("resource", {}).items()})
    return flat


def _text(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _differences(
    original: dict[str, Any], delivered: dict[str, Any]
) -> tuple[ProviderDeliveryDifference, ...]:
    before, after = _flat(original), _flat(delivered)
    return tuple(
        ProviderDeliveryDifference(
            field=key, original=_text(before.get(key)), delivered=_text(after.get(key))
        )
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    )


def _created(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


async def operation_detail(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, operation_id: UUID
) -> ProviderOperationDetail:
    await ledger.require_book(conn, business_id, book_id)
    await assert_provider_receipt_ready(conn)
    operation = await load_operation(conn, business_id, book_id, operation_id)
    if operation is None:
        raise NotFoundError("Provider operation not found")
    rows = await (
        await conn.execute(
            _EVENTS,
            (
                business_id,
                operation.connection_id,
                operation.kind,
                operation.provider_object_id,
                operation_id,
            ),
        )
    ).fetchall()
    deliveries: dict[UUID, list[tuple[Any, ...]]] = defaultdict(list)
    for row in await (
        await conn.execute(_DELIVERIES, (business_id, [row[0] for row in rows]))
    ).fetchall():
        deliveries[row[0]].append(tuple(row))
    events = tuple(
        ProviderEventView(
            event_id=row[0],
            event_type=row[1],
            created=_created(row[2]),
            decision=None
            if row[4] is None
            else ProviderDecisionView(outcome=row[4], reason=row[5], decided_at=row[6]),
            deliveries=tuple(
                ProviderDeliveryView(
                    received_at=delivery[4],
                    digest=delivery[1][:12],
                    matches_original=delivery[3],
                    differences=() if delivery[3] else _differences(row[3], delivery[2]),
                )
                for delivery in deliveries[row[0]]
            ),
        )
        for row in rows
    )
    return ProviderOperationDetail(
        business_id=business_id,
        book_id=book_id,
        operation=operation,
        events=events,
        link=await _link(conn, business_id, operation_id),
        manual_payments=await _candidates(conn, business_id, book_id, operation),
    )


async def _link(
    conn: RuntimeConnection, business_id: UUID, operation_id: UUID
) -> ProviderLinkView | None:
    row = await (
        await conn.execute(
            "select payment_id,note,created_by,created_at from gba.provider_payment_links "
            "where tenant_id=%s and operation_id=%s",
            (business_id, operation_id),
        )
    ).fetchone()
    return (
        None
        if row is None
        else ProviderLinkView(payment_id=row[0], note=row[1], linked_by=row[2], linked_at=row[3])
    )


async def _candidates(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, operation: ProviderOperationSummary
) -> tuple[ProviderLinkCandidate, ...]:
    """Manual payments of the book that name the provider ID under the H identity key (K5a-fix
    finding 13), voided ones included so that their state is shown."""
    rows = await (
        await conn.execute(
            "select id from gba.external_payments where tenant_id=%s and book_id=%s "
            "and attestation='manual_attestation' "
            "and pg_catalog.lower(%s)=any(gba.provider_reference_ids(external_reference)) "
            "order by id limit 20",
            (business_id, book_id, operation.provider_object_id),
        )
    ).fetchall()
    found = []
    for (payment_id,) in rows:
        payment = await settlements.load_payment(conn, business_id, book_id, payment_id)
        if payment is None:
            raise DatabaseUnavailableError("A manual payment is unavailable")
        last = payment.revisions[-1] if payment.revisions else None
        found.append(
            ProviderLinkCandidate(
                payment_id=payment.payment_id,
                state=payment.state,
                amount=payment.effective_amount,
                currency=payment.currency,
                actual_external_date=(
                    last.actual_external_date
                    if last is not None and last.actual_external_date is not None
                    else payment.actual_external_date
                ),
                external_reference=payment.external_reference,
            )
        )
    return tuple(found)


async def link(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    operation_id: UUID,
    user_id: UUID,
    body: ProviderLinkInput,
) -> ProviderLinkResult:
    """K3b: record that a manual payment is this observed operation; no journal is written.

    The same payment and note again return the link; anything else for a linked operation is
    refused. SQL checks every fact again under the ledger and operation locks.
    """
    await require_workflow(conn, business_id)
    await ledger.require_book(conn, business_id, book_id)
    await assert_provider_receipt_ready(conn)
    operation = await load_operation(conn, business_id, book_id, operation_id)
    if operation is None:
        raise NotFoundError("Provider operation not found")
    current = await _link(conn, business_id, operation_id)
    if current is not None:
        if (current.payment_id, current.note) == (body.payment_id, body.note):
            return ProviderLinkResult(
                business_id=business_id, book_id=book_id, operation=operation, link=current
            )
        raise ProviderOperationLinkedError(
            "This provider operation is linked to a manual payment",
            payment_id=str(current.payment_id),
        )
    # Locks the operation and refuses one that is applied, linked or not observed.
    facts = await observed(conn, business_id, book_id, operation_id)
    payment = await settlements.load_payment(conn, business_id, book_id, body.payment_id)
    if payment is None:
        raise NotFoundError("Payment not found")
    candidate = next(
        (
            x
            for x in await _candidates(conn, business_id, book_id, operation)
            if x.payment_id == body.payment_id
        ),
        None,
    )
    taken = await (
        await conn.execute(
            "select operation_id from gba.provider_payment_links "
            "where tenant_id=%s and book_id=%s and payment_id=%s",
            (business_id, book_id, body.payment_id),
        )
    ).fetchone()
    direction = "receivable" if facts.kind == "payment" else "payable"
    reason = (
        "not_manual"
        if payment.attestation != "manual_attestation"
        else "voided"
        if payment.state == "voided"
        else "payment_linked"
        if taken is not None
        else "direction"
        if payment.direction != direction
        else "currency"
        if payment.currency != facts.currency
        else "amount"
        if to_minor(payment.effective_amount, payment.minor_units) != facts.amount_minor
        else "reference"
        if candidate is None
        else "date"
        if abs((candidate.actual_external_date - facts.actual_date).days) > 3
        else None
    )
    if reason is not None:
        raise ProviderLinkMismatchError(
            "This manual payment does not match the provider operation", reason=reason
        )
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into gba.provider_payment_links "
                "(tenant_id,book_id,payment_id,operation_id,note,created_by) "
                "values (%s,%s,%s,%s,%s,%s)",
                (business_id, book_id, body.payment_id, operation_id, body.note, user_id),
            )
    except psycopg.errors.CheckViolation as exc:
        # K5a-fix (finding 10): SQL saw facts the checks above did not; nothing was linked.
        reason = link_refusal_reason(exc)
        message = (
            "The provider connection is not admitted for money now"
            if reason == "not_admitted"
            else "The provider facts changed; reload and compare again"
        )
        raise ProviderLinkMismatchError(message, reason=reason) from exc
    summary = await load_operation(conn, business_id, book_id, operation_id)
    recorded = await _link(conn, business_id, operation_id)
    if summary is None or recorded is None:
        raise DatabaseUnavailableError("The provider link is unavailable")
    return ProviderLinkResult(
        business_id=business_id, book_id=book_id, operation=summary, link=recorded
    )


def _item(row: tuple[Any, ...]) -> ProviderAttentionItem:
    return ProviderAttentionItem(
        event_id=row[0],
        connection_id=row[1],
        kind="undecided" if row[4] is None else "no_operation",
        event_type=row[2],
        object_id=row[8],
        created=_created(row[3]),
        reason=row[4],
        acknowledgement=None
        if row[5] is None
        else ProviderAcknowledgementView(
            note=row[5], acknowledged_by=row[6], acknowledged_at=row[7]
        ),
    )


async def list_attention(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> ProviderAttentionList:
    await ledger.require_book(conn, business_id, book_id)
    await assert_provider_receipt_ready(conn)
    rows = await (
        await conn.execute(
            _ATTENTION + "and (%s::uuid is null or e.id>%s) order by e.id limit %s",
            (business_id, book_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_item(tuple(row)) for row in rows[:limit])
    return ProviderAttentionList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].event_id if len(rows) > limit else None,
    )


async def _attention_item(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, event_id: UUID
) -> ProviderAttentionItem | None:
    row = await (
        await conn.execute(_ATTENTION + "and e.id=%s", (business_id, book_id, event_id))
    ).fetchone()
    return None if row is None else _item(tuple(row))


async def acknowledge(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    event_id: UUID,
    user_id: UUID,
    body: ProviderAcknowledgeInput,
) -> ProviderAcknowledgementResult:
    """Record once; the same note again returns the record, another note is refused."""
    await require_workflow(conn, business_id)
    await ledger.require_book(conn, business_id, book_id)
    await assert_provider_receipt_ready(conn)
    item = await _attention_item(conn, business_id, book_id, event_id)
    if item is None:
        known = await (
            await conn.execute(
                "select 1 from gba.provider_event_inbox e "
                "join gba.provider_receipt_connections c "
                "on c.tenant_id=e.tenant_id and c.id=e.connection_id "
                "where e.tenant_id=%s and c.book_id=%s and e.id=%s and exists(select 1 "
                "from gba.provider_event_attestations a "
                "where a.tenant_id=e.tenant_id and a.event_id=e.id)",
                (business_id, book_id, event_id),
            )
        ).fetchone()
        if known is None:
            raise NotFoundError("Provider event not found")
        raise ProviderAttentionNotNeededError(
            "This event belongs to a provider operation", reason="operation"
        )
    if item.kind == "undecided":
        raise ProviderAttentionNotNeededError("This event is not decided yet", reason="undecided")
    if item.acknowledgement is None:
        try:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.provider_event_acknowledgements "
                    "(tenant_id,event_id,note,created_by) values (%s,%s,%s,%s)",
                    (business_id, event_id, body.note, user_id),
                )
        except psycopg.errors.UniqueViolation:
            pass  # Another request recorded it first; compare its note below.
        except psycopg.errors.CheckViolation as exc:
            # K5a-fix (finding 10): SQL decides that this event takes no acknowledgement.
            raise ProviderAttentionNotNeededError(
                "This event takes no acknowledgement; reload to see its decision", reason="facts"
            ) from exc
        item = await _attention_item(conn, business_id, book_id, event_id)
        if item is None or item.acknowledgement is None:
            raise DatabaseUnavailableError("The acknowledgement is unavailable")
    if item.acknowledgement.note != body.note:
        raise ProviderAttentionAcknowledgedError(
            "This event was already acknowledged with another note"
        )
    return ProviderAcknowledgementResult(business_id=business_id, book_id=book_id, item=item)
