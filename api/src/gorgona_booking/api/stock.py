"""Stock API of J2 to J4: accounts of materials, receipts, write-offs, transfers, returns,
balances and cost.

Quantities follow the branch scope of the caller, and so does a transfer, which moves
quantities only. Amounts, cost and posting rules are company-wide finance data: a
branch-limited member, a delegate and platform support never receive them.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import ROLE_PERMISSIONS, Permission
from gorgona_booking.business import stock as service
from gorgona_booking.business.stock_contracts import (
    BalanceList,
    CostList,
    DocumentInput,
    DocumentList,
    DocumentView,
    PostingRulesInput,
    PostingRulesView,
    TransferInput,
)
from gorgona_booking.db.inventory_guard import assert_inventory_ready
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import (
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/inventory", tags=["inventory"])
Revision = Annotated[int | None, Query(ge=1, le=2147483647)]
Limit = Annotated[int, Query(ge=1, le=100)]
_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
BalanceCursor = Annotated[str | None, Query(pattern=f"^{_UUID}:{_UUID}:{_UUID}$")]
CostCursor = Annotated[str | None, Query(pattern=f"^{_UUID}:{_UUID}$")]


@asynccontextmanager
async def _branch(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.INVENTORY_READ,
) -> AsyncIterator[TenantAccess]:
    """Quantities, read or moved between places: the branch scope of the caller applies."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=True,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        await assert_inventory_ready(access.conn)
        yield access


@asynccontextmanager
async def _company(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission,
    *,
    lock: bool = False,
) -> AsyncIterator[TenantAccess]:
    """Money: company-wide members only; a write takes the ledger posting lock first."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        exclusive="ledger" if lock else None,
    ) as access:
        await assert_location_scope_ready(access.conn)
        await assert_inventory_ready(access.conn)
        yield access


def _holds(access: TenantAccess, permission: Permission) -> bool:
    return (
        access.via == "membership"
        and access.location_id is None
        and access.role is not None
        and permission in ROLE_PERMISSIONS[access.role]
    )


def _ids(cursor: str | None) -> tuple[UUID, ...] | None:
    return tuple(UUID(part) for part in cursor.split(":")) if cursor else None


@router.get("/posting-rules/{book_id}")
async def get_posting_rules(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> PostingRulesView:
    async with _company(request, principal, business_id, Permission.FINANCE_READ) as access:
        return await service.load_rules(access.conn, business_id, book_id, revision)


@router.put("/posting-rules/{book_id}")
async def put_posting_rules(
    business_id: UUID,
    book_id: UUID,
    body: PostingRulesInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> PostingRulesView:
    async with _company(
        request, principal, business_id, Permission.FINANCE_MANAGE, lock=True
    ) as access:
        return await service.save_rules(
            access.conn,
            business_id,
            book_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


@router.get("/documents")
async def get_documents(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    place_id: UUID | None = None,
    after: UUID | None = None,
    limit: Limit = 100,
) -> DocumentList:
    async with _branch(request, principal, business_id) as access:
        return await service.list_documents(access.conn, business_id, place_id, after, limit)


@router.get("/documents/{document_id}")
async def get_document(
    business_id: UUID,
    document_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> DocumentView:
    async with _branch(request, principal, business_id) as access:
        return await service.load_document(
            access.conn,
            business_id,
            document_id,
            money=_holds(access, Permission.FINANCE_READ),
        )


@router.put("/documents/{document_id}")
async def put_document(
    business_id: UUID,
    document_id: UUID,
    body: DocumentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DocumentView:
    if isinstance(body, TransferInput):
        # A transfer moves quantities only: no posting lock and no finance right. The
        # branch scope decides which places exist for the caller.
        async with _branch(request, principal, business_id, Permission.INVENTORY_MANAGE) as access:
            return await service.post_transfer(
                access.conn,
                business_id,
                document_id,
                principal.user_id,
                principal.actor,
                idempotency_key,
                body,
            )
    async with _company(
        request, principal, business_id, Permission.INVENTORY_MANAGE, lock=True
    ) as access:
        # A receipt, a write-off and a return change the books: they also need the right
        # to manage finance.
        if not _holds(access, Permission.FINANCE_MANAGE):
            raise PermissionDeniedError("Posting a stock document also requires finance access")
        return await service.post_document(
            access.conn,
            business_id,
            document_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


@router.get("/balances")
async def get_balances(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    place_id: UUID | None = None,
    item_id: UUID | None = None,
    after: BalanceCursor = None,
    limit: Limit = 100,
) -> BalanceList:
    async with _branch(request, principal, business_id) as access:
        cursor = _ids(after)
        return await service.list_balances(
            access.conn,
            business_id,
            place_id,
            item_id,
            (cursor[0], cursor[1], cursor[2]) if cursor else None,
            limit,
        )


@router.get("/costs")
async def get_costs(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: CostCursor = None,
    limit: Limit = 100,
) -> CostList:
    async with _company(request, principal, business_id, Permission.FINANCE_READ) as access:
        cursor = _ids(after)
        return await service.list_costs(
            access.conn, business_id, (cursor[0], cursor[1]) if cursor else None, limit
        )
