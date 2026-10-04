from typing import Any

import pytest
from pydantic import ValidationError

from gorgona_booking.business.catalog import CATALOG, INDUSTRIES
from gorgona_booking.business.contracts import ProfileInput
from gorgona_booking.business.service import profile_request_hash


def test_catalog_identities_are_stable_and_cover_all_naics_sectors() -> None:
    assert [i.id for i in INDUSTRIES] == list(range(1, 40))
    assert len({i.code for i in INDUSTRIES}) == 39
    assert INDUSTRIES[0].code == "beauty"
    assert INDUSTRIES[23].code == "logistics"
    assert INDUSTRIES[38].code == "public_administration"
    assert {s for i in INDUSTRIES for s in i.naics_sectors} == {
        "11",
        "21",
        "22",
        "23",
        "31-33",
        "42",
        "44-45",
        "48-49",
        "51",
        "52",
        "53",
        "54",
        "55",
        "56",
        "61",
        "62",
        "71",
        "72",
        "81",
        "92",
    }
    assert all(i.workflow_readiness == "planned" for i in CATALOG.industries)


@pytest.mark.parametrize(
    "changes",
    [
        {"industry_ids": [True]},
        {"industry_ids": ["1"]},
        {"industry_ids": [1.0]},
        {"industry_ids": [0]},
        {"industry_ids": [40]},
        {"industry_ids": [1, 1]},
        {"industry_ids": []},
        {"expected_revision": True},
        {"expected_revision": "0"},
        {"expected_revision": -1},
        {"catalog_version": 2},
        {"schema_version": True},
        {"business_formats": ["b2b", "b2b"]},
        {"business_formats": ["unknown"]},
        {"custom_activity_name": "   "},
        {"tenant_id": "injected-owner"},
    ],
)
def test_profile_input_rejects_ambiguous_or_invalid_data(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ProfileInput.model_validate({"expected_revision": 0, "industry_ids": [1], **changes})


def test_selection_order_does_not_change_idempotency_hash() -> None:
    a = ProfileInput(expected_revision=0, industry_ids=(1, 24), business_formats=("b2b", "b2c"))
    b = ProfileInput(expected_revision=0, industry_ids=(24, 1), business_formats=("b2c", "b2b"))
    assert profile_request_hash(a) == profile_request_hash(b)
    assert profile_request_hash(a) != profile_request_hash(
        a.model_copy(update={"expected_revision": 1})
    )
