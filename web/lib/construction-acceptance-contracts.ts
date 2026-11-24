import { z } from "zod";

const id = z.uuid();
const day = z.iso
  .date()
  .refine((date) => date >= "2000-01-01" && date <= "2100-12-31");
const instant = z.iso.datetime({ offset: true });
const number = z.int().positive();
const source = z.enum(["paper", "email", "platform"]);
const phase = z.string().min(1).max(64);
const note = z.string().min(1).max(1000).nullable();
const releaseSchema = z.strictObject({
  released_on: day,
  amount_minor: z.int().positive(),
  note,
  recorded_at: instant,
});
const acceptanceSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: id,
    number,
    scope: z.enum(["phase", "final"]),
    phase: phase.nullable(),
    accepted_on: day,
    signatory: z.string().min(1).max(200),
    source,
    note,
    warranty_starts_on: day.nullable(),
    warranty_ends_on: day.nullable(),
    recorded_at: instant,
    release: releaseSchema.nullable(),
  })
  .refine(
    (v) =>
      (!v.release || v.release.released_on >= v.accepted_on) &&
      (v.scope === "phase"
        ? v.phase !== null &&
          v.warranty_starts_on === null &&
          v.warranty_ends_on === null
        : v.phase === null &&
          v.warranty_starts_on === v.accepted_on &&
          v.warranty_ends_on !== null &&
          v.warranty_ends_on > v.accepted_on),
  );

const phaseAcceptanceSchema = z.strictObject({
  phase,
  finished: z.boolean(),
  open_items: z.int().nonnegative(),
  billed_in_full: z.boolean(),
  // Downward adjustments can make a phase's net retained amount negative.
  retained_minor: z.int(),
  acceptance: number.nullable(),
  released_minor: z.int().positive().nullable(),
});

const acceptanceListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: id,
    currency: z.string().regex(/^[A-Z]{3}$/),
    retained_minor: z.int().nonnegative(),
    released_minor: z.int().nonnegative(),
    held_minor: z.int().nonnegative(),
    phases: z.array(phaseAcceptanceSchema),
    final: acceptanceSchema.nullable(),
    items: z.array(acceptanceSchema),
  })
  .refine((v) => {
    const byPhase = new Map(
      v.items.flatMap((item) =>
        item.phase === null ? [] : [[item.phase, item] as const],
      ),
    );
    const final = v.items.find((item) => item.scope === "final");
    return (
      v.retained_minor - v.released_minor === v.held_minor &&
      v.items.every(
        (item, index) =>
          item.project_id === v.project_id && item.number === index + 1,
      ) &&
      v.items.length === byPhase.size + Number(final !== undefined) &&
      (!final || v.items.at(-1) === final) &&
      (v.final === null
        ? final === undefined
        : v.final.scope === "final" &&
          v.final.number === final?.number &&
          v.final.project_id === v.project_id) &&
      new Set(v.phases.map((item) => item.phase)).size === v.phases.length &&
      v.phases.every((item) => {
        const acceptance = byPhase.get(item.phase);
        return (
          item.acceptance === (acceptance?.number ?? null) &&
          item.released_minor === (acceptance?.release?.amount_minor ?? null)
        );
      })
    );
  });

export type Acceptance = z.infer<typeof acceptanceSchema>;
export type AcceptanceList = z.infer<typeof acceptanceListSchema>;
export type AcceptanceBody = {
  schema_version: 1;
  accepted_on: string;
  signatory: string;
  source: Exclude<z.infer<typeof source>, "platform">;
  note: string | null;
} & (
  | { scope: "phase"; phase: string; warranty_ends_on: null }
  | { scope: "final"; phase: null; warranty_ends_on: string }
);
export type AcceptanceReleaseBody = {
  schema_version: 1;
  released_on: string;
  note: string | null;
};

const route =
  /^\/construction\/projects\/([0-9a-f-]{36})\/acceptances(?:\/(\d+)(\/release)?)?$/i;

export function constructionAcceptanceResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  const match = route.exec(suffix);
  if (!match) return null;
  const [, projectId, number, release] = match;
  if (!number && method === "GET")
    return acceptanceListSchema.refine((v) => v.project_id === projectId);
  if (method === (!number || release ? "POST" : "GET"))
    return acceptanceSchema.refine(
      (v) =>
        v.project_id === projectId &&
        (!number || v.number === Number(number)) &&
        (!release || v.release !== null),
    );
  return null;
}
