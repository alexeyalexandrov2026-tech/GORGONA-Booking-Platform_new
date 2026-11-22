"""Unit contract tests for ENTERPRISE-01 Slice 2 (0144): group reporting grants & snapshots."""

from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.enterprise_reporting import (
    GroupReportGrantInput,
    GroupReportSnapshotInput,
)


def test_group_reporting_contracts_validate_sets_and_period_keys() -> None:
    grant = GroupReportGrantInput(
        expected_revision=0,
        organizer_business_id=uuid7(),
        group_id=uuid7(),
        allowed_report_sets=["revenue_by_currency", "revenue_by_currency", "order_volume"],
    )
    assert grant.allowed_report_sets == ["revenue_by_currency", "order_volume"]

    with pytest.raises(ValidationError):
        GroupReportGrantInput(
            expected_revision=0,
            organizer_business_id=uuid7(),
            group_id=uuid7(),
            allowed_report_sets=[],
        )

    with pytest.raises(ValidationError):
        GroupReportSnapshotInput(
            organizer_business_id=uuid7(),
            group_id=uuid7(),
            legal_entity_id=uuid7(),
            period_key="2026/10",
            currency="USD",
            report_set="revenue_by_currency",
        )
