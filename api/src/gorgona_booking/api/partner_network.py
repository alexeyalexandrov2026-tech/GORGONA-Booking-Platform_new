"""AMARKAL v2.29.0: Public Partner & Certified Integrator Network API (`/partners/`).

Zero DB migrations required: exposes the structured US partner & implementation
practice directory, 3-tier certification tracks, and a rate-limited + honeypot-protected
partner application intake dispatched over the existing SMTP/Resend transport.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import deque
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid7

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.self_service import enforce_sliding_window_rate_limit, extract_client_ip
from gorgona_booking.notifications.transports import resolve_notification_transports

router = APIRouter(tags=["partner-network"])
_logger = logging.getLogger(__name__)

PartnerTrack = Literal[
    "implementation_migration",
    "cpa_finance_holding",
    "industrial_mrp_iot",
    "isv_plugin_mcp",
]

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_PARTNER_RATE_LIMIT_STORE: dict[str, deque[float]] = {}


class PartnerPracticeListing(BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: str
    practice_name: str
    partner_tier: str
    track: PartnerTrack
    region_label: str
    states_covered: list[str]
    naics_specialties: list[str]
    erp_migrations: list[str]
    deliverables: list[str]
    availability: str


class CertificationTierView(BaseModel):
    model_config = ConfigDict(frozen=True)
    tier_code: str
    title: str
    target_audience: str
    curriculum: list[str]
    benefits: list[str]


class PartnerDirectoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    listings: list[PartnerPracticeListing]
    certification_tiers: list[CertificationTierView]
    agency_capabilities: list[str]


class PartnerApplicationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    company_name: str = Field(min_length=2, max_length=160)
    contact_name: str = Field(min_length=2, max_length=120)
    work_email: str = Field(min_length=5, max_length=160)
    us_state: str = Field(min_length=2, max_length=40)
    partner_track: PartnerTrack = "implementation_migration"
    naics_focus: str = Field(min_length=2, max_length=160)
    team_size: str = Field(default="5-25", max_length=40)
    website_url: str = Field(default="", max_length=240)
    experience_summary: str = Field(default="", max_length=1500)
    website: str = Field(default="", max_length=120)  # Honeypot anti-bot field


class PartnerApplicationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    received: bool
    reference_id: str
    message: str


PARTNER_DIRECTORY_LISTINGS: tuple[PartnerPracticeListing, ...] = (
    PartnerPracticeListing(
        slug="amarkal-direct-midwest-freight",
        practice_name="AMARKAL Direct Implementation Desk — Freight, 3PL & Logistics",
        partner_tier="Official AMARKAL Solutions Architecture",
        track="implementation_migration",
        region_label="Midwest & Nationwide US",
        states_covered=["IL", "OH", "MI", "IN", "WI", "Nationwide"],
        naics_specialties=["484 Freight Trucking", "488 Freight Brokerage", "493 Warehousing"],
        erp_migrations=["QuickBooks", "Odoo", "NetSuite", "Excel / TMS CSV"],
        deliverables=[
            "Turnkey 48-hour CSV & OFX data migration",
            "US Payroll (FLSA/CA/Union) + Stripe 0% fee checkout setup",
            "Predictive EAM fleet telemetry & preventive work orders",
        ],
        availability="Accepting US Mid-Market Implementations",
    ),
    PartnerPracticeListing(
        slug="amarkal-finance-holding-practice",
        practice_name="Multi-Entity Holding, US GAAP & CPA Consolidation Practice",
        partner_tier="Certified ERP & CPA Advisory Track",
        track="cpa_finance_holding",
        region_label="Northeast & Cross-Border (US / CA / EU)",
        states_covered=["NY", "NJ", "DE", "MA", "TX", "Cross-Border"],
        naics_specialties=["All 39 NAICS", "5412 CPA & Advisory", "Multi-Entity Holdings"],
        erp_migrations=["NetSuite OneWorld", "QuickBooks Online", "Zoho Books", "Xero"],
        deliverables=[
            "Double-entry FIN-03 chart of accounts & audit setup",
            "US Bank Feeds (Plaid BYOK / OFX) & Human-in-the-Loop reconciliation",
            "Holding consolidation, Due To/Due From eliminations & NCI reporting",
        ],
        availability="Founding CPA Partner Slots Open",
    ),
    PartnerPracticeListing(
        slug="amarkal-industrial-mrp-iot-pod",
        practice_name="Industrial MRP II, Construction & Equipment Fleet Integrators",
        partner_tier="Vertical Systems Integrator Track",
        track="industrial_mrp_iot",
        region_label="South, Gulf & West Coast US",
        states_covered=["TX", "CA", "FL", "GA", "AZ", "WA"],
        naics_specialties=["31-33 Manufacturing", "23 Construction", "532 Equipment Rental"],
        erp_migrations=["Odoo Manufacturing", "Monday.com", "Procore", "Legacy On-Prem ERP"],
        deliverables=[
            "Multi-level BOM explosion & atomic raw-material reservations",
            "IoT sensor webhook & Samsara/Motive ELD maintenance rules",
            "Executive BI Gantt timelines & Board Pack reporting",
        ],
        availability="Accepting Q4/Q1 Deployment Scoping",
    ),
    PartnerPracticeListing(
        slug="amarkal-isv-sdk-mcp-engineering",
        practice_name="Custom Plugin SDK (`amarkal-plugin.json`) & Remote MCP Engineering",
        partner_tier="Verified ISV & Developer Partner Track",
        track="isv_plugin_mcp",
        region_label="Remote US & Global Engineering",
        states_covered=["CA", "NY", "WA", "TX", "IL", "Global Remote"],
        naics_specialties=["488 Customs & EDI", "62 Healthcare FHIR", "44-45 Omnichannel Retail"],
        erp_migrations=["Custom API Bridges", "X12 EDI 850/810", "HL7 FHIR", "Remote MCP Agents"],
        deliverables=[
            "Custom `amarkal-plugin.json` manifest design & SSRF security audit",
            "HMAC-SHA256 webhook bridges & AES-256-GCM BYOK vault integration",
            "Autonomous MCP tool workflows with strict $0.00 HITL guardrails",
        ],
        availability="Open to Agencies & ISV Teams",
    ),
)

CERTIFICATION_TIERS: tuple[CertificationTierView, ...] = (
    CertificationTierView(
        tier_code="TIER 01 · ASSOCIATE",
        title="AMARKAL Certified Implementation Specialist",
        target_audience="Independent ERP consultants, bookkeepers, and operations agencies",
        curriculum=[
            "39 NAICS Blueprint activation & No-Code Workspace Studio",
            "1-Click CSV Migration Wizard & Sample Enterprise Sandbox workflows",
            "US Bank Feeds (OFX/QFX/CSV/Plaid BYOK) & Executive BI dashboards",
        ],
        benefits=[
            "Multi-client Agency Workspace Switcher via native Delegations",
            "Listed in public AMARKAL Certified Partner Directory",
            "Direct engineering escalation channel for client launches",
        ],
    ),
    CertificationTierView(
        tier_code="TIER 02 · FINANCE & HOLDING",
        title="Certified Multi-Entity & CPA Advisory Partner",
        target_audience="US CPA firms, fractional CFO practices, and NetSuite migration teams",
        curriculum=[
            "Double-Entry FIN-03 Ledger, 3-Way PO Match & Stripe 0% reconciliation",
            "Holding Multi-Entity Consolidation, Due To/Due From eliminations & NCI",
            "US Payroll Compliance (FLSA, CA §510, Union CBA) & Multi-Currency FX",
        ],
        benefits=[
            "Read/write scoped client delegation without sharing owner credentials",
            "1-click Board Pack CSV & consolidated US GAAP/IFRS exports",
            "Co-marketing placement on US vertical & competitor migration pages",
        ],
    ),
    CertificationTierView(
        tier_code="TIER 03 · ISV & ARCHITECT",
        title="AMARKAL Plugin SDK & MCP Systems Integrator",
        target_audience="Systems integrators, EDI/IoT consultancies, and vertical ISV builders",
        curriculum=[
            "PostgreSQL 18 FORCE RLS security model & Clean Core plugin boundaries",
            "Building & publishing verified `amarkal-plugin.json` Marketplace extensions",
            "Industrial MRP II, Predictive EAM IoT webhooks & 11-tool Native MCP",
        ],
        benefits=[
            "Verified Publisher badge in AMARKAL Plugin Marketplace (`/app-marketplace/`)",
            "Zero revenue-share toll booth on client implementation retainers",
            "Early access to upcoming SDK scopes & enterprise webhook schemas",
        ],
    ),
)

AGENCY_CAPABILITIES: tuple[str, ...] = (
    "Native Multi-Client Workspace Switcher: manage dozens of client businesses from one login.",
    "Time-Bounded Scoped Delegations: least-privilege client access without sharing passwords.",
    "PostgreSQL 18 FORCE RLS Isolation: strict cryptographic & row-level client separation.",
    "1-Click [DEMO] Sandbox & CSV Migration Wizard: cut client onboarding from months to days.",
)


def filter_partner_listings(
    *,
    track: str | None = None,
    query: str | None = None,
) -> list[PartnerPracticeListing]:
    """Deterministically filter public partner practices by track and free-text query."""
    q = (query or "").strip().lower()
    results: list[PartnerPracticeListing] = []
    for item in PARTNER_DIRECTORY_LISTINGS:
        if track and item.track != track:
            continue
        if q:
            haystack = " ".join(
                [
                    item.practice_name,
                    item.partner_tier,
                    item.region_label,
                    " ".join(item.states_covered),
                    " ".join(item.naics_specialties),
                    " ".join(item.erp_migrations),
                    " ".join(item.deliverables),
                ]
            ).lower()
            if q not in haystack:
                continue
        results.append(item)
    return results


@router.get(
    "/v1/public/partners",
    response_model=PartnerDirectoryResponse,
)
async def get_public_partner_directory(
    track: Annotated[PartnerTrack | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> PartnerDirectoryResponse:
    """Return the public AMARKAL Partner Directory and 3-tier certification tracks."""
    return PartnerDirectoryResponse(
        listings=filter_partner_listings(track=track, query=q),
        certification_tiers=list(CERTIFICATION_TIERS),
        agency_capabilities=list(AGENCY_CAPABILITIES),
    )


@router.post(
    "/v1/public/partners/apply",
    response_model=PartnerApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def apply_partner_network(
    body: PartnerApplicationRequest,
    request: Request,
) -> PartnerApplicationResponse:
    """Rate-limited, honeypot-protected application intake for agencies, CPAs, and ISVs."""
    ref_id = f"PARTNER-{str(uuid7())[-6:].upper()}"
    if body.website.strip():
        return PartnerApplicationResponse(
            received=True,
            reference_id=ref_id,
            message="Thank you. Our Partner Desk will review your application shortly.",
        )

    clean_email = body.work_email.strip().lower()
    if not _EMAIL_RE.match(clean_email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Please enter a valid business email address.",
        )

    settings = getattr(request.app.state, "settings", None)
    env_name = settings.environment if settings is not None else "local"
    if env_name in ("staging", "production"):
        client_ip = extract_client_ip(request)
        enforce_sliding_window_rate_limit(
            _PARTNER_RATE_LIMIT_STORE,
            key=client_ip,
            window_seconds=900.0,
            max_requests=5,
            detail="Too many partner applications from this network. Please retry in 15 minutes.",
        )

    notify_to = (
        os.environ.get("GBA_DEMO_NOTIFY_EMAIL", "").strip()
        or os.environ.get("GBA_SMTP_SENDER", "").strip()
        or "ops@amarkal-platform.com"
    )
    transports, _ = resolve_notification_transports()
    email_transport = transports["email"]
    subject = (
        f"[AMARKAL Partner Application] {body.company_name.strip()} "
        f"({body.us_state.strip()}) — {ref_id}"
    )
    plain_body = (
        f"New AMARKAL Partner & Integrator Network Application\n"
        f"Reference: {ref_id}\n"
        f"Received: {datetime.now(UTC).isoformat()}\n"
        f"Firm / Agency: {body.company_name.strip()}\n"
        f"Contact: {body.contact_name.strip()} <{clean_email}>\n"
        f"US State / Region: {body.us_state.strip()}\n"
        f"Partner Track: {body.partner_track}\n"
        f"NAICS Focus: {body.naics_focus.strip()}\n"
        f"Team Size: {body.team_size.strip()}\n"
        f"Website: {body.website_url.strip() or '(not provided)'}\n\n"
        f"Experience / Migration Background:\n"
        f"{body.experience_summary.strip() or '(none provided)'}\n"
    )
    try:
        await asyncio.to_thread(
            email_transport.send,
            channel="email",
            recipient=notify_to,
            subject=subject[:240],
            body=plain_body[:2000],
            idempotency_key=f"partner-app-{ref_id}",
        )
    except Exception:
        _logger.warning("Partner application %s email dispatch failed", ref_id)

    return PartnerApplicationResponse(
        received=True,
        reference_id=ref_id,
        message=(
            f"Partner application {ref_id} received. Our US Partner Enablement Desk "
            f"responds within 1 business day with certification syllabus and sandbox access."
        ),
    )
