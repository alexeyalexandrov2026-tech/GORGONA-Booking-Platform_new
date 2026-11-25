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

MODULE_REGISTRY_VERSION: Literal[17] = 17
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
    _module(
        "workforce",
        "Workforce",
        _OPTIONAL,
        ("users_access",),
        next(scenario.status for scenario in SCENARIOS if scenario.id == "WORK-01"),
        "Staff profiles and skills, versioned shifts with one assigned person in the shared "
        "occupancy, handovers, swaps and open shifts with a colleague's consent and a "
        "manager's approval, versioned timesheets with corrections, and a per-branch setting "
        "for seeing colleagues' shifts (ADR-0025). Technical acceptance: "
        "docs/plan/evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md (code f41f9a8). "
        "No payroll, rates, leave, automatic scheduling, notifications or geolocation.",
        "New staff profiles, skills, shifts, assignments and shift changes, changes of the "
        "branch setting, clock-ins, breaks, corrections and decisions on time entries. History "
        "and reads continue, an open time entry can still be closed, and an uncertain command "
        "can still be resolved or discarded.",
    ),
    # ADR-0038 (PRO-01): owner-authorized release enablement (v2.0 US release).
    _module(
        "projects",
        "Projects and work",
        _OPTIONAL,
        ("counterparties", "documents", "finance_documents"),
        Readiness.TECHNICALLY_VERIFIED,
        "PRO-01 (ADR-0038): legal matters, projects and recurring engagements with "
        "append-only revision history, conflict-of-interest checks before legal-case activation, "
        "time tracking, FIN-03 billing, and PostgreSQL 18 FORCE RLS ethical-wall restrictions.",
        "New matters, conflict checks and ethical-wall memberships. Reads and history continue.",
    ),
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
    _module(
        "inventory",
        "Inventory and customer warehouses",
        _OPTIONAL,
        ("finance",),
        next(scenario.status for scenario in SCENARIOS if scenario.id == "STOCK-01"),
        "Basic materials (ADR-0026). Implemented so far: the shared material list, the "
        "storage places of a branch, the accounts of materials for a book, receipts with "
        "amounts and write-offs at the moving-average cost, which post to the ledger, and "
        "transfers between storage places, which move no money, and returns against a line "
        "of a receipt or a write-off. "
        "The Materials and Stock documents screens show and post them (STOCK-01, technically "
        "verified 2026-10-20). "
        "No customer-owned goods, batches, serial numbers or purchase orders.",
        "New materials, storage places, posting rules and stock documents. Reads and history "
        "continue.",
    ),
    # ADR-0044 (SPECIAL-03): owner-authorized release enablement (v2.0 US release).
    _module(
        "assets",
        "Assets and maintenance",
        _OPTIONAL,
        ("organization",),
        Readiness.TECHNICALLY_VERIFIED,
        "SPECIAL-03 (ADR-0044): branch-scoped managed assets, insert-only inspections, "
        "work orders and critical safety/environmental incidents across field industries.",
        "New managed assets, inspections, work orders and incidents. Reads continue.",
    ),
    _module("communications", "Communications", _OPTIONAL, ("counterparties",)),
    _module("support", "Support", _OPTIONAL, ("counterparties",)),
    # ADR-0041 (ENTERPRISE-01): owner-authorized release enablement (v2.0 US release).
    _module(
        "analytics",
        "Analytics",
        _OPTIONAL,
        ("organization",),
        Readiness.TECHNICALLY_VERIFIED,
        "ENTERPRISE-01 (ADR-0041): corporate SSO identity providers, SCIM-style employee "
        "deprovisioning with immediate access revocation, and consent-based consolidated group "
        "reporting without ownership transfer.",
        "New SSO providers, directory links, lifecycle events and group reports. Reads continue.",
    ),
    _module("automation_ai", "Automation and AI", _OPTIONAL, ("users_access",)),
    # ADR-0028 (package M): owner-authorized release enablement (v2.0 US release).
    _module(
        "transport",
        "Transport and logistics",
        _OPTIONAL,
        ("counterparties",),
        Readiness.TECHNICALLY_VERIFIED,
        "Package M (ADR-0028..0033): shipment orders with loads, trips with stops in their own "
        "time zones and legs; crews and fleet assignments, stop events with partial delivery, "
        "carrier dispatcher grants, clearance, screens and money (order rates, customer invoices "
        "and trip pay through FIN-03).",
        "New shipment orders and trips. Reads continue.",
    ),
    # ADR-0035 (package O): owner-authorized release enablement (v2.0 US release).
    _module(
        "construction",
        "Construction and repair",
        _OPTIONAL,
        ("counterparties", "finance_documents"),
        Readiness.TECHNICALLY_VERIFIED,
        "Package O (ADR-0035): construction projects, estimates, proposals, contracts, change "
        "orders, retainage, customer acceptance, execution, billing and screens.",
        "New construction projects, estimate versions and proposals. Reads continue.",
    ),
    # ADR-0036 (package R): owner-authorized release enablement (v2.0 US release).
    _module(
        "rental",
        "Rental and hire",
        _OPTIONAL,
        ("counterparties", "finance_documents"),
        Readiness.TECHNICALLY_VERIFIED,
        "Package R (ADR-0036): rental item classes, units, bookings, agreements, deposits, "
        "inspections, change/problem resolution, settlement and screens.",
        "New rental classes and units. Reads continue.",
    ),
    _module(
        "property",
        "Property management",
        _OPTIONAL,
        ("counterparties",),
        Readiness.TECHNICALLY_VERIFIED,
        "PROPERTY-01: parcel, building and unit catalog, listings, showings, leases, move-out "
        "inspections, maintenance work orders and contractor portal.",
        "New property objects and revisions. Reads and history continue.",
    ),
    _module(
        "restaurant",
        "Restaurants and food service",
        _OPTIONAL,
        ("booking_resources", "counterparties", "finance_documents", "inventory", "workforce"),
        Readiness.TECHNICALLY_VERIFIED,
        "REST-01 (ADR-0037): branch dining areas, tables, reservations, versioned menus, "
        "recipes/BOM, kitchen station tickets, split billing, refunds and FIN-03 settlement.",
        "New dining areas, tables and table reservations. Reads and history continue.",
    ),
    # ADR-0039 (SUPPLY-01): owner-authorized release enablement (v2.0 US release).
    _module(
        "supply",
        "Supply chain, 3PL WMS and manufacturing",
        _OPTIONAL,
        ("counterparties", "finance_documents", "inventory"),
        Readiness.TECHNICALLY_VERIFIED,
        "SUPPLY-01 (ADR-0039): multi-warehouse WMS bins, goods-owner isolation (company vs 3PL "
        "bailor), lot/batch and serial tracking, BOM manufacturing, QC and trade/3PL orders.",
        "New goods owners, warehouse bins, lots, serial units and WMS movements. Reads continue.",
    ),
    # ADR-0042 (SPECIAL-01): owner-authorized release enablement (v2.0 US release).
    _module(
        "hospitality_events",
        "Education, fitness, hospitality and events",
        _OPTIONAL,
        ("counterparties",),
        Readiness.TECHNICALLY_VERIFIED,
        "SPECIAL-01 (ADR-0042): education cohorts and fitness memberships with session tracking, "
        "hospitality rooms and stays with housekeeping states, and events with ticket capacity "
        "conservation.",
        "New programs, enrollments, rooms, stays, events and tickets. Reads continue.",
    ),
    # ADR-0043 (SPECIAL-02): regulated US clinical module; requires HIPAA BAA before enabling.
    _module(
        "clinical_care",
        "Healthcare, veterinary and social care",
        _OPTIONAL,
        ("counterparties",),
        Readiness.IMPLEMENTED,
        "SPECIAL-02 (ADR-0043): consent-gated patient, veterinary and social care records "
        "with immediate write blocks and sensitive-note redaction upon consent revocation. "
        "Requires US HIPAA BAA & clinical security audit before production enablement.",
        "New care subjects, consents, plans and encounters. Reads continue with consent gating.",
    ),
    # ADR-0045 (SPECIAL-04): regulated US civic/advisory module; requires compliance review.
    _module(
        "public_civic",
        "Staffing, advisory, organizations and public administration",
        _OPTIONAL,
        ("counterparties",),
        Readiness.IMPLEMENTED,
        "SPECIAL-04 (ADR-0045): programs, dual-review cases, approved allocations (placements, "
        "mandates, memberships, grants, permits) and insert-only transparency audit events. "
        "Requires US SEC/FINRA or FedRAMP/StateRAMP review before production enablement.",
        "New civic programs, cases, allocations and audit events. Reads continue.",
    ),
    # ADR-0040 (MARKET-01): owner-authorized release enablement (v2.0 US release).
    _module(
        "storefronts",
        "Storefronts and marketplaces",
        _OPTIONAL,
        ("counterparties", "finance_documents"),
        Readiness.TECHNICALLY_VERIFIED,
        "MARKET-01 (ADR-0040): business storefronts with strict explicit published_fields "
        "projection, client-operated marketplaces with zero GORGONA transaction commission, "
        "and single-seller order/payment isolation.",
        "New storefronts, listings, marketplaces and orders. Reads continue.",
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
