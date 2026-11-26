"""AI Business Architect: turns a plain-English description or price-list photo
into a validated, ready-to-launch US business blueprint for human approval.

Uses Cloudflare Workers AI (`@cf/meta/llama-3.3-70b-instruct-fp8-fast` for text and
`@cf/meta/llama-4-scout-17b-16e-instruct` for multimodal price/menu photos) with a
deterministic grounded fallback so onboarding works 100% reliably in every environment.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import logging
import os
import re
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.business.catalog import INDUSTRIES, INDUSTRY_IDS, BusinessFormat
from gorgona_booking.business.onboarding_presets import resolve_onboarding_modules

_LOG = logging.getLogger(__name__)
_TEXT_MODEL_DEFAULT = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
_VISION_MODEL_DEFAULT = "@cf/meta/llama-4-scout-17b-16e-instruct"
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_CODE_CLEAN_RE = re.compile(r"[^A-Z0-9]+")
_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9]+")

_US_TIMEZONE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "new york",
            "nyc",
            "miami",
            "boston",
            "atlanta",
            "philadelphia",
            "orlando",
            "tampa",
            "charlotte",
            "washington",
            "detroit",
            "fl",
            "ny",
            "nj",
            "ma",
            "ga",
            "nc",
            "va",
            "oh",
            "pa",
            "est",
            "edt",
        ),
        "America/New_York",
    ),
    (
        (
            "chicago",
            "austin",
            "dallas",
            "houston",
            "san antonio",
            "nashville",
            "minneapolis",
            "kansas",
            "new orleans",
            "tx",
            "texas",
            "il",
            "tn",
            "mn",
            "cst",
            "cdt",
        ),
        "America/Chicago",
    ),
    (
        (
            "denver",
            "salt lake",
            "albuquerque",
            "boise",
            "co",
            "colorado",
            "ut",
            "mst",
            "mdt",
        ),
        "America/Denver",
    ),
    (("phoenix", "scottsdale", "tucson", "az", "arizona"), "America/Phoenix"),
    (
        (
            "los angeles",
            "san francisco",
            "san diego",
            "seattle",
            "portland",
            "las vegas",
            "silicon valley",
            "ca",
            "california",
            "wa",
            "or",
            "nv",
            "pst",
            "pdt",
        ),
        "America/Los_Angeles",
    ),
    (("honolulu", "maui", "hawaii", "hi"), "Pacific/Honolulu"),
    (("anchorage", "alaska", "ak"), "America/Anchorage"),
)

_INDUSTRY_KEYWORDS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1, ("salon", "barber", "hair", "nail", "spa", "lash", "brow", "esthetic", "beauty")),
    (2, ("restaurant", "cafe", "coffee", "bistro", "bar", "bakery", "diner", "sushi", "pizza")),
    (3, ("retail", "boutique", "store", "shop", "merchandise")),
    (4, ("ecommerce", "e-commerce", "online store", "dtc")),
    (5, ("wholesale", "distributor", "b2b supply")),
    (6, ("law", "legal", "attorney", "counsel", "litigation", "notary")),
    (7, ("accounting", "cpa", "tax", "bookkeeping", "audit")),
    (8, ("consulting", "advisory", "agency", "strategy")),
    (9, ("marketing", "creative", "design", "photo", "video", "studio")),
    (10, ("software", "it ", "msp", "cyber", "cloud", "tech")),
    (12, ("tutor", "school", "academy", "training", "music lesson", "course", "education")),
    (13, ("gym", "fitness", "pilates", "yoga", "crossfit", "personal trainer", "martial")),
    (14, ("clinic", "dental", "dentist", "medical", "therapy", "chiro", "doctor", "medspa")),
    (15, ("vet", "veterinary", "grooming", "pet", "dog", "animal")),
    (17, ("hotel", "motel", "resort", "tour", "travel", "inn", "hospitality")),
    (18, ("event", "wedding", "venue", "concert", "entertainment", "escape room")),
    (19, ("construction", "remodel", "contractor", "roofing", "general contractor", "builder")),
    (20, ("hvac", "plumb", "electric", "handyman", "lawn", "landscap", "pest", "repair")),
    (21, ("auto", "car", "detailing", "ppf", "tint", "mechanic", "tire", "collision", "ceramic")),
    (22, ("real estate", "property", "broker", "leasing", "apartment", "hoa")),
    (23, ("rental", "rent ", "charter", "fleet", "boat", "equipment hire", "trailer")),
    (24, ("trucking", "freight", "dispatch", "courier", "moving", "logistics", "delivery")),
    (25, ("warehouse", "3pl", "fulfillment", "storage")),
    (26, ("manufactur", "fabrication", "cnc", "machine shop")),
    (33, ("cleaning", "janitorial", "maid", "facilities")),
)


class BlueprintServiceItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    name: str = Field(min_length=2, max_length=160)
    duration_minutes: int = Field(ge=10, le=480)
    price_cents: int = Field(ge=0, le=5_000_000)
    currency: Literal["USD"] = "USD"


class BlueprintResourceItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    display_name: str = Field(min_length=2, max_length=120)
    kind: Literal["artist", "chair", "room", "equipment"] = "artist"


class BlueprintHoursItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    weekday: int = Field(ge=1, le=7)
    opens_minute: int = Field(ge=0, le=1410)
    closes_minute: int = Field(ge=30, le=1440)


class AiBlueprintRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    description: str = Field(min_length=8, max_length=2000)
    price_list_image_data_url: str | None = Field(default=None, max_length=5_500_000)


class AiBusinessBlueprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    engine: Literal["cloudflare", "grounded"]
    model: str
    business_name: str
    slug: str
    location_name: str
    timezone: str
    industry_ids: tuple[int, ...]
    business_formats: tuple[BusinessFormat, ...]
    enableable_module_ids: tuple[str, ...]
    pending_module_ids: tuple[str, ...]
    services: tuple[BlueprintServiceItem, ...]
    resources: tuple[BlueprintResourceItem, ...]
    business_hours: tuple[BlueprintHoursItem, ...]
    cancellation_summary: str
    recommended_connectors: tuple[str, ...]
    rationale: str


def _safe_slug(name: str) -> str:
    clean = _SLUG_CLEAN_RE.sub("-", name.lower()).strip("-")[:50]
    return clean if len(clean) >= 2 else "my-us-business"


def _safe_code(name: str, idx: int) -> str:
    raw = _CODE_CLEAN_RE.sub("_", name.upper()).strip("_")[:48]
    if not raw or not raw[0].isalpha():
        raw = f"SVC_{raw or idx}"
    if len(raw) < 2:
        raw = f"SVC_{idx}"
    return raw


def _detect_timezone(text: str) -> str:
    low = f" {text.lower()} "
    for hints, tz in _US_TIMEZONE_HINTS:
        if any(f" {h} " in low or f"{h}," in low or f"{h}." in low for h in hints):
            return tz
    return "America/New_York"


def _detect_industries(text: str) -> tuple[int, ...]:
    low = text.lower()
    found: list[int] = []
    for ind_id, words in _INDUSTRY_KEYWORDS:
        if any(w in low for w in words):
            found.append(ind_id)
    if not found:
        return (8,)
    return tuple(sorted(set(found))[:4])


def _default_connectors(industry_ids: tuple[int, ...]) -> tuple[str, ...]:
    base = ["native_mcp", "zapier_make", "quickbooks_online", "google_calendar"]
    if any(i in industry_ids for i in (1, 2, 13, 14, 15, 20, 21)):
        base.append("reserve_with_google")
    if any(i in industry_ids for i in (5, 6, 7, 8, 19, 22, 23, 24, 25)):
        base.append("stripe_ach_pos")
    return tuple(base)


def _deterministic_blueprint(description: str) -> AiBusinessBlueprint:
    first_clause = re.split(r"[.,\n;!?]", description.strip())[0].strip()
    name_guess = re.sub(
        r"^(?:i run|we run|my business is|we are|this is|launch|create)\s+(?:a|an|the)?\s*",
        "",
        first_clause,
        flags=re.IGNORECASE,
    ).strip()[:80]
    business_name = name_guess.title() if len(name_guess) >= 3 else "GORGONA US Workspace"
    tz = _detect_timezone(description)
    industry_ids = _detect_industries(description)
    preset = resolve_onboarding_modules(industry_ids)
    low = description.lower()
    formats: list[BusinessFormat] = [BusinessFormat.B2C]
    if any(w in low for w in ("b2b", "commercial", "wholesale", "corporate", "fleet", "3pl")):
        formats = [BusinessFormat.B2B]
    if any(w in low for w in ("franchise", "locations", "branches", "multi-location")):
        formats.append(BusinessFormat.FRANCHISE)

    primary = industry_ids[0]
    starter_map: dict[int, tuple[tuple[str, int, int], ...]] = {
        1: (
            ("Signature Service", 60, 8500),
            ("Express Refresh", 30, 4500),
            ("Deluxe Treatment", 90, 14500),
        ),
        2: (
            ("Dinner Table Reservation (2-4 Guests)", 90, 0),
            ("Private Tasting Table", 120, 9500),
            ("Chef Counter Experience", 90, 12500),
        ),
        6: (
            ("Initial Legal Consultation", 45, 25000),
            ("Contract Review Session", 60, 35000),
            ("Entity Formation Strategy", 90, 50000),
        ),
        13: (
            ("1-on-1 Personal Training", 60, 9500),
            ("Small Group Session", 60, 3500),
            ("Fitness Assessment", 45, 6500),
        ),
        19: (
            ("On-Site Estimate & Scope Walk", 60, 0),
            ("Design & Permit Consultation", 90, 25000),
            ("Project Milestone Inspection", 60, 15000),
        ),
        20: (
            ("Diagnostic Service Call", 60, 9900),
            ("Standard Maintenance Visit", 90, 18900),
            ("Priority Emergency Dispatch", 60, 24900),
        ),
        21: (
            ("Full Interior & Exterior Detail", 180, 28000),
            ("Ceramic Coating Package", 300, 95000),
            ("Window Tint Installation", 120, 39000),
        ),
        22: (
            ("Property Showing & Tour", 45, 0),
            ("Owner Onboarding Walkthrough", 60, 0),
            ("Move-In / Move-Out Inspection", 60, 15000),
        ),
        23: (
            ("Half-Day Equipment Rental", 240, 14500),
            ("Full-Day Fleet Reservation", 480, 26000),
            ("Safety Orientation & Pickup", 30, 0),
        ),
    }
    raw_services = starter_map.get(
        primary,
        (
            ("Discovery & Intake Session", 45, 9500),
            ("Standard Service Engagement", 60, 17500),
            ("Comprehensive Deep Session", 120, 32000),
        ),
    )
    services = tuple(
        BlueprintServiceItem(
            code=_safe_code(s_name, idx + 1),
            name=s_name,
            duration_minutes=dur,
            price_cents=cents,
            currency="USD",
        )
        for idx, (s_name, dur, cents) in enumerate(raw_services)
    )
    resources = (
        BlueprintResourceItem(display_name="Lead Specialist", kind="artist"),
        BlueprintResourceItem(display_name="Service Station 1", kind="artist"),
    )
    hours = tuple(
        BlueprintHoursItem(weekday=wd, opens_minute=540, closes_minute=1080) for wd in range(1, 7)
    )
    return AiBusinessBlueprint(
        engine="grounded",
        model="deterministic-us-architect-v1",
        business_name=business_name,
        slug=_safe_slug(business_name),
        location_name="Main US Location",
        timezone=tz,
        industry_ids=industry_ids,
        business_formats=tuple(dict.fromkeys(formats)),
        enableable_module_ids=preset.enableable_module_ids,
        pending_module_ids=preset.pending_module_ids,
        services=services,
        resources=resources,
        business_hours=hours,
        cancellation_summary="Free cancellation or rescheduling up to 24 hours before appointment.",
        recommended_connectors=_default_connectors(industry_ids),
        rationale=(
            f"Configured for US market ({tz}) with verified NAICS modules and starter services. "
            "Review and adjust any item before launching your workspace."
        ),
    )


def _call_cf_blueprint_sync(
    description: str,
    image_data_url: str | None,
) -> tuple[str, dict[str, Any]] | None:
    account_id = os.environ.get("GBA_CF_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("GBA_CF_API_TOKEN", "").strip()
    if not account_id or not api_token:
        return None
    use_vision = bool(
        image_data_url
        and image_data_url.startswith(
            ("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")
        )
    )
    model = (
        os.environ.get("GBA_CF_VISION_MODEL", _VISION_MODEL_DEFAULT).strip()
        if use_vision
        else os.environ.get("GBA_CF_MODEL", _TEXT_MODEL_DEFAULT).strip()
    ) or (_VISION_MODEL_DEFAULT if use_vision else _TEXT_MODEL_DEFAULT)

    industry_catalog_text = "\n".join(f"{i.id}: {i.name} ({i.code})" for i in INDUSTRIES)
    system_prompt = (
        "You are GORGONA AI Business Architect for United States businesses (USD only). "
        "Given the owner's business description (and optional price list image), design a complete "
        "ready-to-launch workspace blueprint. Pick 1 to 3 exact industry_ids from this catalog:\n"
        f"{industry_catalog_text}\n\n"
        "Return ONLY valid JSON (no markdown commentary) with exact keys:\n"
        "- business_name (string)\n"
        "- location_name (string, e.g. 'Austin HQ' or 'Main Location')\n"
        "- timezone (valid US IANA timezone: America/New_York, America/Chicago, America/Denver, "
        "America/Phoenix, America/Los_Angeles, America/Anchorage, or Pacific/Honolulu)\n"
        "- industry_ids (array of 1..3 integers from 1..39)\n"
        "- business_formats (array of strings from: b2c, b2b, marketplace, franchise, holding)\n"
        "- services (array of 3..6 objects: "
        "{name, duration_minutes (15..480), price_usd (number)})\n"
        "- resources (array of 1..4 objects: {display_name, kind: 'artist'|'room'|'equipment'})\n"
        "- business_hours (array of objects: "
        "{weekday (1=Mon..7=Sun), opens_hour (0..23), closes_hour (1..24)})\n"
        "- cancellation_summary (1 concise sentence)\n"
        "- rationale (1-2 concise sentences explaining the architecture chosen)"
    )

    user_content: Any
    if use_vision and image_data_url:
        user_content = [
            {"type": "text", "text": f"Business description:\n{description[:1800]}"},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    else:
        user_content = f"Business description:\n{description[:1800]}"

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
            "max_tokens": 900,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    conn = http.client.HTTPSConnection("api.cloudflare.com", 443, timeout=22.0)
    try:
        conn.request(
            "POST",
            f"/client/v4/accounts/{account_id}/ai/v1/chat/completions",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_token}",
            },
        )
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            _LOG.warning("Cloudflare AI Architect HTTP %s on %s", resp.status, model)
            return None
        parsed = json.loads(raw.decode("utf-8"))
        msg = ((parsed.get("choices") or [{}])[0]).get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            return None
        cleaned = _JSON_FENCE_RE.sub("", content.strip()).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(cleaned[start : end + 1])
        if not isinstance(data, dict):
            return None
        return (model, data)
    except Exception as exc:
        _LOG.warning("Cloudflare AI Architect failed: %s", type(exc).__name__)
        return None
    finally:
        conn.close()


async def generate_business_blueprint(req: AiBlueprintRequest) -> AiBusinessBlueprint:
    """Generate a validated US business workspace blueprint via Cloudflare Workers AI."""
    fallback = _deterministic_blueprint(req.description)
    cf = await asyncio.to_thread(
        _call_cf_blueprint_sync, req.description, req.price_list_image_data_url
    )
    if cf is None:
        return fallback
    model, raw = cf

    raw_name = str(raw.get("business_name") or "").strip()[:160]
    business_name = raw_name if len(raw_name) >= 2 else fallback.business_name
    raw_loc = str(raw.get("location_name") or "").strip()[:160]
    location_name = raw_loc if len(raw_loc) >= 2 else fallback.location_name

    tz_cand = str(raw.get("timezone") or "").strip()
    try:
        ZoneInfo(tz_cand)
        timezone = tz_cand
    except Exception:
        timezone = fallback.timezone

    raw_inds = raw.get("industry_ids")
    ind_list: list[int] = []
    if isinstance(raw_inds, list):
        for item in raw_inds:
            try:
                iv = int(item)
                if iv in INDUSTRY_IDS and iv not in ind_list:
                    ind_list.append(iv)
            except TypeError, ValueError:
                continue
    industry_ids = tuple(sorted(ind_list[:4])) if ind_list else fallback.industry_ids
    preset = resolve_onboarding_modules(industry_ids)

    raw_fmts = raw.get("business_formats")
    fmts: list[BusinessFormat] = []
    if isinstance(raw_fmts, list):
        for f_item in raw_fmts:
            try:
                bf = BusinessFormat(str(f_item).strip().lower())
                if bf not in fmts:
                    fmts.append(bf)
            except ValueError:
                continue
    business_formats = tuple(fmts) if fmts else fallback.business_formats

    services_out: list[BlueprintServiceItem] = []
    seen_codes: set[str] = set()
    raw_svcs = raw.get("services")
    if isinstance(raw_svcs, list):
        for idx, s in enumerate(raw_svcs[:8], start=1):
            if not isinstance(s, dict):
                continue
            s_name = str(s.get("name") or "").strip()[:160]
            if len(s_name) < 2:
                continue
            try:
                dur = max(10, min(480, int(s.get("duration_minutes") or 60)))
            except TypeError, ValueError:
                dur = 60
            try:
                price_usd = float(s.get("price_usd", 0))
                cents = max(0, min(5_000_000, round(price_usd * 100)))
            except TypeError, ValueError:
                cents = 0
            code = _safe_code(s_name, idx)
            if code in seen_codes:
                code = f"{code[:58]}_{idx}"
            seen_codes.add(code)
            services_out.append(
                BlueprintServiceItem(
                    code=code,
                    name=s_name,
                    duration_minutes=dur,
                    price_cents=cents,
                    currency="USD",
                )
            )
    services = tuple(services_out) if services_out else fallback.services

    resources_out: list[BlueprintResourceItem] = []
    raw_res = raw.get("resources")
    if isinstance(raw_res, list):
        for r in raw_res[:6]:
            if not isinstance(r, dict):
                continue
            r_name = str(r.get("display_name") or "").strip()[:120]
            if len(r_name) < 2:
                continue
            rk = str(r.get("kind") or "artist").strip().lower()
            kind: Literal["artist", "chair", "room", "equipment"] = (
                rk if rk in ("artist", "chair", "room", "equipment") else "artist"  # type: ignore[assignment]
            )
            resources_out.append(BlueprintResourceItem(display_name=r_name, kind=kind))
    resources = tuple(resources_out) if resources_out else fallback.resources

    hours_out: list[BlueprintHoursItem] = []
    seen_days: set[int] = set()
    raw_hrs = raw.get("business_hours")
    if isinstance(raw_hrs, list):
        for h in raw_hrs[:7]:
            if not isinstance(h, dict):
                continue
            try:
                wd = int(h.get("weekday") or 0)
                oh = int(h.get("opens_hour", 9))
                ch = int(h.get("closes_hour", 18))
            except TypeError, ValueError:
                continue
            if not (1 <= wd <= 7) or wd in seen_days:
                continue
            opens_m = max(0, min(1380, oh * 60))
            closes_m = max(opens_m + 30, min(1440, ch * 60))
            seen_days.add(wd)
            hours_out.append(
                BlueprintHoursItem(weekday=wd, opens_minute=opens_m, closes_minute=closes_m)
            )
    business_hours = (
        tuple(sorted(hours_out, key=lambda x: x.weekday)) if hours_out else fallback.business_hours
    )

    cancel_txt = str(raw.get("cancellation_summary") or "").strip()[:300]
    rationale_txt = str(raw.get("rationale") or "").strip()[:500]

    return AiBusinessBlueprint(
        engine="cloudflare",
        model=model,
        business_name=business_name,
        slug=_safe_slug(business_name),
        location_name=location_name,
        timezone=timezone,
        industry_ids=industry_ids,
        business_formats=business_formats,
        enableable_module_ids=preset.enableable_module_ids,
        pending_module_ids=preset.pending_module_ids,
        services=services,
        resources=resources,
        business_hours=business_hours,
        cancellation_summary=cancel_txt or fallback.cancellation_summary,
        recommended_connectors=_default_connectors(industry_ids),
        rationale=rationale_txt or fallback.rationale,
    )
