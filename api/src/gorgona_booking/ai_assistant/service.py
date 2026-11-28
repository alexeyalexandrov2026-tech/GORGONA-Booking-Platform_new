"""Grounded AI Booking Assistant (customer) and Business Copilot (owner).

Security & truthfulness invariants:
- Every customer query runs strictly inside a Host-resolved `tenant_transaction`.
- Every owner query runs strictly inside `authorized_tenant` with `BUSINESS_READ`.
- Neither surface ever fabricates availability, prices, or policies: slots are queried
  live via `customer.queries.availability`, and owner insights come from real PG18 queries.
- Optional LLM synthesis via Cloudflare Workers AI (`GBA_CF_ACCOUNT_ID` + `GBA_CF_API_TOKEN`)
  or Gemini (`GBA_GEMINI_API_KEY`) strictly narrates the verified facts with stdlib HTTPS
  (zero extra dependencies) and falls back cleanly to deterministic output.
- Human control over AI (AGENTS.md): Copilot is strictly read-only and proposes actions.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from gorgona_booking.ai_assistant.byok import (
    TenantByokAiConfig,
    call_byok_llm_sync,
    load_active_tenant_byok_ai,
)
from gorgona_booking.customer import queries as customer_queries
from gorgona_booking.customer.contracts import AvailabilityQuery, BootstrapView, VariantView
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.growth.service import get_growth_settings

_LOG = logging.getLogger(__name__)
_DEFAULT_CF_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_CYRILLIC_RE = re.compile(r"[\u0430-\u044f\u0451]")
_WORD_RE = re.compile(r"[a-z\u0430-\u044f\u04510-9]{3,}")
_PRICE_CAP_RE = re.compile(
    r"(?:under|below|max|less than|<=|\u0434\u043e|menos de)\s*\$?\s*(\d{1,5})",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_WEEKDAY_MAP = {
    "monday": 0,
    "mon": 0,
    "понедельник": 0,
    "lunes": 0,
    "tuesday": 1,
    "tue": 1,
    "вторник": 1,
    "martes": 1,
    "wednesday": 2,
    "wed": 2,
    "среда": 2,
    "среду": 2,
    "miércoles": 2,
    "miercoles": 2,
    "thursday": 3,
    "thu": 3,
    "четверг": 3,
    "jueves": 3,
    "friday": 4,
    "fri": 4,
    "пятница": 4,
    "пятницу": 4,
    "viernes": 4,
    "saturday": 5,
    "sat": 5,
    "суббота": 5,
    "субботу": 5,
    "sábado": 5,
    "sabado": 5,
    "sunday": 6,
    "sun": 6,
    "воскресенье": 6,
    "domingo": 6,
}


@dataclass(frozen=True)
class RecommendedSlot:
    location_id: UUID
    location_name: str
    variant_id: UUID
    service_name: str
    variant_name: str
    resource_id: UUID
    resource_name: str
    day: date
    start_at: datetime
    end_at: datetime
    timezone: str
    price_cents: int
    currency: str
    duration_minutes: int


AiEngine = Literal[
    "cloudflare",
    "gemini",
    "byok_anthropic",
    "byok_gemini",
    "byok_openai",
    "grounded",
]


@dataclass(frozen=True)
class AssistantResult:
    engine: AiEngine
    business_name: str
    reply: str
    recommended_slots: list[RecommendedSlot]
    waitlist_suggested: bool
    cancellation_summary: str


@dataclass(frozen=True)
class CopilotInsight:
    priority: Literal["high", "medium", "low"]
    category: str
    title: str
    detail: str
    action_path: str


@dataclass(frozen=True)
class CopilotResult:
    engine: AiEngine
    business_name: str
    reply: str
    metrics: dict[str, Any]
    insights: list[CopilotInsight]


def parse_assistant_intent(message: str, *, today: date, max_day: date) -> dict[str, Any]:
    """Deterministic multilingual (EN/RU/ES) intent parser for date, window, budget, and sort."""
    lower = message.lower()
    target_days: list[date] = []

    iso_match = _ISO_DATE_RE.search(lower)
    if iso_match:
        try:
            parsed = date.fromisoformat(iso_match.group(1))
            if today <= parsed <= max_day:
                target_days.append(parsed)
        except ValueError:
            pass

    if any(w in lower for w in ("tomorrow", "завтра", "mañana", "manana")):
        cand = today + timedelta(days=1)
        if cand <= max_day and cand not in target_days:
            target_days.append(cand)
    elif any(w in lower for w in ("today", "сегодня", "hoy", "now", "сейчас")):
        if today not in target_days:
            target_days.append(today)
    elif any(w in lower for w in ("weekend", "выходн", "fin de semana")):
        days_until_sat = (5 - today.weekday()) % 7
        for offset in (days_until_sat, days_until_sat + 1):
            cand = today + timedelta(days=offset)
            if today <= cand <= max_day and cand not in target_days:
                target_days.append(cand)
    else:
        for word, wd in _WEEKDAY_MAP.items():
            if word in lower:
                delta = (wd - today.weekday()) % 7
                if delta == 0:
                    delta = 7
                cand = today + timedelta(days=delta)
                if cand <= max_day and cand not in target_days:
                    target_days.append(cand)
                break

    if not target_days:
        target_days.append(today)
        nxt = today + timedelta(days=1)
        if nxt <= max_day:
            target_days.append(nxt)

    window: str = "any"
    if any(w in lower for w in ("morning", "утром", "утро", "am", "mañana temprano")):
        window = "morning"
    elif any(w in lower for w in ("afternoon", "днем", "днём", "после обеда", "tarde")):
        window = "afternoon"
    elif any(w in lower for w in ("evening", "вечер", "вечером", "night", "noche")):
        window = "evening"

    max_price_cents: int | None = None
    pm = _PRICE_CAP_RE.search(lower)
    if pm:
        max_price_cents = int(pm.group(1)) * 100

    sort_by = "relevance"
    if any(w in lower for w in ("cheap", "lowest", "budget", "дешев", "бюджет", "barat")):
        sort_by = "price"
    elif any(w in lower for w in ("fast", "quick", "short", "быстр", "коротк", "rápid", "rapid")):
        sort_by = "duration"

    language = "en"
    if _CYRILLIC_RE.search(lower):
        language = "ru"
    elif any(w in lower for w in ("hola", "mañana", "cita", "precio", "tarde", "buenos")):
        language = "es"

    tokens = [
        t
        for t in _WORD_RE.findall(lower)
        if t
        not in {
            "the",
            "and",
            "for",
            "with",
            "have",
            "any",
            "open",
            "slot",
            "slots",
            "time",
            "times",
            "book",
            "booking",
            "appointment",
            "tomorrow",
            "today",
            "morning",
            "afternoon",
            "evening",
            "under",
            "please",
            "can",
            "you",
            "есть",
            "запис",
            "время",
            "завтра",
            "сегодня",
        }
    ]

    return {
        "target_days": target_days[:2],
        "window": window,
        "max_price_cents": max_price_cents,
        "sort_by": sort_by,
        "language": language,
        "tokens": tokens,
    }


def _rank_variants(
    variants: list[VariantView],
    *,
    tokens: list[str],
    max_price_cents: int | None,
    sort_by: str,
) -> list[VariantView]:
    filtered = [v for v in variants if max_price_cents is None or v.price_cents <= max_price_cents]
    if not filtered:
        filtered = list(variants)

    def _score(v: VariantView) -> tuple[int, int, int]:
        haystack = f"{v.service_name} {v.name} {' '.join(v.provides)}".lower()
        hits = sum(1 for t in tokens if t in haystack)
        if sort_by == "price":
            return (-hits, v.price_cents, v.duration_minutes)
        if sort_by == "duration":
            return (-hits, v.duration_minutes, v.price_cents)
        return (-hits, v.price_cents, v.duration_minutes)

    return sorted(filtered, key=_score)


def _matches_window(instant: datetime, tz_name: str, window: str) -> bool:
    if window == "any":
        return True
    hour = instant.astimezone(ZoneInfo(tz_name)).hour
    if window == "morning":
        return hour < 12
    if window == "afternoon":
        return 12 <= hour < 17
    if window == "evening":
        return hour >= 17
    return True


def _strip_reasoning_tags(text: str) -> str:
    """Remove any model reasoning tags without altering verified prose."""
    return _THINK_BLOCK_RE.sub("", text).strip()


def _call_cloudflare_sync(system_prompt: str, user_payload: dict[str, Any]) -> str | None:
    """Optional Cloudflare Workers AI synthesis via OpenAI-compatible stdlib HTTPS."""
    account_id = os.environ.get("GBA_CF_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("GBA_CF_API_TOKEN", "").strip()
    if not account_id or not api_token:
        return None
    model = os.environ.get("GBA_CF_MODEL", _DEFAULT_CF_MODEL).strip() or _DEFAULT_CF_MODEL
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0.25,
            "max_tokens": 360,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    conn = http.client.HTTPSConnection("api.cloudflare.com", 443, timeout=15.0)
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
            _LOG.warning(
                "Cloudflare Workers AI returned HTTP %s for model %s",
                resp.status,
                model,
            )
            return None
        parsed = json.loads(raw.decode("utf-8"))
        choices = parsed.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return None
        msg = choices[0].get("message") or {}
        if not isinstance(msg, dict):
            return None
        content = msg.get("content")
        if not isinstance(content, str):
            return None
        clean = _strip_reasoning_tags(content)
        return clean[:1200] if clean else None
    except Exception as exc:
        _LOG.warning("Cloudflare Workers AI call failed: %s", type(exc).__name__)
        return None
    finally:
        conn.close()


def _call_gemini_sync(system_prompt: str, user_payload: dict[str, Any]) -> str | None:
    """Optional Gemini grounded synthesis via stdlib HTTPS. Returns None if unconfigured/failed."""
    api_key = os.environ.get("GBA_GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.environ.get("GBA_GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    body = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": json.dumps(user_payload, ensure_ascii=False)}],
                }
            ],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 320},
        }
    ).encode("utf-8")
    conn = http.client.HTTPSConnection("generativelanguage.googleapis.com", 443, timeout=10.0)
    try:
        conn.request(
            "POST",
            f"/v1beta/models/{model}:generateContent",
            body=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
        )
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            return None
        parsed = json.loads(raw.decode("utf-8"))
        candidates = parsed.get("candidates") or []
        if not candidates:
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
        return text[:1200] if text else None
    except Exception:
        return None
    finally:
        conn.close()


def _synthesize_reply_sync(
    system_prompt: str,
    user_payload: dict[str, Any],
    byok_config: TenantByokAiConfig | None = None,
) -> (
    tuple[
        Literal["cloudflare", "gemini", "byok_anthropic", "byok_gemini", "byok_openai"],
        str,
    ]
    | None
):
    """Select tenant BYOK LLM first (if enabled), then platform LLM with safe fallback."""
    if byok_config is not None and byok_config.enabled:
        byok_reply = call_byok_llm_sync(byok_config, system_prompt, user_payload)
        if byok_reply:
            return byok_reply
    provider = os.environ.get("GBA_AI_PROVIDER", "auto").strip().lower() or "auto"
    if provider == "grounded":
        return None
    if provider in ("auto", "cloudflare"):
        cf_reply = _call_cloudflare_sync(system_prompt, user_payload)
        if cf_reply:
            return ("cloudflare", cf_reply)
        if provider == "cloudflare":
            return None
    if provider in ("auto", "gemini"):
        gemini_reply = _call_gemini_sync(system_prompt, user_payload)
        if gemini_reply:
            return ("gemini", gemini_reply)
    return None


def _format_money(cents: int, currency: str) -> str:
    return f"{currency} {cents / 100:.2f}"


def _deterministic_customer_reply(
    *,
    boot: BootstrapView,
    slots: list[RecommendedSlot],
    language: str,
    waitlist_suggested: bool,
) -> str:
    if slots:
        top = slots[0]
        local_time = top.start_at.astimezone(ZoneInfo(top.timezone)).strftime("%b %d at %I:%M %p")
        price_txt = _format_money(top.price_cents, top.currency)
        if language == "ru":
            return (
                f"Нашёл {len(slots)} свободных слотов в {boot.name}. "
                f"Ближайший вариант: {top.service_name} ({top.variant_name}) "
                f"({top.resource_name}) — {local_time}, {price_txt} "
                f"({top.duration_minutes} мин). "
                "Нажмите на подходящий слот ниже, чтобы перейти к бронированию."
            )
        if language == "es":
            return (
                f"Encontré {len(slots)} horarios disponibles en {boot.name}. "
                f"Opción más cercana: {top.service_name} ({top.variant_name}) con "
                f"{top.resource_name} — {local_time}, {price_txt} ({top.duration_minutes} min). "
                "Seleccione cualquier horario abajo para reservar al instante."
            )
        return (
            f"I found {len(slots)} live open times at {boot.name}. "
            f"Earliest match: {top.service_name} ({top.variant_name}) with {top.resource_name} "
            f"on {local_time} for {price_txt} ({top.duration_minutes} min). "
            "Select any verified slot below to continue straight to reservation."
        )
    if waitlist_suggested:
        if language == "ru":
            return (
                f"На выбранные даты в {boot.name} свободных окон сейчас нет. "  # noqa: RUF001
                "Оставьте заявку в умном листе ожидания — мы сразу уведомим вас, "
                "как только освободится окно."
            )
        return (
            f"There are no open times matching your request at {boot.name} right now. "
            "Join the smart waitlist below to be notified as soon as a spot opens."
        )
    return (
        f"Welcome to {boot.name}. We offer {len(boot.variants)} bookable service option(s). "
        "Ask about any service, price, policy, or date and I will check live availability."
    )


@dataclass(frozen=True)
class CustomerAssistantContext:
    boot: BootstrapView
    ai_assistant_tone: str
    message: str
    language: str
    ranked_variants: list[VariantView]
    recommended_slots: list[RecommendedSlot]
    waitlist_suggested: bool
    early_result: AssistantResult | None = None
    byok_config: TenantByokAiConfig | None = None


async def gather_customer_assistant_context(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    message: str,
    location_id: UUID | None = None,
    preferred_day: date | None = None,
    environment: str = "local",
) -> CustomerAssistantContext:
    """Gather verified live catalog and slot availability inside a short DB transaction."""
    settings = await get_growth_settings(conn, tenant_id=tenant_id)
    boot = await customer_queries.bootstrap(conn)
    if not settings.ai_assistant_enabled:
        raise ValueError("AI Assistant is currently disabled by this business")
    if not boot.locations or not boot.variants:
        return CustomerAssistantContext(
            boot=boot,
            ai_assistant_tone=settings.ai_assistant_tone,
            message=message,
            language="en",
            ranked_variants=[],
            recommended_slots=[],
            waitlist_suggested=False,
            early_result=AssistantResult(
                engine="grounded",
                business_name=boot.name,
                reply=(
                    f"{boot.name} is preparing its bookable services. Please check back shortly."
                ),
                recommended_slots=[],
                waitlist_suggested=False,
                cancellation_summary=boot.cancellation.summary,
            ),
        )

    loc = next((item for item in boot.locations if item.id == location_id), boot.locations[0])
    intent = parse_assistant_intent(message, today=loc.today, max_day=loc.last_day)
    days: list[date] = (
        [preferred_day]
        if (preferred_day is not None and loc.today <= preferred_day <= loc.last_day)
        else intent["target_days"]
    )
    ranked_variants = _rank_variants(
        boot.variants,
        tokens=intent["tokens"],
        max_price_cents=intent["max_price_cents"],
        sort_by=intent["sort_by"],
    )

    artist_names = {a.id: a.name for a in boot.artists}
    lower_msg = message.lower()
    matched_artist = next(
        (a.id for a in boot.artists if a.location_id == loc.id and a.name.lower() in lower_msg),
        None,
    )

    recommended: list[RecommendedSlot] = []
    seen: set[tuple[UUID, datetime]] = set()
    for variant in ranked_variants[:3]:
        for day_item in days:
            if len(recommended) >= 6:
                break
            try:
                avail = await customer_queries.availability(
                    conn,
                    AvailabilityQuery(
                        location_id=loc.id,
                        variant_id=variant.id,
                        resource_id=matched_artist,
                        day=day_item,
                    ),
                )
            except Exception as exc:
                _LOG.debug(
                    "Skipping assistant availability probe for variant %s: %s", variant.id, exc
                )
                continue
            for slot in avail.slots:
                if not _matches_window(slot.start_at, avail.timezone, intent["window"]):
                    continue
                dedupe_key = (variant.id, slot.start_at)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                recommended.append(
                    RecommendedSlot(
                        location_id=loc.id,
                        location_name=loc.name,
                        variant_id=variant.id,
                        service_name=variant.service_name,
                        variant_name=variant.name,
                        resource_id=slot.resource_id,
                        resource_name=artist_names.get(slot.resource_id, "Specialist"),
                        day=day_item,
                        start_at=slot.start_at,
                        end_at=slot.end_at,
                        timezone=avail.timezone,
                        price_cents=avail.quote.total_cents,
                        currency=avail.quote.currency,
                        duration_minutes=avail.quote.booking_duration_minutes,
                    )
                )
                if len(recommended) >= 6:
                    break

    waitlist_suggested = len(recommended) == 0 and settings.waitlist_auto_offer
    byok_config = await load_active_tenant_byok_ai(
        conn, tenant_id=tenant_id, environment=environment
    )
    return CustomerAssistantContext(
        boot=boot,
        ai_assistant_tone=settings.ai_assistant_tone,
        message=message,
        language=str(intent["language"]),
        ranked_variants=ranked_variants,
        recommended_slots=recommended,
        waitlist_suggested=waitlist_suggested,
        byok_config=byok_config,
    )


async def synthesize_customer_assistant(ctx: CustomerAssistantContext) -> AssistantResult:
    """Synthesize customer assistant narration strictly OUTSIDE any DB transaction."""
    if ctx.early_result is not None:
        return ctx.early_result

    boot = ctx.boot
    synthesized = await asyncio.to_thread(
        _synthesize_reply_sync,
        (
            f"You are the AI Booking Assistant for {boot.name}. "
            f"Tone: {ctx.ai_assistant_tone}. "
            "Answer strictly using the verified catalog, live slots, and cancellation policy "
            "provided in JSON. Keep exact service, variant, and specialist names from JSON. "
            "Never invent prices, times, or promises. Reply naturally in the same language "
            "as customer_message in 2-3 concise sentences."
        ),
        {
            "customer_message": ctx.message[:500],
            "business_name": boot.name,
            "cancellation_policy": boot.cancellation.summary,
            "verified_catalog_top": [
                {
                    "service": v.service_name,
                    "variant": v.name,
                    "price": _format_money(v.price_cents, v.currency),
                    "duration_minutes": v.duration_minutes,
                }
                for v in ctx.ranked_variants[:6]
            ],
            "verified_open_slots": [
                {
                    "service": s.service_name,
                    "variant": s.variant_name,
                    "specialist": s.resource_name,
                    "local_time": s.start_at.astimezone(ZoneInfo(s.timezone)).strftime(
                        "%Y-%m-%d %I:%M %p %Z"
                    ),
                    "price": _format_money(s.price_cents, s.currency),
                }
                for s in ctx.recommended_slots
            ],
            "waitlist_suggested": ctx.waitlist_suggested,
        },
        ctx.byok_config,
    )

    if synthesized:
        engine, ai_reply = synthesized
        return AssistantResult(
            engine=engine,
            business_name=boot.name,
            reply=ai_reply,
            recommended_slots=ctx.recommended_slots,
            waitlist_suggested=ctx.waitlist_suggested,
            cancellation_summary=boot.cancellation.summary,
        )

    return AssistantResult(
        engine="grounded",
        business_name=boot.name,
        reply=_deterministic_customer_reply(
            boot=boot,
            slots=ctx.recommended_slots,
            language=ctx.language,
            waitlist_suggested=ctx.waitlist_suggested,
        ),
        recommended_slots=ctx.recommended_slots,
        waitlist_suggested=ctx.waitlist_suggested,
        cancellation_summary=boot.cancellation.summary,
    )


async def ask_customer_assistant(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    message: str,
    location_id: UUID | None = None,
    preferred_day: date | None = None,
) -> AssistantResult:
    ctx = await gather_customer_assistant_context(
        conn,
        tenant_id=tenant_id,
        message=message,
        location_id=location_id,
        preferred_day=preferred_day,
    )
    return await synthesize_customer_assistant(ctx)


@dataclass(frozen=True)
class CopilotContext:
    business_name: str
    metrics: dict[str, Any]
    insights: list[CopilotInsight]
    byok_config: TenantByokAiConfig | None = None


def build_enterprise_copilot_insights(metrics: dict[str, Any]) -> list[CopilotInsight]:
    """Build deterministic high-signal insights from MRP II, EAM/IoT, Inbox, Payroll & FX."""
    out: list[CopilotInsight] = []
    mrp_shortages = int(metrics.get("mrp_shortage_runs_count", 0) or 0)
    if mrp_shortages > 0:
        out.append(
            CopilotInsight(
                priority="high",
                category="mrp_supply_chain",
                title=(f"Resolve raw-material shortages on {mrp_shortages} MRP production run(s)"),
                detail=(
                    "Open Industrial ERP -> Production Runs to generate a 1-click Draft PO "
                    "for missing raw materials before manufacturing starts."
                ),
                action_path="/industrial/",
            )
        )
    eam_wos = int(metrics.get("eam_open_work_orders_count", 0) or 0)
    if eam_wos > 0:
        out.append(
            CopilotInsight(
                priority="high",
                category="predictive_eam",
                title=f"Schedule {eam_wos} predictive IoT maintenance work order(s)",
                detail=(
                    "Equipment telemetry triggered pre-failure maintenance alerts. Dispatch a "
                    "technician in Industrial ERP -> Predictive Work Orders to avoid downtime."
                ),
                action_path="/industrial/",
            )
        )
    unread_threads = int(metrics.get("inbox_unread_threads_count", 0) or 0)
    if unread_threads > 0:
        out.append(
            CopilotInsight(
                priority="high",
                category="omnichannel_crm",
                title=f"Reply to {unread_threads} unread client conversation(s)",
                detail=(
                    "Clients are waiting in your Omnichannel Inbox across Email, Virtual PBX, "
                    "SMS, or WhatsApp. Reply directly from one unified timeline."
                ),
                action_path="/inbox/",
            )
        )
    draft_payroll = int(metrics.get("draft_payroll_runs_count", 0) or 0)
    if draft_payroll > 0:
        out.append(
            CopilotInsight(
                priority="medium",
                category="us_payroll",
                title=f"Review and approve {draft_payroll} draft US Payroll run(s)",
                detail=(
                    "Human owner approval is required before exporting Gusto/ADP/Check payroll "
                    "files in Global Finance & US Payroll."
                ),
                action_path="/global-finance/",
            )
        )
    fx_open = int(metrics.get("fx_open_entries_count", 0) or 0)
    fx_pnl_cents = int(metrics.get("fx_unrealized_gain_loss_cents", 0) or 0)
    if fx_open > 0 and fx_pnl_cents != 0:
        direction = "gain" if fx_pnl_cents > 0 else "loss"
        out.append(
            CopilotInsight(
                priority="medium",
                category="fx_treasury",
                title=(
                    f"Unrealized FX {direction} of ${fx_pnl_cents / 100:+,.2f} across "
                    f"{fx_open} open multi-currency entry(ies)"
                ),
                detail=(
                    "Review live Mark-to-Market FX rates or settle open receivables/payables in "
                    "Global Finance -> Multi-Currency FX Ledger to lock in realized USD value."
                ),
                action_path="/global-finance/",
            )
        )
    return out


async def gather_owner_copilot_context(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    environment: str = "local",
) -> CopilotContext:
    """Gather cross-domain live PostgreSQL 18 facts inside a short read-only transaction."""
    growth = await get_growth_settings(conn, tenant_id=tenant_id)
    now = datetime.now(UTC)
    horizon = now + timedelta(days=7)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT display_name, booking_state FROM gba.tenants WHERE id = %s",
            (tenant_id,),
        )
        trow = await cur.fetchone()
        business_name = str(trow["display_name"]) if trow else "AMARKAL Business"
        booking_state = str(trow["booking_state"]) if trow else "draft"

        await cur.execute(
            """
            SELECT count(*) AS upcoming_count,
                   coalesce(sum(total_cents), 0) AS upcoming_cents
            FROM gba.bookings
            WHERE tenant_id = %s AND status = 'CONFIRMED'
              AND starts_at >= %s AND starts_at < %s
            """,
            (tenant_id, now, horizon),
        )
        brow = await cur.fetchone() or {"upcoming_count": 0, "upcoming_cents": 0}

        await cur.execute(
            """
            SELECT count(*) AS waiting_count,
                   coalesce(sum(v.price_cents), 0) AS recoverable_cents
            FROM gba.waitlist_entries w
            JOIN gba.service_variants v ON v.tenant_id = w.tenant_id AND v.id = w.variant_id
            WHERE w.tenant_id = %s AND w.status = 'waiting'
            """,
            (tenant_id,),
        )
        wrow = await cur.fetchone() or {"waiting_count": 0, "recoverable_cents": 0}

        await cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE status = 'sent') AS sent_count,
                count(*) FILTER (WHERE status IN ('failed', 'dead_lettered')) AS failed_count
            FROM gba.notification_outbox
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        nrow = await cur.fetchone() or {"sent_count": 0, "failed_count": 0}

        await cur.execute(
            "SELECT count(*) AS cnt FROM gba.locations WHERE tenant_id = %s",
            (tenant_id,),
        )
        loc_count = int((await cur.fetchone() or {"cnt": 0})["cnt"])

        await cur.execute(
            """
            SELECT count(*) AS cnt FROM gba.service_variants
            WHERE tenant_id = %s AND status = 'published' AND is_bookable
            """,
            (tenant_id,),
        )
        bookable_count = int((await cur.fetchone() or {"cnt": 0})["cnt"])

        await cur.execute(
            "SELECT count(*) AS cnt FROM gba.resources WHERE tenant_id = %s AND is_active",
            (tenant_id,),
        )
        staff_count = int((await cur.fetchone() or {"cnt": 0})["cnt"])

        await cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE status = 'paid') AS paid_count,
                coalesce(sum(amount_cents) FILTER (WHERE status = 'paid'), 0) AS paid_cents,
                count(*) FILTER (WHERE status = 'open') AS open_count,
                coalesce(sum(amount_cents) FILTER (WHERE status = 'open'), 0) AS open_cents
            FROM gba.payment_sessions
            WHERE tenant_id = %s
              AND created_at >= now() - interval '30 days'
            """,
            (tenant_id,),
        )
        prow = await cur.fetchone() or {
            "paid_count": 0,
            "paid_cents": 0,
            "open_count": 0,
            "open_cents": 0,
        }

        await cur.execute(
            """
            SELECT
                (SELECT count(*) FROM gba.connector_installations
                 WHERE tenant_id = %s AND status = 'installed') AS connectors_cnt,
                (SELECT count(*) FROM gba.api_keys
                 WHERE tenant_id = %s AND revoked_at IS NULL) AS mcp_keys_cnt,
                (SELECT count(*) FROM gba.media_assets
                 WHERE tenant_id = %s) AS media_cnt
            """,
            (tenant_id, tenant_id, tenant_id),
        )
        erow = await cur.fetchone() or {"connectors_cnt": 0, "mcp_keys_cnt": 0, "media_cnt": 0}

        await cur.execute(
            """
            SELECT
                (SELECT count(*) FROM gba.mrp_production_runs
                 WHERE tenant_id = %s
                   AND shortage_count > 0
                   AND status NOT IN ('completed', 'cancelled')) AS mrp_shortage_runs,
                (SELECT count(*) FROM gba.eam_predictive_work_orders
                 WHERE tenant_id = %s
                   AND status IN ('open', 'in_progress')) AS eam_open_wos,
                (SELECT count(*) FROM gba.omnichannel_threads
                 WHERE tenant_id = %s
                   AND status = 'open'
                   AND unread_count > 0) AS inbox_unread_threads,
                (SELECT count(*) FROM gba.fx_ledger_entries
                 WHERE tenant_id = %s AND status = 'open') AS fx_open_entries,
                (SELECT coalesce(sum(fx_gain_loss_cents), 0) FROM gba.fx_ledger_entries
                 WHERE tenant_id = %s AND status = 'open') AS fx_unrealized_cents,
                (SELECT count(*) FROM gba.payroll_runs
                 WHERE tenant_id = %s AND status = 'draft') AS draft_payroll_runs
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id, tenant_id),
        )
        ent_row = await cur.fetchone() or {
            "mrp_shortage_runs": 0,
            "eam_open_wos": 0,
            "inbox_unread_threads": 0,
            "fx_open_entries": 0,
            "fx_unrealized_cents": 0,
            "draft_payroll_runs": 0,
        }

    stripe_paid_cents = int(prow["paid_cents"])
    stripe_open_cents = int(prow["open_cents"])
    upcoming_cents = int(brow["upcoming_cents"])
    active_volume = max(upcoming_cents, stripe_paid_cents)
    commission_saved_cents = (active_volume * 5) // 100

    metrics: dict[str, Any] = {
        "booking_state": booking_state,
        "locations_count": loc_count,
        "active_staff_count": staff_count,
        "bookable_services_count": bookable_count,
        "upcoming_7d_confirmed_bookings": int(brow["upcoming_count"]),
        "upcoming_7d_booked_value_cents": upcoming_cents,
        "waiting_waitlist_count": int(wrow["waiting_count"]),
        "waitlist_recoverable_value_cents": int(wrow["recoverable_cents"]),
        "notifications_sent_count": int(nrow["sent_count"]),
        "notifications_failed_count": int(nrow["failed_count"]),
        "stripe_30d_paid_count": int(prow["paid_count"]),
        "stripe_30d_paid_cents": stripe_paid_cents,
        "stripe_30d_open_count": int(prow["open_count"]),
        "stripe_30d_open_cents": stripe_open_cents,
        "installed_connectors_count": int(erow["connectors_cnt"]),
        "active_mcp_keys_count": int(erow["mcp_keys_cnt"]),
        "brand_media_assets_count": int(erow["media_cnt"]),
        "estimated_commission_saved_vs_5pct_cents": commission_saved_cents,
        "google_review_url_configured": bool(growth.google_review_url),
        "ai_assistant_enabled": growth.ai_assistant_enabled,
        "reminder_hours_before": growth.reminder_hours_before,
        "rebooking_days_after": growth.rebooking_days_after,
        "mrp_shortage_runs_count": int(ent_row["mrp_shortage_runs"]),
        "eam_open_work_orders_count": int(ent_row["eam_open_wos"]),
        "inbox_unread_threads_count": int(ent_row["inbox_unread_threads"]),
        "fx_open_entries_count": int(ent_row["fx_open_entries"]),
        "fx_unrealized_gain_loss_cents": int(ent_row["fx_unrealized_cents"]),
        "draft_payroll_runs_count": int(ent_row["draft_payroll_runs"]),
    }

    insights: list[CopilotInsight] = []
    insights.extend(build_enterprise_copilot_insights(metrics))
    if metrics["waiting_waitlist_count"] > 0:
        rec_usd = metrics["waitlist_recoverable_value_cents"] / 100
        wait_cnt = metrics["waiting_waitlist_count"]
        insights.append(
            CopilotInsight(
                priority="high",
                category="revenue_recovery",
                title=f"Recover ${rec_usd:,.2f} from {wait_cnt} waitlisted client(s)",
                detail=(
                    "Clients are actively waiting for open slots. Notify them with one click in "
                    "Settings -> Growth & Waitlist to fill cancellations automatically."
                ),
                action_path="/settings/",
            )
        )
    if metrics["stripe_30d_open_count"] > 0:
        open_usd = stripe_open_cents / 100
        insights.append(
            CopilotInsight(
                priority="high",
                category="payments",
                title=(
                    f"Follow up on {metrics['stripe_30d_open_count']} open Stripe "
                    f"checkout link(s) (${open_usd:,.2f})"
                ),
                detail=(
                    "Sync or resend pending USD payment links in App Hub -> Stripe US Payments "
                    "to convert open checkouts with 0% platform commission."
                ),
                action_path="/integrations/",
            )
        )
    if bookable_count == 0 or staff_count == 0:
        insights.append(
            CopilotInsight(
                priority="high",
                category="activation",
                title="Publish at least one bookable service and active team member",
                detail=(
                    "Your online booking page and AI Booking Assistant need at least one "
                    "published service and active resource to present live availability."
                ),
                action_path="/services/",
            )
        )
    if not growth.google_review_url:
        insights.append(
            CopilotInsight(
                priority="medium",
                category="local_seo",
                title="Connect your Google Business Profile review link",
                detail=(
                    "Adding your Google Review URL enables post-visit review booster messages and "
                    "drives zero-commission organic bookings from Google Search and Maps."
                ),
                action_path="/settings/",
            )
        )
    if metrics["active_mcp_keys_count"] == 0:
        insights.append(
            CopilotInsight(
                priority="medium",
                category="ai_automation",
                title="Connect Claude, ChatGPT, or custom agents via Native MCP",
                detail=(
                    "Create a scoped MCP API key in App Hub so your AI agents can inspect live "
                    "bookings, payments, and unit economics under FORCE RLS isolation."
                ),
                action_path="/integrations/",
            )
        )
    if metrics["notifications_failed_count"] > 0:
        insights.append(
            CopilotInsight(
                priority="medium",
                category="reliability",
                title=f"Review {metrics['notifications_failed_count']} failed notification(s)",
                detail=(
                    "Inspect the Email/SMS outbox in Settings to verify recipient formats "
                    "or provider credentials."
                ),
                action_path="/settings/",
            )
        )
    insights.append(
        CopilotInsight(
            priority="low",
            category="retention",
            title=(
                f"Automated cadence: {growth.reminder_hours_before}h reminders & "
                f"{growth.rebooking_days_after}d rebooking"
            ),
            detail=(
                "Use prepaid packages/gift certificates (/prepaid/) and zero-commission "
                "marketplace publishing (/marketplace/) to lock in repeat revenue."
            ),
            action_path="/prepaid/",
        )
    )
    byok_config = await load_active_tenant_byok_ai(
        conn, tenant_id=tenant_id, environment=environment
    )
    return CopilotContext(
        business_name=business_name,
        metrics=metrics,
        insights=insights,
        byok_config=byok_config,
    )


async def synthesize_owner_copilot(
    ctx: CopilotContext,
    *,
    question: str | None = None,
) -> CopilotResult:
    """Run optional external LLM synthesis strictly OUTSIDE any PostgreSQL transaction."""
    clean_q = (question or "").strip()[:500]
    synthesized = await asyncio.to_thread(
        _synthesize_reply_sync,
        (
            f"You are the governed AI Business Copilot for {ctx.business_name} on AMARKAL Platform "
            "(US Business OS, 0% platform commission, zero vendor lock-in). "
            "Use ONLY the live JSON metrics and insights provided. Never invent revenue or claims. "
            "Reply naturally and concisely in the owner's language (Russian if Russian, else "
            "English) with concrete, actionable next steps."
        ),
        {
            "owner_question": (
                clean_q or "Give me a concise executive summary and top growth actions."
            ),
            "business_name": ctx.business_name,
            "live_metrics": ctx.metrics,
            "insights": [
                {"priority": i.priority, "title": i.title, "detail": i.detail} for i in ctx.insights
            ],
        },
        ctx.byok_config,
    )

    if synthesized:
        engine, ai_reply = synthesized
        return CopilotResult(
            engine=engine,
            business_name=ctx.business_name,
            reply=ai_reply,
            metrics=ctx.metrics,
            insights=ctx.insights,
        )

    is_ru = bool(_CYRILLIC_RE.search(clean_q.lower()))
    booked_usd = ctx.metrics["upcoming_7d_booked_value_cents"] / 100
    paid_usd = ctx.metrics["stripe_30d_paid_cents"] / 100
    wait_usd = ctx.metrics["waitlist_recoverable_value_cents"] / 100
    bookable_count = ctx.metrics["bookable_services_count"]
    staff_count = ctx.metrics["active_staff_count"]
    if is_ru:
        summary = (
            f"Сводка по {ctx.business_name}: на ближайшие 7 дней подтверждено "
            f"{ctx.metrics['upcoming_7d_confirmed_bookings']} записей на сумму ${booked_usd:,.2f}, "
            f"оплачено через Stripe за 30 дней: ${paid_usd:,.2f}. "
            f"В листе ожидания: {ctx.metrics['waiting_waitlist_count']} заявок "  # noqa: RUF001
            f"(потенциал ${wait_usd:,.2f}). "
            f"Активных услуг: {bookable_count}, сотрудников: {staff_count}. "
            f"Главный приоритет: {ctx.insights[0].title}."
        )
    else:
        summary = (
            f"{ctx.business_name} live pulse: {ctx.metrics['upcoming_7d_confirmed_bookings']} "
            f"confirmed booking(s) over the next 7 days (${booked_usd:,.2f} booked value), "
            f"${paid_usd:,.2f} paid via Stripe in the last 30 days, "
            f"{ctx.metrics['waiting_waitlist_count']} waitlisted client(s) (${wait_usd:,.2f} "
            f"recoverable), {bookable_count} published service(s), {staff_count} active team "
            f"member(s). Top priority: {ctx.insights[0].title}."
        )

    return CopilotResult(
        engine="grounded",
        business_name=ctx.business_name,
        reply=summary,
        metrics=ctx.metrics,
        insights=ctx.insights,
    )


async def ask_owner_copilot(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    question: str | None = None,
) -> CopilotResult:
    """Read-only owner AI copilot grounded strictly in live tenant PostgreSQL 18 facts."""
    ctx = await gather_owner_copilot_context(conn, tenant_id=tenant_id)
    return await synthesize_owner_copilot(ctx, question=question)
