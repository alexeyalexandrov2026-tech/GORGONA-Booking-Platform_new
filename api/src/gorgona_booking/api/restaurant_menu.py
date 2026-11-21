"""REST-01 Slice 2: versioned menu items, modifiers and recipe BOMs."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import restaurant_menu as menu
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/restaurant", tags=["restaurant"])


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


@router.get("/menu-items")
async def list_menu_items(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    category: str | None = None,
    kitchen_station: menu.KitchenStation | None = None,
    active_only: bool = False,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> menu.MenuItemList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await menu.list_menu_items(
            access.conn,
            business_id,
            location_id=location_id,
            category=category,
            kitchen_station=kitchen_station,
            active_only=active_only,
            after=after,
            limit=limit,
        )


@router.get("/menu-items/{menu_item_id}")
async def get_menu_item(
    business_id: UUID,
    menu_item_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
) -> menu.MenuItemView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await menu.get_menu_item(access.conn, business_id, menu_item_id, revision=revision)


@router.get("/menu-items/{menu_item_id}/revisions")
async def list_menu_item_revisions(
    business_id: UUID,
    menu_item_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> menu.MenuItemRevisionList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await menu.list_menu_item_revisions(access.conn, business_id, menu_item_id)


@router.put("/menu-items/{menu_item_id}")
async def put_menu_item(
    business_id: UUID,
    menu_item_id: UUID,
    body: menu.MenuItemInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> menu.MenuItemView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        return await menu.save_menu_item(
            access.conn,
            business_id,
            menu_item_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.put("/menu-items/{menu_item_id}/modifier-groups")
async def put_menu_item_modifier_groups(
    business_id: UUID,
    menu_item_id: UUID,
    body: menu.MenuItemModifierGroupsInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> menu.MenuItemModifierGroupsView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        return await menu.set_menu_item_modifier_groups(
            access.conn,
            business_id,
            menu_item_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/modifier-groups")
async def list_modifier_groups(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    active_only: bool = False,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> menu.ModifierGroupList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await menu.list_modifier_groups(
            access.conn,
            business_id,
            location_id=location_id,
            active_only=active_only,
            after=after,
            limit=limit,
        )


@router.get("/modifier-groups/{group_id}")
async def get_modifier_group(
    business_id: UUID,
    group_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> menu.ModifierGroupView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await menu.get_modifier_group(access.conn, business_id, group_id)


@router.put("/modifier-groups/{group_id}")
async def put_modifier_group(
    business_id: UUID,
    group_id: UUID,
    body: menu.ModifierGroupInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> menu.ModifierGroupView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        return await menu.save_modifier_group(
            access.conn,
            business_id,
            group_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.put("/modifier-groups/{group_id}/options/{option_id}")
async def put_modifier_option(
    business_id: UUID,
    group_id: UUID,
    option_id: UUID,
    body: menu.ModifierOptionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> menu.ModifierOptionView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        return await menu.save_modifier_option(
            access.conn,
            business_id,
            group_id,
            option_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/menu-items/{menu_item_id}/recipes")
async def list_recipes(
    business_id: UUID,
    menu_item_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> menu.RecipeList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await menu.list_recipes(access.conn, business_id, menu_item_id)


@router.get("/menu-items/{menu_item_id}/recipes/{revision}")
async def get_recipe(
    business_id: UUID,
    menu_item_id: UUID,
    revision: Annotated[int, Path(ge=1, le=2_147_483_647)],
    request: Request,
    principal: CurrentPrincipal,
) -> menu.RecipeView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await menu.get_recipe(access.conn, business_id, menu_item_id, revision)


@router.post("/menu-items/{menu_item_id}/recipes")
async def create_recipe(
    business_id: UUID,
    menu_item_id: UUID,
    body: menu.RecipeInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> menu.RecipeView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        return await menu.create_recipe_revision(
            access.conn,
            business_id,
            menu_item_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
