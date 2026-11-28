"""AMARKAL v2.28.0: Plugin Marketplace & Developer SDK API (`amarkal-plugin.json`).

Security & Clean Core invariants:
- Strictly additive under PostgreSQL 18 `ENABLE + FORCE ROW LEVEL SECURITY`.
- Zero arbitrary untrusted code execution inside AMARKAL core: every plugin runs as an
  isolated remote HTTPS API, Remote MCP, OAuth2, or HMAC-SHA256 Webhook extension with
  explicit least-privilege scopes and SSRF-hardened endpoint validation.
- Integrates seamlessly with existing `gba.custom_plugins` and AES-256-GCM Secret Vault.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["plugin-marketplace"])

PluginProtocol = Literal["https_api", "mcp_remote", "webhook_bridge", "oauth2_custom"]
InstallStatus = Literal["installed", "paused", "uninstalled"]
SubmissionStatus = Literal["draft", "validated", "submitted_for_review", "published_private"]

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")

ALLOWED_PLUGIN_SCOPES: frozenset[str] = frozenset(
    {
        "read:invoices",
        "write:invoices",
        "read:counterparties",
        "read:documents",
        "read:inventory",
        "write:inventory",
        "read:bookings",
        "read:eam_telemetry",
        "write:eam_telemetry",
        "read:payroll_summary",
        "read:bank_feeds",
        "write:webhooks",
        "mcp:tools",
    }
)

ALLOWED_WEBHOOK_EVENTS: frozenset[str] = frozenset(
    {
        "invoice.issued",
        "payment.paid",
        "quote.accepted",
        "purchase_order.approved",
        "booking.created",
        "mrp.run.completed",
        "eam.work_order.created",
        "inbox.message.received",
        "bank_feed.reconciled",
    }
)


class MarketplacePluginCard(BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: str
    version: str
    display_name: str
    publisher_name: str
    verified: bool
    source_tier: Literal["official_curated", "tenant_private_sdk"]
    category: str
    protocol: PluginProtocol
    summary: str
    naics_tags: list[str]
    default_endpoint_url: str
    requested_scopes: list[str]
    subscribed_events: list[str]
    install_status: InstallStatus | None
    installed_at: datetime | None


class MarketplaceInstallationView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    plugin_slug: str
    plugin_version: str
    display_name: str
    publisher_name: str
    category: str
    protocol: PluginProtocol
    endpoint_url: str
    granted_scopes: list[str]
    subscribed_events: list[str]
    status: InstallStatus
    installed_at: datetime
    updated_at: datetime


class DeveloperSubmissionView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    plugin_slug: str
    version: str
    display_name: str
    publisher_name: str
    category: str
    protocol: PluginProtocol
    naics_codes: list[str]
    manifest_json: dict[str, Any]
    validation_status: SubmissionStatus
    validation_warnings: list[str]
    created_at: datetime


class MarketplaceCatalogResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    catalog: list[MarketplacePluginCard]
    installations: list[MarketplaceInstallationView]
    submissions: list[DeveloperSubmissionView]
    allowed_scopes: list[str]
    allowed_events: list[str]
    sdk_manifest_template: dict[str, Any]


class InstallMarketplacePluginRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    plugin_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,62}$")
    endpoint_url: str | None = Field(default=None, max_length=500)
    granted_scopes: list[str] | None = None
    config_public: dict[str, Any] = Field(default_factory=dict)


class UpdateInstallationStatusRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: InstallStatus


class ValidateManifestRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    manifest: dict[str, Any]


class ValidateManifestResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    valid: bool
    errors: list[str]
    warnings: list[str]
    normalized_manifest: dict[str, Any] | None


class CreateDeveloperSubmissionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    manifest: dict[str, Any]
    publish_mode: Literal["published_private", "submitted_for_review"] = "published_private"


CURATED_MARKETPLACE_PLUGINS: tuple[dict[str, Any], ...] = (
    {
        "slug": "us-customs-ace-edi",
        "version": "1.2.0",
        "display_name": "US Customs ACE & CBP EDI Bridge",
        "publisher_name": "AMARKAL Logistics Extensions",
        "verified": True,
        "category": "Logistics & EDI",
        "protocol": "https_api",
        "summary": (
            "Sync commercial invoices, HTS codes, bills of lading, and customs "
            "release statuses with US CBP ACE terminals."
        ),
        "naics_tags": ["484 Trucking", "488 Freight Brokerage", "42 Wholesale"],
        "default_endpoint_url": "https://api.ace-bridge.amarkal-partners.example/v1",
        "requested_scopes": ["read:documents", "read:counterparties", "read:invoices"],
        "subscribed_events": ["invoice.issued", "purchase_order.approved"],
    },
    {
        "slug": "edi-850-810-b2b",
        "version": "1.1.0",
        "display_name": "EDI 850 / 856 / 810 Retail & Supply Bridge",
        "publisher_name": "AMARKAL Verified Partners",
        "verified": True,
        "category": "Logistics & EDI",
        "protocol": "webhook_bridge",
        "summary": (
            "Automate X12 EDI 850 Purchase Orders, 856 Advance Ship Notices, "
            "and 810 Invoices with big-box US retailers and 3PL warehouses."
        ),
        "naics_tags": ["31-33 Manufacturing", "42 Wholesale", "493 Warehousing"],
        "default_endpoint_url": "https://edi.x12-gateway.amarkal-partners.example/webhook",
        "requested_scopes": ["read:invoices", "read:inventory", "write:webhooks"],
        "subscribed_events": ["purchase_order.approved", "invoice.issued"],
    },
    {
        "slug": "samsara-motive-eld",
        "version": "2.0.1",
        "display_name": "Samsara / Motive ELD & Fleet IoT Telemetry",
        "publisher_name": "AMARKAL Industrial IoT",
        "verified": True,
        "category": "Logistics & EDI",
        "protocol": "webhook_bridge",
        "summary": (
            "Stream engine hours, odometer miles, fault codes, and reefer temps "
            "into Predictive EAM to auto-trigger preventive work orders."
        ),
        "naics_tags": ["484 Trucking", "23 Construction", "532 Equipment Rental"],
        "default_endpoint_url": "https://eld-sync.amarkal-partners.example/v1/stream",
        "requested_scopes": ["read:eam_telemetry", "write:eam_telemetry"],
        "subscribed_events": ["eam.work_order.created"],
    },
    {
        "slug": "avalara-avatax-us",
        "version": "1.4.0",
        "display_name": "US Multi-State Sales Tax Engine (Avalara BYOK)",
        "publisher_name": "AMARKAL Finance Connectors",
        "verified": True,
        "category": "Finance & Tax",
        "protocol": "https_api",
        "summary": (
            "Real-time rooftop-accurate US state, county, and city sales tax "
            "rates across 13,000+ US jurisdictions via tenant BYOK key."
        ),
        "naics_tags": ["All 39 NAICS", "44-45 Retail", "54 Professional Services"],
        "default_endpoint_url": "https://rest.avatax.com/api/v2",
        "requested_scopes": ["read:invoices", "read:counterparties"],
        "subscribed_events": ["invoice.issued", "quote.accepted"],
    },
    {
        "slug": "quickbooks-xero-cpa-sync",
        "version": "1.3.0",
        "display_name": "CPA Tax Firm QuickBooks / Xero Ledger Mirror",
        "publisher_name": "AMARKAL Finance Connectors",
        "verified": True,
        "category": "Finance & Tax",
        "protocol": "oauth2_custom",
        "summary": (
            "Push reconciled FIN-03 journals and US bank feed summaries to your "
            "external CPA firm without leaving AMARKAL's double-entry core."
        ),
        "naics_tags": ["All 39 NAICS", "5412 Accounting"],
        "default_endpoint_url": "https://quickbooks.api.intuit.com/v3/company",
        "requested_scopes": ["read:invoices", "read:bank_feeds", "read:payroll_summary"],
        "subscribed_events": ["invoice.issued", "bank_feed.reconciled"],
    },
    {
        "slug": "hl7-fhir-clinic-bridge",
        "version": "1.0.4",
        "display_name": "HL7 FHIR Clinic & Medical Device Bridge",
        "publisher_name": "AMARKAL Healthcare Verified",
        "verified": True,
        "category": "Healthcare & Field",
        "protocol": "https_api",
        "summary": (
            "Scoped FHIR R4 metadata sync for diagnostic instruments, clinic "
            "appointments, and B2B lab billing without PHI sprawl."
        ),
        "naics_tags": ["621 Ambulatory Healthcare", "622 Clinics & Labs"],
        "default_endpoint_url": "https://fhir-bridge.amarkal-partners.example/r4",
        "requested_scopes": ["read:bookings", "read:documents"],
        "subscribed_events": ["booking.created"],
    },
    {
        "slug": "procore-field-sync",
        "version": "1.1.2",
        "display_name": "Procore Construction RFI & Submittal Sync",
        "publisher_name": "AMARKAL Field & Build",
        "verified": True,
        "category": "Healthcare & Field",
        "protocol": "oauth2_custom",
        "summary": (
            "Mirror construction submittals, change orders, and job-site safety "
            "logs alongside AMARKAL subcontractor draw schedules."
        ),
        "naics_tags": ["236 Building Construction", "238 Specialty Contractors"],
        "default_endpoint_url": "https://api.procore.com/rest/v1.1",
        "requested_scopes": ["read:documents", "read:counterparties"],
        "subscribed_events": ["quote.accepted", "purchase_order.approved"],
    },
    {
        "slug": "shopify-amazon-fba-sync",
        "version": "1.5.0",
        "display_name": "Shopify & Amazon FBA Multi-Channel Inventory",
        "publisher_name": "AMARKAL Commerce Extensions",
        "verified": True,
        "category": "Commerce & CRM",
        "protocol": "webhook_bridge",
        "summary": (
            "Keep SKU stock counts and B2C storefront orders synchronized across "
            "AMARKAL 0%-fee Shop, Shopify, and Amazon FBA fulfillment centers."
        ),
        "naics_tags": ["44-45 Retail", "454 E-Commerce", "493 Fulfillment"],
        "default_endpoint_url": "https://commerce-sync.amarkal-partners.example/v1",
        "requested_scopes": ["read:inventory", "write:inventory", "write:webhooks"],
        "subscribed_events": ["payment.paid", "mrp.run.completed"],
    },
    {
        "slug": "docusign-esign-envelope",
        "version": "1.2.1",
        "display_name": "DocuSign & eSignature Contract Envelope Bridge",
        "publisher_name": "AMARKAL Commerce Extensions",
        "verified": True,
        "category": "Commerce & CRM",
        "protocol": "oauth2_custom",
        "summary": (
            "Dispatch B2B quotes, leases, and carrier agreements for legally "
            "binding US ESIGN / UETA electronic signatures with signed PDF archival."
        ),
        "naics_tags": ["531 Real Estate", "5411 Legal", "All 39 NAICS"],
        "default_endpoint_url": "https://na4.docusign.net/restapi/v2.1",
        "requested_scopes": ["read:documents", "read:counterparties"],
        "subscribed_events": ["quote.accepted"],
    },
    {
        "slug": "twilio-whatsapp-pbx",
        "version": "1.3.0",
        "display_name": "Twilio Programmable Voice, SMS & WhatsApp",
        "publisher_name": "AMARKAL Omnichannel",
        "verified": True,
        "category": "Commerce & CRM",
        "protocol": "webhook_bridge",
        "summary": (
            "Route live US DID phone calls, voicemails, SMS, and WhatsApp "
            "Business conversations directly into AMARKAL Unified Client Inbox."
        ),
        "naics_tags": ["All 39 NAICS", "72 Hospitality", "81 Services"],
        "default_endpoint_url": "https://api.twilio.com/2010-04-01",
        "requested_scopes": ["write:webhooks", "read:counterparties"],
        "subscribed_events": ["inbox.message.received", "booking.created"],
    },
    {
        "slug": "slack-teams-approval-bot",
        "version": "1.2.0",
        "display_name": "Slack & Microsoft Teams Executive Approval Bot",
        "publisher_name": "AMARKAL AI & Automation",
        "verified": True,
        "category": "AI & MCP",
        "protocol": "webhook_bridge",
        "summary": (
            "Deliver interactive Block Kit & Adaptive Card notifications for "
            "high-value PO approvals, EAM maintenance alerts, and weekly BI briefs."
        ),
        "naics_tags": ["All 39 NAICS"],
        "default_endpoint_url": "https://hooks.slack.com/services",
        "requested_scopes": ["write:webhooks", "read:invoices"],
        "subscribed_events": [
            "purchase_order.approved",
            "eam.work_order.created",
            "quote.accepted",
        ],
    },
    {
        "slug": "mcp-external-warehouse-agent",
        "version": "1.0.0",
        "display_name": "External WMS & Robotics Remote MCP Connector",
        "publisher_name": "AMARKAL AI & Automation",
        "verified": True,
        "category": "AI & MCP",
        "protocol": "mcp_remote",
        "summary": (
            "Expose scoped read/write tools to external warehouse robotics and "
            "autonomous supply-chain agents via Model Context Protocol (MCP)."
        ),
        "naics_tags": ["31-33 Manufacturing", "493 Warehousing", "488 Logistics"],
        "default_endpoint_url": "https://mcp-wms.amarkal-partners.example/mcp",
        "requested_scopes": ["mcp:tools", "read:inventory", "read:eam_telemetry"],
        "subscribed_events": ["mrp.run.completed", "eam.work_order.created"],
    },
)

SDK_MANIFEST_TEMPLATE: dict[str, Any] = {
    "schema_version": "1.0",
    "slug": "my-customs-terminal-bridge",
    "version": "1.0.0",
    "display_name": "Regional US Customs Terminal Sync",
    "publisher_name": "Your Company Engineering",
    "category": "Logistics & EDI",
    "protocol": "https_api",
    "endpoint_url": "https://api.example-terminal.com/amarkal/v1",
    "naics_codes": ["484", "488"],
    "summary": "Synchronizes customs release manifests and commercial invoices via HTTPS.",
    "scopes": ["read:documents", "read:invoices"],
    "events": ["invoice.issued"],
}


def _clean(raw: Any, *, max_len: int = 200) -> str:
    return re.sub(r"\s+", " ", _CTRL_RE.sub(" ", str(raw or ""))).strip()[:max_len]


def _validate_public_https_url(raw_url: str) -> str | None:
    """Return an error string if URL fails strict HTTPS or SSRF private-host protection."""
    url = raw_url.strip()
    if len(url) < 12 or len(url) > 500:
        return "endpoint_url must be between 12 and 500 characters."
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return "endpoint_url must use https://."
    host = (parsed.hostname or "").strip().lower()
    if not host or "." not in host:
        return "endpoint_url must include a valid public domain name."
    if host in ("localhost", "ip6-localhost") or host.endswith(
        (".local", ".internal", ".localhost", ".lan")
    ):
        return "endpoint_url cannot target local or internal hostnames."
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return "endpoint_url cannot target private, loopback, or link-local IP addresses."
    except ValueError:
        pass
    return None


def validate_plugin_manifest(
    manifest: dict[str, Any],
) -> tuple[bool, list[str], list[str], dict[str, Any] | None]:
    """Deterministically validate an `amarkal-plugin.json` v1 developer SDK manifest."""
    errors: list[str] = []
    warnings: list[str] = []

    schema_ver = str(manifest.get("schema_version") or "").strip()
    if schema_ver != "1.0":
        errors.append("schema_version must be '1.0'.")

    slug = str(manifest.get("slug") or "").strip().lower()
    if not _SLUG_RE.match(slug):
        errors.append("slug must match ^[a-z0-9][a-z0-9_-]{2,62}$.")

    version = str(manifest.get("version") or "").strip()
    if not _SEMVER_RE.match(version):
        errors.append("version must be valid SemVer (e.g., 1.0.0).")

    display_name = _clean(manifest.get("display_name"), max_len=120)
    if len(display_name) < 2:
        errors.append("display_name must be at least 2 characters.")

    publisher_name = _clean(manifest.get("publisher_name"), max_len=120)
    if len(publisher_name) < 2:
        errors.append("publisher_name must be at least 2 characters.")

    category = _clean(manifest.get("category") or "Custom Extension", max_len=64)
    protocol = str(manifest.get("protocol") or "").strip()
    if protocol not in ("https_api", "mcp_remote", "webhook_bridge", "oauth2_custom"):
        errors.append(
            "protocol must be one of: https_api, mcp_remote, webhook_bridge, oauth2_custom."
        )

    endpoint_url = str(manifest.get("endpoint_url") or "").strip()
    url_err = _validate_public_https_url(endpoint_url)
    if url_err:
        errors.append(url_err)

    raw_scopes = manifest.get("scopes")
    if not isinstance(raw_scopes, list) or not raw_scopes:
        errors.append("scopes must be a non-empty list of least-privilege scopes.")
        clean_scopes: list[str] = []
    else:
        clean_scopes = sorted({str(s).strip() for s in raw_scopes if str(s).strip()})
        unknown_scopes = [s for s in clean_scopes if s not in ALLOWED_PLUGIN_SCOPES]
        if unknown_scopes:
            errors.append(f"Unsupported scopes requested: {', '.join(unknown_scopes)}.")

    raw_events = manifest.get("events", [])
    clean_events: list[str] = []
    if not isinstance(raw_events, list):
        errors.append("events must be a list of AMARKAL event names.")
    else:
        clean_events = sorted({str(e).strip() for e in raw_events if str(e).strip()})
        unknown_events = [e for e in clean_events if e not in ALLOWED_WEBHOOK_EVENTS]
        if unknown_events:
            errors.append(f"Unsupported webhook events: {', '.join(unknown_events)}.")

    raw_naics = manifest.get("naics_codes", [])
    naics_codes = (
        [_clean(n, max_len=16) for n in raw_naics[:10] if _clean(n, max_len=16)]
        if isinstance(raw_naics, list)
        else []
    )
    if not naics_codes:
        warnings.append("No NAICS industry codes specified; extension will appear as horizontal.")

    summary = _clean(manifest.get("summary") or "", max_len=360)
    if len(summary) < 10:
        warnings.append("Add a 10+ character summary so businesses understand the extension.")

    if len(clean_scopes) > 5:
        warnings.append("Consider narrowing scopes to <= 5 for least-privilege marketplace review.")

    if errors:
        return False, errors, warnings, None

    normalized = {
        "schema_version": "1.0",
        "slug": slug,
        "version": version,
        "display_name": display_name,
        "publisher_name": publisher_name,
        "category": category,
        "protocol": protocol,
        "endpoint_url": endpoint_url,
        "naics_codes": naics_codes,
        "summary": summary or f"Custom {protocol} extension by {publisher_name}.",
        "scopes": clean_scopes,
        "events": clean_events,
    }
    return True, [], warnings, normalized


@router.get(
    "/v1/businesses/{business_id}/app-marketplace/catalog",
    response_model=MarketplaceCatalogResponse,
)
async def get_marketplace_catalog(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> MarketplaceCatalogResponse:
    """Return curated extensions, tenant private SDK plugins, installations, and SDK template."""
    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_READ,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            """
            SELECT id, plugin_slug, plugin_version, display_name, publisher_name,
                   category, protocol, endpoint_url, granted_scopes,
                   subscribed_events, status, installed_at, updated_at
            FROM gba.marketplace_plugin_installations
            WHERE tenant_id = %s
            ORDER BY updated_at DESC
            """,
            (business_id,),
        )
        inst_rows = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            """
            SELECT id, plugin_slug, version, display_name, publisher_name,
                   category, protocol, naics_codes, manifest_json,
                   validation_status, validation_warnings, created_at
            FROM gba.marketplace_developer_submissions
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            """,
            (business_id,),
        )
        sub_rows = [dict(r) for r in await cur.fetchall()]

    inst_by_slug = {str(r["plugin_slug"]): r for r in inst_rows}
    catalog_cards: list[MarketplacePluginCard] = []
    seen_slugs: set[str] = set()

    for item in CURATED_MARKETPLACE_PLUGINS:
        slug = str(item["slug"])
        seen_slugs.add(slug)
        inst = inst_by_slug.get(slug)
        catalog_cards.append(
            MarketplacePluginCard(
                slug=slug,
                version=str(item["version"]),
                display_name=str(item["display_name"]),
                publisher_name=str(item["publisher_name"]),
                verified=bool(item["verified"]),
                source_tier="official_curated",
                category=str(item["category"]),
                protocol=item["protocol"],
                summary=str(item["summary"]),
                naics_tags=list(item["naics_tags"]),
                default_endpoint_url=str(item["default_endpoint_url"]),
                requested_scopes=list(item["requested_scopes"]),
                subscribed_events=list(item["subscribed_events"]),
                install_status=inst["status"] if inst else None,
                installed_at=inst["installed_at"] if inst else None,
            )
        )

    for sub in sub_rows:
        slug = str(sub["plugin_slug"])
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        m = dict(sub["manifest_json"] or {})
        inst = inst_by_slug.get(slug)
        catalog_cards.append(
            MarketplacePluginCard(
                slug=slug,
                version=str(sub["version"]),
                display_name=str(sub["display_name"]),
                publisher_name=str(sub["publisher_name"]),
                verified=False,
                source_tier="tenant_private_sdk",
                category=str(sub["category"]),
                protocol=sub["protocol"],
                summary=str(m.get("summary") or "Private workspace SDK extension."),
                naics_tags=list(sub["naics_codes"] or []),
                default_endpoint_url=str(m.get("endpoint_url") or ""),
                requested_scopes=list(m.get("scopes") or []),
                subscribed_events=list(m.get("events") or []),
                install_status=inst["status"] if inst else None,
                installed_at=inst["installed_at"] if inst else None,
            )
        )

    return MarketplaceCatalogResponse(
        catalog=catalog_cards,
        installations=[MarketplaceInstallationView(**r) for r in inst_rows],
        submissions=[DeveloperSubmissionView(**r) for r in sub_rows],
        allowed_scopes=sorted(ALLOWED_PLUGIN_SCOPES),
        allowed_events=sorted(ALLOWED_WEBHOOK_EVENTS),
        sdk_manifest_template=SDK_MANIFEST_TEMPLATE,
    )


@router.post(
    "/v1/businesses/{business_id}/app-marketplace/install",
    response_model=MarketplaceInstallationView,
    status_code=status.HTTP_201_CREATED,
)
async def install_marketplace_plugin(
    business_id: UUID,
    body: InstallMarketplacePluginRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> MarketplaceInstallationView:
    """1-click install a curated or private SDK extension under strict tenant isolation."""
    curated = next(
        (p for p in CURATED_MARKETPLACE_PLUGINS if p["slug"] == body.plugin_slug),
        None,
    )

    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        meta: dict[str, Any] | None = curated
        if meta is None:
            await cur.execute(
                """
                SELECT plugin_slug, version, display_name, publisher_name,
                       category, protocol, manifest_json
                FROM gba.marketplace_developer_submissions
                WHERE tenant_id = %s AND plugin_slug = %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (business_id, body.plugin_slug),
            )
            sub_row = await cur.fetchone()
            if sub_row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Plugin '{body.plugin_slug}' not found in marketplace catalog.",
                )
            m = dict(sub_row["manifest_json"] or {})
            meta = {
                "slug": str(sub_row["plugin_slug"]),
                "version": str(sub_row["version"]),
                "display_name": str(sub_row["display_name"]),
                "publisher_name": str(sub_row["publisher_name"]),
                "category": str(sub_row["category"]),
                "protocol": sub_row["protocol"],
                "default_endpoint_url": str(m.get("endpoint_url") or ""),
                "requested_scopes": list(m.get("scopes") or []),
                "subscribed_events": list(m.get("events") or []),
            }

        endpoint = (body.endpoint_url or str(meta["default_endpoint_url"])).strip()
        if endpoint:
            err = _validate_public_https_url(endpoint)
            if err:
                raise HTTPException(status_code=400, detail=err)

        scopes = (
            [s for s in body.granted_scopes if s in ALLOWED_PLUGIN_SCOPES]
            if body.granted_scopes is not None
            else list(meta["requested_scopes"])
        )
        events = list(meta["subscribed_events"])

        # Mirror into existing gba.custom_plugins so App Hub & webhook dispatcher know about it
        custom_plugin_id: UUID | None = None
        if endpoint:
            await cur.execute(
                """
                INSERT INTO gba.custom_plugins (
                    tenant_id, slug, display_name, category, protocol, endpoint_url,
                    auth_header_name, auth_scheme, scopes, subscribed_events,
                    description, status, created_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'Authorization', 'Bearer', %s, %s, %s, 'active', %s)
                ON CONFLICT (tenant_id, slug) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    endpoint_url = EXCLUDED.endpoint_url,
                    scopes = EXCLUDED.scopes,
                    subscribed_events = EXCLUDED.subscribed_events,
                    status = 'active',
                    updated_at = now()
                RETURNING id
                """,
                (
                    business_id,
                    body.plugin_slug,
                    str(meta["display_name"])[:120],
                    str(meta["category"])[:64],
                    meta["protocol"],
                    endpoint,
                    scopes,
                    events,
                    f"Installed from AMARKAL Plugin Marketplace ({meta['publisher_name']})"[:400],
                    session.principal.user_id,
                ),
            )
            cp = await cur.fetchone()
            if cp:
                custom_plugin_id = cp["id"]

        await cur.execute(
            """
            INSERT INTO gba.marketplace_plugin_installations (
                tenant_id, plugin_slug, plugin_version, display_name, publisher_name,
                category, protocol, endpoint_url, granted_scopes, subscribed_events,
                config_public, custom_plugin_id, status, installed_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'installed', %s)
            ON CONFLICT (tenant_id, plugin_slug) DO UPDATE SET
                plugin_version = EXCLUDED.plugin_version,
                endpoint_url = EXCLUDED.endpoint_url,
                granted_scopes = EXCLUDED.granted_scopes,
                subscribed_events = EXCLUDED.subscribed_events,
                config_public = EXCLUDED.config_public,
                custom_plugin_id = EXCLUDED.custom_plugin_id,
                status = 'installed',
                updated_at = now()
            RETURNING id, plugin_slug, plugin_version, display_name, publisher_name,
                      category, protocol, endpoint_url, granted_scopes,
                      subscribed_events, status, installed_at, updated_at
            """,
            (
                business_id,
                body.plugin_slug,
                str(meta["version"]),
                str(meta["display_name"]),
                str(meta["publisher_name"]),
                str(meta["category"]),
                meta["protocol"],
                endpoint,
                scopes,
                events,
                Jsonb(body.config_public),
                custom_plugin_id,
                session.principal.user_id,
            ),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to install marketplace plugin.")
    return MarketplaceInstallationView(**row)


@router.post(
    "/v1/businesses/{business_id}/app-marketplace/installations/{plugin_slug}/status",
    response_model=MarketplaceInstallationView,
)
async def update_marketplace_installation_status(
    business_id: UUID,
    plugin_slug: str,
    body: UpdateInstallationStatusRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> MarketplaceInstallationView:
    """Pause, resume, or uninstall an installed marketplace plugin cleanly."""
    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            """
            UPDATE gba.marketplace_plugin_installations
            SET status = %s, updated_at = now()
            WHERE tenant_id = %s AND plugin_slug = %s
            RETURNING id, plugin_slug, plugin_version, display_name, publisher_name,
                      category, protocol, endpoint_url, granted_scopes,
                      subscribed_events, status, installed_at, updated_at, custom_plugin_id
            """,
            (body.status, business_id, plugin_slug),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Plugin installation not found.")

        cp_id = row.pop("custom_plugin_id", None)
        if cp_id is not None:
            cp_status = "active" if body.status == "installed" else "paused"
            await cur.execute(
                """
                UPDATE gba.custom_plugins
                SET status = %s, updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (cp_status, business_id, cp_id),
            )

    return MarketplaceInstallationView(**row)


@router.post(
    "/v1/businesses/{business_id}/app-marketplace/sdk/validate",
    response_model=ValidateManifestResponse,
)
async def validate_developer_manifest(
    business_id: UUID,
    body: ValidateManifestRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> ValidateManifestResponse:
    """Dry-run validation of an `amarkal-plugin.json` Developer SDK manifest."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ):
        ok, errors, warnings, normalized = validate_plugin_manifest(body.manifest)

    return ValidateManifestResponse(
        valid=ok,
        errors=errors,
        warnings=warnings,
        normalized_manifest=normalized,
    )


@router.post(
    "/v1/businesses/{business_id}/app-marketplace/sdk/submissions",
    response_model=DeveloperSubmissionView,
    status_code=status.HTTP_201_CREATED,
)
async def create_developer_submission(
    business_id: UUID,
    body: CreateDeveloperSubmissionRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> DeveloperSubmissionView:
    """Validate and register a custom `amarkal-plugin.json` extension for workspace or review."""
    ok, errors, warnings, normalized = validate_plugin_manifest(body.manifest)
    if not ok or normalized is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manifest validation failed: " + "; ".join(errors),
        )

    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            """
            INSERT INTO gba.marketplace_developer_submissions (
                tenant_id, plugin_slug, version, display_name, publisher_name,
                category, protocol, naics_codes, manifest_json,
                validation_status, validation_warnings, created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, plugin_slug, version) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                publisher_name = EXCLUDED.publisher_name,
                category = EXCLUDED.category,
                protocol = EXCLUDED.protocol,
                naics_codes = EXCLUDED.naics_codes,
                manifest_json = EXCLUDED.manifest_json,
                validation_status = EXCLUDED.validation_status,
                validation_warnings = EXCLUDED.validation_warnings,
                updated_at = now()
            RETURNING id, plugin_slug, version, display_name, publisher_name,
                      category, protocol, naics_codes, manifest_json,
                      validation_status, validation_warnings, created_at
            """,
            (
                business_id,
                normalized["slug"],
                normalized["version"],
                normalized["display_name"],
                normalized["publisher_name"],
                normalized["category"],
                normalized["protocol"],
                normalized["naics_codes"],
                Jsonb(normalized),
                body.publish_mode,
                warnings,
                session.principal.user_id,
            ),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to save developer submission.")
    return DeveloperSubmissionView(**row)
