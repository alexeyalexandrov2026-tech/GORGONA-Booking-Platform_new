"""Immutable provider-admission declarations, with no money or provider actions.

Reuse company finance authorization, ledger books/serialization and ordinary
idempotency/audit primitives. H4 has its own finite, permanent reference receipts;
neither its metadata nor a submitted request enables a financial capability.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    SerializationFailure,
    UniqueViolation,
)

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import commands, ledger
from gorgona_booking.business.module_gate import FINANCE_MODULE, module_writes, require_module
from gorgona_booking.business.provider_admission_contracts import (
    AdmissionActionInput,
    AdmissionCommandKind,
    AdmissionCommandReference,
    AdmissionCommandStatus,
    AdmissionDraftInput,
    AdmissionList,
    AdmissionReceipt,
    AdmissionState,
    AdmissionView,
    OperationalCapabilities,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DatabaseUnavailableError,
    InvalidReferenceError,
    NotFoundError,
)

_KEY = " where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s"
_CONSTRAINTS = ",".join(
    "gba." + name + "_consistent"
    for name in (
        "provider_admission_requests",
        "provider_admission_versions",
        "provider_admission_evidence",
    )
)


class AdmissionStateError(ConflictError):
    code = "PROVIDER_ADMISSION_STATE_INVALID"


class AdmissionCommandCancelledError(ConflictError):
    code = "PROVIDER_ADMISSION_COMMAND_CANCELLED"


def _scope(
    business: UUID, actor: str, operation: AdmissionCommandKind, key: str
) -> IdempotencyScope:
    return IdempotencyScope(business, actor, "business.provider_admission." + operation, key)


async def _lock(conn: RuntimeConnection, business: UUID) -> None:
    try:
        await conn.execute("select gba.lock_ledger(%s)", (business,))
    except SerializationFailure as exc:
        raise DatabaseUnavailableError(
            "Admission writes require read committed transactions"
        ) from exc


async def _flush(conn: RuntimeConnection) -> None:
    await conn.execute("set constraints " + _CONSTRAINTS + " immediate")
    await conn.execute("set constraints " + _CONSTRAINTS + " deferred")


@asynccontextmanager
async def _writes(conn: RuntimeConnection) -> AsyncIterator[None]:
    try:
        async with module_writes(FINANCE_MODULE), conn.transaction():
            yield
            await _flush(conn)
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Admission references belong to this company and book") from exc
    except (CheckViolation, UniqueViolation) as exc:
        raise AdmissionStateError("Admission request changed; reload before continuing") from exc
    except SerializationFailure as exc:
        raise DatabaseUnavailableError("Admission transaction settings are not ready") from exc


async def load_request(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    request_id: UUID,
    *,
    revision: int | None = None,
) -> AdmissionView | None:
    row = await (
        await conn.execute(
            "select "
            "revision,state,provider,country,business_activity,requested_operation,assessment,"
            "account_reference,notes,evidence_status,charge_enabled,refund_enabled,transfer_enabled,payout_enabled,created_at"
            " "
            "from gba.provider_admission_versions where tenant_id=%s and "
            "book_id=%s and request_id=%s "
            "and (%s::integer is null or revision=%s) order by revision desc limit 1",
            (business_id, book_id, request_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    references = await (
        await conn.execute(
            "select reference from gba.provider_admission_evidence "
            "where tenant_id=%s and book_id=%s and request_id=%s and "
            "revision=%s order by reference_no",
            (business_id, book_id, request_id, row[0]),
        )
    ).fetchall()
    return AdmissionView(
        business_id=business_id,
        book_id=book_id,
        request_id=request_id,
        revision=row[0],
        state=row[1],
        provider=row[2],
        country=row[3],
        business_activity=row[4],
        requested_operation=row[5],
        assessment=row[6],
        account_reference=row[7],
        notes=row[8],
        evidence_status=row[9],
        operational_capabilities=OperationalCapabilities(
            charge=row[10],
            refund=row[11],
            transfer=row[12],
            payout=row[13],
        ),
        evidence_references=tuple(reference[0] for reference in references),
        created_at=row[14],
    )


async def _view(
    conn: RuntimeConnection, business: UUID, reference: AdmissionReceipt
) -> AdmissionView:
    result = await load_request(
        conn, business, reference.book_id, reference.request_id, revision=reference.revision
    )
    if result is None:
        raise DatabaseUnavailableError("The stored admission version is missing")
    return result


async def list_requests(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> AdmissionList:
    await ledger.require_book(conn, business_id, book_id)
    rows = await (
        await conn.execute(
            "select id from gba.provider_admission_requests where tenant_id=%s and book_id=%s "
            "and (%s::uuid is null or id>%s) order by id limit %s",
            (business_id, book_id, after, after, limit + 1),
        )
    ).fetchall()
    items = []
    for (request_id,) in rows[:limit]:
        item = await load_request(conn, business_id, book_id, request_id)
        if item is None:
            raise DatabaseUnavailableError("An admission request has no version")
        items.append(item)
    return AdmissionList(
        business_id=business_id,
        book_id=book_id,
        items=tuple(items),
        next_after=items[-1].request_id if len(rows) > limit else None,
    )


async def _stored(
    conn: RuntimeConnection,
    business: UUID,
    actor: str,
    operation: AdmissionCommandKind,
    key: str,
) -> tuple[str, AdmissionReceipt] | None:
    row = await (
        await conn.execute(
            "select request_hash,book_id,request_id,revision from gba.provider_admission_receipts"  # noqa: S608 - fixed SQL predicate
            + _KEY,
            (business, actor, operation, key),
        )
    ).fetchone()
    return (
        None
        if row is None
        else (row[0], AdmissionReceipt(book_id=row[1], request_id=row[2], revision=row[3]))
    )


async def _claim(
    conn: RuntimeConnection,
    *,
    business: UUID,
    actor: str,
    operation: AdmissionCommandKind,
    key: str,
    digest: str,
) -> AdmissionReceipt | None:
    await _lock(conn, business)
    if await (
        await conn.execute(
            "select 1 from gba.provider_admission_cancellations" + _KEY,  # noqa: S608 - fixed SQL predicate
            (business, actor, operation, key),
        )
    ).fetchone():
        raise AdmissionCommandCancelledError("This unresolved admission command was cancelled")
    stored = await _stored(conn, business, actor, operation, key)
    if stored is not None and stored[0] != digest:
        raise IdempotencyKeyReusedError("This key was used with another admission command")
    scope = _scope(business, actor, operation, key)
    cached = await commands.claim(conn, scope, digest, AdmissionReceipt)
    if stored is None:
        if cached is not None:
            raise DatabaseUnavailableError("The admission command outcome is incomplete")
        return None
    if cached is not None and cached != stored[1]:
        raise DatabaseUnavailableError("The admission command references disagree")
    if cached is None:
        await commands.complete(conn, scope, stored[1])
    return stored[1]


async def _complete(
    conn: RuntimeConnection,
    *,
    business: UUID,
    actor: str,
    user: UUID,
    operation: AdmissionCommandKind,
    key: str,
    digest: str,
    receipt: AdmissionReceipt,
) -> None:
    await _flush(conn)
    await conn.execute(
        "insert into gba.provider_admission_receipts "
        "(tenant_id,actor_key,operation,idempotency_key,request_hash,book_id,request_id,revision,created_by)"
        " "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            business,
            actor,
            operation,
            key,
            digest,
            receipt.book_id,
            receipt.request_id,
            receipt.revision,
            user,
        ),
    )
    await commands.audit(
        conn,
        business,
        actor,
        "provider_admission." + operation,
        "provider_admission_request",
        str(receipt.request_id),
        {"book_id": str(receipt.book_id), "revision": receipt.revision},
    )
    await commands.complete(conn, _scope(business, actor, operation, key), receipt)


async def _insert_version(
    conn: RuntimeConnection,
    *,
    business: UUID,
    book: UUID,
    request_id: UUID,
    user: UUID,
    revision: int,
    state: AdmissionState,
    body: AdmissionDraftInput,
) -> None:
    await conn.execute(
        "insert into gba.provider_admission_versions "
        "(tenant_id,book_id,request_id,revision,state,provider,country,business_activity,requested_operation,"
        "assessment,account_reference,notes,evidence_count,created_by) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            business,
            book,
            request_id,
            revision,
            state,
            body.provider,
            body.country,
            body.business_activity,
            body.requested_operation,
            body.assessment,
            body.account_reference,
            body.notes,
            len(body.evidence_references),
            user,
        ),
    )
    await conn.execute(
        "insert into gba.provider_admission_evidence "
        "(tenant_id,book_id,request_id,revision,reference_no,reference) "
        "select %s,%s,%s,%s,r.n::smallint,r.reference from "
        "unnest(%s::text[]) with ordinality as r(reference,n)",
        (business, book, request_id, revision, list(body.evidence_references)),
    )


async def save_draft(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    request_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: AdmissionDraftInput,
) -> AdmissionView:
    digest = commands.fingerprint(
        {"book_id": str(book_id), "request_id": str(request_id), **body.model_dump(mode="json")}
    )
    prior = await _claim(
        conn, business=business_id, actor=actor, operation="admission_draft", key=key, digest=digest
    )
    if prior is not None:
        return await _view(conn, business_id, prior)
    await require_module(conn, business_id, FINANCE_MODULE)
    await ledger.require_book(conn, business_id, book_id)
    current = await load_request(conn, business_id, book_id, request_id)
    actual = current.revision if current else 0
    if actual != body.expected_revision:
        raise ConflictError("Admission request changed; reload before saving", revision=actual)
    if current is not None and current.state != "draft":
        raise AdmissionStateError("A submitted or withdrawn request keeps its history")
    receipt = AdmissionReceipt(book_id=book_id, request_id=request_id, revision=actual + 1)
    async with _writes(conn):
        if current is None:
            await conn.execute(
                "insert into gba.provider_admission_requests "
                "(tenant_id,book_id,id,created_by) values (%s,%s,%s,%s)",
                (business_id, book_id, request_id, user_id),
            )
        await _insert_version(
            conn,
            business=business_id,
            book=book_id,
            request_id=request_id,
            user=user_id,
            revision=receipt.revision,
            state="draft",
            body=body,
        )
        await _complete(
            conn,
            business=business_id,
            actor=actor,
            user=user_id,
            operation="admission_draft",
            key=key,
            digest=digest,
            receipt=receipt,
        )
    return await _view(conn, business_id, receipt)


async def transition(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    request_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: AdmissionActionInput,
    action: Literal["submit", "withdraw"],
) -> AdmissionView:
    operation: AdmissionCommandKind = (
        "admission_submit" if action == "submit" else "admission_withdraw"
    )
    digest = commands.fingerprint(
        {"book_id": str(book_id), "request_id": str(request_id), **body.model_dump(mode="json")}
    )
    prior = await _claim(
        conn, business=business_id, actor=actor, operation=operation, key=key, digest=digest
    )
    if prior is not None:
        return await _view(conn, business_id, prior)
    await ledger.require_book(conn, business_id, book_id)
    current = await load_request(conn, business_id, book_id, request_id)
    if current is None:
        raise NotFoundError("Admission request not found")
    if current.revision != body.expected_revision:
        raise ConflictError(
            "Admission request changed; reload before continuing", revision=current.revision
        )
    if current.state == "withdrawn" or (action == "submit" and current.state != "draft"):
        raise AdmissionStateError("This admission transition is not allowed")
    if action == "submit":
        await require_module(conn, business_id, FINANCE_MODULE)
        if not current.evidence_references:
            raise AdmissionStateError(
                "Submission needs manually supplied unverified evidence references"
            )
    preserved = AdmissionDraftInput(
        expected_revision=current.revision,
        provider=current.provider,
        country=current.country,
        business_activity=current.business_activity,
        requested_operation=current.requested_operation,
        assessment=current.assessment,
        account_reference=current.account_reference,
        evidence_references=current.evidence_references,
        notes=current.notes,
    )
    receipt = AdmissionReceipt(
        book_id=book_id, request_id=request_id, revision=current.revision + 1
    )
    async with _writes(conn):
        await _insert_version(
            conn,
            business=business_id,
            book=book_id,
            request_id=request_id,
            user=user_id,
            revision=receipt.revision,
            state="submitted" if action == "submit" else "withdrawn",
            body=preserved,
        )
        await _complete(
            conn,
            business=business_id,
            actor=actor,
            user=user_id,
            operation=operation,
            key=key,
            digest=digest,
            receipt=receipt,
        )
    return await _view(conn, business_id, receipt)


async def resolve_command(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    actor: str,
    key: str,
    body: AdmissionCommandReference,
) -> AdmissionCommandStatus:
    await _lock(conn, business_id)
    _scope(business_id, actor, body.operation, key)
    await ledger.require_book(conn, business_id, body.book_id)
    expected = AdmissionReceipt(
        book_id=body.book_id, request_id=body.subject_id, revision=body.revision
    )
    stored = await _stored(conn, business_id, actor, body.operation, key)
    found = None if stored is None else stored[1]
    state: Literal["committed", "unresolved", "cancelled"] = (
        "committed" if found is not None else "unresolved"
    )
    if found is None:
        row = await (
            await conn.execute(
                "select book_id,request_id,revision from gba.provider_admission_cancellations"  # noqa: S608 - fixed SQL predicate
                + _KEY,
                (business_id, actor, body.operation, key),
            )
        ).fetchone()
        if row is not None:
            found, state = (
                AdmissionReceipt(book_id=row[0], request_id=row[1], revision=row[2]),
                "cancelled",
            )
    if found is not None and found != expected:
        raise InvalidReferenceError("This outcome belongs to another admission reference")
    return AdmissionCommandStatus(
        business_id=business_id, key=key, operation=body.operation, state=state
    )


async def cancel_command(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: AdmissionCommandReference,
) -> AdmissionCommandStatus:
    result = await resolve_command(conn, business_id=business_id, actor=actor, key=key, body=body)
    if result.state != "unresolved":
        return result
    async with _writes(conn):
        await conn.execute(
            "insert into gba.provider_admission_cancellations "
            "(tenant_id,actor_key,operation,idempotency_key,book_id,request_id,revision,cancelled_by)"
            " "
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
            "provider_admission.command_cancelled",
            "provider_admission_command",
            key,
            {"book_id": str(body.book_id), "operation": body.operation},
        )
    return result.model_copy(update={"state": "cancelled"})
