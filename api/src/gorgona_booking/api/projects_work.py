"""PRO-01 Slice 2 API: stages, tasks, DAG dependencies, restricted matter files, and ACL search."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import quote, unquote
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import Response

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import projects_work as pw
from gorgona_booking.business.document_contracts import MEDIA_TYPES
from gorgona_booking.business.file_errors import (
    FileScanningNotConfiguredError,
    FileTooLargeError,
    InvalidFileNameError,
    UnsupportedMediaTypeError,
)
from gorgona_booking.business.file_validation import MAX_FILE_BYTES, validate_file
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/projects", tags=["projects"])
_SCANNER_REQUIRED = frozenset({"staging", "production"})


@asynccontextmanager
async def _access(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    permission: Permission,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=True,
        allow_delegation=False,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


def _content_disposition(file_name: str) -> str:
    fallback = "".join(
        c if c.isascii() and c.isprintable() and c not in '"\\;' else "_" for c in file_name
    )
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(file_name, safe='')}"


async def _read_capped(request: Request) -> bytes:
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_FILE_BYTES:
            raise FileTooLargeError("Files must not exceed 10 MiB")
    return bytes(data)


@router.get("/search")
async def search_projects(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> pw.ProjectSearchResult:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pw.search_projects(access.conn, business_id, query=q, limit=limit)


@router.get("/matters/{matter_id}/stages")
async def list_stages(
    business_id: UUID, matter_id: UUID, request: Request, principal: CurrentPrincipal
) -> pw.StageList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pw.list_stages(access.conn, business_id, matter_id)


@router.put("/matters/{matter_id}/stages/{stage_id}")
async def put_stage(
    business_id: UUID,
    matter_id: UUID,
    stage_id: UUID,
    body: pw.StageInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pw.StageView:
    async with _access(business_id, request, principal, Permission.PROJECTS_MANAGE) as access:
        return await pw.save_stage(
            access.conn,
            business_id,
            matter_id,
            stage_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/matters/{matter_id}/stages/{stage_id}/submit")
async def post_submit_stage(
    business_id: UUID,
    matter_id: UUID,
    stage_id: UUID,
    body: pw.StageSubmitInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pw.StageView:
    async with _access(business_id, request, principal, Permission.PROJECTS_WORK) as access:
        return await pw.submit_stage_deliverable(
            access.conn,
            business_id,
            matter_id,
            stage_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/matters/{matter_id}/stages/{stage_id}/decision")
async def post_decide_stage(
    business_id: UUID,
    matter_id: UUID,
    stage_id: UUID,
    body: pw.StageDecisionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pw.StageView:
    async with _access(business_id, request, principal, Permission.PROJECTS_MANAGE) as access:
        return await pw.decide_stage(
            access.conn,
            business_id,
            matter_id,
            stage_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/matters/{matter_id}/tasks")
async def list_tasks(
    business_id: UUID,
    matter_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    stage_id: UUID | None = None,
    status: pw.TaskStatus | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> pw.TaskList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pw.list_tasks(
            access.conn,
            business_id,
            matter_id,
            stage_id=stage_id,
            status=status,
            after=after,
            limit=limit,
        )


@router.get("/matters/{matter_id}/tasks/{task_id}")
async def get_task(
    business_id: UUID,
    matter_id: UUID,
    task_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> pw.TaskView:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pw.get_task(access.conn, business_id, matter_id, task_id)


@router.put("/matters/{matter_id}/tasks/{task_id}")
async def put_task(
    business_id: UUID,
    matter_id: UUID,
    task_id: UUID,
    body: pw.TaskInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pw.TaskView:
    async with _access(business_id, request, principal, Permission.PROJECTS_WORK) as access:
        return await pw.save_task(
            access.conn,
            business_id,
            matter_id,
            task_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/matters/{matter_id}/tasks/{task_id}/dependencies")
async def list_task_dependencies(
    business_id: UUID,
    matter_id: UUID,
    task_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> pw.TaskDependencyList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pw.list_task_dependencies(access.conn, business_id, matter_id, task_id)


@router.post("/matters/{matter_id}/tasks/{task_id}/dependencies")
async def post_task_dependency(
    business_id: UUID,
    matter_id: UUID,
    task_id: UUID,
    body: pw.TaskDependencyInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pw.TaskDependencyView:
    async with _access(business_id, request, principal, Permission.PROJECTS_WORK) as access:
        return await pw.add_task_dependency(
            access.conn,
            business_id,
            matter_id,
            task_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/matters/{matter_id}/files")
async def list_matter_files(
    business_id: UUID, matter_id: UUID, request: Request, principal: CurrentPrincipal
) -> pw.MatterFileList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pw.list_matter_files(access.conn, business_id, matter_id)


@router.put("/matters/{matter_id}/files/{file_id}")
async def put_matter_file(
    business_id: UUID,
    matter_id: UUID,
    file_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
    title: Annotated[str, Query(min_length=1, max_length=200)],
    category: pw.FileCategory = "other",
    stage_id: UUID | None = None,
    task_id: UUID | None = None,
    linked_document_id: UUID | None = None,
    content_type: Annotated[str | None, Header()] = None,
    content_length: Annotated[int | None, Header(ge=0)] = None,
    file_name: Annotated[str | None, Header(alias="X-File-Name", max_length=12288)] = None,
) -> pw.MatterFileView:
    if request.app.state.settings.environment in _SCANNER_REQUIRED:
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
    content = await _read_capped(request)
    validated = await asyncio.to_thread(validate_file, content, declared, original_name or "file")
    async with _access(business_id, request, principal, Permission.PROJECTS_WORK) as access:
        return await pw.upload_matter_file(
            access.conn,
            business_id,
            matter_id,
            file_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            title=title,
            category=category,
            stage_id=stage_id,
            task_id=task_id,
            linked_document_id=linked_document_id,
            validated=validated,
            content=content,
        )


@router.get("/matters/{matter_id}/files/{file_id}/content")
async def get_matter_file_content(
    business_id: UUID,
    matter_id: UUID,
    file_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        meta, content = await pw.get_matter_file_content(
            access.conn, business_id, matter_id, file_id, actor=principal.actor
        )
    return Response(
        content,
        media_type=meta.media_type,
        headers={
            "Content-Disposition": _content_disposition(meta.file_name),
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-File-SHA256": meta.sha256,
        },
    )
