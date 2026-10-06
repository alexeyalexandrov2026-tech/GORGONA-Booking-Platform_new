"""Company-wide documents, raw file uploads and verified downloads (ADR-0020 E2).

Upload order (ADR-0021): refuse staging/production before anything is read, check the
declared type and length, authorize briefly without holding locks while bytes arrive,
read the body with a hard cap, validate off the event loop with bounded work, then
reauthorize and store in one transaction. Files are always downloaded as attachments.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import quote, unquote
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Request
from fastapi.responses import Response

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import ROLE_PERMISSIONS, Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.business import documents as service
from gorgona_booking.business.document_contracts import (
    MEDIA_TYPES,
    CounterpartyDocuments,
    DocumentFileView,
    DocumentHistory,
    DocumentInput,
    DocumentLinkInput,
    DocumentLinkResult,
    DocumentLinks,
    DocumentList,
    DocumentView,
)
from gorgona_booking.business.file_errors import (
    FileScanningNotConfiguredError,
    FileTooLargeError,
    InvalidFileNameError,
    UnsupportedMediaTypeError,
)
from gorgona_booking.business.file_validation import MAX_FILE_BYTES, validate_file
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import (
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses", tags=["documents"])
Limit = Annotated[int, Query(ge=1, le=100)]
Revision = Annotated[int | None, Query(ge=1, le=2_147_483_647)]
VersionNumber = Annotated[int, Path(ge=1, le=2_147_483_647)]
# Environments where uploads wait for a malware scanner (owner decision, ADR-0020).
_SCANNER_REQUIRED = frozenset({"staging", "production"})


def _uploads_enabled(request: Request) -> bool:
    return request.app.state.settings.environment not in _SCANNER_REQUIRED


@asynccontextmanager
async def _access(
    request: Request,
    principal: Principal,
    business_id: UUID,
    permission: Permission,
    *,
    exclusive: bool = False,
) -> AsyncIterator[TenantAccess]:
    # Company-wide only: no branch, delegation or platform opt-in.
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        exclusive="documents" if exclusive else None,
    ) as access:
        # Optional modules fail closed if an access boundary or gate is missing or altered.
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/{business_id}/documents")
async def get_documents(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    archived: bool = False,
    after: UUID | None = None,
    limit: Limit = 50,
) -> DocumentList:
    async with _access(request, principal, business_id, Permission.DOCUMENTS_READ) as access:
        return await service.list_documents(
            access.conn,
            business_id,
            query=q,
            archived=archived,
            after=after,
            limit=limit,
            uploads_enabled=_uploads_enabled(request),
        )


@router.get("/{business_id}/documents/{document_id}")
async def get_document(
    business_id: UUID,
    document_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> DocumentView:
    async with _access(request, principal, business_id, Permission.DOCUMENTS_READ) as access:
        result = await service.load_document(
            access.conn, business_id, document_id, revision=revision
        )
        if result is None:
            raise NotFoundError("Document version not found")
        return result


@router.put("/{business_id}/documents/{document_id}")
async def put_document(
    business_id: UUID,
    document_id: UUID,
    body: DocumentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DocumentView:
    async with _access(
        request, principal, business_id, Permission.DOCUMENTS_MANAGE, exclusive=True
    ) as access:
        return await service.save_document(
            access.conn,
            business_id=business_id,
            document_id=document_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{business_id}/documents/{document_id}/versions")
async def get_document_history(
    business_id: UUID,
    document_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    before: Revision = None,
    limit: Limit = 50,
) -> DocumentHistory:
    async with _access(request, principal, business_id, Permission.DOCUMENTS_READ) as access:
        return await service.document_history(
            access.conn, business_id, document_id, before=before, limit=limit
        )


def _content_disposition(file_name: str) -> str:
    fallback = "".join(
        c if c.isascii() and c.isprintable() and c not in '"\\;' else "_" for c in file_name
    )
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(file_name, safe='')}"


@router.get("/{business_id}/documents/{document_id}/versions/{revision}/file")
async def get_document_file(
    business_id: UUID,
    document_id: UUID,
    revision: VersionNumber,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with _access(request, principal, business_id, Permission.DOCUMENTS_READ) as access:
        metadata, content = await service.file_content(
            access.conn,
            business_id=business_id,
            document_id=document_id,
            revision=revision,
            actor=principal.actor,
        )
    return Response(
        content,
        media_type=metadata.media_type,
        headers={
            "Content-Disposition": _content_disposition(metadata.file_name),
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
            # A separate policy; the framing middleware appends frame-ancestors.
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-File-SHA256": metadata.sha256,
        },
    )


@router.get("/{business_id}/document-files/{file_id}")
async def get_file_metadata(
    business_id: UUID,
    file_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> DocumentFileView:
    async with _access(request, principal, business_id, Permission.DOCUMENTS_READ) as access:
        result = await service.load_file(access.conn, business_id, file_id)
        if result is None:
            raise NotFoundError("File not found")
        return result


async def _read_capped(request: Request) -> bytes:
    """The whole body, refusing it as soon as it exceeds the cap (also when chunked)."""
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_FILE_BYTES:
            raise FileTooLargeError("Files must not exceed 10 MiB")
    return bytes(data)


@router.put("/{business_id}/document-files/{file_id}")
async def put_document_file(
    business_id: UUID,
    file_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
    content_type: Annotated[str | None, Header()] = None,
    content_length: Annotated[int | None, Header(ge=0)] = None,
    file_name: Annotated[str | None, Header(alias="X-File-Name", max_length=12288)] = None,
) -> DocumentFileView:
    if not _uploads_enabled(request):
        raise FileScanningNotConfiguredError(
            "File uploads need a malware scanner, which is not configured in this environment"
        )
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if declared not in MEDIA_TYPES:
        raise UnsupportedMediaTypeError("Upload a PDF, PNG or JPEG file")
    if content_length is not None and content_length > MAX_FILE_BYTES:
        raise FileTooLargeError("Files must not exceed 10 MiB")
    try:
        original_name = unquote(file_name, encoding="utf-8", errors="strict") if file_name else ""
    except UnicodeDecodeError as exc:
        raise InvalidFileNameError("Send the file name percent-encoded as UTF-8") from exc
    # Brief check: no locks are held while the bytes arrive.
    async with _access(request, principal, business_id, Permission.DOCUMENTS_MANAGE) as access:
        await service.precheck_upload(access.conn, business_id, principal.actor, idempotency_key)
    content = await _read_capped(request)
    validated = await asyncio.to_thread(validate_file, content, declared, original_name or "file")
    async with _access(
        request, principal, business_id, Permission.DOCUMENTS_MANAGE, exclusive=True
    ) as access:
        return await service.store_file(
            access.conn,
            business_id=business_id,
            file_id=file_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            validated=validated,
            content=content,
        )


@router.get("/{business_id}/documents/{document_id}/counterparty-links")
async def get_document_links(
    business_id: UUID,
    document_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> DocumentLinks:
    async with _access(request, principal, business_id, Permission.DOCUMENTS_READ) as access:
        _require_counterparty_access(access)
        return await service.document_links(access.conn, business_id, document_id)


@router.post("/{business_id}/documents/{document_id}/counterparty-links")
async def post_document_link(
    business_id: UUID,
    document_id: UUID,
    body: DocumentLinkInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DocumentLinkResult:
    async with _access(
        request, principal, business_id, Permission.DOCUMENTS_MANAGE, exclusive=True
    ) as access:
        _require_counterparty_access(access)
        return await service.change_counterparty_link(
            access.conn,
            business_id=business_id,
            document_id=document_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{business_id}/counterparties/{counterparty_id}/documents")
async def get_counterparty_documents(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> CounterpartyDocuments:
    async with _access(request, principal, business_id, Permission.DOCUMENTS_READ) as access:
        _require_counterparty_access(access)
        return await service.counterparty_documents(
            access.conn, business_id, counterparty_id, after=after, limit=limit
        )


def _require_counterparty_access(access: TenantAccess) -> None:
    """Links name counterparties: their readers need both permissions."""
    if Permission.COUNTERPARTIES_READ not in ROLE_PERMISSIONS.get(access.role or "", frozenset()):
        raise PermissionDeniedError("Counterparty access is required for document links")
