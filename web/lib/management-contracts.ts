import { z } from "zod";
import { ledgerResponseSchema } from "./ledger-contracts";
import { inventoryResponseSchema } from "./inventory-contracts";
import {
  creditSchema,
  financialResponseSchema,
  invoiceSchema,
  obligationSchema,
} from "./financial-contracts";
import { admissionResponseSchema } from "./admission-contracts";
import { counterpartyResponseSchema } from "./counterparty-contracts";
import { documentResponseSchema } from "./document-contracts";
import { agreementResponseSchema } from "./agreement-contracts";
import { reservationResponseSchema } from "./reservation-contracts";
import { workforceResponseSchema } from "./workforce-contracts";
import { availabilitySchema } from "./contracts";
import {
  businessSchema,
  businessProfileSchema,
  industryCatalogSchema,
} from "./business-contracts";
import {
  legalEntityListSchema,
  legalEntitySchema,
} from "./legal-entity-contracts";
import { departmentListSchema, departmentSchema } from "./department-contracts";
import {
  delegatedBusinessSchema,
  delegationListSchema,
  delegationSchema,
} from "./delegation-contracts";
import {
  businessGroupListSchema,
  businessGroupSchema,
} from "./group-contracts";
import {
  configurationPreviewSchema,
  configurationSchema,
  configurationVersionListSchema,
  configurationVersionSchema,
  moduleCatalogSchema,
  readinessRegistrySchema,
} from "./configuration-contracts";
const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
const count = z.number().int().nonnegative();
const record = z.record(z.string(), z.unknown());
const booking = z.object({
  booking_id: id,
  status: z.enum(["HOLD", "CONFIRMED", "CANCELLED", "EXPIRED"]),
  location_id: id,
  location_timezone: z.string().min(1),
  resource_id: id,
  resource_name: z.string(),
  variant_id: id,
  service_name: z.string(),
  variant_name: z.string(),
  starts_at: instant,
  ends_at: instant,
  total_cents: count,
  currency: z.string().length(3),
  customer_name: z.string().nullable(),
  customer_email: z.string().nullable(),
  customer_phone: z.string().nullable(),
  created_at: instant,
  created_by: z.string(),
});
const activity = z.object({
  id,
  actor: z.string(),
  action: z.string(),
  target_type: z.string(),
  target_id: z.string(),
  details: record,
  occurred_at: instant,
});
// L1/L7a: the ordered stages of a service; empty for a service of one stage.
export const stageKinds = ["active", "processing", "finish"] as const;
export const stageResources = [
  "specialist",
  "chair",
  "room",
  "equipment",
] as const;
const stage = z.strictObject({
  position: z.number().int().min(1).max(10),
  kind: z.enum(stageKinds),
  minutes: z.number().int().min(1).max(720),
  resources: z.array(z.enum(stageResources)).max(4),
});
const service = z.object({
  id,
  service_id: id,
  code: z.string(),
  name: z.string(),
  status: z.string(),
  price_cents: count,
  currency: z.string().length(3),
  booking_duration_minutes: count.nullable(),
  is_bookable: z.boolean(),
  revision: z.number().int().positive(),
  stages: z.array(stage).max(10).default([]),
});
// L3/L7b1: a visit's completion — planned and actual materials, and its write-off.
const quantityText = z.string().regex(/^(0|[1-9][0-9]{0,14})(\.[0-9]{1,3})?$/);
const completion = z.strictObject({
  booking_id: id,
  location_id: id,
  completed_at: z.iso.datetime({ offset: true }),
  completed_by: id,
  materials: z
    .array(
      z.strictObject({
        item_id: id,
        planned: quantityText,
        actual: quantityText,
      }),
    )
    .max(60),
  stock_document_id: id.nullable(),
  consumption_posted_at: z.iso.datetime({ offset: true }).nullable(),
});
// L4/L5/L7b2a: the visit invoice, the visit commission and a specialist's plan.
const money = z.string().regex(/^(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?$/);
const visitInvoice = z.strictObject({
  booking_id: id,
  book_id: id,
  document_id: id,
  invoice: invoiceSchema,
  obligation: obligationSchema.nullable(),
});
const visitCommission = z.strictObject({
  booking_id: id,
  book_id: id,
  document_id: id,
  accrual: invoiceSchema,
  tips_account_id: id.nullable(),
  tips: money,
});
const commissionPlan = z.strictObject({
  resource_id: id,
  counterparty_id: id,
  currency: z.string().regex(/^[A-Z]{3}$/),
  revision: z.number().int().positive(),
  updated_at: z.iso.datetime({ offset: true }),
  rules: z
    .array(
      z
        .strictObject({
          service_id: id.nullable(),
          percent: z
            .string()
            .regex(/^(0|[1-9][0-9]{0,2})\.[0-9]{2}$/)
            .nullable(),
          amount: money.nullable(),
        })
        .refine((rule) => (rule.percent === null) !== (rule.amount === null)),
    )
    .max(50),
});
// L6/L7b2b: a prepaid balance — a package of one service's units or a certificate's value.
const prepaid = z
  .strictObject({
    prepaid_id: id,
    kind: z.enum(["package", "certificate"]),
    counterparty_id: id,
    variant_id: id.nullable(),
    units: z.number().int().min(1).max(1000).nullable(),
    remaining_units: z.number().int().min(0).max(1000).nullable(),
    value: money,
    remaining_value: money,
    currency: z.string().regex(/^[A-Z]{3}$/),
    usable: z.boolean(),
    sale: invoiceSchema,
  })
  .refine(
    (v) =>
      (v.kind === "package") === (v.variant_id !== null && v.units !== null) &&
      (v.units === null) === (v.remaining_units === null) &&
      (v.units === null || (v.remaining_units ?? 0) <= v.units),
  );
const prepaidList = z
  .strictObject({
    items: z.array(prepaid).max(50),
    next_cursor: id.nullable(),
  })
  .refine(
    (v) => new Set(v.items.map((x) => x.prepaid_id)).size === v.items.length,
  );
const redemption = z.strictObject({
  booking_id: id,
  prepaid_id: id,
  units: z.union([z.literal(0), z.literal(1)]),
  amount: money,
  credit: creditSchema,
  prepaid,
});
// L3/L7a: the materials one service uses, in the material's own unit.
const recipe = z.strictObject({
  owner_id: id,
  owner_revision: z.number().int().positive(),
  lines: z
    .array(
      z.strictObject({
        item_id: id,
        quantity: z.string().regex(/^(0|[1-9][0-9]{0,14})(\.[0-9]{1,3})?$/),
      }),
    )
    .max(20),
});
const staff = z.object({
  id,
  location_id: id,
  kind: z.string(),
  display_name: z.string(),
  is_active: z.boolean(),
});
const hours = z.object({
  id,
  weekday: z.number().int().min(1).max(7),
  opens_minute: count,
  closes_minute: count,
});
const schedule = z.object({
  resource_id: id,
  display_name: z.string(),
  is_active: z.boolean(),
  location_id: id,
  hours: z.array(hours),
  service_ids: z.array(id),
});
const client = z.object({
  customer_name: z.string(),
  email: z.string(),
  phone: z.string(),
  total_bookings: count,
  confirmed_bookings: count,
  last_booking_at: instant.nullable(),
});
const me = z.object({
  user_id: id,
  display_name: z.string(),
  platform_roles: z.array(z.string()),
  memberships: z.array(
    z.object({
      salon_id: id,
      salon_name: z.string().nullable(),
      role: z.string(),
      status: z.string(),
      location_id: id.nullable(),
    }),
  ),
  delegations: z.array(delegatedBusinessSchema),
});
const member = z.strictObject({
  membership_id: id,
  user_id: id,
  display_name: z.string().nullable(),
  role: z.string(),
  status: z.string(),
  location_id: id.nullable(),
});
const overview = z.object({
  salon_id: id,
  salon_name: z.string(),
  status: z.string(),
  booking_state: z.string(),
  stats: z.object({
    today_bookings_count: count,
    confirmed_bookings_count: count,
    cancelled_bookings_count: count,
    today_revenue_cents: count,
    today_booked_value: z.array(
      z.object({ currency: z.string().length(3), amount_cents: count }),
    ),
    active_staff_count: count,
    total_services_count: count,
  }),
  today_bookings: z.array(booking),
  recent_activity: z.array(activity),
});
const settings = z.object({
  salon_id: id,
  slug: z.string(),
  display_name: z.string(),
  status: z.string(),
  booking_state: z.string(),
  locations: z.array(z.object({ id, name: z.string(), timezone: z.string() })),
  business_hours: z.array(hours.extend({ location_id: id })),
  policies: z.object({
    booking_rules: record.optional(),
    cancellation_policy: record.optional(),
    deposit_policy: record.optional(),
  }),
  fact_confirmations: z.array(
    z.object({
      fact_key: z.string(),
      status: z.string(),
      source_note: z.string().nullable(),
      recorded_by: z.string(),
      recorded_at: instant,
    }),
  ),
  embed_origins: z.array(
    z.object({
      id,
      origin: z.string(),
      status: z.string(),
      updated_at: instant,
    }),
  ),
});
// API ReadinessView (api/setup.py): every required fact with its status.
export const readinessSchema = z.strictObject({
  salon_id: id,
  ready: z.boolean(),
  booking_state: z.enum(["not_live", "live"]),
  items: z.array(
    z.strictObject({
      fact: z.string(),
      status: z.enum(["confirmed", "unconfirmed", "missing"]),
      detail: z.string(),
    }),
  ),
});
export type Readiness = z.infer<typeof readinessSchema>;

/** A response is validated before management views receive any external fields. */
export function managementResponseSchema(
  path: string,
  method: string,
): z.ZodType {
  const clean = path.split("?")[0] ?? "";
  if (clean === "/v1/me") return me;
  const business = clean.match(/^\/v1\/businesses\/[0-9a-f-]{36}(.*)$/i);
  if (business) {
    const financial = financialResponseSchema(business[1] ?? "", method);
    if (financial) return financial;
    const admission = admissionResponseSchema(business[1] ?? "", method);
    if (admission) return admission;
    const ledger = ledgerResponseSchema(business[1] ?? "", method);
    if (ledger) return ledger;
    const inventory = inventoryResponseSchema(business[1] ?? "", method);
    if (inventory) return inventory;
    const counterparties = counterpartyResponseSchema(
      business[1] ?? "",
      method,
    );
    if (counterparties) return counterparties;
    const documents = documentResponseSchema(business[1] ?? "", method);
    if (documents) return documents;
    const agreements = agreementResponseSchema(business[1] ?? "", method);
    if (agreements) return agreements;
    const reservations = reservationResponseSchema(business[1] ?? "", method);
    if (reservations) return reservations;
    const workforce = workforceResponseSchema(business[1] ?? "", method);
    if (workforce) return workforce;
    if (business[1] === "" && method === "GET") return businessSchema;
    if (business[1] === "/industry-catalog" && method === "GET")
      return industryCatalogSchema;
    if (business[1] === "/profile" && method === "PUT")
      return businessProfileSchema;
    if (business[1] === "/legal-entities" && method === "GET")
      return legalEntityListSchema;
    if (
      /^\/legal-entities\/[0-9a-f-]{36}$/i.test(business[1] ?? "") &&
      (method === "GET" || method === "PUT")
    )
      return legalEntitySchema;
    if (business[1] === "/departments" && method === "GET")
      return departmentListSchema;
    if (
      /^\/departments\/[0-9a-f-]{36}$/i.test(business[1] ?? "") &&
      (method === "GET" || method === "PUT")
    )
      return departmentSchema;
    if (business[1] === "/delegations" && method === "GET")
      return delegationListSchema;
    const grant =
      /^\/delegations\/[0-9a-f-]{36}(\/(accept|decline|revoke|delegates))?$/i.exec(
        business[1] ?? "",
      );
    if (
      grant &&
      ((!grant[1] && (method === "GET" || method === "PUT")) ||
        (grant[2] === "delegates" && method === "PUT") ||
        (grant[2] && grant[2] !== "delegates" && method === "POST"))
    )
      return delegationSchema;
    if (business[1] === "/groups" && method === "GET")
      return businessGroupListSchema;
    const group =
      /^\/groups\/[0-9a-f-]{36}(\/(accept|decline|leave)|\/members\/[0-9a-f-]{36}(\/remove)?)?$/i.exec(
        business[1] ?? "",
      );
    if (
      group &&
      ((!group[1] && (method === "GET" || method === "PUT")) ||
        (group[2] && method === "POST") ||
        (group[1]?.startsWith("/members/") &&
          (group[3] ? method === "POST" : method === "PUT")))
    )
      return businessGroupSchema;
    if (method === "GET") {
      if (business[1] === "/module-catalog") return moduleCatalogSchema;
      if (business[1] === "/readiness-registry") return readinessRegistrySchema;
      if (business[1] === "/configuration") return configurationSchema;
      if (business[1] === "/configuration/versions")
        return configurationVersionListSchema;
      if (/^\/configuration\/versions\/[1-9]\d{0,9}$/.test(business[1] ?? ""))
        return configurationVersionSchema;
      if (
        /^\/configuration\/versions\/[1-9]\d{0,9}\/preview$/.test(
          business[1] ?? "",
        )
      )
        return configurationPreviewSchema;
    }
    if (business[1] === "/configuration/draft" && method === "PUT")
      return configurationVersionSchema;
    if (
      /^\/configuration\/versions\/[1-9]\d{0,9}\/(validate|publish)$/.test(
        business[1] ?? "",
      ) &&
      method === "POST"
    )
      return configurationVersionSchema;
    throw new Error("Unrecognized business response contract");
  }
  const suffix = clean.replace(/^\/v1\/salons\/[0-9a-f-]{36}/i, "");
  if (suffix === "/availability") return availabilitySchema;
  if (suffix === "/workspace")
    return z.object({
      salon_id: id,
      location_id: id.nullable(),
      locations: z.array(
        z.object({ id, name: z.string(), timezone: z.string() }),
      ),
      business_hours: z.array(hours.extend({ location_id: id })),
      booking_enabled: z.boolean(),
    });
  if (suffix === "/overview") return overview;
  if (suffix === "/settings") return settings;
  if (suffix === "/activity") return z.array(activity);
  if (suffix === "/clients") return z.array(client);
  if (suffix === "/clients/history") return z.array(booking);
  if (suffix === "/bookings")
    return method === "GET" ? z.array(booking) : booking;
  if (
    /^\/bookings\/[0-9a-f-]{36}\/(complete|completion|consumption)$/i.test(
      suffix,
    )
  )
    return completion;
  if (/^\/bookings\/[0-9a-f-]{36}\/invoice$/i.test(suffix)) return visitInvoice;
  if (/^\/bookings\/[0-9a-f-]{36}\/commission$/i.test(suffix))
    return visitCommission;
  if (/^\/bookings\/[0-9a-f-]{36}\/redeem$/i.test(suffix)) return redemption;
  if (/^\/bookings\//.test(suffix)) return booking;
  if (suffix === "/prepaid") return method === "GET" ? prepaidList : prepaid;
  if (suffix === "/services")
    return method === "GET" ? z.array(service) : service;
  if (/^\/services\/[0-9a-f-]{36}\/materials$/i.test(suffix)) return recipe;
  if (/^\/services\//.test(suffix)) return service;
  if (suffix === "/members" && method === "GET") return z.array(member);
  if (suffix === "/staff") return method === "GET" ? z.array(staff) : staff;
  if (/^\/staff\/[^/]+\/(schedule|services)$/.test(suffix)) return schedule;
  if (/^\/staff\/[0-9a-f-]{36}\/commission$/i.test(suffix))
    return commissionPlan;
  if (/^\/staff\//.test(suffix)) return staff;
  if (suffix === "/readiness" && method === "GET") return readinessSchema;
  if (
    (suffix === "/business-hours" ||
      suffix === "/policies" ||
      /^\/facts\//.test(suffix)) &&
    method === "PUT"
  )
    return readinessSchema;
  throw new Error("Unrecognized management response contract");
}
