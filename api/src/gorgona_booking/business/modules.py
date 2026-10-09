"""Platform module registry (master plan §4, ADR-0019).

The server decides which modules a configuration may enable: only optional modules
that are at least technically verified and whose dependencies are enabled. Core
modules are always on. A registry change never alters a published configuration;
a business opts in by publishing a new version.
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.business.readiness_registry import SCENARIOS, Readiness, at_least
from gorgona_booking.errors import DomainError

MODULE_REGISTRY_VERSION: Literal[2] = 2
MINIMUM_READINESS = Readiness.TECHNICALLY_VERIFIED
BOOKING_MODULE = "booking_resources"


class ModuleDisabledError(DomainError):
    code = "MODULE_DISABLED"


class ModuleKind(StrEnum):
    CORE = "core"
    OPTIONAL = "optional"


class PlatformModule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z_]{1,62}$")
    name: str
    kind: ModuleKind
    depends_on: tuple[str, ...]
    readiness: Readiness
    # Whether a configuration may turn this module on; core modules are always on.
    enableable: bool
    limits: str
    stops: str


class ModuleCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    registry_version: int = MODULE_REGISTRY_VERSION
    minimum_readiness: Readiness = MINIMUM_READINESS
    modules: tuple[PlatformModule, ...]


def _module(
    module_id: str,
    name: str,
    kind: ModuleKind,
    depends_on: tuple[str, ...],
    readiness: Readiness = Readiness.PLANNED,
    limits: str = "Not implemented; it cannot be enabled.",
    stops: str = "Nothing: the module has no operations yet.",
) -> PlatformModule:
    return PlatformModule(
        id=module_id,
        name=name,
        kind=kind,
        depends_on=depends_on,
        readiness=readiness,
        enableable=kind is ModuleKind.OPTIONAL and at_least(readiness, MINIMUM_READINESS),
        limits=limits,
        stops=stops,
    )


_CORE, _OPTIONAL = ModuleKind.CORE, ModuleKind.OPTIONAL

MODULES: tuple[PlatformModule, ...] = (
    _module(
        "organization",
        "Organization and structure",
        _CORE,
        (),
        Readiness.TECHNICALLY_VERIFIED,
        "Company, legal entity drafts, locations, departments and groups. Networks and "
        "franchises are groups of independent businesses.",
        "Always on.",
    ),
    _module(
        "users_access",
        "Users and access",
        _CORE,
        ("organization",),
        Readiness.TECHNICALLY_VERIFIED,
        "Members, roles, one branch per membership, invitations, delegation of booking work "
        "and the audit log.",
        "Always on.",
    ),
    _module(
        "counterparties",
        "Customers and counterparties",
        _OPTIONAL,
        ("organization",),
        Readiness.TECHNICALLY_VERIFIED,
        "Versioned cards and contacts, manual duplicate decisions and booking links. "
        "Technical evidence: docs/plan/evidence/2026-10-05-counterparties/ACCEPTANCE.md. "
        "Contracts keep insert-only versions (draft, agreed, terminated); signing happens "
        "outside the platform and is only attested; a termination ends the latest agreed "
        "version from a possibly future date and is final. Contract evidence: "
        "docs/plan/evidence/2026-10-05-agreements/ACCEPTANCE.md. No electronic signature, "
        "consent management, import or erasure.",
        "New cards, versions, match decisions, booking links and contract versions. Reads "
        "and history continue.",
    ),
    _module("sales", "Sales", _OPTIONAL, ("counterparties", "products_services")),
    _module("products_services", "Products and services", _OPTIONAL, ("organization",)),
    _module(
        BOOKING_MODULE,
        "Booking and resources",
        _OPTIONAL,
        ("organization", "users_access"),
        Readiness.TECHNICALLY_VERIFIED,
        "Single-resource booking with its own service catalog, prices and compatible add-ons, "
        "staff hours and the customer booking site; staff reservations of one or more "
        "resources share one occupancy with bookings (ADR-0022). No multi-resource booking, "
        "capacity above one or payments.",
        "New bookings and reschedules in the workspace, on the customer site and by delegates, "
        "and new resource reservations. Cancellations, existing holds, history and reads "
        "continue.",
    ),
    _module("workforce", "Workforce", _OPTIONAL, ("users_access",)),
    _module("projects", "Projects and work", _OPTIONAL, ("counterparties",)),
    _module(
        "documents",
        "Documents",
        _OPTIONAL,
        ("organization",),
        Readiness.TECHNICALLY_VERIFIED,
        "Versioned documents with validity dates and one immutable PDF, PNG or JPEG file of at "
        "most 10 MiB per version, checked against a bounded format profile but not scanned for "
        "malware; uploads are refused in staging and production until a scanner exists. "
        "Manual links to counterparties. Technical evidence: "
        "docs/plan/evidence/2026-10-05-documents/ACCEPTANCE.md. No templates, signatures, "
        "per-document access, retention or erasure.",
        "New uploads, documents, versions and counterparty links. Reads, history and "
        "downloads continue.",
    ),
    _module(
        "finance",
        "Finance",
        _OPTIONAL,
        ("organization",),
        Readiness.TECHNICALLY_VERIFIED,
        "Ledger foundation (ADR-0023): books, neutral chart, double entry, reversals, monthly "
        "periods and currency-separated trial balances. Technical acceptance: "
        "docs/plan/evidence/2026-10-06-ledger/ACCEPTANCE.md (code 95a0de4). "
        "No invoices, payments, tax filing, payroll or currency conversion.",
        "New books, account versions, entries, reversals and period events. Reads and "
        "unresolved-command recovery continue.",
    ),
    _module(
        "finance_documents",
        "Invoices and external settlements",
        _OPTIONAL,
        ("finance", "counterparties"),
        next(scenario.status for scenario in SCENARIOS if scenario.id == "FIN-03"),
        "Internal invoices and manual accruals, obligations with settlement reserves, manually "
        "attested external payments with corrections, credit notes and refund obligations "
        "(ADR-0024). Technical acceptance: "
        "docs/plan/evidence/2026-10-09-h-acceptance/ACCEPTANCE.md (code 319f144). "
        "No provider integration, network payments, tax invoices or currency conversion.",
        "New invoices, accruals, obligations, reserves, external confirmations, corrections "
        "and credits. History, recovery and eligible non-money release continue.",
    ),
    _module("procurement", "Procurement", _OPTIONAL, ("counterparties", "finance")),
    _module("inventory", "Inventory and customer warehouses", _OPTIONAL, ("products_services",)),
    _module("assets", "Assets and maintenance", _OPTIONAL, ("organization",)),
    _module("communications", "Communications", _OPTIONAL, ("counterparties",)),
    _module("support", "Support", _OPTIONAL, ("counterparties",)),
    _module("analytics", "Analytics", _OPTIONAL, ("organization",)),
    _module("automation_ai", "Automation and AI", _OPTIONAL, ("users_access",)),
    _module(
        "storefronts", "Storefronts and marketplaces", _OPTIONAL, ("products_services", "sales")
    ),
)
MODULES_BY_ID = {module.id: module for module in MODULES}
CORE_MODULE_IDS = tuple(m.id for m in MODULES if m.kind is ModuleKind.CORE)
OPTIONAL_MODULE_IDS = frozenset(m.id for m in MODULES if m.kind is ModuleKind.OPTIONAL)
# What a business without a published configuration runs (owner decision, ADR-0019).
BASELINE_MODULE_IDS: tuple[str, ...] = (BOOKING_MODULE,)
MODULE_CATALOG = ModuleCatalog(modules=MODULES)

ProblemCode = Literal["MODULE_NOT_READY", "DEPENDENCY_MISSING", "REGISTRY_CHANGED"]


def selection_problems(module_ids: Iterable[str]) -> list[tuple[ProblemCode, str, str]]:
    """(code, module_id, message) for every rule an optional-module selection breaks."""
    selected = set(module_ids)
    enabled = selected | set(CORE_MODULE_IDS)
    problems: list[tuple[ProblemCode, str, str]] = []
    for module_id in sorted(selected):
        module = MODULES_BY_ID[module_id]
        if not module.enableable:
            problems.append(
                (
                    "MODULE_NOT_READY",
                    module_id,
                    f"{module.name} is {module.readiness.value} and cannot be enabled yet",
                )
            )
        for dependency in module.depends_on:
            if dependency not in enabled:
                problems.append(
                    (
                        "DEPENDENCY_MISSING",
                        module_id,
                        f"{module.name} needs {MODULES_BY_ID[dependency].name}",
                    )
                )
    return problems


def effective_modules(module_ids: Iterable[str]) -> tuple[str, ...]:
    return (*CORE_MODULE_IDS, *sorted(set(module_ids)))
