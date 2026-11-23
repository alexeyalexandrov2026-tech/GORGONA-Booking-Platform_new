"""Unit contract tests for MARKET-01 Slice 1 (0141): storefronts, explicit published_fields
projection, and zero-commission marketplaces.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import DELEGABLE_PERMISSIONS, PERMISSIONS_VERSION, Permission
from gorgona_booking.business import modules
from gorgona_booking.business.market_storefronts import (
    ListingInput,
    ListingView,
    MarketplaceInput,
    StorefrontInput,
    StorefrontView,
    project_public_listing,
)
from gorgona_booking.business.readiness_registry import Readiness


def test_storefronts_module_and_market_permissions_registered_conservatively() -> None:
    assert modules.MODULE_REGISTRY_VERSION == 14
    mod = modules.MODULES_BY_ID["storefronts"]
    assert mod.readiness == Readiness.IMPLEMENTED
    assert mod.enableable is False
    assert set(mod.depends_on) == {"counterparties", "finance_documents"}
    assert PERMISSIONS_VERSION == 23
    for perm in (Permission.MARKET_READ, Permission.MARKET_MANAGE):
        assert perm not in DELEGABLE_PERMISSIONS


def test_public_projection_emits_only_intersection_of_selected_fields() -> None:
    now = datetime.now(UTC)
    sf = StorefrontView(
        storefront_id=uuid7(),
        location_id=uuid7(),
        legal_entity_id=uuid7(),
        slug="acme-shop",
        display_name="Acme Shop",
        description="Private desc",
        location_city="Austin",
        currency="USD",
        published_fields=["title", "price", "currency", "brand"],
        is_published=True,
        revision=1,
        recorded_by=uuid7(),
        recorded_at=now,
    )
    lst = ListingView(
        listing_id=uuid7(),
        location_id=sf.location_id,
        storefront_id=sf.storefront_id,
        legal_entity_id=sf.legal_entity_id,
        sku="SKU-SECRET-01",
        title="Precision Valve",
        description="Unpublished listing description",
        category="hardware",
        brand="Acme",
        currency="USD",
        price_minor=12500,
        available_quantity=10,
        internal_cost_minor=4000,
        internal_notes="CONFIDENTIAL MARGIN 68%",
        published_fields=["title", "price", "currency", "description", "sku"],
        moderation_status="published",
        revision=1,
        recorded_by=uuid7(),
        recorded_at=now,
    )
    proj = project_public_listing(storefront=sf, listing=lst)
    # Intersection of storefront [title, price, currency, brand] and listing fields
    assert proj.published_fields == ["title", "price", "currency"]
    assert set(proj.fields.keys()) == {"title", "price", "currency"}
    assert "internal_cost_minor" not in proj.fields
    assert "internal_notes" not in proj.fields
    assert "description" not in proj.fields
    assert "sku" not in proj.fields
    assert "brand" not in proj.fields


def test_storefront_and_marketplace_contracts_reject_invalid_fields_and_slugs() -> None:
    with pytest.raises(ValidationError):
        StorefrontInput(
            expected_revision=0,
            location_id=uuid7(),
            legal_entity_id=uuid7(),
            slug="BAD SLUG!",
            display_name="Shop",
            currency="USD",
            published_fields=["title"],
        )
    with pytest.raises(ValidationError):
        ListingInput(
            expected_revision=0,
            location_id=uuid7(),
            storefront_id=uuid7(),
            sku="SKU-1",
            title="Item",
            category="cat",
            currency="USD",
            price_minor=100,
            published_fields=[],
        )
    with pytest.raises(ValidationError):
        MarketplaceInput(
            expected_revision=0,
            location_id=uuid7(),
            slug="mp-1",
            title="MP",
            operator_fee_bps=9000,
        )
