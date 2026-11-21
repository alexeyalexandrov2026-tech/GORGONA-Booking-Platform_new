"""Unit contract checks for REST-01 Slice 2 menu, modifiers and recipe BOMs."""

from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business import restaurant_menu as menu


def test_menu_item_input_validation() -> None:
    loc = uuid7()
    item = menu.MenuItemInput(
        schema_version=1,
        expected_revision=0,
        location_id=loc,
        code="BURGER_01",
        name="  Classic Burger  ",
        category=" Mains ",
        kitchen_station="hot",
        price_minor=1450,
        currency="USD",
        description="  Brioche bun\nHouse sauce ",
    )
    assert item.name == "Classic Burger"
    assert item.category == "Mains"
    assert item.description == "Brioche bun\nHouse sauce"

    with pytest.raises(ValidationError):
        menu.MenuItemInput(
            schema_version=1,
            expected_revision=0,
            location_id=loc,
            code="bad code",
            name="Burger",
            category="Mains",
            kitchen_station="hot",
            price_minor=1450,
            currency="USD",
        )

    with pytest.raises(ValidationError):
        menu.MenuItemInput(
            schema_version=1,
            expected_revision=0,
            location_id=loc,
            code="BURGER_01",
            name="Burger",
            category="Mains",
            kitchen_station="hot",
            price_minor=-1,
            currency="USD",
        )

    with pytest.raises(ValidationError):
        menu.MenuItemInput(
            schema_version=1,
            expected_revision=0,
            location_id=loc,
            code="BURGER_01",
            name="Burger",
            category="Mains",
            kitchen_station="hot",
            price_minor=100,
            currency="us",
        )


def test_modifier_group_and_option_validation() -> None:
    loc = uuid7()
    grp = menu.ModifierGroupInput(
        schema_version=1,
        expected_revision=0,
        location_id=loc,
        code="TEMP",
        name="Doneness",
        min_select=1,
        max_select=1,
        currency="USD",
    )
    assert grp.min_select == 1

    with pytest.raises(ValidationError):
        menu.ModifierGroupInput(
            schema_version=1,
            expected_revision=0,
            location_id=loc,
            code="TEMP",
            name="Doneness",
            min_select=3,
            max_select=2,
            currency="USD",
        )

    # Stock item and quantity must be paired
    with pytest.raises(ValidationError):
        menu.ModifierOptionInput(
            schema_version=1,
            expected_revision=0,
            code="EXTRA_CHEESE",
            name="Extra Cheese",
            price_delta_minor=200,
            stock_item_id=uuid7(),
            stock_quantity=None,
        )

    with pytest.raises(ValidationError):
        menu.ModifierOptionInput(
            schema_version=1,
            expected_revision=0,
            code="EXTRA_CHEESE",
            name="Extra Cheese",
            price_delta_minor=200,
            stock_item_id=None,
            stock_quantity=50,
        )

    # Negative price delta is allowed for deductions like "No side"
    opt = menu.ModifierOptionInput(
        schema_version=1,
        expected_revision=0,
        code="NO_SIDE",
        name="No Side",
        price_delta_minor=-150,
    )
    assert opt.price_delta_minor == -150


def test_modifier_group_attach_and_recipe_uniqueness() -> None:
    dup = uuid7()
    with pytest.raises(ValidationError):
        menu.MenuItemModifierGroupsInput(schema_version=1, modifier_group_ids=[dup, dup])

    mat = uuid7()
    with pytest.raises(ValidationError):
        menu.RecipeInput(
            schema_version=1,
            expected_revision=0,
            lines=[
                menu.RecipeLineInput(stock_item_id=mat, quantity=100),
                menu.RecipeLineInput(stock_item_id=mat, quantity=50),
            ],
        )

    with pytest.raises(ValidationError):
        menu.RecipeInput(schema_version=1, expected_revision=0, lines=[])
