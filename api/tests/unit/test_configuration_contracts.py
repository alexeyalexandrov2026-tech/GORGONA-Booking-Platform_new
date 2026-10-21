"""Configuration inputs, module registry and readiness records (ADR-0019)."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from gorgona_booking.business.catalog import CATALOG
from gorgona_booking.business.configuration_contracts import (
    ConfigurationCommand,
    ConfigurationDraftInput,
)
from gorgona_booking.business.modules import (
    BASELINE_MODULE_IDS,
    BOOKING_MODULE,
    CORE_MODULE_IDS,
    MODULES,
    MODULES_BY_ID,
    OPTIONAL_MODULE_IDS,
    ModuleKind,
    effective_modules,
    selection_problems,
)
from gorgona_booking.business.readiness_registry import (
    PROFILES,
    READINESS_REGISTRY,
    SCENARIOS,
    Readiness,
    at_least,
)

_REPOSITORY = Path(__file__).resolve().parents[3]
_MASTER_PLAN = _REPOSITORY / "docs" / "plan" / "GORGONA_MASTER_PLAN.md"


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "1"},
        {"schema_version": True},
        {"expected_version": -1},
        {"expected_version": True},
        {"expected_version": "0"},
        {"profile_revision": 0},
        {"profile_revision": 1.0},
        {"module_ids": [BOOKING_MODULE, BOOKING_MODULE]},
        {"module_ids": ["organization"]},
        {"module_ids": ["unknown_module"]},
        {"tenant_id": "injected-owner"},
        {"state": "published"},
    ],
)
def test_invalid_drafts_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ConfigurationDraftInput.model_validate(
            {"expected_version": 0, "profile_revision": 1, "module_ids": [], **changes}
        )


def test_commands_need_a_real_revision() -> None:
    for body in ({"expected_revision": 0}, {"expected_revision": "1"}, {"state": "published"}):
        with pytest.raises(ValidationError):
            ConfigurationCommand.model_validate(body)
    draft = ConfigurationDraftInput(
        expected_version=0, profile_revision=1, module_ids=("finance", BOOKING_MODULE)
    )
    # A draft accepts registered modules; validation enforces readiness before publication.
    assert draft.module_ids == ("finance", BOOKING_MODULE)


def test_module_registry_is_consistent() -> None:
    ids = [module.id for module in MODULES]
    assert len(ids) == len(set(ids)) == 19
    assert CORE_MODULE_IDS == ("organization", "users_access")
    for module in MODULES:
        assert set(module.depends_on) <= MODULES_BY_ID.keys(), module.id
        assert module.id not in module.depends_on
        assert module.enableable == (
            module.kind is ModuleKind.OPTIONAL
            and at_least(module.readiness, Readiness.TECHNICALLY_VERIFIED)
        )
    for core in CORE_MODULE_IDS:
        assert at_least(MODULES_BY_ID[core].readiness, Readiness.TECHNICALLY_VERIFIED)
    # No dependency cycles: a depth-first walk never revisits its own path.

    def walk(module_id: str, path: tuple[str, ...]) -> None:
        assert module_id not in path, path
        for dependency in MODULES_BY_ID[module_id].depends_on:
            walk(dependency, (*path, module_id))

    for module_id in ids:
        walk(module_id, ())
    assert [m.id for m in MODULES if m.enableable] == [
        "counterparties",
        BOOKING_MODULE,
        "workforce",
        "documents",
        "finance",
        "finance_documents",
        "inventory",
    ]
    assert BASELINE_MODULE_IDS == (BOOKING_MODULE,)


def test_selection_rules() -> None:
    assert selection_problems([BOOKING_MODULE]) == []
    assert selection_problems(["finance"]) == []
    assert selection_problems([]) == []
    problems = selection_problems(["sales"])
    assert ("MODULE_NOT_READY", "sales") in {(p[0], p[1]) for p in problems}
    assert {p[0] for p in problems if p[1] == "sales"} == {"MODULE_NOT_READY", "DEPENDENCY_MISSING"}
    assert effective_modules([BOOKING_MODULE]) == ("organization", "users_access", BOOKING_MODULE)
    assert OPTIONAL_MODULE_IDS.isdisjoint(CORE_MODULE_IDS)


def test_readiness_records_cover_every_scenario_and_profile() -> None:
    plan = _MASTER_PLAN.read_text(encoding="utf-8")
    section = plan.split("### 14.1.1.", 1)[1].split("### 14.2.", 1)[0]
    plan_ids = re.findall(r"^\| ([A-Z]+-\d{2}) \|", section, flags=re.MULTILINE)
    assert len(plan_ids) == 28
    assert [scenario.id for scenario in SCENARIOS] == plan_ids
    assert [profile.industry_id for profile in PROFILES] == list(range(1, 40))
    assert READINESS_REGISTRY.statuses == tuple(Readiness)


def test_verified_records_cite_existing_evidence_and_owners_stay_unassigned() -> None:
    for scenario in SCENARIOS:
        assert scenario.implementation_owner is None, scenario.id
        assert scenario.industry_acceptance_owner is None, scenario.id
        for path in scenario.evidence:
            assert (_REPOSITORY / path).is_file(), (scenario.id, path)
        if at_least(scenario.status, Readiness.TECHNICALLY_VERIFIED):
            assert scenario.code_version, scenario.id
            assert scenario.schema_version, scenario.id
            assert scenario.evidence, scenario.id
            assert scenario.verified_on, scenario.id
        # Pilot and production statuses need owner decisions that do not exist yet.
        assert not at_least(scenario.status, Readiness.PILOT_ACCEPTED), scenario.id


def test_work_01_and_core_04_are_verified_and_workforce_follows_work_01() -> None:
    by_id = {scenario.id: scenario for scenario in SCENARIOS}
    work, core = by_id["WORK-01"], by_id["CORE-04"]
    assert (work.status, work.code_version, work.schema_version) == (
        Readiness.TECHNICALLY_VERIFIED,
        "f41f9a849a34a732433bea75514da758e345b859",
        35,
    )
    assert (core.status, core.code_version, core.schema_version) == (
        Readiness.TECHNICALLY_VERIFIED,
        "bf3645d987f06f9993d6e6b4087f54168bc0fc26",
        19,
    )
    workforce = MODULES_BY_ID["workforce"]
    assert (workforce.readiness, workforce.enableable) == (work.status, True)
    assert workforce.depends_on == ("users_access",)


def test_fin_02_is_technically_verified_within_its_stated_limits() -> None:
    # K5c (owner 2026-10-20: «делай, как ты считаешь нужным… я доверяю тебе»): the acceptance
    # record and the K5r source; never a pilot or production approval.
    fin = next(scenario for scenario in SCENARIOS if scenario.id == "FIN-02")
    assert (fin.status, fin.code_version, fin.schema_version) == (
        Readiness.TECHNICALLY_VERIFIED,
        "b4e69e82152961380d21761c9a100515ea1645d1",
        62,
    )
    assert "docs/plan/evidence/2026-10-20-fin-02-acceptance/ACCEPTANCE.md" in fin.evidence
    for limit in ("test mode", "USD", "no live", "no production approval"):
        assert limit in fin.scope, limit


def test_catalog_readiness_comes_from_the_registry() -> None:
    by_id = {profile.industry_id: profile.status for profile in PROFILES}
    assert {i.id: i.workflow_readiness for i in CATALOG.industries} == by_id
    assert all(status == Readiness.PLANNED for status in by_id.values())
