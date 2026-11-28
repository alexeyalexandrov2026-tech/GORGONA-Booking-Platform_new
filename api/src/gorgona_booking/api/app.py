"""FastAPI application factory."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from gorgona_booking.api import (
    agreements,
    ai_assistant,
    ai_autonomy,
    businesses,
    commercial,
    configurations,
    connectors,
    construction,
    counterparties,
    customer,
    delegations,
    departments,
    documents,
    enterprise_reporting,
    enterprise_sso,
    financial_documents,
    groups,
    growth,
    health,
    holds,
    inventory,
    ledger,
    legal_entities,
    market_orders,
    market_storefronts,
    media,
    members,
    notifications,
    payments,
    platform,
    projects_billing,
    projects_matters,
    projects_time,
    projects_work,
    property_catalog,
    property_leases,
    property_listings,
    property_maintenance,
    property_showings,
    provider_admission,
    public_demo,
    rental,
    reservations,
    restaurant_billing,
    restaurant_checks,
    restaurant_floor,
    restaurant_menu,
    salons,
    search,
    self_service,
    setup,
    shift_changes,
    special_assets,
    special_care,
    special_civic,
    special_venues,
    stock,
    supply_manufacturing,
    supply_trade,
    supply_wms,
    timesheets,
    transport,
    visits,
    workforce,
    workforce_desk,
)
from gorgona_booking.api.errors import install_error_handlers
from gorgona_booking.api.framing import FramingPolicyMiddleware
from gorgona_booking.api.health import ReadinessProbe
from gorgona_booking.api.request_id import RequestIdMiddleware
from gorgona_booking.api.trusted_proxy import (
    AzureFrontDoorMiddleware,
    GoogleCloudLoadBalancerMiddleware,
)
from gorgona_booking.auth.verifier import OidcJwtVerifier, RemoteJwksKeySource, TokenVerifier
from gorgona_booking.booking.service import BookingService
from gorgona_booking.config import Settings, assert_environment_allowed
from gorgona_booking.db.pool import (
    RuntimePool,
    assert_safe_runtime_role,
    create_runtime_pool,
    pool_readiness_probe,
)
from gorgona_booking.observability import AccessLogMiddleware


def create_app(
    settings: Settings | None = None,
    *,
    pool: RuntimePool | None = None,
    readiness_probe: ReadinessProbe | None = None,
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    """Build the app. An injected `pool` is borrowed; otherwise one is opened from
    `settings.database_url` for the app's lifetime and closed on shutdown."""
    settings = settings or Settings.from_env()
    assert_environment_allowed(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned: RuntimePool | None = None
        if app.state.pool is None and settings.database_url is not None:
            owned = create_runtime_pool(
                settings.database_url.get_secret_value(),
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
            )
            await owned.open(wait=True, timeout=10.0)
            try:
                # Fail fast: never serve with a credential that can bypass RLS.
                async with owned.connection() as conn:
                    await assert_safe_runtime_role(conn)
            except BaseException:
                await owned.close()
                raise
            app.state.pool = owned
            app.state.booking_service = BookingService(
                owned, hold_ttl_seconds=settings.hold_ttl_seconds
            )
            if app.state.readiness_probe is None:
                app.state.readiness_probe = pool_readiness_probe(owned)
        try:
            yield
        finally:
            if owned is not None:
                await owned.close()

    app = FastAPI(title="GORGONA Booking AI", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.pool = pool
    app.state.booking_service = (
        BookingService(pool, hold_ttl_seconds=settings.hold_ttl_seconds)
        if pool is not None
        else None
    )
    app.state.token_verifier = token_verifier or _configured_verifier(settings)
    app.state.readiness_probe = readiness_probe or (
        pool_readiness_probe(pool) if pool is not None else None
    )

    # Innermost: sees the effective (tenant) Host after the trusted-proxy rewrite.
    app.add_middleware(
        FramingPolicyMiddleware,
        allow_loopback=settings.environment in ("local", "test", "ci"),
    )
    if settings.trusted_proxy == "azure_front_door" and settings.front_door_id is not None:
        # Added before RequestIdMiddleware, so it runs inside it: refusals carry a request ID.
        app.add_middleware(AzureFrontDoorMiddleware, front_door_id=settings.front_door_id)
    elif settings.trusted_proxy == "google_cloud_lb" and settings.edge_token is not None:
        app.add_middleware(
            GoogleCloudLoadBalancerMiddleware,
            edge_secret=settings.edge_token.get_secret_value(),
        )
    # Inside RequestIdMiddleware (so the request ID is known), outside everything else.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(health.router)
    # The M1 endpoint omits customer policy/capability validation and is development only.
    # Hosted bookings use customer.router; the underlying booking service remains reusable.
    if settings.environment in ("local", "test", "ci"):
        app.include_router(holds.router)
    app.include_router(salons.router)
    app.include_router(businesses.router)
    app.include_router(legal_entities.router)
    app.include_router(departments.router)
    app.include_router(delegations.router)
    app.include_router(groups.router)
    app.include_router(configurations.router)
    app.include_router(counterparties.router)
    app.include_router(documents.router)
    app.include_router(agreements.router)
    app.include_router(ledger.router)
    app.include_router(financial_documents.router)
    app.include_router(provider_admission.router)
    app.include_router(reservations.router)
    app.include_router(workforce.router)
    app.include_router(shift_changes.router)
    app.include_router(timesheets.router)
    app.include_router(workforce_desk.router)
    app.include_router(inventory.router)
    app.include_router(stock.router)
    app.include_router(visits.router)
    app.include_router(transport.router)
    app.include_router(construction.router)
    app.include_router(rental.router)
    app.include_router(property_catalog.router)
    app.include_router(property_leases.router)
    app.include_router(property_listings.router)
    app.include_router(property_showings.router)
    app.include_router(property_maintenance.router)
    app.include_router(restaurant_floor.router)
    app.include_router(restaurant_menu.router)
    app.include_router(restaurant_checks.router)
    app.include_router(restaurant_billing.router)
    app.include_router(projects_matters.router)
    app.include_router(projects_work.router)
    app.include_router(projects_time.router)
    app.include_router(projects_billing.router)
    app.include_router(supply_wms.router)
    app.include_router(supply_manufacturing.router)
    app.include_router(supply_trade.router)
    app.include_router(market_storefronts.router)
    app.include_router(market_orders.router)
    app.include_router(enterprise_sso.router)
    app.include_router(enterprise_reporting.router)
    app.include_router(special_venues.router)
    app.include_router(special_care.router)
    app.include_router(special_assets.router)
    app.include_router(special_civic.router)
    app.include_router(members.router)
    app.include_router(search.router)
    app.include_router(self_service.router)
    app.include_router(notifications.router)
    app.include_router(growth.router)
    app.include_router(ai_assistant.router)
    app.include_router(ai_autonomy.router)
    app.include_router(connectors.router)
    app.include_router(media.router)
    app.include_router(payments.router)
    app.include_router(commercial.router)
    app.include_router(public_demo.router)
    app.include_router(setup.router)
    app.include_router(platform.router)
    app.include_router(customer.router)

    if settings.auth_issuer and settings.auth_client_id and settings.auth_scope:
        authority = settings.auth_issuer
        client_id = settings.auth_client_id
        scope = settings.auth_scope
        google_api_key = os.environ.get("GBA_GOOGLE_IDENTITY_API_KEY", "").strip()
        google_oauth_client_id = os.environ.get("GBA_GOOGLE_OAUTH_CLIENT_ID", "").strip()

        @app.get("/auth-config.json", include_in_schema=False)
        async def auth_config() -> JSONResponse:
            payload: dict[str, str] = {
                "authority": authority,
                "client_id": client_id,
                "scope": scope,
            }
            if google_api_key:
                payload["provider"] = "google_identity"
                payload["api_key"] = google_api_key
                if google_oauth_client_id:
                    payload["google_oauth_client_id"] = google_oauth_client_id
            return JSONResponse(
                content=payload,
                headers={"Cache-Control": "no-store"},
            )

    if settings.customer_web_dir is not None:
        # API routes are registered first. The export and APIs share the trusted Host.
        app.mount(
            "/", StaticFiles(directory=settings.customer_web_dir, html=True), name="customer-web"
        )
    return app


def _configured_verifier(settings: Settings) -> TokenVerifier | None:
    """The external IdP from GBA_AUTH_* settings, or None (protected routes answer 503)."""
    if not settings.auth_configured:
        return None
    issuer, audience, jwks_url = (
        settings.auth_issuer,
        settings.auth_audience,
        settings.auth_jwks_url,
    )
    if issuer is None or audience is None or jwks_url is None:  # enforced by Settings
        return None
    return OidcJwtVerifier(
        issuer=issuer,
        audience=audience,
        key_source=RemoteJwksKeySource(jwks_url),
        algorithms=settings.auth_algorithms,
        leeway_seconds=settings.auth_leeway_seconds,
    )
