"""HTTP routes for AMARKAL v2.16.0 No-Code Workspace Studio (Custom Fields, Kanban, Brand Theme)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.workspace_studio import (
    BoardEntityKind,
    BrandThemeView,
    CardPriority,
    CustomFieldDefinitionView,
    CustomFieldType,
    CustomFieldValueView,
    EntityKind,
    SurfacePreset,
    WorkspaceBoardCardView,
    WorkspaceBoardView,
    create_board_card,
    create_custom_field_definition,
    create_workspace_board,
    delete_board_card,
    delete_custom_field_definition,
    delete_workspace_board,
    get_brand_theme,
    list_board_cards,
    list_custom_field_definitions,
    list_custom_field_values,
    list_workspace_boards,
    move_board_card,
    upsert_brand_theme,
    upsert_custom_field_value,
)
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(
    prefix="/v1/businesses/{business_id}/workspace-studio", tags=["workspace-studio"]
)


class CustomFieldDefinitionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    entity_kind: EntityKind
    field_key: str
    label: str
    field_type: CustomFieldType
    options: list[str]
    is_required: bool
    display_order: int
    created_at: datetime


class CreateCustomFieldRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entity_kind: EntityKind
    field_key: str = Field(min_length=2, max_length=48)
    label: str = Field(min_length=2, max_length=80)
    field_type: CustomFieldType = "text"
    options: list[str] = Field(default_factory=list)
    is_required: bool = False
    display_order: int = Field(default=0, ge=0, le=1000)


class UpsertCustomFieldValueRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    definition_id: UUID
    entity_id: str = Field(min_length=1, max_length=120)
    value: Any


class CustomFieldValueResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    definition_id: UUID
    field_key: str
    label: str
    field_type: CustomFieldType
    entity_kind: EntityKind
    entity_id: str
    value: Any
    updated_at: datetime


class KanbanLaneInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str = Field(min_length=2, max_length=48)
    title: str = Field(min_length=2, max_length=60)
    color_hex: str = Field(default="#111111", pattern=r"^#[0-9A-Fa-f]{6}$")


class CreateBoardRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    slug: str = Field(min_length=2, max_length=63)
    title: str = Field(min_length=2, max_length=120)
    entity_kind: BoardEntityKind = "general"
    lanes: list[KanbanLaneInput] | None = None


class WorkspaceBoardResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    slug: str
    title: str
    entity_kind: BoardEntityKind
    lanes: list[dict[str, str]]
    created_at: datetime
    updated_at: datetime


class CreateBoardCardRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    lane_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=1000)
    priority: CardPriority = "medium"
    amount_cents: int | None = Field(default=None, ge=0, le=999_999_999)
    due_date: date | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class MoveBoardCardRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    target_lane_id: str = Field(min_length=1, max_length=64)
    target_position: int = Field(default=0, ge=0, le=10000)


class WorkspaceBoardCardResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    board_id: UUID
    lane_id: str
    title: str
    description: str
    priority: CardPriority
    amount_cents: int | None = None
    due_date: date | None = None
    position: int
    custom_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class BrandThemeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    brand_display_name: str | None = None
    logo_url: str | None = None
    accent_hex: str
    accent_contrast_on_white: float
    surface_preset: SurfacePreset
    dashboard_widgets: list[str]
    updated_at: datetime | None = None


class UpdateBrandThemeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    brand_display_name: str | None = Field(default=None, max_length=120)
    logo_url: str | None = Field(default=None, max_length=500)
    accent_hex: str = Field(default="#111111", pattern=r"^#[0-9A-Fa-f]{6}$")
    surface_preset: SurfacePreset = "monolith_light"
    dashboard_widgets: list[str] = Field(default_factory=list)


def _def_resp(d: CustomFieldDefinitionView) -> CustomFieldDefinitionResponse:
    return CustomFieldDefinitionResponse(
        id=d.id,
        entity_kind=d.entity_kind,
        field_key=d.field_key,
        label=d.label,
        field_type=d.field_type,
        options=d.options,
        is_required=d.is_required,
        display_order=d.display_order,
        created_at=d.created_at,
    )


def _val_resp(v: CustomFieldValueView) -> CustomFieldValueResponse:
    return CustomFieldValueResponse(
        id=v.id,
        definition_id=v.definition_id,
        field_key=v.field_key,
        label=v.label,
        field_type=v.field_type,
        entity_kind=v.entity_kind,
        entity_id=v.entity_id,
        value=v.value,
        updated_at=v.updated_at,
    )


def _board_resp(b: WorkspaceBoardView) -> WorkspaceBoardResponse:
    return WorkspaceBoardResponse(
        id=b.id,
        slug=b.slug,
        title=b.title,
        entity_kind=b.entity_kind,
        lanes=b.lanes,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


def _card_resp(c: WorkspaceBoardCardView) -> WorkspaceBoardCardResponse:
    return WorkspaceBoardCardResponse(
        id=c.id,
        board_id=c.board_id,
        lane_id=c.lane_id,
        title=c.title,
        description=c.description,
        priority=c.priority,
        amount_cents=c.amount_cents,
        due_date=c.due_date,
        position=c.position,
        custom_fields=c.custom_fields,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _theme_resp(t: BrandThemeView) -> BrandThemeResponse:
    return BrandThemeResponse(
        brand_display_name=t.brand_display_name,
        logo_url=t.logo_url,
        accent_hex=t.accent_hex,
        accent_contrast_on_white=t.accent_contrast_on_white,
        surface_preset=t.surface_preset,
        dashboard_widgets=t.dashboard_widgets,
        updated_at=t.updated_at,
    )


@router.get("/custom-fields", response_model=list[CustomFieldDefinitionResponse])
async def get_custom_fields_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    entity_kind: Annotated[EntityKind | None, Query()] = None,
) -> list[CustomFieldDefinitionResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_custom_field_definitions(
            session.conn, tenant_id=business_id, entity_kind=entity_kind
        )
    return [_def_resp(r) for r in rows]


@router.post(
    "/custom-fields",
    response_model=CustomFieldDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_custom_field_route(
    business_id: UUID,
    body: CreateCustomFieldRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> CustomFieldDefinitionResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            item = await create_custom_field_definition(
                session.conn,
                tenant_id=business_id,
                entity_kind=body.entity_kind,
                field_key=body.field_key,
                label=body.label,
                field_type=body.field_type,
                options=body.options,
                is_required=body.is_required,
                display_order=body.display_order,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _def_resp(item)


@router.delete("/custom-fields/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_field_route(
    business_id: UUID,
    definition_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        await delete_custom_field_definition(
            session.conn, tenant_id=business_id, definition_id=definition_id
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/custom-fields/values", response_model=list[CustomFieldValueResponse])
async def get_custom_field_values_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    entity_kind: Annotated[EntityKind, Query()],
    entity_id: Annotated[str, Query(min_length=1, max_length=120)],
) -> list[CustomFieldValueResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_custom_field_values(
            session.conn, tenant_id=business_id, entity_kind=entity_kind, entity_id=entity_id
        )
    return [_val_resp(r) for r in rows]


@router.put("/custom-fields/values", response_model=CustomFieldValueResponse)
async def put_custom_field_value_route(
    business_id: UUID,
    body: UpsertCustomFieldValueRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> CustomFieldValueResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            item = await upsert_custom_field_value(
                session.conn,
                tenant_id=business_id,
                definition_id=body.definition_id,
                entity_id=body.entity_id,
                raw_value=body.value,
                user_id=principal.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _val_resp(item)


@router.get("/boards", response_model=list[WorkspaceBoardResponse])
async def get_boards_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[WorkspaceBoardResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_workspace_boards(session.conn, tenant_id=business_id)
    return [_board_resp(r) for r in rows]


@router.post(
    "/boards",
    response_model=WorkspaceBoardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_board_route(
    business_id: UUID,
    body: CreateBoardRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> WorkspaceBoardResponse:
    lanes_payload = [lane.model_dump() for lane in body.lanes] if body.lanes else None
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            item = await create_workspace_board(
                session.conn,
                tenant_id=business_id,
                slug=body.slug,
                title=body.title,
                entity_kind=body.entity_kind,
                lanes=lanes_payload,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _board_resp(item)


@router.delete("/boards/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board_route(
    business_id: UUID,
    board_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        await delete_workspace_board(session.conn, tenant_id=business_id, board_id=board_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/boards/{board_id}/cards", response_model=list[WorkspaceBoardCardResponse])
async def get_board_cards_route(
    business_id: UUID,
    board_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[WorkspaceBoardCardResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_board_cards(session.conn, tenant_id=business_id, board_id=board_id)
    return [_card_resp(r) for r in rows]


@router.post(
    "/boards/{board_id}/cards",
    response_model=WorkspaceBoardCardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_board_card_route(
    business_id: UUID,
    board_id: UUID,
    body: CreateBoardCardRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> WorkspaceBoardCardResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            item = await create_board_card(
                session.conn,
                tenant_id=business_id,
                board_id=board_id,
                lane_id=body.lane_id,
                title=body.title,
                description=body.description,
                priority=body.priority,
                amount_cents=body.amount_cents,
                due_date=body.due_date,
                custom_fields=body.custom_fields,
                user_id=principal.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _card_resp(item)


@router.post(
    "/boards/{board_id}/cards/{card_id}/move",
    response_model=WorkspaceBoardCardResponse,
)
async def post_move_board_card_route(
    business_id: UUID,
    board_id: UUID,
    card_id: UUID,
    body: MoveBoardCardRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> WorkspaceBoardCardResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            item = await move_board_card(
                session.conn,
                tenant_id=business_id,
                board_id=board_id,
                card_id=card_id,
                target_lane_id=body.target_lane_id,
                target_position=body.target_position,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _card_resp(item)


@router.delete("/boards/{board_id}/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board_card_route(
    business_id: UUID,
    board_id: UUID,
    card_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        await delete_board_card(
            session.conn, tenant_id=business_id, board_id=board_id, card_id=card_id
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/brand-theme", response_model=BrandThemeResponse)
async def get_brand_theme_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> BrandThemeResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        theme = await get_brand_theme(session.conn, tenant_id=business_id)
    return _theme_resp(theme)


@router.put("/brand-theme", response_model=BrandThemeResponse)
async def put_brand_theme_route(
    business_id: UUID,
    body: UpdateBrandThemeRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> BrandThemeResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            theme = await upsert_brand_theme(
                session.conn,
                tenant_id=business_id,
                brand_display_name=body.brand_display_name,
                logo_url=body.logo_url,
                accent_hex=body.accent_hex,
                surface_preset=body.surface_preset,
                dashboard_widgets=body.dashboard_widgets,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _theme_resp(theme)
