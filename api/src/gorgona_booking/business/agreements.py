"""Contracts with counterparties: drafts, attested agreement and termination (ADR-0020 E3).

Callers hold the per-business `counterparties` lock before the membership share lock.
A command claims its key, replays a stored reference-only receipt for the same body,
checks the module, inserts one version, audits without titles, numbers or summaries
and stores its receipt in one transaction. Nothing is updated or deleted; the
database enforces the same transitions and the unchanged agreed content.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands
from gorgona_booking.business.agreement_contracts import (
    ATTESTATION,
    AgreeInput,
    AgreementDraftInput,
    AgreementHistory,
    AgreementInForce,
    AgreementList,
    AgreementReceipt,
    AgreementRevision,
    AgreementSummary,
    AgreementView,
    DocumentReference,
    TerminateInput,
)
from gorgona_booking.business.counterparties import CounterpartyStateError
from gorgona_booking.business.module_gate import (
    COUNTERPARTIES_MODULE,
    module_writes,
    require_module,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DomainError,
    InvalidReferenceError,
    NotFoundError,
)


class AgreementStateError(ConflictError):
    code = "AGREEMENT_STATE_INVALID"


class AttestationRequiredError(DomainError):
    code = "ATTESTATION_REQUIRED"


class AgreementDateError(DomainError):
    code = "AGREEMENT_DATE_INVALID"


class AgreementInputError(DomainError):
    code = "AGREEMENT_INVALID"


_DRAFT = "business.agreement.draft"
_AGREE = "business.agreement.agree"
_TERMINATE = "business.agreement.terminate"
_FOREIGN_KEYS = {
    "agreements_counterparty_fk": "counterparty_id",
    "agreements_legal_entity_fk": "legal_entity_id",
    "agreement_versions_document_fk": "document",
}


def latest_calendar_day() -> date:
    """The latest date anywhere on Earth: a signing date cannot be after it."""
    return (datetime.now(UTC) + timedelta(hours=14)).date()


_VERSION_COLUMNS = (
    "a.counterparty_id, a.legal_entity_id, v.revision, v.state, v.title, v.number, "
    "v.summary, v.effective_from, v.effective_until, v.signed_on, v.attestation, "
    "v.document_id, v.document_revision, v.terminated_on, v.created_at, "
    "(select max(x.revision) from gba.agreement_versions x where x.tenant_id = v.tenant_id "
    "and x.agreement_id = v.agreement_id and x.state = 'agreed' and x.revision <= v.revision), "
    "v.terminates_revision"
)


async def load_agreement(
    conn: RuntimeConnection,
    business_id: UUID,
    agreement_id: UUID,
    *,
    revision: int | None = None,
) -> AgreementView | None:
    row = await (
        await conn.execute(
            f"select {_VERSION_COLUMNS} from gba.agreement_versions v "  # noqa: S608 - fixed
            "join gba.agreements a on a.tenant_id = v.tenant_id and a.id = v.agreement_id "
            "where v.tenant_id = %s and v.agreement_id = %s "
            "and (%s::integer is null or v.revision = %s) "
            "order by v.revision desc limit 1",
            (business_id, agreement_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    return AgreementView(
        business_id=business_id,
        agreement_id=agreement_id,
        counterparty_id=row[0],
        legal_entity_id=row[1],
        revision=row[2],
        state=row[3],
        title=row[4],
        number=row[5],
        summary=row[6],
        effective_from=row[7],
        effective_until=row[8],
        signed_on=row[9],
        attestation=row[10],
        document=(
            DocumentReference(document_id=row[11], revision=row[12])
            if row[11] is not None
            else None
        ),
        terminated_on=row[13],
        created_at=row[14],
        in_force_revision=row[15],
        terminates_revision=row[16],
    )


async def _require(conn: RuntimeConnection, business_id: UUID, agreement_id: UUID) -> AgreementView:
    current = await load_agreement(conn, business_id, agreement_id)
    if current is None:
        raise NotFoundError("Contract not found")
    return current


async def _version(
    conn: RuntimeConnection, business_id: UUID, agreement_id: UUID, revision: int
) -> AgreementView:
    result = await load_agreement(conn, business_id, agreement_id, revision=revision)
    if result is None:
        raise RuntimeError("A stored agreement version is missing")
    return result


async def _card_state(conn: RuntimeConnection, business_id: UUID, counterparty_id: UUID) -> str:
    row = await (
        await conn.execute(
            "select state from gba.counterparty_versions "
            "where tenant_id = %s and counterparty_id = %s order by revision desc limit 1",
            (business_id, counterparty_id),
        )
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Unknown counterparty", field="counterparty_id")
    return str(row[0])


async def list_agreements(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> AgreementList:
    exists = await (
        await conn.execute(
            "select 1 from gba.counterparties where tenant_id = %s and id = %s",
            (business_id, counterparty_id),
        )
    ).fetchone()
    if exists is None:
        raise NotFoundError("Counterparty not found")
    rows = await (
        await conn.execute(
            "with family as (select %(record)s::uuid as id union "
            "select v.counterparty_id from gba.counterparty_versions v "
            "where v.tenant_id = %(business)s and v.merged_into = %(record)s "
            "and v.revision = (select max(x.revision) from gba.counterparty_versions x "
            "where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)), "
            "latest as (select distinct on (v.agreement_id) v.* from gba.agreement_versions v "
            "where v.tenant_id = %(business)s order by v.agreement_id, v.revision desc), "
            "in_force as (select distinct on (v.agreement_id) v.* from gba.agreement_versions v "
            "where v.tenant_id = %(business)s and v.state = 'agreed' "
            "order by v.agreement_id, v.revision desc) "
            "select a.id, a.counterparty_id, l.revision, l.state, l.title, l.number, "
            "l.effective_from, l.effective_until, l.terminated_on, l.created_at, i.revision, "
            "i.title, i.number, i.effective_from, i.effective_until, i.signed_on "
            "from gba.agreements a join family f on f.id = a.counterparty_id "
            "join latest l on l.agreement_id = a.id "
            "left join in_force i on i.agreement_id = a.id where a.tenant_id = %(business)s "
            "and (%(after)s::uuid is null or a.id < %(after)s) "
            "order by a.id desc limit %(limit)s",
            {
                "business": business_id,
                "record": counterparty_id,
                "after": after,
                "limit": limit + 1,
            },
        )
    ).fetchall()
    items = tuple(_summary(tuple(row)) for row in rows[:limit])
    return AgreementList(
        business_id=business_id,
        counterparty_id=counterparty_id,
        items=items,
        next_cursor=items[-1].agreement_id if len(rows) > limit else None,
    )


def _summary(row: tuple[Any, ...]) -> AgreementSummary:
    return AgreementSummary(
        agreement_id=row[0],
        counterparty_id=row[1],
        revision=row[2],
        state=row[3],
        title=row[4],
        number=row[5],
        effective_from=row[6],
        effective_until=row[7],
        terminated_on=row[8],
        updated_at=row[9],
        in_force=(
            AgreementInForce(
                revision=row[10],
                title=row[11],
                number=row[12],
                effective_from=row[13],
                effective_until=row[14],
                signed_on=row[15],
            )
            if row[10] is not None
            else None
        ),
    )


async def agreement_history(
    conn: RuntimeConnection,
    business_id: UUID,
    agreement_id: UUID,
    *,
    before: int | None,
    limit: int,
) -> AgreementHistory:
    await _require(conn, business_id, agreement_id)
    rows = await (
        await conn.execute(
            "select v.revision, v.state, v.title, v.signed_on, v.terminated_on, "
            # Only the draft that was still open when the termination followed it.
            "v.state = 'draft' and exists (select 1 from gba.agreement_versions t "
            "where t.tenant_id = v.tenant_id and t.agreement_id = v.agreement_id "
            "and t.state = 'terminated' and t.revision = v.revision + 1 "
            "and t.terminates_revision < v.revision), v.created_at "
            "from gba.agreement_versions v where v.tenant_id = %s and v.agreement_id = %s "
            "and (%s::integer is null or v.revision < %s) order by v.revision desc limit %s",
            (business_id, agreement_id, before, before, limit + 1),
        )
    ).fetchall()
    items = tuple(
        AgreementRevision(
            revision=r[0],
            state=r[1],
            title=r[2],
            signed_on=r[3],
            terminated_on=r[4],
            abandoned=r[5],
            created_at=r[6],
        )
        for r in rows[:limit]
    )
    return AgreementHistory(
        business_id=business_id,
        agreement_id=agreement_id,
        items=items,
        next_cursor=items[-1].revision if len(rows) > limit else None,
    )


async def _insert(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    agreement_id: UUID,
    user_id: UUID,
    revision: int,
    state: str,
    content: AgreementView | AgreementDraftInput,
    document: DocumentReference | None,
    signed_on: date | None = None,
    terminated_on: date | None = None,
    terminates_revision: int | None = None,
    new_identity: AgreementDraftInput | None = None,
) -> None:
    try:
        async with module_writes(COUNTERPARTIES_MODULE), conn.transaction():
            if new_identity is not None:
                await conn.execute(
                    "insert into gba.agreements (tenant_id, id, counterparty_id, "
                    "legal_entity_id, created_by) values (%s, %s, %s, %s, %s)",
                    (
                        business_id,
                        agreement_id,
                        new_identity.counterparty_id,
                        new_identity.legal_entity_id,
                        user_id,
                    ),
                )
            await conn.execute(
                "insert into gba.agreement_versions (tenant_id, agreement_id, revision, state, "
                "title, number, summary, effective_from, effective_until, signed_on, "
                "attestation, document_id, document_revision, terminated_on, "
                "terminates_revision, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business_id,
                    agreement_id,
                    revision,
                    state,
                    content.title,
                    content.number,
                    content.summary,
                    content.effective_from,
                    content.effective_until,
                    signed_on,
                    ATTESTATION if state != "draft" else None,
                    document.document_id if document else None,
                    document.revision if document else None,
                    terminated_on,
                    terminates_revision,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        field = _FOREIGN_KEYS.get(exc.diag.constraint_name or "")
        if field is None:
            raise
        raise InvalidReferenceError("Unknown reference", field=field) from exc
    except CheckViolation as exc:
        message = exc.diag.message_primary or ""
        if exc.diag.constraint_name:
            # A column rule the API input checks did not cover: never a conflict.
            raise AgreementInputError("The contract text or dates are not accepted") from exc
        if "signing date" in message:
            # The database clock decides the latest calendar day.
            raise AgreementDateError("The signing date cannot be in the future") from exc
        # The database re-checks state and card under the counterparties lock.
        raise ConflictError("This contract or counterparty changed. Reload it.") from exc


async def _audit(
    conn: RuntimeConnection,
    business_id: UUID,
    actor: str,
    action: str,
    agreement_id: UUID,
    details: dict[str, object],
) -> None:
    await commands.audit(conn, business_id, actor, action, "agreement", str(agreement_id), details)


def _expect(current: AgreementView | None, expected: int) -> int:
    revision = current.revision if current else 0
    if expected != revision:
        raise ConflictError("This contract changed. Reload it before saving.", revision=revision)
    return revision + 1


async def save_draft(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    agreement_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: AgreementDraftInput,
) -> AgreementView:
    """Create a contract or add a draft version; after agreement it is an amendment."""
    scope = IdempotencyScope(business_id, actor, _DRAFT, key)
    request_hash = commands.fingerprint(
        {"agreement_id": str(agreement_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, AgreementReceipt)
    if receipt is not None:
        return await _version(conn, business_id, receipt.agreement_id, receipt.revision)

    await require_module(conn, business_id, COUNTERPARTIES_MODULE)
    current = await load_agreement(conn, business_id, agreement_id)
    revision = _expect(current, body.expected_revision)
    if current is not None:
        if (body.counterparty_id, body.legal_entity_id) != (
            current.counterparty_id,
            current.legal_entity_id,
        ):
            raise InvalidReferenceError(
                "A contract keeps its counterparty and legal entity", field="counterparty_id"
            )
        if current.state == "terminated":
            raise AgreementStateError("A terminated contract cannot change")
    if await _card_state(conn, business_id, body.counterparty_id) != "active":
        raise CounterpartyStateError("Only an active counterparty can get contract changes")
    await _insert(
        conn,
        business_id=business_id,
        agreement_id=agreement_id,
        user_id=user_id,
        revision=revision,
        state="draft",
        content=body,
        document=body.document,
        new_identity=body if current is None else None,
    )
    await _audit(
        conn,
        business_id,
        actor,
        "agreement.drafted",
        agreement_id,
        {
            "revision": revision,
            "counterparty_id": str(body.counterparty_id),
            # Every save while an agreed version is in force amends it.
            "amendment": current is not None and current.in_force_revision is not None,
            "has_document": body.document is not None,
        },
    )
    await commands.complete(
        conn, scope, AgreementReceipt(agreement_id=agreement_id, revision=revision)
    )
    return await _version(conn, business_id, agreement_id, revision)


async def agree(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    agreement_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: AgreeInput,
) -> AgreementView:
    """Record that the latest draft was signed outside the platform, unchanged."""
    scope = IdempotencyScope(business_id, actor, _AGREE, key)
    request_hash = commands.fingerprint(
        {"agreement_id": str(agreement_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, AgreementReceipt)
    if receipt is not None:
        return await _version(conn, business_id, receipt.agreement_id, receipt.revision)

    await require_module(conn, business_id, COUNTERPARTIES_MODULE)
    current = await _require(conn, business_id, agreement_id)
    revision = _expect(current, body.expected_revision)
    if current.state != "draft":
        raise AgreementStateError("Only a draft can be recorded as agreed")
    if body.attestation != ATTESTATION:
        raise AttestationRequiredError("Confirm that the contract was signed outside the platform")
    if body.signed_on > latest_calendar_day():
        raise AgreementDateError("The signing date cannot be in the future")
    if await _card_state(conn, business_id, current.counterparty_id) != "active":
        raise CounterpartyStateError("Only an active counterparty can agree a contract")
    document = body.document or current.document
    await _insert(
        conn,
        business_id=business_id,
        agreement_id=agreement_id,
        user_id=user_id,
        revision=revision,
        state="agreed",
        content=current,
        document=document,
        signed_on=body.signed_on,
    )
    await _audit(
        conn,
        business_id,
        actor,
        "agreement.agreed",
        agreement_id,
        {
            "revision": revision,
            "counterparty_id": str(current.counterparty_id),
            "signed_on": body.signed_on.isoformat(),
            "has_document": document is not None,
        },
    )
    await commands.complete(
        conn, scope, AgreementReceipt(agreement_id=agreement_id, revision=revision)
    )
    return await _version(conn, business_id, agreement_id, revision)


async def terminate(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    agreement_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: TerminateInput,
) -> AgreementView:
    """End the agreed version in force, from a possibly future date.

    The termination repeats the latest agreed version unchanged. An open amendment
    draft is not signed by it: it stays in the history, abandoned.
    """
    scope = IdempotencyScope(business_id, actor, _TERMINATE, key)
    request_hash = commands.fingerprint(
        {"agreement_id": str(agreement_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, AgreementReceipt)
    if receipt is not None:
        return await _version(conn, business_id, receipt.agreement_id, receipt.revision)

    await require_module(conn, business_id, COUNTERPARTIES_MODULE)
    current = await _require(conn, business_id, agreement_id)
    revision = _expect(current, body.expected_revision)
    if current.state == "terminated" or current.in_force_revision is None:
        raise AgreementStateError("Only an agreed contract can be terminated")
    agreed = await _version(conn, business_id, agreement_id, current.in_force_revision)
    if agreed.signed_on is None:
        raise RuntimeError("A stored agreed version has no signing date")
    if body.terminated_on < agreed.signed_on:
        raise AgreementDateError("A contract cannot end before it was signed")
    await _insert(
        conn,
        business_id=business_id,
        agreement_id=agreement_id,
        user_id=user_id,
        revision=revision,
        state="terminated",
        content=agreed,
        document=agreed.document,
        signed_on=agreed.signed_on,
        terminated_on=body.terminated_on,
        terminates_revision=agreed.revision,
    )
    await _audit(
        conn,
        business_id,
        actor,
        "agreement.terminated",
        agreement_id,
        {
            "revision": revision,
            "counterparty_id": str(current.counterparty_id),
            "terminates_revision": agreed.revision,
            "abandoned_draft_revision": current.revision if current.state == "draft" else None,
            "terminated_on": body.terminated_on.isoformat(),
        },
    )
    await commands.complete(
        conn, scope, AgreementReceipt(agreement_id=agreement_id, revision=revision)
    )
    return await _version(conn, business_id, agreement_id, revision)
