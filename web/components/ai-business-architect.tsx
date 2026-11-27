"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { WEEKDAYS } from "../lib/business-time";
import { readAsDataUrl, validateImageFile } from "../lib/media-api";
import {
  BLUEPRINT_LIMITS as L,
  RESOURCE_KINDS,
  registerSelfServiceBusiness,
  requestAiBlueprint,
  type AiBlueprint,
  type IndustryPreset,
  type RegisterBusinessInput,
  type RegisterBusinessResult,
  type ResourceKind,
} from "../lib/onboarding-api";

const US_TIMEZONES = [
  { id: "America/New_York", label: "Eastern (America/New_York)" },
  { id: "America/Chicago", label: "Central (America/Chicago)" },
  { id: "America/Denver", label: "Mountain (America/Denver)" },
  { id: "America/Phoenix", label: "Arizona (America/Phoenix)" },
  { id: "America/Los_Angeles", label: "Pacific (America/Los_Angeles)" },
  { id: "America/Anchorage", label: "Alaska (America/Anchorage)" },
  { id: "Pacific/Honolulu", label: "Hawaii (Pacific/Honolulu)" },
];

const FORMAT_LABELS: Record<string, string> = {
  b2c: "B2C (Consumers)",
  b2b: "B2B (Businesses)",
  marketplace: "Marketplace",
  franchise: "Franchise / Network",
  holding: "Holding / Multi-entity",
};

const RESOURCE_KIND_LABELS: Record<ResourceKind, string> = {
  artist: "Team member",
  chair: "Station",
  room: "Room",
  equipment: "Equipment",
};

const CONNECTOR_NAMES: Record<string, string> = {
  native_mcp: "AMARKAL Native MCP Server",
  zapier_make: "Zapier / Make / n8n",
  quickbooks_online: "QuickBooks Online (US)",
  google_calendar: "Google Calendar & Outlook",
  reserve_with_google: "Reserve with Google & Maps",
  twilio_voice_sms: "Twilio SMS & AI Voice (BYOK)",
  meta_messaging: "WhatsApp & Instagram DM (BYOK)",
  stripe_ach_pos: "Stripe US (Cards, Apple Pay, ACH)",
};

const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const PRICE_RE = /^\d{1,6}(\.\d{1,2})?$/;
const PENDING_BLUEPRINT_KEY = "amarkal_pending_blueprint_v1";

interface PendingBlueprintState {
  description: string;
  blueprint: AiBlueprint;
  draft: Draft;
  approved: boolean;
}

interface ServiceRow {
  key: string;
  name: string;
  duration: string;
  price: string;
}
interface ResourceRow {
  key: string;
  name: string;
  kind: ResourceKind;
}
interface HoursRow {
  weekday: number;
  open: boolean;
  opens: string;
  closes: string;
}
interface Draft {
  business_name: string;
  slug: string;
  location_name: string;
  timezone: string;
  industry_ids: number[];
  business_formats: string[];
  services: ServiceRow[];
  resources: ResourceRow[];
  hours: HoursRow[];
  cancellation: string;
}
interface FieldError {
  id: string;
  message: string;
}

let rowSeq = 0;
function rowKey(): string {
  rowSeq += 1;
  return `row-${rowSeq}`;
}

function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 50);
}

function minuteToTime(minute: number): string {
  const m = Math.max(0, Math.min(1440, minute)) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

function timeToMinute(value: string, closing: boolean): number | null {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const minute = Number(match[1]) * 60 + Number(match[2]);
  if (minute > 1439) return null;
  return closing && minute === 0 ? 1440 : minute;
}

function centsToPrice(cents: number): string {
  return (cents / 100).toFixed(2);
}

function priceToCents(value: string): number | null {
  const clean = value.trim().replace(/^\$/, "").replaceAll(",", "");
  if (!PRICE_RE.test(clean)) return null;
  return Math.round(Number(clean) * 100);
}

function serviceCodes(names: string[]): string[] {
  const used = new Set<string>();
  return names.map((name, index) => {
    let code = name
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 40);
    if (!/^[A-Z]/.test(code)) code = `SVC_${code}`.slice(0, 40);
    if (code.length < 2) code = `SVC_${index + 1}`;
    let candidate = code;
    let n = 2;
    while (used.has(candidate)) {
      candidate = `${code}_${n}`;
      n += 1;
    }
    used.add(candidate);
    return candidate;
  });
}

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

function draftFrom(bp: AiBlueprint): Draft {
  const hoursByDay = new Map(bp.business_hours.map((h) => [h.weekday, h]));
  const kinds = RESOURCE_KINDS as readonly string[];
  return {
    business_name: bp.business_name.slice(0, 200),
    slug: SLUG_RE.test(bp.slug) ? bp.slug : slugify(bp.business_name),
    location_name: bp.location_name.slice(0, 200),
    timezone: bp.timezone,
    industry_ids: [...bp.industry_ids].sort((a, b) => a - b),
    business_formats: bp.business_formats.length
      ? [...bp.business_formats]
      : ["b2c"],
    services: bp.services.slice(0, L.servicesMax).map((s) => ({
      key: rowKey(),
      name: s.name,
      duration: String(s.duration_minutes),
      price: centsToPrice(s.price_cents),
    })),
    resources: bp.resources.slice(0, L.resourcesMax).map((r) => ({
      key: rowKey(),
      name: r.display_name,
      kind: (kinds.includes(r.kind) ? r.kind : "artist") as ResourceKind,
    })),
    hours: WEEKDAYS.map(({ index }) => {
      const h = hoursByDay.get(index);
      return {
        weekday: index,
        open: Boolean(h),
        opens: minuteToTime(h?.opens_minute ?? 540),
        closes: minuteToTime(h?.closes_minute ?? 1080),
      };
    }),
    cancellation: bp.cancellation_summary.slice(0, L.cancellationMax),
  };
}

function validate(draft: Draft, approved: boolean): FieldError[] {
  const errors: FieldError[] = [];
  const name = draft.business_name.trim();
  if (!name || name.length > 200)
    errors.push({
      id: "ai-business-name",
      message: "Enter a business name (up to 200 characters).",
    });
  if (
    draft.slug.length < 2 ||
    draft.slug.length > 63 ||
    !SLUG_RE.test(draft.slug)
  )
    errors.push({
      id: "ai-slug",
      message:
        "The URL slug needs 2–63 lowercase letters, digits, or single hyphens.",
    });
  if (!draft.location_name.trim())
    errors.push({
      id: "ai-location",
      message: "Enter a name for your primary location.",
    });
  if (!draft.industry_ids.length)
    errors.push({
      id: "ai-industry-add",
      message: "Select at least one industry.",
    });
  if (!draft.business_formats.length)
    errors.push({
      id: "ai-format-b2c",
      message: "Select at least one business format.",
    });
  if (!draft.services.length)
    errors.push({
      id: "ai-add-service",
      message: "Add at least one service customers can book.",
    });
  draft.services.forEach((s, i) => {
    const n = s.name.trim();
    if (n.length < L.serviceNameMin || n.length > L.serviceNameMax)
      errors.push({
        id: `ai-svc-name-${s.key}`,
        message: `Service ${i + 1}: the name needs ${L.serviceNameMin}–${L.serviceNameMax} characters.`,
      });
    const d = Number(s.duration);
    if (!/^\d+$/.test(s.duration) || d < L.durationMin || d > L.durationMax)
      errors.push({
        id: `ai-svc-duration-${s.key}`,
        message: `Service ${i + 1}: the duration must be a whole number of minutes from ${L.durationMin} to ${L.durationMax}.`,
      });
    const cents = priceToCents(s.price);
    if (cents === null || cents > L.priceCentsMax)
      errors.push({
        id: `ai-svc-price-${s.key}`,
        message: `Service ${i + 1}: enter a USD price from $0.00 to ${usd.format(L.priceCentsMax / 100)}.`,
      });
  });
  if (draft.services.length && !draft.resources.length)
    errors.push({
      id: "ai-add-resource",
      message: "Add at least one resource so customers can book your services.",
    });
  draft.resources.forEach((r, i) => {
    const n = r.name.trim();
    if (n.length < L.resourceNameMin || n.length > L.resourceNameMax)
      errors.push({
        id: `ai-res-name-${r.key}`,
        message: `Resource ${i + 1}: the name needs ${L.resourceNameMin}–${L.resourceNameMax} characters.`,
      });
  });
  const openDays = draft.hours.filter((h) => h.open);
  if (draft.services.length && !openDays.length)
    errors.push({
      id: "ai-hours-1-open",
      message: "Open at least one day of the week.",
    });
  for (const h of openDays) {
    const label =
      WEEKDAYS.find((w) => w.index === h.weekday)?.label ?? "This day";
    const o = timeToMinute(h.opens, false);
    const c = timeToMinute(h.closes, true);
    if (o === null || c === null || o >= c || o > 1410 || c < 30)
      errors.push({
        id: `ai-hours-${h.weekday}-opens`,
        message: `${label}: the opening time must be earlier than the closing time.`,
      });
  }
  if (draft.cancellation.trim().length > L.cancellationMax)
    errors.push({
      id: "ai-cancellation",
      message: `The cancellation summary can have up to ${L.cancellationMax} characters.`,
    });
  if (!approved)
    errors.push({
      id: "ai-approve",
      message: "Confirm that you reviewed and approve this blueprint.",
    });
  return errors;
}

function toInput(draft: Draft): RegisterBusinessInput {
  const codes = serviceCodes(draft.services.map((s) => s.name.trim()));
  return {
    business_name: draft.business_name.trim(),
    slug: draft.slug,
    location_name: draft.location_name.trim(),
    timezone: draft.timezone,
    industry_ids: [...draft.industry_ids].sort((a, b) => a - b),
    business_formats: draft.business_formats,
    starter_services: draft.services.map((s, i) => ({
      code: codes[i] ?? `SVC_${i + 1}`,
      name: s.name.trim(),
      duration_minutes: Number(s.duration),
      price_cents: priceToCents(s.price) ?? 0,
      currency: "USD",
    })),
    starter_resources: draft.resources.map((r) => ({
      display_name: r.name.trim(),
      kind: r.kind,
    })),
    starter_hours: draft.hours
      .filter((h) => h.open)
      .map((h) => ({
        weekday: h.weekday,
        opens_minute: timeToMinute(h.opens, false) ?? 0,
        closes_minute: timeToMinute(h.closes, true) ?? 0,
      })),
    cancellation_summary: draft.cancellation.trim() || null,
  };
}

export function AiBusinessArchitect({
  presets,
  signedIn = true,
  onCreated,
  onRequireSignIn,
}: {
  presets: IndustryPreset[];
  signedIn?: boolean;
  onCreated: (result: RegisterBusinessResult) => void;
  onRequireSignIn?: () => void;
}) {
  const router = useRouter();
  const [description, setDescription] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [blueprint, setBlueprint] = useState<AiBlueprint | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [slugEdited, setSlugEdited] = useState(false);
  const [approved, setApproved] = useState(false);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [addIndustry, setAddIndustry] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const photoUrlRef = useRef<string | null>(null);
  const errorSummaryRef = useRef<HTMLDivElement>(null);
  const keys = useRef(new Map<string, string>());
  const descriptionId = useId();
  const photoHintId = useId();

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      try {
        const raw = sessionStorage.getItem(PENDING_BLUEPRINT_KEY);
        if (!raw) return;
        const saved = JSON.parse(raw) as Partial<PendingBlueprintState>;
        if (saved.blueprint && saved.draft) {
          if (typeof saved.description === "string")
            setDescription(saved.description);
          setBlueprint(saved.blueprint);
          setDraft(saved.draft);
          setApproved(Boolean(saved.approved));
        }
      } catch {
        sessionStorage.removeItem(PENDING_BLUEPRINT_KEY);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(
    () => () => {
      abortRef.current?.abort();
      if (photoUrlRef.current) URL.revokeObjectURL(photoUrlRef.current);
    },
    [],
  );

  const errorFor = (id: string) => errors.find((e) => e.id === id)?.message;
  const fieldProps = (id: string) => {
    const message = errorFor(id);
    return {
      id,
      "aria-invalid": message ? (true as const) : undefined,
      "aria-describedby": message ? `${id}-error` : undefined,
    };
  };
  const fieldError = (id: string) => {
    const message = errorFor(id);
    return message ? (
      <span id={`${id}-error`} className="usr-field-error">
        {message}
      </span>
    ) : null;
  };

  const presetById = useMemo(
    () => new Map(presets.map((p) => [p.id, p])),
    [presets],
  );
  const modulePreview = useMemo(() => {
    const enableable = new Set<string>();
    const pending = new Set<string>();
    for (const id of draft?.industry_ids ?? []) {
      const p = presetById.get(id);
      if (!p) continue;
      for (const m of p.enableable_module_ids) enableable.add(m);
      for (const m of p.pending_module_ids) pending.add(m);
    }
    return {
      enableable: Array.from(enableable).sort(),
      pending: Array.from(pending)
        .filter((m) => !enableable.has(m))
        .sort(),
    };
  }, [draft?.industry_ids, presetById]);

  const timezones = useMemo(() => {
    const tz = draft?.timezone;
    if (
      tz &&
      !US_TIMEZONES.some((z) => z.id === tz) &&
      /^(America|Pacific)\//.test(tz)
    )
      return [...US_TIMEZONES, { id: tz, label: tz }];
    return US_TIMEZONES;
  }, [draft?.timezone]);

  function update(patch: Partial<Draft>) {
    setDraft((d) => (d ? { ...d, ...patch } : d));
  }

  async function choosePhoto(file: File | null) {
    setPhotoError(null);
    if (photoUrlRef.current) URL.revokeObjectURL(photoUrlRef.current);
    photoUrlRef.current = null;
    setPhotoUrl(null);
    setPhoto(null);
    if (!file) return;
    if (file.size > L.imageBytesMax) {
      setPhotoError(
        "The photo is larger than 4 MB. Choose a smaller PNG, JPEG, or WEBP image.",
      );
      return;
    }
    const invalid = await validateImageFile(file);
    if (invalid) {
      setPhotoError(invalid);
      return;
    }
    const url = URL.createObjectURL(file);
    photoUrlRef.current = url;
    setPhotoUrl(url);
    setPhoto(file);
  }

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    const text = description.trim();
    setGenerateError(null);
    if (text.length < L.descriptionMin || text.length > L.descriptionMax) {
      setGenerateError(
        `Describe your business in ${L.descriptionMin}–${L.descriptionMax} characters.`,
      );
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setGenerating(true);
    try {
      let image: string | null = null;
      if (photo) {
        image = await readAsDataUrl(photo);
        if (image.length > L.imageDataUrlMax)
          throw new Error(
            "The encoded photo is too large. Choose an image under 4 MB.",
          );
      }
      const bp = await requestAiBlueprint(
        { description: text, price_list_image_data_url: image },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setBlueprint(bp);
      setDraft(draftFrom(bp));
      setSlugEdited(false);
      setApproved(false);
      setErrors([]);
      setSubmitError(null);
    } catch (err) {
      if (controller.signal.aborted) return;
      setGenerateError(
        err instanceof Error
          ? err.message
          : "The AI Business Architect could not draft a blueprint.",
      );
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setGenerating(false);
      }
    }
  }

  function cancelGenerate() {
    abortRef.current?.abort();
    abortRef.current = null;
    setGenerating(false);
  }

  async function launch() {
    if (!draft) return;
    setSubmitError(null);
    const found = validate(draft, approved);
    setErrors(found);
    if (found.length) {
      requestAnimationFrame(() => errorSummaryRef.current?.focus());
      return;
    }
    if (!signedIn) {
      try {
        if (blueprint) {
          const payload: PendingBlueprintState = {
            description,
            blueprint,
            draft,
            approved: true,
          };
          sessionStorage.setItem(
            PENDING_BLUEPRINT_KEY,
            JSON.stringify(payload),
          );
        }
      } catch {
        /* ignore restricted sessionStorage */
      }
      if (onRequireSignIn) {
        onRequireSignIn();
      } else {
        router.push("/auth/signin/?mode=signup&next=/onboarding/");
      }
      return;
    }
    const input = toInput(draft);
    const signature = JSON.stringify(input);
    let key = keys.current.get(signature);
    if (!key) {
      key = crypto.randomUUID();
      keys.current.set(signature, key);
    }
    setSubmitting(true);
    try {
      const result = await registerSelfServiceBusiness(input, key);
      try {
        sessionStorage.removeItem(PENDING_BLUEPRINT_KEY);
      } catch {
        /* ignore */
      }
      onCreated(result);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Business registration failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const engineBadge = blueprint ? (
    blueprint.engine === "cloudflare" ? (
      <span className="usr-badge usr-badge-ai">
        Drafted by Cloudflare Workers AI · {blueprint.model}
      </span>
    ) : blueprint.engine === "grounded" ? (
      <span className="usr-badge usr-badge-fallback">
        Deterministic fallback · {blueprint.model}
      </span>
    ) : (
      <span className="usr-badge">
        Engine: {blueprint.engine} · {blueprint.model}
      </span>
    )
  ) : null;

  return (
    <div className="usr-stack">
      <form className="usr-card" onSubmit={(e) => void generate(e)} noValidate>
        <h2>1. Describe your business</h2>
        <p className="usr-muted">
          Tell the AI Business Architect what you sell, where you operate, and
          when you are open. It drafts services, USD prices, resources, weekly
          hours, and a cancellation policy. Nothing is created until you review
          the draft and approve it.
        </p>
        <label htmlFor={descriptionId}>
          Business description
          <textarea
            id={descriptionId}
            className="usr-textarea"
            required
            minLength={L.descriptionMin}
            maxLength={L.descriptionMax}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Example: Mobile auto detailing in Austin, TX. Interior and exterior details, ceramic coating, and window tint. Open Monday to Saturday, 8 AM to 6 PM. Two detailing vans."
          />
          <span className="usr-muted">
            {description.trim().length} / {L.descriptionMax} characters
          </span>
        </label>
        <label>
          Price list or menu photo (optional)
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            aria-describedby={photoHintId}
            onChange={(e) => void choosePhoto(e.target.files?.[0] ?? null)}
          />
          <span id={photoHintId} className="usr-muted">
            PNG, JPEG, or WEBP up to 4 MB. The photo is sent only to draft this
            blueprint and is not stored.
          </span>
        </label>
        {photoError && (
          <p className="usr-field-error" role="alert">
            {photoError}
          </p>
        )}
        {photoUrl && photo && (
          <div className="usr-inline" style={{ marginBottom: 16 }}>
            <Image
              src={photoUrl}
              alt={`Selected price list: ${photo.name}`}
              width={160}
              height={160}
              unoptimized
              className="usr-preview"
              style={{ width: "auto", maxWidth: 160, height: "auto" }}
            />
            <button
              type="button"
              className="secondary usr-small-btn"
              onClick={() => void choosePhoto(null)}
            >
              Remove photo
            </button>
          </div>
        )}
        {generateError && (
          <div className="mgmt-error-banner" role="alert">
            <p style={{ margin: 0 }}>{generateError}</p>
          </div>
        )}
        {draft && (
          <p className="hold-note">
            Drafting again replaces the blueprint below, including your edits.
          </p>
        )}
        <div className="usr-inline">
          <button type="submit" disabled={generating}>
            {generating
              ? "Drafting your blueprint…"
              : draft
                ? "Draft a new blueprint"
                : "Draft my business blueprint"}
          </button>
          {generating && (
            <button
              type="button"
              className="secondary"
              onClick={cancelGenerate}
            >
              Cancel
            </button>
          )}
        </div>
        <p className="usr-muted" aria-live="polite" style={{ marginTop: 12 }}>
          {generating
            ? "The AI Business Architect is drafting your blueprint. This can take up to a minute."
            : ""}
        </p>
      </form>

      {draft && blueprint && (
        <section
          className="usr-card"
          aria-labelledby="ai-review-heading"
          aria-busy={submitting}
        >
          <h2 id="ai-review-heading">2. Review and edit your blueprint</h2>
          <div className="usr-inline" style={{ marginBottom: 12 }}>
            {engineBadge}
          </div>
          {blueprint.engine === "grounded" && (
            <p className="hold-note">
              Live AI drafting was unavailable, so AMARKAL Platform used its
              deterministic US starter template. Check every service, price, and
              hour before you approve.
            </p>
          )}
          {blueprint.rationale && (
            <p className="usr-muted">{blueprint.rationale}</p>
          )}

          {errors.length > 0 && (
            <div
              className="usr-errors"
              role="alert"
              tabIndex={-1}
              ref={errorSummaryRef}
            >
              <strong>
                Fix {errors.length} {errors.length === 1 ? "item" : "items"}{" "}
                before launching:
              </strong>
              <ul>
                {errors.map((e) => (
                  <li key={e.id}>
                    <a href={`#${e.id}`}>{e.message}</a>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <h3>Company and primary location</h3>
          <div className="usr-grid">
            <label>
              Business name
              <input
                {...fieldProps("ai-business-name")}
                type="text"
                maxLength={200}
                value={draft.business_name}
                onChange={(e) => {
                  const next = e.target.value;
                  update(
                    slugEdited
                      ? { business_name: next }
                      : { business_name: next, slug: slugify(next) },
                  );
                }}
              />
              {fieldError("ai-business-name")}
            </label>
            <label>
              URL slug (lowercase letters, digits, hyphens)
              <input
                {...fieldProps("ai-slug")}
                type="text"
                maxLength={63}
                value={draft.slug}
                onChange={(e) => {
                  setSlugEdited(true);
                  update({ slug: e.target.value.toLowerCase() });
                }}
              />
              {fieldError("ai-slug")}
            </label>
            <label>
              Primary location name
              <input
                {...fieldProps("ai-location")}
                type="text"
                maxLength={200}
                value={draft.location_name}
                onChange={(e) => update({ location_name: e.target.value })}
              />
              {fieldError("ai-location")}
            </label>
            <label>
              US time zone
              <select
                id="ai-timezone"
                value={draft.timezone}
                onChange={(e) => update({ timezone: e.target.value })}
              >
                {!timezones.some((z) => z.id === draft.timezone) && (
                  <option value={draft.timezone} disabled>
                    Choose a US time zone
                  </option>
                )}
                {timezones.map((z) => (
                  <option key={z.id} value={z.id}>
                    {z.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <fieldset className="usr-checks">
            <legend>Business formats</legend>
            {Object.entries(FORMAT_LABELS).map(([id, label]) => (
              <label key={id} className="usr-check">
                <input
                  type="checkbox"
                  id={`ai-format-${id}`}
                  checked={draft.business_formats.includes(id)}
                  onChange={() =>
                    update({
                      business_formats: draft.business_formats.includes(id)
                        ? draft.business_formats.filter((f) => f !== id)
                        : [...draft.business_formats, id],
                    })
                  }
                />
                {label}
              </label>
            ))}
          </fieldset>
          {fieldError("ai-format-b2c")}

          <h3>Industries</h3>
          <ul
            className="usr-inline"
            style={{ listStyle: "none", padding: 0, margin: "0 0 12px" }}
            aria-label="Selected industries"
          >
            {draft.industry_ids.map((id) => {
              const p = presetById.get(id);
              const name = p ? `#${id} ${p.name}` : `Industry #${id}`;
              return (
                <li key={id} className="usr-chip">
                  {name}
                  <button
                    type="button"
                    aria-label={`Remove ${name}`}
                    onClick={() =>
                      update({
                        industry_ids: draft.industry_ids.filter(
                          (x) => x !== id,
                        ),
                      })
                    }
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="usr-inline" style={{ alignItems: "flex-end" }}>
            <label style={{ flex: "1 1 260px", marginBottom: 0 }}>
              Add an industry
              <select
                {...fieldProps("ai-industry-add")}
                value={addIndustry}
                onChange={(e) => setAddIndustry(e.target.value)}
              >
                <option value="">Choose one of the 39 industries…</option>
                {presets
                  .filter((p) => !draft.industry_ids.includes(p.id))
                  .map((p) => (
                    <option key={p.id} value={String(p.id)}>
                      #{p.id} {p.name}
                    </option>
                  ))}
              </select>
            </label>
            <button
              type="button"
              className="secondary"
              disabled={!addIndustry}
              onClick={() => {
                const id = Number(addIndustry);
                if (!id || draft.industry_ids.includes(id)) return;
                update({
                  industry_ids: [...draft.industry_ids, id].sort(
                    (a, b) => a - b,
                  ),
                });
                setAddIndustry("");
              }}
            >
              Add industry
            </button>
          </div>
          {fieldError("ai-industry-add")}
          <p className="usr-muted" style={{ marginTop: 12 }}>
            <strong>Modules activated on launch:</strong> organization,
            users_access
            {modulePreview.enableable.length
              ? `, ${modulePreview.enableable.join(", ")}`
              : ""}
          </p>
          {modulePreview.pending.length > 0 && (
            <p className="hold-note">
              Specialized modules awaiting acceptance (not enabled
              automatically): {modulePreview.pending.join(", ")}
            </p>
          )}

          <h3>Services and USD prices</h3>
          <div className="usr-rows">
            {draft.services.map((s, i) => (
              <div key={s.key} className="usr-row">
                <label>
                  Service {i + 1} name
                  <input
                    {...fieldProps(`ai-svc-name-${s.key}`)}
                    type="text"
                    maxLength={L.serviceNameMax}
                    value={s.name}
                    onChange={(e) =>
                      update({
                        services: draft.services.map((x) =>
                          x.key === s.key ? { ...x, name: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  {fieldError(`ai-svc-name-${s.key}`)}
                </label>
                <label>
                  Duration (minutes)
                  <input
                    {...fieldProps(`ai-svc-duration-${s.key}`)}
                    type="number"
                    inputMode="numeric"
                    min={L.durationMin}
                    max={L.durationMax}
                    step={5}
                    value={s.duration}
                    onChange={(e) =>
                      update({
                        services: draft.services.map((x) =>
                          x.key === s.key
                            ? { ...x, duration: e.target.value }
                            : x,
                        ),
                      })
                    }
                  />
                  {fieldError(`ai-svc-duration-${s.key}`)}
                </label>
                <label>
                  Price (USD)
                  <input
                    {...fieldProps(`ai-svc-price-${s.key}`)}
                    type="text"
                    inputMode="decimal"
                    value={s.price}
                    onChange={(e) =>
                      update({
                        services: draft.services.map((x) =>
                          x.key === s.key ? { ...x, price: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  {fieldError(`ai-svc-price-${s.key}`) ??
                    (priceToCents(s.price) !== null ? (
                      <span className="usr-muted">
                        {usd.format((priceToCents(s.price) ?? 0) / 100)}
                      </span>
                    ) : null)}
                </label>
                <button
                  type="button"
                  className="usr-danger usr-small-btn"
                  aria-label={`Remove service ${i + 1}${s.name ? `: ${s.name}` : ""}`}
                  onClick={() =>
                    update({
                      services: draft.services.filter((x) => x.key !== s.key),
                    })
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            id="ai-add-service"
            className="secondary"
            disabled={draft.services.length >= L.servicesMax}
            onClick={() =>
              update({
                services: [
                  ...draft.services,
                  { key: rowKey(), name: "", duration: "60", price: "0.00" },
                ],
              })
            }
          >
            Add service
          </button>
          {fieldError("ai-add-service")}
          <p className="usr-muted">
            Up to {L.servicesMax} services. Each becomes a published, bookable
            service with a standard variant.
          </p>

          <h3>Resources</h3>
          <div className="usr-rows">
            {draft.resources.map((r, i) => (
              <div key={r.key} className="usr-row usr-row-2">
                <label>
                  Resource {i + 1} name
                  <input
                    {...fieldProps(`ai-res-name-${r.key}`)}
                    type="text"
                    maxLength={L.resourceNameMax}
                    value={r.name}
                    onChange={(e) =>
                      update({
                        resources: draft.resources.map((x) =>
                          x.key === r.key ? { ...x, name: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  {fieldError(`ai-res-name-${r.key}`)}
                </label>
                <label>
                  Kind
                  <select
                    value={r.kind}
                    onChange={(e) =>
                      update({
                        resources: draft.resources.map((x) =>
                          x.key === r.key
                            ? { ...x, kind: e.target.value as ResourceKind }
                            : x,
                        ),
                      })
                    }
                  >
                    {RESOURCE_KINDS.map((k) => (
                      <option key={k} value={k}>
                        {RESOURCE_KIND_LABELS[k]}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="usr-danger usr-small-btn"
                  aria-label={`Remove resource ${i + 1}${r.name ? `: ${r.name}` : ""}`}
                  onClick={() =>
                    update({
                      resources: draft.resources.filter((x) => x.key !== r.key),
                    })
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            id="ai-add-resource"
            className="secondary"
            disabled={draft.resources.length >= L.resourcesMax}
            onClick={() =>
              update({
                resources: [
                  ...draft.resources,
                  { key: rowKey(), name: "", kind: "artist" },
                ],
              })
            }
          >
            Add resource
          </button>
          {fieldError("ai-add-resource")}
          <p className="usr-muted">
            Up to {L.resourcesMax} resources. Every resource can perform every
            starter service and follows the weekly hours below.
          </p>

          <h3>Weekly hours</h3>
          <p className="usr-muted">
            Times use the {draft.timezone} time zone. Choose 12:00 AM as the
            closing time to stay open until midnight.
          </p>
          <div className="usr-table-wrap" style={{ marginBottom: 16 }}>
            {draft.hours.map((h) => {
              const label =
                WEEKDAYS.find((w) => w.index === h.weekday)?.label ??
                `Day ${h.weekday}`;
              const patch = (p: Partial<HoursRow>) =>
                update({
                  hours: draft.hours.map((x) =>
                    x.weekday === h.weekday ? { ...x, ...p } : x,
                  ),
                });
              return (
                <div key={h.weekday} className="usr-hours-row">
                  <label className="usr-check" style={{ margin: 0 }}>
                    <input
                      type="checkbox"
                      id={`ai-hours-${h.weekday}-open`}
                      checked={h.open}
                      onChange={(e) => patch({ open: e.target.checked })}
                    />
                    {label}
                  </label>
                  <label>
                    Opens
                    <input
                      {...fieldProps(`ai-hours-${h.weekday}-opens`)}
                      type="time"
                      step={1800}
                      disabled={!h.open}
                      value={h.opens}
                      aria-label={`${label} opening time`}
                      onChange={(e) => patch({ opens: e.target.value })}
                    />
                  </label>
                  <label>
                    Closes
                    <input
                      type="time"
                      step={1800}
                      disabled={!h.open}
                      value={h.closes}
                      aria-label={`${label} closing time`}
                      onChange={(e) => patch({ closes: e.target.value })}
                    />
                  </label>
                  {fieldError(`ai-hours-${h.weekday}-opens`)}
                </div>
              );
            })}
          </div>
          {fieldError("ai-hours-1-open")}

          <h3>Cancellation policy</h3>
          <label>
            Cancellation summary shown to customers
            <textarea
              {...fieldProps("ai-cancellation")}
              className="usr-textarea"
              style={{ minHeight: 80 }}
              maxLength={L.cancellationMax}
              value={draft.cancellation}
              onChange={(e) => update({ cancellation: e.target.value })}
            />
            <span className="usr-muted">
              {draft.cancellation.trim().length} / {L.cancellationMax}{" "}
              characters
            </span>
            {fieldError("ai-cancellation")}
          </label>

          {blueprint.recommended_connectors.length > 0 && (
            <>
              <h3>Recommended connections</h3>
              <p className="usr-muted">
                These are suggestions only. Nothing is connected automatically;
                after launch you can connect them in{" "}
                <Link href="/integrations/">AMARKAL App Hub</Link>.
              </p>
              <ul>
                {blueprint.recommended_connectors.map((id) => (
                  <li key={id}>{CONNECTOR_NAMES[id] ?? id}</li>
                ))}
              </ul>
            </>
          )}

          <h3>Approve and launch</h3>
          <label className="usr-check">
            <input
              {...fieldProps("ai-approve")}
              type="checkbox"
              checked={approved}
              onChange={(e) => setApproved(e.target.checked)}
            />
            I reviewed this AI-drafted blueprint and approve creating this
            business with the services, prices, resources, hours, and policy
            above.
          </label>
          {fieldError("ai-approve")}
          <p style={{ fontSize: "0.85rem" }}>
            By creating a workspace, you agree to the{" "}
            <Link href="/legal/terms/">Terms of Service</Link> and{" "}
            <Link href="/legal/privacy/">Privacy Policy</Link>.
          </p>
          {submitError && (
            <div className="mgmt-error-banner" role="alert">
              <p style={{ margin: 0 }}>{submitError}</p>
            </div>
          )}
          {!signedIn && (
            <p className="hold-note">
              You are previewing as a guest. Your edited blueprint is saved
              automatically — create a free account on the final step to launch
              your live workspace in one click.
            </p>
          )}
          <button
            type="button"
            disabled={submitting}
            onClick={() => void launch()}
          >
            {submitting
              ? "Launching your business…"
              : signedIn
                ? "Approve & Launch Business"
                : "Create free account & Launch Business"}
          </button>
        </section>
      )}
    </div>
  );
}
