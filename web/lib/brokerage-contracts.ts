import { z } from "zod";
import { invoiceSchema, obligationSchema } from "./financial-contracts";

// N6 (package N): strict response contracts of the brokerage routes (N1-N5) and the rule of the board.
const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
const day = z.iso.date();
const decimal = z.string().regex(/^(0|[1-9][0-9]*)(\.[0-9]{1,3})?$/);
const money = z.string().regex(/^-?(0|[1-9][0-9]*)(\.[0-9]{1,3})?$/);
const revision = z.number().int().positive();
const source = z.string().regex(/^[a-z][a-z0-9_.-]{0,31}$/);
const unique = <T>(items: T[], key: (item: T) => string) =>
  new Set(items.map(key)).size === items.length;

const authorityVersion = z.strictObject({
  revision,
  jurisdiction: z.string().regex(/^[A-Z]{2}$/),
  authority_number: z.string().min(1).max(32),
  bond_reference: z.string().min(1).max(64),
  status: z.enum(["active", "withdrawn"]),
  effective_from: day,
  expires_on: day.nullable(),
  source,
  checked_on: day,
  created_at: instant,
});
export const authoritySchema = z.strictObject({
  current: authorityVersion.nullable(),
  versions: z.array(authorityVersion).max(1000),
});

const profileVersion = z.strictObject({
  revision,
  jurisdiction: z.string().regex(/^[A-Z]{2}$/),
  authority_number: z.string().min(1).max(32).nullable(),
  liability_expires_on: day.nullable(),
  cargo_expires_on: day.nullable(),
  safety_rating: z.enum([
    "satisfactory",
    "conditional",
    "unsatisfactory",
    "unrated",
  ]),
  source,
  checked_on: day,
  created_at: instant,
});
export const carrierProfileSchema = z.strictObject({
  counterparty_id: id,
  current: profileVersion.nullable(),
  versions: z.array(profileVersion).max(1000),
});

export const eligibilitySchema = z.strictObject({
  on: day,
  eligible: z.boolean(),
  reasons: z.array(z.string().min(1).max(64)).max(20),
});

const answerSource = z.enum([
  "email",
  "phone",
  "load_board",
  "other",
  "platform",
]);
export const tenderSchema = z.strictObject({
  tender_id: id,
  trip_id: id,
  legs: z.array(z.number().int().min(1).max(100)).min(1).max(100),
  counterparty_id: id,
  currency: z.string().regex(/^[A-Z]{3}$/),
  basis: z.enum(["fixed", "per_mile"]),
  amount: decimal,
  terms: z.string().min(1).max(2000),
  offered_at: instant,
  expires_at: instant,
  state: z.enum(["offered", "accepted", "declined", "withdrawn", "expired"]),
  answers: z
    .array(
      z.strictObject({
        kind: z.enum(["accepted", "declined", "withdrawn"]),
        source: answerSource,
        occurred_at: instant,
      }),
    )
    .max(10),
});
export const tenderListSchema = z
  .strictObject({ items: z.array(tenderSchema).max(1000) })
  .refine((v) => unique(v.items, (x) => x.tender_id));

const confirmationVersion = z.strictObject({
  revision,
  basis: z.enum(["fixed", "per_mile"]),
  amount: decimal,
  terms: z.string().min(1).max(2000),
  document_id: id.nullable(),
  proposed_at: instant,
  state: z.enum(["proposed", "agreed", "declined"]),
  answer: z
    .strictObject({
      kind: z.enum(["agreed", "declined"]),
      source: answerSource,
      occurred_at: instant,
    })
    .nullable(),
});
export const confirmationSchema = z.strictObject({
  tender_id: id,
  currency: z.string().regex(/^[A-Z]{3}$/),
  in_force: confirmationVersion.nullable(),
  versions: z.array(confirmationVersion).max(1000),
});

export const carrierPaySchema = z.strictObject({
  tender_id: id,
  revision,
  miles: z
    .string()
    .regex(/^[0-9]+\.[0-9]$/)
    .nullable(),
  book_id: id,
  document_id: id,
  accrual: invoiceSchema,
  obligation: obligationSchema.nullable(),
});

const marginLine = z.strictObject({ tender_id: id, amount: money });
export const marginSchema = z.strictObject({
  order_id: id,
  currency: z
    .string()
    .regex(/^[A-Z]{3}$/)
    .nullable(),
  revenue: money.nullable(),
  carrier_cost: money.nullable(),
  margin: money.nullable(),
  tenders: z.array(marginLine).max(1000),
  shared: z.array(marginLine).max(1000),
  currencies_differ: z.boolean(),
});

export type Authority = z.infer<typeof authoritySchema>;
export type CarrierProfile = z.infer<typeof carrierProfileSchema>;
export type Eligibility = z.infer<typeof eligibilitySchema>;
export type Tender = z.infer<typeof tenderSchema>;
export type TenderList = z.infer<typeof tenderListSchema>;
export type Confirmation = z.infer<typeof confirmationSchema>;
export type CarrierPay = z.infer<typeof carrierPaySchema>;
export type Margin = z.infer<typeof marginSchema>;

/** The legs of a trip no accepted tender covers: what the board still has to cover. */
export function uncoveredLegs(
  legs: { position: number }[],
  tenders: Pick<Tender, "legs" | "state">[],
): number[] {
  const covered = new Set(
    tenders.filter((t) => t.state === "accepted").flatMap((t) => t.legs),
  );
  return legs.map((l) => l.position).filter((p) => !covered.has(p));
}

const REASONS: Record<string, string> = {
  no_authority: "no broker authority is recorded",
  withdrawn: "the authority is withdrawn",
  not_effective: "the authority is not yet effective",
  expired: "the authority has expired",
  stale_check: "the facts were checked too long ago",
  no_profile: "no carrier profile is recorded",
  unknown_authority: "the carrier's authority is unknown",
  unsatisfactory: "the safety rating is unsatisfactory",
};

/** A refusal or eligibility reason code said in words. */
export function reasonText(code: string): string {
  if (REASONS[code]) return REASONS[code];
  const insurance = /^(liability|cargo)_(expired|unknown)$/.exec(code);
  if (insurance) return `${insurance[1]} insurance ${insurance[2]}`;
  return code.replaceAll("_", " ");
}

const U = "[0-9a-f-]{36}";
const path = (p: string) => new RegExp(`^\\/transport${p}$`, "i");

/** The response contract of a brokerage route under /v1/businesses/{id}, or null. */
export function brokerageResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  const read = method === "GET";
  if (path("\\/broker-authority").test(suffix) && (read || method === "PUT"))
    return authoritySchema;
  if (
    (path("\\/broker-authority\\/eligibility").test(suffix) ||
      path(`\\/carriers\\/${U}\\/eligibility`).test(suffix)) &&
    read
  )
    return eligibilitySchema;
  if (
    path(`\\/carriers\\/${U}\\/profile`).test(suffix) &&
    (read || method === "PUT")
  )
    return carrierProfileSchema;
  if (path(`\\/trips\\/${U}\\/tenders`).test(suffix) && read)
    return tenderListSchema;
  if (
    (path(`\\/tenders\\/${U}`).test(suffix) && (read || method === "PUT")) ||
    (path(`\\/tenders\\/${U}\\/answers`).test(suffix) && method === "POST")
  )
    return tenderSchema;
  if (
    (path(`\\/tenders\\/${U}\\/rate-confirmation`).test(suffix) &&
      (read || method === "PUT")) ||
    (path(`\\/tenders\\/${U}\\/rate-confirmation\\/[0-9]{1,10}\\/answers`).test(
      suffix,
    ) &&
      method === "POST")
  )
    return confirmationSchema;
  if (
    path(`\\/tenders\\/${U}\\/accrual`).test(suffix) &&
    (read || method === "POST")
  )
    return carrierPaySchema;
  if (path(`\\/orders\\/${U}\\/margin`).test(suffix) && read)
    return marginSchema;
  return null;
}
