"""H2 settlement documents: prepared, approved, reserved, released or cancelled.

No money moves here. A reserve holds part of an obligation so that two documents
cannot plan the same amount: the cap P + C + R <= A is checked under the ledger
lock and again by SQL at commit. A sent or unknown outcome is never released by
time, module state or a lost response, only by an explicit attested resolution.

A confirmation records a fact a human attests about money that moved outside this
program. It moves exactly its allocations from the reserve to confirmed money, posts
one balanced G journal and binds a permanent external identity to one payment.

A void or a correction is a new revision of that payment, never an edit: it reverses
the journal of the version it replaces, returns those allocations to the reserve and,
for a correction, confirms the replacement within that reserve. P and R follow the
latest revision. A payment another fact depends on needs a separate reconciliation.
"""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid7

from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    SerializationFailure,
    UniqueViolation,
)
from pydantic import ValidationError

from gorgona_booking.business import commands, financial_commands, ledger
from gorgona_booking.business.financial_commands import Reference
from gorgona_booking.business.financial_contracts import FinancialCommandKind
from gorgona_booking.business.financial_documents import (
    FEATURE,
    FinancialDocumentStateError,
    require_workflow,
)
from gorgona_booking.business.financial_math import (
    FinancialAmountError,
    FinancialBalance,
    FinancialCapError,
    correct_confirmation,
    reserve,
)
from gorgona_booking.business.financial_math import confirm as confirm_reserved
from gorgona_booking.business.ledger_contracts import (
    LineInput,
    PaymentCorrectionPosting,
    PaymentPosting,
    from_minor,
    to_minor,
)
from gorgona_booking.business.module_gate import FINANCE_MODULE, module_writes
from gorgona_booking.business.settlement_contracts import (
    ObligationList,
    ObligationSummary,
    ObligationView,
    PaymentAllocationView,
    PaymentConfirmInput,
    PaymentCorrectInput,
    PaymentRevisionView,
    PaymentState,
    PaymentView,
    PaymentVoidInput,
    SettlementAction,
    SettlementActionInput,
    SettlementAllocationView,
    SettlementCancelInput,
    SettlementEventKind,
    SettlementEventView,
    SettlementList,
    SettlementPrepareInput,
    SettlementReceipt,
    SettlementReleaseInput,
    SettlementStatus,
    SettlementSummary,
    SettlementView,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DatabaseUnavailableError,
    InvalidReferenceError,
    NotFoundError,
)

_CONSTRAINTS = ", ".join(
    "gba." + name
    for name in (
        "settlement_documents_consistent",
        "settlement_allocations_consistent",
        "settlement_events_consistent",
        "settlement_command_receipts_consistent",
        "external_payments_consistent",
        "external_payment_allocations_consistent",
        "external_payments_entry_fk",
        "external_payment_revisions_consistent",
        "external_payment_revision_allocations_consistent",
        "external_payment_revisions_reversal_fk",
        "external_payment_revisions_entry_fk",
        "journal_entries_payment_consistent",
        "journal_lines_payment_consistent",
        "journal_entries_invoice_consistent",
        "journal_lines_invoice_consistent",
        "journal_entries_balanced",
        "journal_lines_balanced",
    )
)
_ACTIONS: dict[SettlementAction, tuple[FinancialCommandKind, SettlementEventKind]] = {
    "approve": ("settlement_approve", "approved"),
    "reserve": ("settlement_reserve", "reserved"),
    "sent": ("settlement_sent", "sent"),
    "release": ("settlement_release", "released"),
    "cancel": ("settlement_cancel", "cancelled"),
}
# The same order as gba.enforce_settlement_event; SQL is the final arbiter.
_FOLLOWS: dict[SettlementEventKind, tuple[SettlementStatus, ...]] = {
    "prepared": (),
    "approved": ("prepared",),
    "reserved": ("approved",),
    "sent": ("reserved",),
    "confirmed": ("reserved", "sent"),
    "released": ("reserved", "sent"),
    "cancelled": ("prepared", "approved"),
    # A released reserve is gone, so its payments can only be voided.
    "payment_voided": ("reserved", "sent", "released"),
    "payment_corrected": ("reserved", "sent"),
}
# Facts in the order gba.settlement_phase reads them: the strongest present wins.
_PHASES: tuple[SettlementStatus, ...] = (
    "cancelled",
    "released",
    "sent",
    "reserved",
    "approved",
    "prepared",
)
_HOLDING: tuple[SettlementStatus, ...] = ("reserved", "sent")
_OBLIGATION = (
    "select o.id,o.source_kind,o.source_id,o.source_revision,o.component,o.counterparty_id,"
    "o.counterparty_revision,o.direction,o.currency,c.minor_units,o.control_account_id,"
    "o.created_at,b.principal_minor,b.paid_minor,b.credited_minor,b.reserved_minor "
    "from gba.financial_obligations o join gba.currencies c on c.code=o.currency "
    "cross join lateral gba.obligation_balance(o.tenant_id,o.book_id,o.id) b "
    "where o.tenant_id=%s and o.book_id=%s "
)


class FinancialOutcomeUnresolvedError(ConflictError):
    code = "FINANCIAL_OUTCOME_UNRESOLVED"


class FinancialSourceRecordedError(ConflictError):
    code = "FINANCIAL_SOURCE_ALREADY_RECORDED"


class FinancialReconciliationRequiredError(ConflictError):
    """Another recorded fact depends on this payment; nothing was changed."""

    code = "FINANCIAL_RECONCILIATION_REQUIRED"


async def _flush(conn: RuntimeConnection) -> None:
    await conn.execute("set constraints " + _CONSTRAINTS + " immediate")
    await conn.execute("set constraints " + _CONSTRAINTS + " deferred")


@asynccontextmanager
async def _writes(conn: RuntimeConnection) -> AsyncIterator[None]:
    try:
        async with module_writes(FINANCE_MODULE, FEATURE), conn.transaction():
            yield
            await _flush(conn)
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError(
            "Every settlement reference must belong to this company and book"
        ) from exc
    except (CheckViolation, UniqueViolation) as exc:
        raise FinancialDocumentStateError(
            "Settlement or obligation changed; reload before continuing"
        ) from exc
    except SerializationFailure as exc:
        raise DatabaseUnavailableError("Financial transaction settings are not ready") from exc


def _receipt(reference: Reference) -> SettlementReceipt:
    return SettlementReceipt(
        book_id=reference.book_id,
        settlement_id=reference.subject_id,
        sequence=reference.revision,
    )


def _balance(row: Sequence[Any]) -> FinancialBalance:
    try:
        return FinancialBalance(
            principal_minor=row[0], paid_minor=row[1], credited_minor=row[2], reserved_minor=row[3]
        )
    except ValidationError as exc:
        raise DatabaseUnavailableError("A stored obligation balance is inconsistent") from exc


def _obligation(row: Sequence[Any]) -> ObligationSummary:
    balance, scale = _balance(row[12:16]), row[9]
    return ObligationSummary(
        obligation_id=row[0],
        source_kind=row[1],
        source_id=row[2],
        source_revision=row[3],
        component=row[4],
        counterparty_id=row[5],
        counterparty_revision=row[6],
        direction=row[7],
        currency=row[8],
        minor_units=scale,
        control_account_id=row[10],
        principal=from_minor(balance.principal_minor, scale),
        paid=from_minor(balance.paid_minor, scale),
        credited=from_minor(balance.credited_minor, scale),
        reserved=from_minor(balance.reserved_minor, scale),
        available=from_minor(balance.available_minor, scale),
        created_at=row[11],
    )


async def list_obligations(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> ObligationList:
    await ledger.require_book(conn, business_id, book_id)
    rows = await (
        await conn.execute(
            _OBLIGATION + "and (%s::uuid is null or o.id>%s) order by o.id limit %s",
            (business_id, book_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_obligation(row) for row in rows[:limit])
    return ObligationList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].obligation_id if len(rows) > limit else None,
    )


async def load_obligation(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, obligation_id: UUID
) -> ObligationView | None:
    row = await (
        await conn.execute(_OBLIGATION + "and o.id=%s", (business_id, book_id, obligation_id))
    ).fetchone()
    if row is None:
        return None
    return ObligationView(business_id=business_id, book_id=book_id, **_obligation(row).model_dump())


async def _effective(
    conn: RuntimeConnection, business: UUID, book: UUID, settlement: UUID, bound: int
) -> tuple[dict[int, UUID], dict[UUID, int]]:
    """Payments by the event that recorded each version, and effective confirmed money
    per obligation, as the facts stood after event `bound`."""
    versions = await (
        await conn.execute(
            "select p.id,1,p.sequence from gba.external_payments p "
            "where p.tenant_id=%s and p.book_id=%s and p.settlement_id=%s "
            "union all select r.payment_id,r.revision,r.sequence "
            "from gba.external_payment_revisions r "
            "where r.tenant_id=%s and r.book_id=%s and r.settlement_id=%s",
            (business, book, settlement) * 2,
        )
    ).fetchall()
    allocated = await (
        await conn.execute(
            "select p.id,1,a.obligation_id,a.amount_minor from gba.external_payments p "
            "join gba.external_payment_allocations a on a.tenant_id=p.tenant_id "
            "and a.book_id=p.book_id and a.payment_id=p.id "
            "where p.tenant_id=%s and p.book_id=%s and p.settlement_id=%s "
            "union all select r.payment_id,r.revision,a.obligation_id,a.amount_minor "
            "from gba.external_payment_revisions r "
            "join gba.external_payment_revision_allocations a on a.tenant_id=r.tenant_id "
            "and a.book_id=r.book_id and a.payment_id=r.payment_id and a.revision=r.revision "
            "where r.tenant_id=%s and r.book_id=%s and r.settlement_id=%s",
            (business, book, settlement) * 2,
        )
    ).fetchall()
    payments: dict[int, UUID] = {}
    latest: dict[UUID, int] = {}
    for payment, revision, recorded in versions:
        if recorded <= bound:
            payments[recorded] = payment
            latest[payment] = max(latest.get(payment, 0), revision)
    confirmed: dict[UUID, int] = {}
    for payment, revision, obligation, amount in allocated:
        if latest.get(payment) == revision:
            confirmed[obligation] = confirmed.get(obligation, 0) + amount
    return payments, confirmed


def _phase(kinds: Sequence[str]) -> SettlementStatus:
    return next(phase for phase in _PHASES if phase in kinds)


def _status(phase: SettlementStatus, total: int, confirmed: int) -> SettlementStatus:
    """A held reserve reads as (partially) confirmed once its payments say so."""
    if phase not in _HOLDING or confirmed == 0:
        return phase
    return "confirmed" if confirmed == total else "partially_confirmed"


async def load_settlement(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    *,
    sequence: int | None = None,
) -> SettlementView | None:
    """The document as its facts stood after `sequence`; the latest when omitted."""
    document = await (
        await conn.execute(
            "select d.direction,d.counterparty_id,d.currency,c.minor_units,d.created_by,"
            "d.created_at from gba.settlement_documents d "
            "join gba.currencies c on c.code=d.currency "
            "where d.tenant_id=%s and d.book_id=%s and d.id=%s",
            (business_id, book_id, settlement_id),
        )
    ).fetchone()
    if document is None:
        return None
    events = await (
        await conn.execute(
            "select sequence,kind,created_by,created_at,resolution,reason,evidence_source "
            "from gba.settlement_events where tenant_id=%s and book_id=%s and settlement_id=%s "
            "and (%s::integer is null or sequence<=%s) order by sequence",
            (business_id, book_id, settlement_id, sequence, sequence),
        )
    ).fetchall()
    lines = await (
        await conn.execute(
            "select obligation_id,amount_minor from gba.settlement_allocations "
            "where tenant_id=%s and book_id=%s and settlement_id=%s order by line_no",
            (business_id, book_id, settlement_id),
        )
    ).fetchall()
    if not events or not lines:
        return None
    payments, confirmed = await _effective(conn, business_id, book_id, settlement_id, events[-1][0])
    scale = document[3]
    phase = _phase([event[1] for event in events])
    held = phase in _HOLDING
    approved_by = next((event[2] for event in events if event[1] == "approved"), None)
    total = sum(line[1] for line in lines)
    settled = sum(confirmed.values())
    return SettlementView(
        business_id=business_id,
        book_id=book_id,
        settlement_id=settlement_id,
        sequence=events[-1][0],
        status=_status(phase, total, settled),
        direction=document[0],
        counterparty_id=document[1],
        currency=document[2],
        minor_units=scale,
        total=from_minor(total, scale),
        confirmed=from_minor(settled, scale),
        reserved=from_minor(total - settled if held else 0, scale),
        prepared_by=document[4],
        approved_by=approved_by,
        approved_by_preparer=None if approved_by is None else approved_by == document[4],
        outcome_unresolved=phase == "sent" and settled < total,
        allocations=tuple(
            SettlementAllocationView(
                obligation_id=line[0],
                amount=from_minor(line[1], scale),
                confirmed=from_minor(confirmed.get(line[0], 0), scale),
                reserved=from_minor(line[1] - confirmed.get(line[0], 0) if held else 0, scale),
            )
            for line in lines
        ),
        events=tuple(
            SettlementEventView(
                sequence=event[0],
                kind=event[1],
                created_by=event[2],
                created_at=event[3],
                resolution=event[4],
                reason=event[5],
                evidence_source=event[6],
                payment_id=payments.get(event[0]),
            )
            for event in events
        ),
        created_at=document[5],
    )


async def list_settlements(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> SettlementList:
    await ledger.require_book(conn, business_id, book_id)
    rows = await (
        await conn.execute(
            "select d.id,d.direction,d.counterparty_id,d.currency,c.minor_units,d.created_at,"
            "(select max(e.sequence) from gba.settlement_events e where e.tenant_id=d.tenant_id "
            "and e.book_id=d.book_id and e.settlement_id=d.id),"
            "gba.settlement_phase(d.tenant_id,d.book_id,d.id),"
            "(select coalesce(sum(a.amount_minor),0) from gba.settlement_allocations a "
            "where a.tenant_id=d.tenant_id and a.book_id=d.book_id and a.settlement_id=d.id),"
            "(select coalesce(sum(e.amount_minor),0) from "
            "gba.effective_payment_allocations(d.tenant_id,d.book_id,null::uuid,d.id) e) "
            "from gba.settlement_documents d join gba.currencies c on c.code=d.currency "
            "where d.tenant_id=%s and d.book_id=%s and (%s::uuid is null or d.id>%s) "
            "order by d.id limit %s",
            (business_id, book_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        SettlementSummary(
            settlement_id=row[0],
            sequence=row[6],
            status=_status(row[7], int(row[8]), int(row[9])),
            direction=row[1],
            counterparty_id=row[2],
            currency=row[3],
            total=from_minor(int(row[8]), row[4]),
            confirmed=from_minor(int(row[9]), row[4]),
            reserved=from_minor(int(row[8]) - int(row[9]) if row[7] in _HOLDING else 0, row[4]),
            created_at=row[5],
        )
        for row in rows[:limit]
    )
    return SettlementList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].settlement_id if len(rows) > limit else None,
    )


async def _view(conn: RuntimeConnection, business: UUID, reference: Reference) -> SettlementView:
    result = await load_settlement(
        conn, business, reference.book_id, reference.subject_id, sequence=reference.revision
    )
    if result is None or result.sequence != reference.revision:
        raise DatabaseUnavailableError("The stored settlement event is missing")
    return result


async def _claim(
    conn: RuntimeConnection,
    business: UUID,
    actor: str,
    operation: FinancialCommandKind,
    key: str,
    digest: str,
) -> Reference | None:
    return await financial_commands.claim(
        conn,
        business=business,
        actor=actor,
        operation=operation,
        key=key,
        request_hash=digest,
        model=SettlementReceipt,
        receipt=_receipt,
    )


async def _event(
    conn: RuntimeConnection,
    business: UUID,
    reference: Reference,
    kind: SettlementEventKind,
    user: UUID,
    *,
    resolution: str | None = None,
    reason: str | None = None,
    evidence_source: str | None = None,
) -> None:
    await conn.execute(
        "insert into gba.settlement_events (tenant_id,book_id,settlement_id,sequence,kind,"
        "resolution,reason,evidence_source,created_by) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            business,
            reference.book_id,
            reference.subject_id,
            reference.revision,
            kind,
            resolution,
            reason,
            evidence_source,
            user,
        ),
    )


async def prepare(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: SettlementPrepareInput,
) -> SettlementView:
    """Create the immutable document and its planned allocations; nothing is held yet."""
    digest = commands.fingerprint(
        {
            "book_id": str(book_id),
            "settlement_id": str(settlement_id),
            **body.model_dump(mode="json"),
        }
    )
    prior = await _claim(conn, business_id, actor, "settlement_prepare", key, digest)
    if prior is not None:
        return await _view(conn, business_id, prior)
    await require_workflow(conn, business_id)
    await ledger.require_book(conn, business_id, book_id)
    current = await load_settlement(conn, business_id, book_id, settlement_id)
    if current is not None:
        raise ConflictError("This settlement already exists; reload", sequence=current.sequence)
    ids = [line.obligation_id for line in body.allocations]
    rows = await (
        await conn.execute(
            "select id,principal_minor from gba.financial_obligations where tenant_id=%s "
            "and book_id=%s and id=any(%s::uuid[]) and counterparty_id=%s and direction=%s "
            "and currency=%s",
            (business_id, book_id, ids, body.counterparty_id, body.direction, body.currency),
        )
    ).fetchall()
    principals = {row[0]: row[1] for row in rows}
    if set(principals) != set(ids):
        raise FinancialDocumentStateError(
            "Every obligation must belong to this book, counterparty, direction and currency"
        )
    scale = await (
        await conn.execute("select minor_units from gba.currencies where code=%s", (body.currency,))
    ).fetchone()
    if scale is None:
        raise InvalidReferenceError("Unknown currency", field="currency")
    amounts: list[int] = []
    for number, line in enumerate(body.allocations, 1):
        try:
            amounts.append(to_minor(line.amount, scale[0]))
        except ValueError as exc:
            raise FinancialAmountError(str(exc), line=number, currency=body.currency) from exc
        if amounts[-1] > principals[line.obligation_id]:
            raise FinancialCapError("A planned allocation exceeds the obligation principal")
    reference = Reference(book_id, settlement_id, 1)
    async with _writes(conn):
        await conn.execute(
            "insert into gba.settlement_documents "
            "(tenant_id,book_id,id,direction,counterparty_id,currency,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s)",
            (
                business_id,
                book_id,
                settlement_id,
                body.direction,
                body.counterparty_id,
                body.currency,
                user_id,
            ),
        )
        await conn.execute(
            "insert into gba.settlement_allocations "
            "(tenant_id,book_id,settlement_id,line_no,obligation_id,amount_minor) "
            "select %s,%s,%s,l.n::smallint,l.obligation,l.amount "
            "from unnest(%s::uuid[],%s::bigint[]) with ordinality as l(obligation,amount,n)",
            (business_id, book_id, settlement_id, ids, amounts),
        )
        await _event(conn, business_id, reference, "prepared", user_id)
        await financial_commands.complete(
            conn,
            business=business_id,
            actor=actor,
            user=user_id,
            operation="settlement_prepare",
            key=key,
            request_hash=digest,
            reference=reference,
            receipt=_receipt(reference),
            flush=_flush,
        )
    return await _view(conn, business_id, reference)


async def act(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    action: SettlementAction,
    body: SettlementActionInput,
) -> SettlementView:
    """Record the next fact of a settlement; only `reserve` changes what is held."""
    operation, kind = _ACTIONS[action]
    digest = commands.fingerprint(
        {
            "book_id": str(book_id),
            "settlement_id": str(settlement_id),
            **body.model_dump(mode="json"),
        }
    )
    prior = await _claim(conn, business_id, actor, operation, key, digest)
    if prior is not None:
        return await _view(conn, business_id, prior)
    current = await load_settlement(conn, business_id, book_id, settlement_id)
    if current is None:
        raise NotFoundError("Settlement not found")
    if current.sequence != body.expected_sequence:
        raise ConflictError(
            "This settlement changed; reload before continuing", sequence=current.sequence
        )
    phase = _phase([event.kind for event in current.events])
    # A fully confirmed settlement is final: nothing remains to send or release.
    if current.status == "confirmed" or phase not in _FOLLOWS[kind]:
        raise FinancialDocumentStateError(f"A {current.status} settlement cannot be {kind}")
    release = body if isinstance(body, SettlementReleaseInput) else None
    resolution = release.resolution if release else None
    if kind == "released" and phase == "sent" and resolution is None:
        raise FinancialOutcomeUnresolvedError(
            "A sent settlement needs an attested outcome before its reserve is released"
        )
    if resolution is not None and phase != "sent":
        raise FinancialDocumentStateError("Only a sent settlement takes an attested resolution")
    # A plain release and a cancel move no money and stay possible while H is off.
    if kind in ("approved", "reserved", "sent") or resolution is not None:
        await require_workflow(conn, business_id)
    if kind == "reserved":
        for line in current.allocations:
            row = await (
                await conn.execute(
                    "select * from gba.obligation_balance(%s,%s,%s)",
                    (business_id, book_id, line.obligation_id),
                )
            ).fetchone()
            if row is None:
                raise DatabaseUnavailableError("A settled obligation is missing")
            reserve(_balance(row), to_minor(line.amount, current.minor_units))
    reference = Reference(book_id, settlement_id, current.sequence + 1)
    reason = (
        body.reason if isinstance(body, SettlementReleaseInput | SettlementCancelInput) else None
    )
    async with _writes(conn):
        await _event(
            conn,
            business_id,
            reference,
            kind,
            user_id,
            resolution=resolution,
            reason=reason,
            evidence_source=release.evidence_source if release else None,
        )
        await financial_commands.complete(
            conn,
            business=business_id,
            actor=actor,
            user=user_id,
            operation=operation,
            key=key,
            request_hash=digest,
            reference=reference,
            receipt=_receipt(reference),
            flush=_flush,
        )
    return await _view(conn, business_id, reference)


async def load_payment(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, payment_id: UUID
) -> PaymentView | None:
    row = await (
        await conn.execute(
            "select p.settlement_id,p.sequence,p.direction,p.currency,c.minor_units,"
            "p.amount_minor,p.actual_external_date,p.entry_date,p.cash_account_id,"
            "p.source_account_alias,p.external_reference,p.attestation,p.entry_id,"
            "p.created_by,p.created_at from gba.external_payments p "
            "join gba.currencies c on c.code=p.currency "
            "where p.tenant_id=%s and p.book_id=%s and p.id=%s",
            (business_id, book_id, payment_id),
        )
    ).fetchone()
    if row is None:
        return None
    lines = await (
        await conn.execute(
            "select obligation_id,amount_minor from gba.external_payment_allocations "
            "where tenant_id=%s and book_id=%s and payment_id=%s order by line_no",
            (business_id, book_id, payment_id),
        )
    ).fetchall()
    revised = await (
        await conn.execute(
            "select revision,sequence,kind,amount_minor,actual_external_date,entry_date,"
            "cash_account_id,attestation,reason,evidence_source,reversal_entry_id,entry_id,"
            "created_by,created_at from gba.external_payment_revisions "
            "where tenant_id=%s and book_id=%s and payment_id=%s order by revision",
            (business_id, book_id, payment_id),
        )
    ).fetchall()
    revised_lines = await (
        await conn.execute(
            "select revision,obligation_id,amount_minor "
            "from gba.external_payment_revision_allocations "
            "where tenant_id=%s and book_id=%s and payment_id=%s order by revision,line_no",
            (business_id, book_id, payment_id),
        )
    ).fetchall()
    scale = row[4]

    def allocation(line: Sequence[Any]) -> PaymentAllocationView:
        return PaymentAllocationView(obligation_id=line[0], amount=from_minor(line[1], scale))

    revisions = tuple(
        PaymentRevisionView(
            revision=r[0],
            sequence=r[1],
            kind=r[2],
            amount=None if r[3] is None else from_minor(r[3], scale),
            actual_external_date=r[4],
            entry_date=r[5],
            cash_account_id=r[6],
            attestation=r[7],
            reason=r[8],
            evidence_source=r[9],
            reversal_entry_id=r[10],
            entry_id=r[11],
            recorded_by=r[12],
            recorded_at=r[13],
            allocations=tuple(allocation(x[1:]) for x in revised_lines if x[0] == r[0]),
        )
        for r in revised
    )
    original = tuple(allocation(line) for line in lines)
    effective = revisions[-1].allocations if revisions else original
    state: PaymentState = (
        "confirmed"
        if not revisions
        else "voided"
        if revisions[-1].kind == "voided"
        else "corrected"
    )
    return PaymentView(
        business_id=business_id,
        book_id=book_id,
        payment_id=payment_id,
        settlement_id=row[0],
        sequence=row[1],
        direction=row[2],
        currency=row[3],
        minor_units=scale,
        amount=from_minor(row[5], scale),
        actual_external_date=row[6],
        entry_date=row[7],
        cash_account_id=row[8],
        source_account_alias=row[9],
        external_reference=row[10],
        attestation=row[11],
        entry_id=row[12],
        recorded_by=row[13],
        recorded_at=row[14],
        allocations=original,
        state=state,
        revision=revisions[-1].revision if revisions else 1,
        effective_amount=from_minor(sum(to_minor(line.amount, scale) for line in effective), scale),
        effective_allocations=effective,
        revisions=revisions,
    )


async def _require_attested_date(conn: RuntimeConnection, business: UUID, actual: date) -> None:
    """No external date after the business's own today, decided by the same SQL the
    trigger uses at the same instant; there is no provider time zone for an attestation."""
    today = await (
        await conn.execute(
            "select z,(pg_catalog.now() at time zone z)::date from gba.business_timezone(%s) z",
            (business,),
        )
    ).fetchone()
    if today is None:
        raise DatabaseUnavailableError("The business time zone is unavailable")
    if actual > today[1]:
        raise ledger.LedgerDateError(
            "An attested external date cannot be after today in the business time zone",
            timezone=today[0],
            today=today[1].isoformat(),
        )


async def _require_cash_not_control(
    conn: RuntimeConnection, business: UUID, book: UUID, cash: UUID
) -> None:
    """Cash and control accounts stay disjoint across the book, not only in one payment."""
    control_as_cash = await (
        await conn.execute(
            "select 1 from gba.financial_obligations where tenant_id=%s and book_id=%s "
            "and control_account_id=%s limit 1",
            (business, book, cash),
        )
    ).fetchone()
    if control_as_cash is not None:
        raise FinancialDocumentStateError("The cash account cannot be a financial control account")


async def _settlement_lines(
    conn: RuntimeConnection, business: UUID, book: UUID, settlement: UUID
) -> dict[UUID, tuple[UUID, int, int, date]]:
    """Per obligation: control account, planned amount, effective confirmed amount of
    this settlement and the date of the accrual it settles."""
    rows = await (
        await conn.execute(
            "select a.obligation_id,o.control_account_id,a.amount_minor,coalesce(("
            "select sum(e.amount_minor) from gba.effective_payment_allocations("
            "a.tenant_id,a.book_id,a.obligation_id,a.settlement_id) e),0),v.issued_on "
            "from gba.settlement_allocations a join gba.financial_obligations o "
            "on o.tenant_id=a.tenant_id and o.book_id=a.book_id and o.id=a.obligation_id "
            "join gba.financial_document_versions v on v.tenant_id=o.tenant_id "
            "and v.book_id=o.book_id and v.document_id=o.source_id "
            "and v.revision=o.source_revision "
            "where a.tenant_id=%s and a.book_id=%s and a.settlement_id=%s",
            (business, book, settlement),
        )
    ).fetchall()
    return {row[0]: (row[1], int(row[2]), int(row[3]), row[4]) for row in rows}


async def confirm(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    payment_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: PaymentConfirmInput,
) -> SettlementView:
    """Record one attested external payment against the reserve of this settlement.

    Exactly the allocated amounts move from reserve to confirmed money and one
    balanced journal is posted. The remainder stays reserved. The same external
    identity under another key or another settlement never posts a second time.
    """
    digest = commands.fingerprint(
        {
            "book_id": str(book_id),
            "settlement_id": str(settlement_id),
            "payment_id": str(payment_id),
            **body.model_dump(mode="json"),
        }
    )
    prior = await _claim(conn, business_id, actor, "settlement_confirm", key, digest)
    if prior is not None:
        return await _view(conn, business_id, prior)
    current = await load_settlement(conn, business_id, book_id, settlement_id)
    if current is None:
        raise NotFoundError("Settlement not found")
    if current.sequence != body.expected_sequence:
        raise ConflictError(
            "This settlement changed; reload before continuing", sequence=current.sequence
        )
    if current.status not in ("reserved", "sent", "partially_confirmed"):
        raise FinancialDocumentStateError(f"A {current.status} settlement cannot be confirmed")
    await require_workflow(conn, business_id)
    await _require_attested_date(conn, business_id, body.actual_external_date)
    # Case, compatibility forms and invisible characters never make a new fact; a
    # manual attestation has no provider contract, so interior whitespace is kept.
    recorded = await (
        await conn.execute(
            "select id from gba.external_payments where tenant_id=%s and book_id=%s "
            "and direction=%s and gba.external_identity_key(source_account_alias,'preserve')"
            "=gba.external_identity_key(%s,'preserve') "
            "and gba.external_identity_key(external_reference,'preserve')"
            "=gba.external_identity_key(%s,'preserve')",
            (
                business_id,
                book_id,
                current.direction,
                body.source_account_alias,
                body.external_reference,
            ),
        )
    ).fetchone()
    if recorded is not None:
        # Only the identifier: the caller already knows the reference it sent.
        raise FinancialSourceRecordedError(
            "This external payment was already recorded", payment_id=str(recorded[0])
        )
    used = await (
        await conn.execute(
            "select 1 from gba.external_payments where tenant_id=%s and book_id=%s and id=%s",
            (business_id, book_id, payment_id),
        )
    ).fetchone()
    if used is not None:
        raise FinancialDocumentStateError("This payment identifier is already used")
    scale = current.minor_units
    try:
        amount = to_minor(body.amount, scale)
    except ValueError as exc:
        raise FinancialAmountError(str(exc), currency=current.currency) from exc
    await _require_cash_not_control(conn, business_id, book_id, body.cash_account_id)
    held = await _settlement_lines(conn, business_id, book_id, settlement_id)
    amounts: list[int] = []
    controls: list[UUID] = []
    for number, line in enumerate(body.allocations, 1):
        if line.obligation_id not in held:
            raise FinancialDocumentStateError(
                "A confirmation allocates only to lines of its settlement"
            )
        try:
            value = to_minor(line.amount, scale)
        except ValueError as exc:
            raise FinancialAmountError(str(exc), line=number, currency=current.currency) from exc
        control, planned, confirmed, accrued = held[line.obligation_id]
        if value > planned - confirmed:
            raise FinancialCapError("Confirmation exceeds the reserved settlement line")
        if body.entry_date < accrued:
            raise ledger.LedgerDateError(
                "A payment cannot be posted before the accrual it settles", line=number
            )
        row = await (
            await conn.execute(
                "select * from gba.obligation_balance(%s,%s,%s)",
                (business_id, book_id, line.obligation_id),
            )
        ).fetchone()
        if row is None:
            raise DatabaseUnavailableError("A settled obligation is missing")
        confirm_reserved(_balance(row), value)
        amounts.append(value)
        controls.append(control)
    if sum(amounts) != amount:
        raise FinancialAmountError(
            "Allocations must equal the confirmed amount exactly", currency=current.currency
        )
    reference = Reference(book_id, settlement_id, current.sequence + 1)
    entry = uuid7()
    cash_side: Literal["debit", "credit"] = (
        "debit" if current.direction == "receivable" else "credit"
    )
    control_side: Literal["debit", "credit"] = "credit" if cash_side == "debit" else "debit"
    async with _writes(conn):
        await _event(conn, business_id, reference, "confirmed", user_id)
        await conn.execute(
            "insert into gba.external_payments (tenant_id,book_id,id,settlement_id,sequence,"
            "direction,currency,amount_minor,actual_external_date,entry_date,cash_account_id,"
            "source_account_alias,external_reference,attestation,entry_id,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                business_id,
                book_id,
                payment_id,
                settlement_id,
                reference.revision,
                current.direction,
                current.currency,
                amount,
                body.actual_external_date,
                body.entry_date,
                body.cash_account_id,
                body.source_account_alias,
                body.external_reference,
                body.attestation,
                entry,
                user_id,
            ),
        )
        await conn.execute(
            "insert into gba.external_payment_allocations "
            "(tenant_id,book_id,payment_id,line_no,obligation_id,amount_minor) "
            "select %s,%s,%s,l.n::smallint,l.obligation,l.amount "
            "from unnest(%s::uuid[],%s::bigint[]) with ordinality as l(obligation,amount,n)",
            (
                business_id,
                book_id,
                payment_id,
                [line.obligation_id for line in body.allocations],
                amounts,
            ),
        )
        await ledger.append_financial_journal(
            conn,
            business_id=business_id,
            book_id=book_id,
            entry_id=entry,
            user_id=user_id,
            body=PaymentPosting(
                entry_date=body.entry_date,
                currency=current.currency,
                source_id=str(payment_id),
                lines=(
                    LineInput(
                        account_id=body.cash_account_id,
                        side=cash_side,
                        amount=from_minor(amount, scale),
                    ),
                    *(
                        LineInput(
                            account_id=control, side=control_side, amount=from_minor(value, scale)
                        )
                        for control, value in zip(controls, amounts, strict=True)
                    ),
                ),
            ),
        )
        await financial_commands.complete(
            conn,
            business=business_id,
            actor=actor,
            user=user_id,
            operation="settlement_confirm",
            key=key,
            request_hash=digest,
            reference=reference,
            receipt=_receipt(reference),
            flush=_flush,
        )
    return await _view(conn, business_id, reference)


def _mirror(side: str) -> Literal["debit", "credit"]:
    return "credit" if side == "debit" else "debit"


async def _require_no_dependents(
    conn: RuntimeConnection, business: UUID, book: UUID, settlement: UUID, touched: list[UUID]
) -> None:
    """Refuse, without any effect, a payment another recorded fact depends on."""
    credited = await (
        await conn.execute(
            "select credited_obligation_id from gba.financial_document_versions "
            "where tenant_id=%s and book_id=%s and state='issued' "
            "and credited_obligation_id=any(%s::uuid[]) "
            "and not gba.credit_voided(tenant_id,book_id,document_id) limit 1",
            (business, book, touched),
        )
    ).fetchone()
    if credited is not None:
        raise FinancialReconciliationRequiredError(
            "An issued credit depends on this payment; reconcile it separately",
            obligation_id=str(credited[0]),
        )
    # A refund is never undone to make a correction possible.
    refund = await (
        await conn.execute(
            "select id from gba.financial_obligations where tenant_id=%s and book_id=%s "
            "and id=any(%s::uuid[]) and source_kind='credit_refund' limit 1",
            (business, book, touched),
        )
    ).fetchone()
    if refund is not None:
        raise FinancialReconciliationRequiredError(
            "A refund payment is reconciled separately", obligation_id=str(refund[0])
        )
    sent = await (
        await conn.execute(
            "select a.settlement_id from gba.settlement_allocations a "
            "where a.tenant_id=%s and a.book_id=%s and a.settlement_id<>%s "
            "and a.obligation_id=any(%s::uuid[]) "
            "and gba.settlement_phase(a.tenant_id,a.book_id,a.settlement_id)='sent' "
            "and (select sum(x.amount_minor) from gba.settlement_allocations x "
            "where x.tenant_id=a.tenant_id and x.book_id=a.book_id "
            "and x.settlement_id=a.settlement_id)>(select coalesce(sum(e.amount_minor),0) "
            "from gba.effective_payment_allocations(a.tenant_id,a.book_id,null::uuid,"
            "a.settlement_id) e) limit 1",
            (business, book, settlement, touched),
        )
    ).fetchone()
    if sent is not None:
        raise FinancialReconciliationRequiredError(
            "A settlement with an unknown sent outcome depends on this payment",
            settlement_id=str(sent[0]),
        )


async def _amend(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    payment_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: PaymentVoidInput,
    correction: PaymentCorrectInput | None,
) -> SettlementView:
    operation: FinancialCommandKind = (
        "settlement_payment_void" if correction is None else "settlement_payment_correct"
    )
    kind: SettlementEventKind = "payment_voided" if correction is None else "payment_corrected"
    digest = commands.fingerprint(
        {
            "book_id": str(book_id),
            "settlement_id": str(settlement_id),
            "payment_id": str(payment_id),
            **body.model_dump(mode="json"),
        }
    )
    prior = await _claim(conn, business_id, actor, operation, key, digest)
    if prior is not None:
        return await _view(conn, business_id, prior)
    current = await load_settlement(conn, business_id, book_id, settlement_id)
    if current is None:
        raise NotFoundError("Settlement not found")
    if current.sequence != body.expected_sequence:
        raise ConflictError(
            "This settlement changed; reload before continuing", sequence=current.sequence
        )
    payment = await load_payment(conn, business_id, book_id, payment_id)
    if payment is None or payment.settlement_id != settlement_id:
        raise NotFoundError("Payment not found")
    if payment.state == "voided":
        raise FinancialDocumentStateError("A voided payment is final")
    phase = _phase([event.kind for event in current.events])
    if phase not in _FOLLOWS[kind]:
        verb = "voided" if correction is None else "corrected"
        raise FinancialDocumentStateError(f"A payment of a {phase} settlement cannot be {verb}")
    if current.outcome_unresolved:
        raise FinancialOutcomeUnresolvedError(
            "Resolve the sent outcome of this settlement before correcting its payment"
        )
    await require_workflow(conn, business_id)
    scale = current.minor_units
    old = {
        line.obligation_id: to_minor(line.amount, scale) for line in payment.effective_allocations
    }
    new: dict[UUID, int] = {}
    for number, line in enumerate(correction.allocations if correction else (), 1):
        try:
            new[line.obligation_id] = to_minor(line.amount, scale)
        except ValueError as exc:
            raise FinancialAmountError(str(exc), line=number, currency=current.currency) from exc
    touched = sorted(set(old) | set(new))
    await _require_no_dependents(conn, business_id, book_id, settlement_id, touched)
    latest = payment.revisions[-1] if payment.revisions else None
    replaced, replaced_on = (
        (payment.entry_id, payment.entry_date)
        if latest is None
        else (latest.entry_id, latest.entry_date)
    )
    if replaced is None:
        raise DatabaseUnavailableError("The journal of the effective payment is missing")
    if body.entry_date < replaced_on:
        raise ledger.LedgerDateError(
            "A correction cannot be posted before the version it replaces",
            replaced_on=replaced_on.isoformat(),
        )
    amount = 0
    controls: list[UUID] = []
    if correction is not None:
        await _require_attested_date(conn, business_id, correction.actual_external_date)
        await _require_cash_not_control(conn, business_id, book_id, correction.cash_account_id)
        try:
            amount = to_minor(correction.amount, scale)
        except ValueError as exc:
            raise FinancialAmountError(str(exc), currency=current.currency) from exc
        held = await _settlement_lines(conn, business_id, book_id, settlement_id)
        for number, line in enumerate(correction.allocations, 1):
            if line.obligation_id not in held:
                raise FinancialDocumentStateError(
                    "A correction allocates only to lines of its settlement"
                )
            control, planned, confirmed, accrued = held[line.obligation_id]
            # The replaced allocation returns to this line before the replacement takes it.
            if new[line.obligation_id] > planned - confirmed + old.get(line.obligation_id, 0):
                raise FinancialCapError("Correction exceeds the reserved settlement line")
            if body.entry_date < accrued:
                raise ledger.LedgerDateError(
                    "A payment cannot be posted before the accrual it settles", line=number
                )
            controls.append(control)
        if sum(new.values()) != amount:
            raise FinancialAmountError(
                "Allocations must equal the corrected amount exactly", currency=current.currency
            )
    for obligation in touched:
        row = await (
            await conn.execute(
                "select * from gba.obligation_balance(%s,%s,%s)",
                (business_id, book_id, obligation),
            )
        ).fetchone()
        if row is None:
            raise DatabaseUnavailableError("A settled obligation is missing")
        balance = _balance(row)
        # A released reserve is not restored: the void only lowers P there.
        if phase in _HOLDING and obligation in old:
            balance = correct_confirmation(balance, old_minor=old[obligation], new_minor=0)
        if obligation in new:
            confirm_reserved(balance, new[obligation])
    previous = await (
        await conn.execute(
            "select account_id,side,amount_minor from gba.journal_lines "
            "where tenant_id=%s and entry_id=%s order by line_no",
            (business_id, replaced),
        )
    ).fetchall()
    revision = payment.revision + 1
    reference = Reference(book_id, settlement_id, current.sequence + 1)
    reversal = uuid7()
    replacement = None if correction is None else uuid7()
    cash_side: Literal["debit", "credit"] = (
        "debit" if current.direction == "receivable" else "credit"
    )
    async with _writes(conn):
        await _event(conn, business_id, reference, kind, user_id)
        await conn.execute(
            "insert into gba.external_payment_revisions (tenant_id,book_id,payment_id,revision,"
            "settlement_id,sequence,kind,amount_minor,actual_external_date,cash_account_id,"
            "entry_date,attestation,reason,evidence_source,reversal_entry_id,entry_id,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                business_id,
                book_id,
                payment_id,
                revision,
                settlement_id,
                reference.revision,
                "voided" if correction is None else "corrected",
                None if correction is None else amount,
                None if correction is None else correction.actual_external_date,
                None if correction is None else correction.cash_account_id,
                body.entry_date,
                body.attestation,
                body.reason,
                body.evidence_source,
                reversal,
                replacement,
                user_id,
            ),
        )
        if correction is not None:
            await conn.execute(
                "insert into gba.external_payment_revision_allocations "
                "(tenant_id,book_id,payment_id,revision,line_no,obligation_id,amount_minor) "
                "select %s,%s,%s,%s,l.n::smallint,l.obligation,l.amount "
                "from unnest(%s::uuid[],%s::bigint[]) with ordinality as l(obligation,amount,n)",
                (
                    business_id,
                    book_id,
                    payment_id,
                    revision,
                    [line.obligation_id for line in correction.allocations],
                    [new[line.obligation_id] for line in correction.allocations],
                ),
            )
        await ledger.append_financial_journal(
            conn,
            business_id=business_id,
            book_id=book_id,
            entry_id=reversal,
            user_id=user_id,
            body=PaymentCorrectionPosting(
                entry_date=body.entry_date,
                currency=current.currency,
                source_id=f"{payment_id}:{revision}:reversal",
                lines=tuple(
                    LineInput(
                        account_id=line[0], side=_mirror(line[1]), amount=from_minor(line[2], scale)
                    )
                    for line in previous
                ),
            ),
        )
        if correction is not None and replacement is not None:
            await ledger.append_financial_journal(
                conn,
                business_id=business_id,
                book_id=book_id,
                entry_id=replacement,
                user_id=user_id,
                body=PaymentCorrectionPosting(
                    entry_date=body.entry_date,
                    currency=current.currency,
                    source_id=f"{payment_id}:{revision}:replacement",
                    lines=(
                        LineInput(
                            account_id=correction.cash_account_id,
                            side=cash_side,
                            amount=from_minor(amount, scale),
                        ),
                        *(
                            LineInput(
                                account_id=control,
                                side=_mirror(cash_side),
                                amount=from_minor(new[line.obligation_id], scale),
                            )
                            for control, line in zip(controls, correction.allocations, strict=True)
                        ),
                    ),
                ),
            )
        await financial_commands.complete(
            conn,
            business=business_id,
            actor=actor,
            user=user_id,
            operation=operation,
            key=key,
            request_hash=digest,
            reference=reference,
            receipt=_receipt(reference),
            flush=_flush,
        )
    return await _view(conn, business_id, reference)


async def void_payment(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    payment_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: PaymentVoidInput,
) -> SettlementView:
    """Record an attested erroneous confirmation: no money moved under this identity.

    The payment's journal is reversed and its allocations return to the reserve of a
    held settlement (a released one only loses P). The identity stays bound to it.
    """
    return await _amend(
        conn,
        business_id=business_id,
        book_id=book_id,
        settlement_id=settlement_id,
        payment_id=payment_id,
        user_id=user_id,
        actor=actor,
        key=key,
        body=body,
        correction=None,
    )


async def correct_payment(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    payment_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: PaymentCorrectInput,
) -> SettlementView:
    """Replace the details of an erroneous attestation of the same external fact.

    The replaced version is reversed and its allocations return to the reserve; the
    replacement is confirmed within that reserve with its own journal, atomically.
    """
    return await _amend(
        conn,
        business_id=business_id,
        book_id=book_id,
        settlement_id=settlement_id,
        payment_id=payment_id,
        user_id=user_id,
        actor=actor,
        key=key,
        body=body,
        correction=body,
    )
