"""Recommended module presets for all 39 industries in the GORGONA catalog.

Presets guide self-service onboarding without ever auto-enabling unverified modules:
`resolve_onboarding_modules()` partitions recommended modules into:
  * `enableable_module_ids`: optional modules with `enableable=True` plus every
    transitive optional dependency needed for a valid published configuration.
  * `pending_module_ids`: recommended optional modules that are still `planned` or
    `implemented` (shown transparently to the business owner, never auto-enabled).
"""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from gorgona_booking.business.catalog import INDUSTRIES, INDUSTRY_IDS
from gorgona_booking.business.modules import (
    BOOKING_MODULE,
    CORE_MODULE_IDS,
    MODULES_BY_ID,
)

# Every industry 1..39 maps to the optional modules that cover its real workflows.
INDUSTRY_RECOMMENDED_MODULES: dict[int, tuple[str, ...]] = {
    1: (
        BOOKING_MODULE,
        "counterparties",
        "documents",
        "finance",
        "finance_documents",
        "inventory",
        "workforce",
    ),
    2: ("restaurant", "inventory", "workforce", "counterparties", "finance", "finance_documents"),
    3: ("storefronts", "inventory", "counterparties", "finance", "finance_documents", "workforce"),
    4: ("storefronts", "inventory", "counterparties", "finance", "finance_documents"),
    5: ("supply", "inventory", "counterparties", "finance", "finance_documents"),
    6: ("projects", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    7: ("projects", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    8: ("projects", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    9: ("projects", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    10: ("projects", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    11: ("projects", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    12: (
        "hospitality_events",
        BOOKING_MODULE,
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    13: (
        "hospitality_events",
        BOOKING_MODULE,
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    14: (
        "clinical_care",
        BOOKING_MODULE,
        "documents",
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    15: (
        "clinical_care",
        BOOKING_MODULE,
        "documents",
        "counterparties",
        "finance",
        "finance_documents",
        "inventory",
        "workforce",
    ),
    16: (
        "clinical_care",
        BOOKING_MODULE,
        "documents",
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    17: (
        "hospitality_events",
        BOOKING_MODULE,
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    18: (
        "hospitality_events",
        BOOKING_MODULE,
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    19: (
        "construction",
        "documents",
        "counterparties",
        "finance",
        "finance_documents",
        "inventory",
        "workforce",
    ),
    20: (
        "assets",
        BOOKING_MODULE,
        "counterparties",
        "finance",
        "finance_documents",
        "inventory",
        "workforce",
    ),
    21: (
        "assets",
        BOOKING_MODULE,
        "inventory",
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    22: ("property", "documents", "counterparties", "finance", "finance_documents"),
    23: ("rental", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    24: ("transport", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    25: (
        "supply",
        "inventory",
        "documents",
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    26: (
        "supply",
        "inventory",
        "assets",
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    27: ("assets", "inventory", "counterparties", "finance", "finance_documents", "workforce"),
    28: ("assets", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    29: ("assets", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    30: (
        "public_civic",
        "documents",
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    31: (
        "public_civic",
        "documents",
        "counterparties",
        "finance",
        "finance_documents",
        "workforce",
    ),
    32: ("assets", "workforce", "documents", "counterparties", "finance", "finance_documents"),
    33: ("assets", BOOKING_MODULE, "workforce", "counterparties", "finance", "finance_documents"),
    34: ("assets", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    35: (
        BOOKING_MODULE,
        "counterparties",
        "documents",
        "finance",
        "finance_documents",
        "workforce",
    ),
    36: ("public_civic", "documents", "counterparties", "finance", "finance_documents"),
    37: ("projects", "documents", "counterparties", "finance", "finance_documents", "workforce"),
    38: ("analytics", "documents", "counterparties", "finance", "finance_documents"),
    39: ("public_civic", "documents", "counterparties", "finance", "finance_documents"),
}


def _expand_dependencies(module_ids: Iterable[str]) -> tuple[str, ...]:
    core = set(CORE_MODULE_IDS)
    resolved: set[str] = set()
    stack = list(module_ids)
    while stack:
        mid = stack.pop()
        if mid in core or mid in resolved:
            continue
        mod = MODULES_BY_ID[mid]
        if not mod.enableable:
            continue
        resolved.add(mid)
        for dep in mod.depends_on:
            if dep not in core and dep not in resolved:
                stack.append(dep)
    return tuple(sorted(resolved))


class ResolvedOnboardingModules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    enableable_module_ids: tuple[str, ...]
    pending_module_ids: tuple[str, ...]


def resolve_onboarding_modules(industry_ids: Iterable[int]) -> ResolvedOnboardingModules:
    raw: set[str] = set()
    for industry_id in industry_ids:
        if industry_id not in INDUSTRY_IDS:
            raise ValueError(f"Unknown industry_id: {industry_id}")
        raw.update(INDUSTRY_RECOMMENDED_MODULES[industry_id])
    enableable = _expand_dependencies(m for m in raw if MODULES_BY_ID[m].enableable)
    pending = tuple(sorted(m for m in raw if not MODULES_BY_ID[m].enableable))
    return ResolvedOnboardingModules(
        enableable_module_ids=enableable,
        pending_module_ids=pending,
    )


class IndustryPresetView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: int
    code: str
    name: str
    examples: str
    naics_sectors: tuple[str, ...]
    workflow_readiness: str
    enableable_module_ids: tuple[str, ...]
    pending_module_ids: tuple[str, ...]


def all_industry_presets() -> tuple[IndustryPresetView, ...]:
    views: list[IndustryPresetView] = []
    for ind in INDUSTRIES:
        resolved = resolve_onboarding_modules((ind.id,))
        views.append(
            IndustryPresetView(
                id=ind.id,
                code=ind.code,
                name=ind.name,
                examples=ind.examples,
                naics_sectors=ind.naics_sectors,
                workflow_readiness=ind.workflow_readiness.value,
                enableable_module_ids=resolved.enableable_module_ids,
                pending_module_ids=resolved.pending_module_ids,
            )
        )
    return tuple(views)
