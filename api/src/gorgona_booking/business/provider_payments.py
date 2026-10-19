"""K3a: observed provider operations ready to confirm a reserved H settlement (ADR-0027).

A finance user applies one operation the receipt worker decided as a success (owner decisions
2026-10-17). Its amount, currency and date are the attested facts; its money goes to the one
clearing account registered for its connection. SQL rechecks everything where it is applied
(`gba.assert_provider_payment`); these reads give the same answer as typed refusals.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from uuid import UUID

from gorgona_booking.business import ledger
from gorgona_booking.business.financial_documents import (
    FinancialDocumentStateError,
    require_workflow,
)
from gorgona_booking.business.ledger_contracts import from_minor
from gorgona_booking.business.settlement_contracts import (
    ProviderClearingAccountInput,
    ProviderClearingAccountSummary,
    ProviderClearingAccountView,
    ProviderConnectionList,
    ProviderConnectionSummary,
    ProviderOperationKind,
    ProviderOperationList,
    ProviderOperationState,
    ProviderOperationSummary,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.errors import ConflictError, DatabaseUnavailableError, NotFoundError

# Owner decision 3: USD only; Stripe states USD in cents, as gba.currencies does.
CURRENCY = "USD"
# The identity of a provider payment in H: this alias and the provider object ID.
SOURCE_ALIAS = "stripe_connect"
NotReady = Literal["revoked", "pending", "needs_review", "delivery_conflict", "not_final"]


class ProviderOperationNotReadyError(ConflictError):
    code = "PROVIDER_OPERATION_NOT_READY"


class ProviderOperationAppliedError(ConflictError):
    code = "PROVIDER_OPERATION_APPLIED"


class ProviderPaymentMismatchError(ConflictError):
    code = "PROVIDER_PAYMENT_MISMATCH"


class ProviderClearingAccountRequiredError(ConflictError):
    code = "PROVIDER_CLEARING_ACCOUNT_REQUIRED"


class ProviderClearingAccountRegisteredError(ConflictError):
    code = "PROVIDER_CLEARING_ACCOUNT_REGISTERED"


class ProviderPaymentLinkRequiredError(ConflictError):
    """An earlier manual payment names this provider object; linking it is a later slice."""

    code = "PROVIDER_PAYMENT_LINK_REQUIRED"


@dataclass(frozen=True)
class ObservedOperation:
    operation_id: UUID
    connection_id: UUID
    kind: ProviderOperationKind
    provider_object_id: str
    parent_object_id: str | None
    currency: str
    amount_minor: int
    actual_date: date


# One row per operation `o` of connection `c`: what its attested events and decisions say.
_FACTS = (
    "o.id,o.connection_id,o.kind,o.provider_object_id,o.parent_object_id,"
    "pg_catalog.upper(o.currency),o.created_at,"
    "exists(select 1 from gba.provider_event_inbox e "
    "cross join lateral gba.provider_receipt_operation(e.facts) f "
    "where e.tenant_id=o.tenant_id and e.connection_id=o.connection_id and f.kind=o.kind "
    "and f.object_id=o.provider_object_id and exists(select 1 from "
    "gba.provider_event_attestations a where a.tenant_id=e.tenant_id and a.event_id=e.id) "
    "and not exists(select 1 from gba.provider_event_decisions d "
    "where d.tenant_id=e.tenant_id and d.event_id=e.id)),"
    "exists(select 1 from gba.provider_event_decisions d where d.tenant_id=o.tenant_id "
    "and d.operation_id=o.id and d.outcome='needs_review'),"
    "exists(select 1 from gba.provider_event_decisions d join gba.provider_event_deliveries x "
    "on x.tenant_id=d.tenant_id and x.event_id=d.event_id where d.tenant_id=o.tenant_id "
    "and d.operation_id=o.id and not x.matches_original),"
    "c.revoked or exists(select 1 from gba.provider_event_decisions d "
    "join gba.provider_event_attestations a on a.tenant_id=d.tenant_id and a.event_id=d.event_id "
    "join gba.provider_verification_configs v on v.tenant_id=a.tenant_id "
    "and v.id=a.verification_config_id where d.tenant_id=o.tenant_id and d.operation_id=o.id "
    "and (v.revoked or a.book_id<>c.book_id)),"
    "s.amount,s.happened,k.minor_units,"
    "(select v.payment_id from gba.external_payment_provenance v "
    "where v.tenant_id=o.tenant_id and v.operation_id=o.id) "
    "from gba.provider_operations o join gba.provider_receipt_connections c "
    "on c.tenant_id=o.tenant_id and c.id=o.connection_id "
    "left join lateral (select (gba.provider_receipt_operation(e.facts)).amount_minor as amount,"
    "(pg_catalog.to_timestamp((e.facts->>'created')::bigint) "
    "at time zone gba.business_timezone(o.tenant_id))::date as happened "
    "from gba.provider_event_decisions d join gba.provider_event_inbox e "
    "on e.tenant_id=d.tenant_id and e.id=d.event_id where d.tenant_id=o.tenant_id "
    "and d.operation_id=o.id and d.reason='success' "
    "order by (e.facts->>'created')::bigint,e.id limit 1) s on true "
    "left join gba.currencies k on k.code=pg_catalog.upper(o.currency) "
    "where o.tenant_id=%s and c.book_id=%s "
)


# The columns of `_FACTS`, named for the state below.
_NAMED = (
    ") f(id,connection_id,kind,provider_object_id,parent_object_id,currency,created_at,"
    "pending,review,delivery,revoked,amount,happened,minor_units,payment_id) "
)
# One state per operation, in SQL so that a state filter is complete across cursor pages. The
# order matches the refusal reasons of `observed`.
_STATE = (
    "case when f.payment_id is not null then case when f.review or f.delivery "
    "then 'applied_with_conflict' else 'applied' end when f.revoked then 'revoked' "
    "when f.pending then 'pending' when f.review or f.delivery then 'needs_review' "
    "when f.amount is null then 'not_final' else 'observed' end"
)


def _summary(row: tuple[Any, ...]) -> ProviderOperationSummary:
    amount, scale = row[11], row[13]
    return ProviderOperationSummary(
        operation_id=row[0],
        connection_id=row[1],
        kind=row[2],
        provider_object_id=row[3],
        parent_object_id=row[4],
        currency=row[5],
        amount=None if amount is None or scale is None else from_minor(int(amount), scale),
        state=row[15],
        payment_id=row[14],
        created_at=row[6],
    )


async def list_operations(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    after: UUID | None,
    limit: int,
    state: ProviderOperationState | None = None,
) -> ProviderOperationList:
    await ledger.require_book(conn, business_id, book_id)
    await assert_provider_receipt_ready(conn)
    rows = await (
        await conn.execute(
            # Fixed fragments only; every value is a parameter.
            "select f.*," + _STATE + " from (select " + _FACTS + _NAMED + "where "  # noqa: S608
            "(%s::text is null or " + _STATE + "=%s) and (%s::uuid is null or f.id>%s) "
            "order by f.id limit %s",
            (business_id, book_id, state, state, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_summary(tuple(row)) for row in rows[:limit])
    return ProviderOperationList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].operation_id if len(rows) > limit else None,
    )


async def load_operation(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, operation_id: UUID
) -> ProviderOperationSummary | None:
    """One operation of the book with its state, as the list shows it (K4b)."""
    row = await (
        await conn.execute(
            # Fixed fragments only; every value is a parameter.
            "select f.*," + _STATE + " from (select " + _FACTS + _NAMED + "where f.id=%s",  # noqa: S608
            (business_id, book_id, operation_id),
        )
    ).fetchone()
    return None if row is None else _summary(tuple(row))


async def list_connections(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> ProviderConnectionList:
    """The book's connections and their clearing accounts: identifiers only, no key material."""
    await ledger.require_book(conn, business_id, book_id)
    await assert_provider_receipt_ready(conn)
    rows = await (
        await conn.execute(
            "select c.id,c.account_id,c.revoked,a.account_id,a.created_by,a.created_at "
            "from gba.provider_receipt_connections c left join gba.provider_clearing_accounts a "
            "on a.tenant_id=c.tenant_id and a.connection_id=c.id and a.book_id=c.book_id "
            "where c.tenant_id=%s and c.book_id=%s and (%s::uuid is null or c.id>%s) "
            "order by c.id limit %s",
            (business_id, book_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        ProviderConnectionSummary(
            connection_id=row[0],
            account_id=row[1],
            revoked=row[2],
            clearing_account=None
            if row[3] is None
            else ProviderClearingAccountSummary(
                account_id=row[3], registered_by=row[4], registered_at=row[5]
            ),
        )
        for row in rows[:limit]
    )
    return ProviderConnectionList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].connection_id if len(rows) > limit else None,
    )


async def observed(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, operation_id: UUID
) -> ObservedOperation:
    """Lock the operation, then read its committed facts: a decision in progress is seen."""
    await assert_provider_receipt_ready(conn)
    locked = await (
        await conn.execute(
            "select o.id from gba.provider_operations o join gba.provider_receipt_connections c "
            "on c.tenant_id=o.tenant_id and c.id=o.connection_id "
            "where o.tenant_id=%s and o.id=%s and c.book_id=%s for update of o",
            (business_id, operation_id, book_id),
        )
    ).fetchone()
    if locked is None:
        raise NotFoundError("Provider operation not found")
    # A new statement: it sees what a worker committed while this one waited for the lock.
    row = await (
        await conn.execute(
            "select " + _FACTS + "and o.id=%s",
            (business_id, book_id, operation_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Provider operation not found")
    values = tuple(row)
    if values[14] is not None:
        raise ProviderOperationAppliedError(
            "This provider operation already moved money", payment_id=str(values[14])
        )
    reason: NotReady | None = (
        "revoked"
        if values[10]
        else "pending"
        if values[7]
        else "needs_review"
        if values[8]
        else "delivery_conflict"
        if values[9]
        else "not_final"
        if values[11] is None
        else None
    )
    if reason is not None:
        raise ProviderOperationNotReadyError(
            "This provider operation cannot move money yet", reason=reason
        )
    return ObservedOperation(
        operation_id=values[0],
        connection_id=values[1],
        kind=values[2],
        provider_object_id=values[3],
        parent_object_id=values[4],
        currency=values[5],
        amount_minor=int(values[11]),
        actual_date=values[12],
    )


async def clearing_account(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, connection_id: UUID
) -> ProviderClearingAccountView | None:
    row = await (
        await conn.execute(
            "select account_id,created_by,created_at from gba.provider_clearing_accounts "
            "where tenant_id=%s and book_id=%s and connection_id=%s",
            (business_id, book_id, connection_id),
        )
    ).fetchone()
    if row is None:
        return None
    return ProviderClearingAccountView(
        business_id=business_id,
        book_id=book_id,
        connection_id=connection_id,
        account_id=row[0],
        registered_by=row[1],
        registered_at=row[2],
    )


async def register_clearing_account(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    connection_id: UUID,
    user_id: UUID,
    body: ProviderClearingAccountInput,
) -> ProviderClearingAccountView:
    """Register once (owner decision 2); the same account again returns the registration."""
    await require_workflow(conn, business_id)
    await ledger.require_book(conn, business_id, book_id)
    current = await clearing_account(conn, business_id, book_id, connection_id)
    if current is not None:
        if current.account_id == body.account_id:
            return current
        raise ProviderClearingAccountRegisteredError(
            "This connection already has its clearing account", account_id=str(current.account_id)
        )
    connection = await (
        await conn.execute(
            "select revoked from gba.provider_receipt_connections "
            "where tenant_id=%s and id=%s and book_id=%s",
            (business_id, connection_id, book_id),
        )
    ).fetchone()
    if connection is None:
        raise NotFoundError("Provider connection not found")
    if connection[0]:
        raise FinancialDocumentStateError("A revoked connection takes no clearing account")
    usable = await (
        await conn.execute(
            "select 1 from gba.ledger_accounts a join gba.ledger_account_versions v "
            "on v.tenant_id=a.tenant_id and v.account_id=a.id "
            "where a.tenant_id=%s and a.book_id=%s and a.id=%s and a.type='asset' "
            "and not v.archived and v.revision=(select max(x.revision) "
            "from gba.ledger_account_versions x where x.tenant_id=a.tenant_id "
            "and x.account_id=a.id) and not exists (select 1 from gba.financial_obligations o "
            "where o.tenant_id=a.tenant_id and o.book_id=a.book_id "
            "and o.control_account_id=a.id)",
            (business_id, book_id, body.account_id),
        )
    ).fetchone()
    if usable is None:
        raise FinancialDocumentStateError(
            "A clearing account is an open asset account and never a control account"
        )
    async with conn.transaction():
        await conn.execute(
            "insert into gba.provider_clearing_accounts "
            "(tenant_id,connection_id,book_id,account_id,created_by) values (%s,%s,%s,%s,%s)",
            (business_id, connection_id, book_id, body.account_id, user_id),
        )
    registered = await clearing_account(conn, business_id, book_id, connection_id)
    if registered is None:
        raise DatabaseUnavailableError("The registered clearing account is unavailable")
    return registered
