"""Company-wide financial foundation (ADR-0023, FIN-01)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import ledger as service
from gorgona_booking.business.ledger_contracts import (
    ACCOUNT_CODE_PATTERN,
    CURRENCY_PATTERN,
    MONTH_PATTERN,
    AccountInput,
    BookInput,
    CloseInput,
    CommandReference,
    CommandStatus,
    EntryInput,
    JournalEntryList,
    JournalEntryListV2,
    JournalEntryView,
    JournalEntryViewV2,
    LedgerAccountList,
    LedgerAccountView,
    LedgerBookView,
    LedgerOverview,
    LedgerPeriodList,
    LedgerPeriodView,
    ReopenInput,
    ReversalInput,
    TrialBalance,
    month,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/ledger", tags=["ledger"])
Limit = Annotated[int, Query(ge=1, le=100)]
Month = Annotated[str, Query(pattern=MONTH_PATTERN)]


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.FINANCE_READ,
    *,
    lock: bool = False,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        exclusive="ledger" if lock or permission != Permission.FINANCE_READ else None,
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


CommandKey = Annotated[str, Path(min_length=8, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$")]


@router.post("/commands/{key}/resolve")
async def resolve_command(
    business_id: UUID,
    key: CommandKey,
    body: CommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> CommandStatus:
    async with _access(request, principal, business_id, lock=True) as access:
        return await service.resolve_command(
            access.conn,
            business_id=business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.post("/commands/{key}/cancel")
async def cancel_command(
    business_id: UUID,
    key: CommandKey,
    body: CommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> CommandStatus:
    permission = (
        Permission.FINANCE_CLOSE
        if body.operation in ("close", "reopen")
        else Permission.FINANCE_MANAGE
    )
    async with _access(request, principal, business_id, permission) as access:
        return await service.cancel_unresolved_command(
            access.conn,
            business_id=business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("")
async def overview(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: str | None = None,
    limit: Limit = 50,
    book_id: UUID | None = None,
) -> LedgerOverview:
    async with _access(request, principal, business_id) as access:
        return await service.ledger_overview(
            access.conn, business_id, after=after, limit=limit, book_id=book_id
        )


@router.get("/books/{book_id}")
async def get_book(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Annotated[int | None, Query(ge=1, le=2147483647)] = None,
) -> LedgerBookView:
    async with _access(request, principal, business_id) as access:
        result = await service.load_book(access.conn, business_id, book_id, revision=revision)
        if result is None:
            raise NotFoundError("Book version not found")
        return result


@router.put("/books/{book_id}")
async def put_book(
    business_id: UUID,
    book_id: UUID,
    body: BookInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> LedgerBookView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await service.save_book(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/books/{book_id}/accounts")
async def accounts(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: Annotated[str | None, Query(pattern=ACCOUNT_CODE_PATTERN)] = None,
    limit: Limit = 50,
) -> LedgerAccountList:
    async with _access(request, principal, business_id) as access:
        return await service.list_accounts(
            access.conn, business_id, book_id, after=after, limit=limit
        )


@router.get("/books/{book_id}/accounts/{account_id}")
async def get_account(
    business_id: UUID,
    book_id: UUID,
    account_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> LedgerAccountView:
    async with _access(request, principal, business_id) as access:
        result = await service.load_account(access.conn, business_id, book_id, account_id)
        if result is None:
            raise NotFoundError("Account not found")
        return result


@router.put("/books/{book_id}/accounts/{account_id}")
async def put_account(
    business_id: UUID,
    book_id: UUID,
    account_id: UUID,
    body: AccountInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> LedgerAccountView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await service.save_account(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            account_id=account_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/books/{book_id}/entries")
async def entries(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    period: Annotated[str | None, Query(pattern=MONTH_PATTERN)] = None,
    after: UUID | None = None,
    limit: Limit = 50,
    schema_version: Literal["1", "2"] = "1",
) -> JournalEntryList | JournalEntryListV2:
    async with _access(request, principal, business_id) as access:
        if schema_version == "2":
            return await service.list_entries(
                access.conn,
                business_id,
                book_id,
                period=month(period) if period else None,
                after=after,
                limit=limit,
                view_version=2,
            )
        return await service.list_entries(
            access.conn,
            business_id,
            book_id,
            period=month(period) if period else None,
            after=after,
            limit=limit,
        )


@router.get("/books/{book_id}/entries/{entry_id}")
async def get_entry(
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    schema_version: Literal["1", "2"] = "1",
) -> JournalEntryView | JournalEntryViewV2:
    async with _access(request, principal, business_id) as access:
        result = (
            await service.load_entry(access.conn, business_id, book_id, entry_id, view_version=2)
            if schema_version == "2"
            else await service.load_entry(access.conn, business_id, book_id, entry_id)
        )
        if result is None:
            raise NotFoundError("Journal entry not found")
        return result


@router.put("/books/{book_id}/entries/{entry_id}")
async def put_entry(
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    body: EntryInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> JournalEntryView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await service.post_entry(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            entry_id=entry_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/books/{book_id}/entries/{entry_id}/reverse")
async def reverse(
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    body: ReversalInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> JournalEntryView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await service.reverse_entry(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            entry_id=entry_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/books/{book_id}/periods")
async def periods(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    before: Annotated[str | None, Query(pattern=MONTH_PATTERN)] = None,
    limit: Limit = 50,
) -> LedgerPeriodList:
    async with _access(request, principal, business_id) as access:
        return await service.list_periods(
            access.conn, business_id, book_id, before=month(before) if before else None, limit=limit
        )


@router.get("/books/{book_id}/periods/{period}")
async def get_period(
    business_id: UUID, book_id: UUID, period: str, request: Request, principal: CurrentPrincipal
) -> LedgerPeriodView:
    from gorgona_booking.business.ledger import LedgerInputError

    try:
        parsed = month(period)
    except ValueError as exc:
        raise LedgerInputError("Write the month as YYYY-MM") from exc
    async with _access(request, principal, business_id) as access:
        return await service.load_period(access.conn, business_id, book_id, parsed)


@router.post("/books/{book_id}/periods/{period}/close")
async def close(
    business_id: UUID,
    book_id: UUID,
    period: str,
    body: CloseInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> LedgerPeriodView:
    return await _change_period(
        business_id, book_id, period, body, request, principal, idempotency_key
    )


@router.post("/books/{book_id}/periods/{period}/reopen")
async def reopen(
    business_id: UUID,
    book_id: UUID,
    period: str,
    body: ReopenInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> LedgerPeriodView:
    return await _change_period(
        business_id, book_id, period, body, request, principal, idempotency_key
    )


async def _change_period(
    business_id: UUID,
    book_id: UUID,
    period: str,
    body: CloseInput | ReopenInput,
    request: Request,
    principal: CurrentPrincipal,
    key: str,
) -> LedgerPeriodView:
    try:
        parsed = month(period)
    except ValueError as exc:
        raise service.LedgerInputError("Write the month as YYYY-MM") from exc
    async with _access(request, principal, business_id, Permission.FINANCE_CLOSE) as access:
        return await service.change_period(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            period=parsed,
            action="reopened" if isinstance(body, ReopenInput) else "closed",
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/books/{book_id}/trial-balance")
async def report(
    business_id: UUID,
    book_id: UUID,
    period_from: Month,
    period_to: Month,
    request: Request,
    principal: CurrentPrincipal,
    currency: Annotated[str | None, Query(pattern=CURRENCY_PATTERN)] = None,
) -> TrialBalance:
    async with _access(request, principal, business_id) as access:
        return await service.trial_balance(
            access.conn,
            business_id,
            book_id,
            period_from=month(period_from),
            period_to=month(period_to),
            currency=currency,
        )
