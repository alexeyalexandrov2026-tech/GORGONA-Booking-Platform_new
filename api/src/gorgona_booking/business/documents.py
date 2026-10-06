"""Company-owned documents, immutable files and counterparty links (ADR-0020 E2).

Callers hold the per-business `documents` lock before the membership share lock. A
command claims its key, replays a stored reference-only receipt for the same body,
checks the module, writes, audits without titles, names or bytes and stores its
receipt in one transaction. Nothing is updated or deleted.
"""

import hashlib
from typing import Any
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands
from gorgona_booking.business.document_contracts import (
    CounterpartyDocuments,
    DocumentFileReceipt,
    DocumentFileView,
    DocumentHistory,
    DocumentInput,
    DocumentLinkReceipt,
    DocumentLinkResult,
    DocumentLinks,
    DocumentLinkView,
    DocumentList,
    DocumentReceipt,
    DocumentRevision,
    DocumentSummary,
    DocumentView,
    FileMetadata,
    LinkCounterpartyInput,
    LinkedCounterparty,
    LinkedDocument,
    UnlinkCounterpartyInput,
)
from gorgona_booking.business.file_errors import FileIntegrityError
from gorgona_booking.business.file_validation import ValidatedFile
from gorgona_booking.business.module_gate import (
    COUNTERPARTIES_MODULE,
    DOCUMENTS_MODULE,
    module_writes,
    require_module,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError


class DocumentStateError(ConflictError):
    code = "DOCUMENT_STATE_INVALID"


class DocumentAlreadyLinkedError(ConflictError):
    code = "DOCUMENT_ALREADY_LINKED"


class CounterpartyNotLinkableError(ConflictError):
    code = "COUNTERPARTY_STATE_INVALID"


_UPLOAD = "business.document_file.upload"
_SAVE = "business.document.save"
_LINK = "business.document.counterparty_link"

_FILE_COLUMNS = (
    "f.id, f.media_type, f.size_bytes, f.sha256, f.file_name, f.validator_version, f.uploaded_at"
)


def _file(row: tuple[Any, ...]) -> FileMetadata:
    return FileMetadata(
        file_id=row[0],
        media_type=row[1],
        size_bytes=row[2],
        sha256=row[3],
        file_name=row[4],
        validator_version=row[5],
        uploaded_at=row[6],
    )


async def load_file(
    conn: RuntimeConnection, business_id: UUID, file_id: UUID
) -> DocumentFileView | None:
    row = await (
        await conn.execute(
            f"select {_FILE_COLUMNS} from gba.document_files f "  # noqa: S608 - fixed columns
            "where f.tenant_id = %s and f.id = %s",
            (business_id, file_id),
        )
    ).fetchone()
    if row is None:
        return None
    return DocumentFileView(business_id=business_id, **_file(tuple(row)).model_dump())


async def precheck_upload(conn: RuntimeConnection, business_id: UUID, actor: str, key: str) -> None:
    """Before the body is read, refuse a new upload while the module is off. A key
    with a stored result may be a replay, which `store_file` answers after reading."""
    scope = IdempotencyScope(business_id, actor, _UPLOAD, key)
    stored = await (
        await conn.execute(
            "select 1 from gba.idempotency_keys where tenant_id = %s and actor_key = %s "
            "and operation = %s and idempotency_key = %s and expires_at > now()",
            (scope.tenant_id, scope.actor_key, scope.operation, scope.key),
        )
    ).fetchone()
    if stored is None:
        await require_module(conn, business_id, DOCUMENTS_MODULE)


async def store_file(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    file_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    validated: ValidatedFile,
    content: bytes,
) -> DocumentFileView:
    """Final upload transaction, after the body was read and validated off the loop."""
    scope = IdempotencyScope(business_id, actor, _UPLOAD, key)
    request_hash = commands.fingerprint(
        {
            "file_id": str(file_id),
            "sha256": validated.sha256,
            "size_bytes": validated.size_bytes,
            "media_type": validated.media_type,
            "file_name": validated.file_name,
        }
    )
    receipt = await commands.claim(conn, scope, request_hash, DocumentFileReceipt)
    if receipt is not None:
        return await _stored_file(conn, business_id, receipt.file_id)

    existing = await (
        await conn.execute(
            "select sha256, size_bytes, media_type, file_name, uploaded_by "
            "from gba.document_files where tenant_id = %s and id = %s",
            (business_id, file_id),
        )
    ).fetchone()
    if existing is not None:
        same = (
            validated.sha256,
            validated.size_bytes,
            validated.media_type,
            validated.file_name,
            user_id,
        )
        if tuple(existing) != same:
            raise ConflictError("This file identifier is already used. Upload with a new one.")
        # The caller's identical upload whose key expired: answer with the stored file.
        await commands.complete(conn, scope, DocumentFileReceipt(file_id=file_id))
        return await _stored_file(conn, business_id, file_id)
    await require_module(conn, business_id, DOCUMENTS_MODULE)
    async with module_writes(DOCUMENTS_MODULE):
        await conn.execute(
            "insert into gba.document_files (tenant_id, id, sha256, size_bytes, media_type, "
            "file_name, validator_version, content, uploaded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %b, %s)",
            (
                business_id,
                file_id,
                validated.sha256,
                validated.size_bytes,
                validated.media_type,
                validated.file_name,
                validated.validator_version,
                content,
                user_id,
            ),
        )
    await commands.audit(
        conn,
        business_id,
        actor,
        "document_file.uploaded",
        "document_file",
        str(file_id),
        {
            "size_bytes": validated.size_bytes,
            "media_type": validated.media_type,
            "sha256": validated.sha256,
            "validator_version": validated.validator_version,
        },
    )
    await commands.complete(conn, scope, DocumentFileReceipt(file_id=file_id))
    return await _stored_file(conn, business_id, file_id)


async def _stored_file(
    conn: RuntimeConnection, business_id: UUID, file_id: UUID
) -> DocumentFileView:
    result = await load_file(conn, business_id, file_id)
    if result is None:
        raise RuntimeError("A stored file is missing")
    return result


async def load_document(
    conn: RuntimeConnection,
    business_id: UUID,
    document_id: UUID,
    *,
    revision: int | None = None,
) -> DocumentView | None:
    row = await (
        await conn.execute(
            "select v.revision, v.title, v.category, v.valid_from, v.valid_until, v.archived, "
            "v.created_at, f.id, f.media_type, f.size_bytes, f.sha256, f.file_name, "
            "f.validator_version, f.uploaded_at "
            "from gba.document_versions v left join gba.document_files f "
            "on f.tenant_id = v.tenant_id and f.id = v.file_id "
            "where v.tenant_id = %s and v.document_id = %s "
            "and (%s::integer is null or v.revision = %s) "
            "order by v.revision desc limit 1",
            (business_id, document_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    return DocumentView(
        business_id=business_id,
        document_id=document_id,
        revision=row[0],
        title=row[1],
        category=row[2],
        valid_from=row[3],
        valid_until=row[4],
        archived=row[5],
        created_at=row[6],
        file=_file(tuple(row[7:14])) if row[7] is not None else None,
    )


async def _require(conn: RuntimeConnection, business_id: UUID, document_id: UUID) -> DocumentView:
    current = await load_document(conn, business_id, document_id)
    if current is None:
        raise NotFoundError("Document not found")
    return current


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


_LATEST_DOCUMENTS = (
    "latest as (select distinct on (v.document_id) v.document_id, v.revision, v.title, "
    "lower(v.title) as title_key, v.category, v.valid_from, v.valid_until, v.archived, "
    "v.created_at, f.media_type from gba.document_versions v "
    "left join gba.document_files f on f.tenant_id = v.tenant_id and f.id = v.file_id "
    "where v.tenant_id = %(business)s order by v.document_id, v.revision desc)"
)


def _summary(row: tuple[Any, ...]) -> DocumentSummary:
    return DocumentSummary(
        document_id=row[0],
        revision=row[1],
        title=row[2],
        category=row[3],
        valid_from=row[4],
        valid_until=row[5],
        archived=row[6],
        media_type=row[7],
        updated_at=row[8],
    )


async def list_documents(
    conn: RuntimeConnection,
    business_id: UUID,
    *,
    query: str | None,
    archived: bool,
    after: UUID | None,
    limit: int,
    uploads_enabled: bool,
) -> DocumentList:
    """Alphabetical by title; archived documents are listed separately."""
    rows = await (
        await conn.execute(
            f"with {_LATEST_DOCUMENTS} "  # noqa: S608 - fixed fragment
            "select l.document_id, l.revision, l.title, l.category, l.valid_from, "
            "l.valid_until, l.archived, l.media_type, l.created_at from latest l "
            "where l.archived = %(archived)s "
            "and (%(pattern)s::text is null or l.title ilike %(pattern)s) "
            "and (%(after)s::uuid is null or (l.title_key, l.document_id) > "
            "(select a.title_key, a.document_id from latest a where a.document_id = %(after)s)) "
            "order by l.title_key, l.document_id limit %(limit)s",
            {
                "business": business_id,
                "archived": archived,
                "pattern": _like(query) if query else None,
                "after": after,
                "limit": limit + 1,
            },
        )
    ).fetchall()
    items = tuple(_summary(tuple(row)) for row in rows[:limit])
    return DocumentList(
        business_id=business_id,
        file_uploads="enabled" if uploads_enabled else "scanner_not_configured",
        items=items,
        next_cursor=items[-1].document_id if len(rows) > limit else None,
    )


async def document_history(
    conn: RuntimeConnection,
    business_id: UUID,
    document_id: UUID,
    *,
    before: int | None,
    limit: int,
) -> DocumentHistory:
    await _require(conn, business_id, document_id)
    rows = await (
        await conn.execute(
            "select revision, title, archived, file_id, created_at from gba.document_versions "
            "where tenant_id = %s and document_id = %s "
            "and (%s::integer is null or revision < %s) order by revision desc limit %s",
            (business_id, document_id, before, before, limit + 1),
        )
    ).fetchall()
    items = tuple(
        DocumentRevision(revision=r[0], title=r[1], archived=r[2], file_id=r[3], created_at=r[4])
        for r in rows[:limit]
    )
    return DocumentHistory(
        business_id=business_id,
        document_id=document_id,
        items=items,
        next_cursor=items[-1].revision if len(rows) > limit else None,
    )


async def save_document(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    document_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: DocumentInput,
) -> DocumentView:
    scope = IdempotencyScope(business_id, actor, _SAVE, key)
    request_hash = commands.fingerprint(
        {"document_id": str(document_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, DocumentReceipt)
    if receipt is not None:
        return await _version(conn, business_id, receipt.document_id, receipt.revision)

    await require_module(conn, business_id, DOCUMENTS_MODULE)
    current = await load_document(conn, business_id, document_id)
    revision = current.revision if current else 0
    if body.expected_revision != revision:
        raise ConflictError("This document changed. Reload it before saving.", revision=revision)
    revision += 1
    try:
        async with module_writes(DOCUMENTS_MODULE), conn.transaction():
            if current is None:
                await conn.execute(
                    "insert into gba.documents (tenant_id, id, created_by) values (%s, %s, %s)",
                    (business_id, document_id, user_id),
                )
            await conn.execute(
                "insert into gba.document_versions (tenant_id, document_id, revision, title, "
                "category, valid_from, valid_until, archived, file_id, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business_id,
                    document_id,
                    revision,
                    body.title,
                    body.category,
                    body.valid_from,
                    body.valid_until,
                    body.archived,
                    body.file_id,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        if exc.diag.constraint_name != "document_versions_file_fk":
            raise
        raise InvalidReferenceError("Unknown file", field="file_id") from exc
    await commands.audit(
        conn,
        business_id,
        actor,
        "document.saved",
        "document",
        str(document_id),
        {
            "revision": revision,
            "category": body.category,
            "archived": body.archived,
            "file_id": str(body.file_id) if body.file_id else None,
            "has_validity": body.valid_from is not None or body.valid_until is not None,
        },
    )
    await commands.complete(
        conn, scope, DocumentReceipt(document_id=document_id, revision=revision)
    )
    return await _version(conn, business_id, document_id, revision)


async def _version(
    conn: RuntimeConnection, business_id: UUID, document_id: UUID, revision: int
) -> DocumentView:
    result = await load_document(conn, business_id, document_id, revision=revision)
    if result is None:
        raise RuntimeError("A stored document version is missing")
    return result


async def file_content(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    document_id: UUID,
    revision: int,
    actor: str,
) -> tuple[FileMetadata, bytes]:
    """The file of one saved version, re-verified against its stored hash and size."""
    row = await (
        await conn.execute(
            f"select {_FILE_COLUMNS}, f.content from gba.document_versions v "  # noqa: S608
            "join gba.document_files f on f.tenant_id = v.tenant_id and f.id = v.file_id "
            "where v.tenant_id = %s and v.document_id = %s and v.revision = %s",
            (business_id, document_id, revision),
            binary=True,
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("This document version has no file")
    metadata, content = _file(tuple(row[:7])), bytes(row[7])
    if (
        len(content) != metadata.size_bytes
        or hashlib.sha256(content).hexdigest() != metadata.sha256
    ):
        raise FileIntegrityError("The stored file failed its integrity check")
    await commands.audit(
        conn,
        business_id,
        actor,
        "document_file.downloaded",
        "document_file",
        str(metadata.file_id),
        {"document_id": str(document_id), "revision": revision},
    )
    return metadata, content


_LINK_COLUMNS = "id, document_id, counterparty_id, sequence, action, decided_at"


def _link(row: tuple[Any, ...]) -> DocumentLinkView:
    return DocumentLinkView(
        link_id=row[0],
        document_id=row[1],
        counterparty_id=row[2],
        sequence=row[3],
        action=row[4],
        decided_at=row[5],
    )


async def _load_link(conn: RuntimeConnection, business_id: UUID, link_id: UUID) -> DocumentLinkView:
    row = await (
        await conn.execute(
            f"select {_LINK_COLUMNS} from gba.document_counterparty_links "  # noqa: S608
            "where tenant_id = %s and id = %s",
            (business_id, link_id),
        )
    ).fetchone()
    if row is None:
        raise RuntimeError("A stored document link is missing")
    return _link(tuple(row))


async def change_counterparty_link(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    document_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: LinkCounterpartyInput | UnlinkCounterpartyInput,
) -> DocumentLinkResult:
    scope = IdempotencyScope(business_id, actor, _LINK, key)
    request_hash = commands.fingerprint(
        {"document_id": str(document_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, DocumentLinkReceipt)
    if receipt is not None:
        link = await _load_link(conn, business_id, receipt.link_id)
        return DocumentLinkResult(business_id=business_id, document_id=link.document_id, link=link)

    await require_module(conn, business_id, DOCUMENTS_MODULE)
    await require_module(conn, business_id, COUNTERPARTIES_MODULE)
    document = await _require(conn, business_id, document_id)
    card = await (
        await conn.execute(
            "select v.state from gba.counterparty_versions v "
            "where v.tenant_id = %s and v.counterparty_id = %s order by v.revision desc limit 1",
            (business_id, body.counterparty_id),
        )
    ).fetchone()
    if card is None:
        raise InvalidReferenceError("Unknown counterparty", field="counterparty_id")
    latest = await (
        await conn.execute(
            "select sequence, action from gba.document_counterparty_links "
            "where tenant_id = %s and document_id = %s and counterparty_id = %s "
            "order by sequence desc limit 1",
            (business_id, document_id, body.counterparty_id),
        )
    ).fetchone()
    if isinstance(body, LinkCounterpartyInput):
        if document.archived:
            raise DocumentStateError("Restore this document before linking it")
        if card[0] != "active":
            raise CounterpartyNotLinkableError("Only an active record can be linked")
        if latest is not None and latest[1] == "linked":
            raise DocumentAlreadyLinkedError("This document is already linked to the record")
        action = "linked"
    else:
        if latest is None or latest[1] != "linked":
            raise InvalidReferenceError(
                "This document is not linked to that record", field="counterparty_id"
            )
        if latest[0] != body.expected_sequence:
            raise ConflictError("This link changed. Reload it.", sequence=latest[0])
        action = "unlinked"
    sequence = (latest[0] if latest else 0) + 1
    try:
        async with module_writes(DOCUMENTS_MODULE, COUNTERPARTIES_MODULE), conn.transaction():
            row = await (
                await conn.execute(
                    "insert into gba.document_counterparty_links (tenant_id, document_id, "  # noqa: S608
                    "counterparty_id, sequence, action, decided_by) "
                    "values (%s, %s, %s, %s, %s, %s) "
                    f"returning {_LINK_COLUMNS}",
                    (business_id, document_id, body.counterparty_id, sequence, action, user_id),
                )
            ).fetchone()
    except (CheckViolation, UniqueViolation) as exc:
        # The trigger re-checks under the counterparty lock: a card merged or archived,
        # or a concurrent link, since the checks above.
        raise ConflictError("This document or record changed. Reload it.") from exc
    if row is None:
        raise RuntimeError("Link insert returned nothing")
    link = _link(tuple(row))
    await commands.audit(
        conn,
        business_id,
        actor,
        f"document.counterparty_{action}",
        "document",
        str(document_id),
        {"counterparty_id": str(body.counterparty_id), "sequence": sequence},
    )
    await commands.complete(conn, scope, DocumentLinkReceipt(link_id=link.link_id))
    return DocumentLinkResult(business_id=business_id, document_id=document_id, link=link)


async def document_links(
    conn: RuntimeConnection, business_id: UUID, document_id: UUID
) -> DocumentLinks:
    await _require(conn, business_id, document_id)
    history = await (
        await conn.execute(
            f"select {_LINK_COLUMNS} from gba.document_counterparty_links "  # noqa: S608
            "where tenant_id = %s and document_id = %s order by id desc limit 200",
            (business_id, document_id),
        )
    ).fetchall()
    current = await (
        await conn.execute(
            "with latest_links as (select distinct on (l.counterparty_id) l.counterparty_id, "
            "l.sequence, l.action, l.decided_at from gba.document_counterparty_links l "
            "where l.tenant_id = %(business)s and l.document_id = %(document)s "
            "order by l.counterparty_id, l.sequence desc) "
            "select ll.counterparty_id, v.display_name, v.state, ll.sequence, ll.decided_at "
            "from latest_links ll join lateral (select x.display_name, x.state "
            "from gba.counterparty_versions x where x.tenant_id = %(business)s "
            "and x.counterparty_id = ll.counterparty_id order by x.revision desc limit 1) v "
            "on true where ll.action = 'linked' "
            "order by lower(v.display_name), ll.counterparty_id",
            {"business": business_id, "document": document_id},
        )
    ).fetchall()
    return DocumentLinks(
        business_id=business_id,
        document_id=document_id,
        current=tuple(
            LinkedCounterparty(
                counterparty_id=r[0], display_name=r[1], state=r[2], sequence=r[3], decided_at=r[4]
            )
            for r in current
        ),
        history=tuple(_link(tuple(row)) for row in history),
    )


async def counterparty_documents(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> CounterpartyDocuments:
    """Documents linked to the record or to a duplicate merged into it."""
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
            f"with {_LATEST_DOCUMENTS}, "  # noqa: S608 - fixed fragments
            "family as (select %(record)s::uuid as id union "
            "select v.counterparty_id from gba.counterparty_versions v "
            "where v.tenant_id = %(business)s and v.merged_into = %(record)s "
            "and v.revision = (select max(x.revision) from gba.counterparty_versions x "
            "where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)), "
            "latest_links as (select distinct on (l.document_id, l.counterparty_id) l.* "
            "from gba.document_counterparty_links l where l.tenant_id = %(business)s "
            "order by l.document_id, l.counterparty_id, l.sequence desc) "
            "select d.document_id, d.revision, d.title, d.category, d.valid_from, "
            "d.valid_until, d.archived, d.media_type, d.created_at, ll.id, "
            "ll.counterparty_id, ll.sequence, ll.decided_at "
            "from latest_links ll join family f on f.id = ll.counterparty_id "
            "join latest d on d.document_id = ll.document_id "
            "where ll.action = 'linked' and (%(after)s::uuid is null or ll.id < %(after)s) "
            "order by ll.id desc limit %(limit)s",
            {
                "business": business_id,
                "record": counterparty_id,
                "after": after,
                "limit": limit + 1,
            },
        )
    ).fetchall()
    items = tuple(
        LinkedDocument(
            document=_summary(tuple(row[:9])),
            counterparty_id=row[10],
            sequence=row[11],
            decided_at=row[12],
        )
        for row in rows[:limit]
    )
    return CounterpartyDocuments(
        business_id=business_id,
        counterparty_id=counterparty_id,
        items=items,
        next_cursor=rows[limit - 1][9] if len(rows) > limit else None,
    )
