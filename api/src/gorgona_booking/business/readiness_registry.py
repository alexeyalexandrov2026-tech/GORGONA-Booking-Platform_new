"""Readiness records (master plan §14.3, ADR-0019), separate from the industry catalog.

Each scenario of §14.1.1 and each industry profile has its own status. A status
changes only in a commit that cites evidence; owners stay empty until the owner
assigns them. A catalog entry or a selected profile never raises a status.
"""

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

READINESS_REGISTRY_VERSION: Literal[1] = 1


class Readiness(StrEnum):
    PLANNED = "planned"
    IMPLEMENTED = "implemented"
    TECHNICALLY_VERIFIED = "technically_verified"
    PILOT_ACCEPTED = "pilot_accepted"
    PRODUCTION_APPROVED = "production_approved"


_ORDER = tuple(Readiness)


def at_least(status: Readiness, minimum: Readiness) -> bool:
    return _ORDER.index(status) >= _ORDER.index(minimum)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScenarioReadiness(_Frozen):
    id: str = Field(pattern=r"^[A-Z]+-\d{2}$")
    status: Readiness
    # What the status covers and what it does not; partial evidence is named here.
    scope: str
    implementation_owner: str | None = None
    industry_acceptance_owner: str | None = None
    code_version: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    schema_version: int | None = Field(default=None, ge=1)
    settings_version: int | None = Field(default=None, ge=1)
    evidence: tuple[str, ...] = ()
    verified_on: date | None = None


class ProfileReadiness(_Frozen):
    industry_id: int = Field(ge=1, le=39)
    status: Readiness
    limitations: str


class ReadinessRegistry(_Frozen):
    schema_version: Literal[1] = 1
    registry_version: int = READINESS_REGISTRY_VERSION
    statuses: tuple[Readiness, ...] = _ORDER
    scenarios: tuple[ScenarioReadiness, ...]
    profiles: tuple[ProfileReadiness, ...]


_AUDIT = "docs/plan/GORGONA_PLAN_AUDIT_2026-10-04.md"
_BASE = "f8db038e4d10c02bec69578cfaba349d21595f71"
_AUDITED = date(2026, 10, 4)


def _verified(
    scenario_id: str, scope: str, schema_version: int, *evidence: str
) -> ScenarioReadiness:
    return ScenarioReadiness(
        id=scenario_id,
        status=Readiness.TECHNICALLY_VERIFIED,
        scope=scope,
        code_version=_BASE,
        schema_version=schema_version,
        evidence=(*evidence, _AUDIT),
        verified_on=_AUDITED,
    )


def _planned(scenario_id: str, scope: str, *evidence: str) -> ScenarioReadiness:
    return ScenarioReadiness(
        id=scenario_id, status=Readiness.PLANNED, scope=scope, evidence=evidence
    )


_NOT_BUILT = "The workflow is not implemented."

SCENARIOS: tuple[ScenarioReadiness, ...] = (
    _verified(
        "BASE-01",
        "ISO weekdays 1..7 and several intervals per day for business and staff hours.",
        9,
        "web/tests/working-hours.spec.ts",
        "api/tests/integration/test_management_browser.py",
    ),
    _verified(
        "BASE-02",
        "Branch time zones, local days, DST gaps and folds in management booking.",
        9,
        "web/tests/business-time.spec.ts",
        "api/tests/integration/test_management_booking_invariants.py",
    ),
    _verified(
        "BASE-03",
        "Confirmed booking value per currency is not reported as paid money; bookings do not "
        "automatically post ledger entries.",
        9,
        "api/tests/unit/test_booking_metrics.py",
    ),
    _verified(
        "BASE-04",
        "One branch per membership in the management workspace; group or dispatcher scopes are "
        "not covered.",
        9,
        "api/tests/integration/test_location_access.py",
    ),
    _verified(
        "CORE-01",
        "Stable catalog of 39 industries and one business with several profiles; selecting a "
        "profile enables no industry workflow.",
        8,
        "api/tests/unit/test_business_profiles.py",
        "api/tests/integration/test_business_profiles.py",
    ),
    ScenarioReadiness(
        id="CORE-02",
        status=Readiness.TECHNICALLY_VERIFIED,
        scope="Configuration versions, module availability and readiness records (ADR-0019); "
        "custom fields and process configuration are not implemented.",
        code_version="5320c4a",
        schema_version=14,
        settings_version=1,
        evidence=(
            "api/tests/integration/test_business_profiles.py",
            "api/tests/integration/test_configurations.py",
            "docs/plan/evidence/2026-10-04-configuration/ACCEPTANCE.md",
        ),
        verified_on=_AUDITED,
    ),
    _planned(
        "CORE-03",
        "Partial: legal entities, departments, delegation and groups are technically verified "
        "(6a81dfd); dispatcher authority and offline draft revocation are not implemented.",
        "docs/plan/evidence/2026-10-04-groups/ACCEPTANCE.md",
        "docs/plan/evidence/2026-10-04-delegation/ACCEPTANCE.md",
    ),
    _planned("CORE-04", "Shared resource occupancy across modules is not implemented."),
    ScenarioReadiness(
        id="FIN-01",
        status=Readiness.TECHNICALLY_VERIFIED,
        code_version="95a0de4ac9f5aa3c96b054c5504f59115b0e4b69",
        schema_version=20,
        scope="Ledger foundation: entity-owned books, balanced double entry, immutable history, "
        "reversals, monthly closing and currency-separated trial balances. "
        "Technical evidence includes exact-SHA CI and independent review. "
        "No invoices, payments, tax filing, payroll, FX or production approval.",
        evidence=(
            "docs/plan/evidence/2026-10-06-ledger/ACCEPTANCE.md",
            "docs/plan/evidence/2026-10-06-ledger/INDEPENDENT_REVIEW_95a0de4.md",
        ),
        verified_on=date(2026, 10, 6),
    ),
    _planned("FIN-02", "No accepted payment integration."),
    ScenarioReadiness(
        id="FIN-03",
        status=Readiness.TECHNICALLY_VERIFIED,
        code_version="319f144f9a234fbfc2cfef5f0aea2708d3870d7e",
        schema_version=31,
        scope="Internal invoices and manual accruals, obligations with settlement reserves under "
        "the P + C + R <= A cap, manually attested external payments with corrections and voids, "
        "credit notes with separate refund obligations. Technical evidence includes exact-SHA CI, "
        "independent reviews and an independent audit. No provider integration, network payment, "
        "tax or statutory invoice, FX or production approval.",
        evidence=(
            "docs/plan/evidence/2026-10-09-h-acceptance/ACCEPTANCE.md",
            "docs/plan/evidence/2026-10-09-h-acceptance-audit/AUDIT.md",
        ),
        verified_on=date(2026, 10, 9),
    ),
    _planned("STOCK-01", "No owner-linked material documents or movements."),
    _planned("WORK-01", "Weekly staff hours are not shifts, swaps or versioned timesheets."),
    _planned(
        "BEAUTY-01",
        "Partial: booking, prices and compatible add-ons work; service stages, multi-resource "
        "release, packages, materials, payments and commissions are not implemented.",
    ),
    _planned("TMS-01", _NOT_BUILT),
    _planned(
        "TMS-02",
        "Partial: the cross-company grant, expiry and revocation work for bookings; dispatcher "
        "operations do not exist.",
        "docs/plan/evidence/2026-10-04-delegation/ACCEPTANCE.md",
    ),
    _planned("TMS-03", "No accepted telematics or HOS integration."),
    _planned("BUILD-01", _NOT_BUILT),
    _planned("RENT-01", _NOT_BUILT),
    _planned("PROPERTY-01", _NOT_BUILT),
    _planned("REST-01", _NOT_BUILT),
    _planned("PRO-01", _NOT_BUILT),
    _planned("SUPPLY-01", _NOT_BUILT),
    _planned("MARKET-01", _NOT_BUILT),
    _planned(
        "ENTERPRISE-01",
        "Partial: revoking a membership blocks the next request; group reports, SSO/SCIM and "
        "employee lifecycle are not implemented.",
    ),
    _planned("OPS-01", "Restore, queue replay and reconciled migration are not measured."),
    _planned("OPS-02", "The load profile has not been run."),
    _planned(
        "OPS-03",
        "Partial: management desktop/mobile, errors and accessibility were checked on synthetic "
        "data; provider failure and offline conflicts were not.",
    ),
)

_PROFILE_LIMITS = {
    1: "Booking, prices and add-ons run through the booking module; the full beauty cycle "
    "(BEAUTY-01) is not implemented.",
    14: "Clinical workflows need a separately accepted qualified module.",
    24: "Transport orders, trips, dispatcher operations and settlements are not implemented.",
}
_DEFAULT_LIMIT = "The full industry workflow is not implemented; the profile describes coverage."

PROFILES: tuple[ProfileReadiness, ...] = tuple(
    ProfileReadiness(
        industry_id=industry_id,
        status=Readiness.PLANNED,
        limitations=_PROFILE_LIMITS.get(industry_id, _DEFAULT_LIMIT),
    )
    for industry_id in range(1, 40)
)
PROFILE_READINESS = {profile.industry_id: profile.status for profile in PROFILES}

READINESS_REGISTRY = ReadinessRegistry(scenarios=SCENARIOS, profiles=PROFILES)
