import { z } from "zod";

const id = z.uuid();
const revision = z.number().int().positive();
const instant = z.iso.datetime({ offset: true });
const day = z.iso.date();
export const agreementState = z.enum(["draft", "agreed", "terminated"]);
const envelope = { schema_version: z.literal(1), business_id: id };
// The server limits text in Unicode code points, not UTF-16 units.
const text = (min: number, max: number) =>
  z.string().refine((v) => {
    const length = Array.from(v).length;
    return length >= min && length <= max;
  });
const ordered = (v: {
  effective_from: string | null;
  effective_until: string | null;
}) =>
  v.effective_from === null ||
  v.effective_until === null ||
  v.effective_from <= v.effective_until;
// A draft is never shown as signed; agreed and terminated versions are attested.
const consistent = (v: {
  state: string;
  signed_on: string | null;
  terminated_on: string | null;
  attestation?: string | null;
}) =>
  v.state === "draft"
    ? v.signed_on === null && v.terminated_on === null && !v.attestation
    : v.signed_on !== null &&
      (v.attestation === undefined || v.attestation !== null) &&
      (v.state === "terminated") === (v.terminated_on !== null);
// The agreed version in force: an agreed version is itself in force, a draft is
// only an unsigned amendment of an earlier one, a termination names what it ends.
const inForce = (v: {
  state: string;
  revision: number;
  in_force_revision: number | null;
  terminates_revision: number | null;
}) =>
  v.state === "agreed"
    ? v.in_force_revision === v.revision && v.terminates_revision === null
    : v.state === "terminated"
      ? v.terminates_revision !== null &&
        v.in_force_revision === v.terminates_revision &&
        v.terminates_revision < v.revision
      : v.terminates_revision === null &&
        (v.in_force_revision === null || v.in_force_revision < v.revision);

const reference = z.strictObject({ document_id: id, revision });
export const agreementSchema = z
  .strictObject({
    ...envelope,
    agreement_id: id,
    counterparty_id: id,
    legal_entity_id: id.nullable(),
    revision,
    state: agreementState,
    title: text(1, 200),
    number: text(1, 64).nullable(),
    summary: text(1, 2000).nullable(),
    effective_from: day.nullable(),
    effective_until: day.nullable(),
    signed_on: day.nullable(),
    attestation: z.literal("signed_outside_platform").nullable(),
    document: reference.nullable(),
    terminated_on: day.nullable(),
    in_force_revision: revision.nullable(),
    terminates_revision: revision.nullable(),
    created_at: instant,
  })
  .refine(
    (v) =>
      ordered(v) &&
      consistent(v) &&
      inForce(v) &&
      (v.terminated_on === null ||
        (v.signed_on !== null && v.terminated_on >= v.signed_on)),
  );
// The agreed version in force, also while an amendment is only drafted.
const inForceSummary = z
  .strictObject({
    revision,
    title: text(1, 200),
    number: text(1, 64).nullable(),
    effective_from: day.nullable(),
    effective_until: day.nullable(),
    signed_on: day,
  })
  .refine(ordered);
// A summary shows the latest version (for an open amendment, the unsigned draft)
// and the agreed version in force.
const summary = z
  .strictObject({
    agreement_id: id,
    counterparty_id: id,
    revision,
    state: agreementState,
    title: text(1, 200),
    number: text(1, 64).nullable(),
    effective_from: day.nullable(),
    effective_until: day.nullable(),
    terminated_on: day.nullable(),
    in_force: inForceSummary.nullable(),
    updated_at: instant,
  })
  .refine(
    (v) =>
      ordered(v) &&
      (v.state === "draft"
        ? v.terminated_on === null &&
          (v.in_force === null || v.in_force.revision < v.revision)
        : v.in_force !== null &&
          (v.state === "agreed"
            ? v.in_force.revision === v.revision && v.terminated_on === null
            : v.in_force.revision < v.revision &&
              v.terminated_on !== null &&
              v.terminated_on >= v.in_force.signed_on)),
  );
export const agreementListSchema = z
  .strictObject({
    ...envelope,
    counterparty_id: id,
    items: z.array(summary).max(100),
    next_cursor: id.nullable(),
  })
  .refine(
    (v) => new Set(v.items.map((a) => a.agreement_id)).size === v.items.length,
  );
export const agreementHistorySchema = z.strictObject({
  ...envelope,
  agreement_id: id,
  items: z
    .array(
      z
        .strictObject({
          revision,
          state: agreementState,
          title: z.string(),
          signed_on: day.nullable(),
          terminated_on: day.nullable(),
          // Only an unsigned draft can be closed by a termination.
          abandoned: z.boolean(),
          created_at: instant,
        })
        .refine((v) => consistent(v) && (!v.abandoned || v.state === "draft")),
    )
    .max(100),
  next_cursor: revision.nullable(),
});

export type ContractStatus =
  | "draft"
  | "in_force"
  | "in_force_amendment_draft"
  | "expired"
  | "termination_scheduled"
  | "terminated";

/**
 * What applies on `today` (YYYY-MM-DD, the viewer's calendar day, as for document
 * validity). An agreed version stays in force while an amendment is only drafted
 * and until a recorded termination takes effect on its day; its own term (not the
 * draft's) decides whether it has ended. `inForce` is that agreed version.
 */
export function contractStatus(
  contract: { state: string; terminated_on: string | null },
  inForce: { effective_until: string | null } | null,
  today: string,
): ContractStatus {
  if (inForce === null) return "draft";
  if (contract.terminated_on !== null && contract.terminated_on <= today)
    return "terminated";
  if (inForce.effective_until !== null && inForce.effective_until < today)
    return "expired";
  if (contract.state === "terminated") return "termination_scheduled";
  return contract.state === "draft" ? "in_force_amendment_draft" : "in_force";
}

/**
 * Drafts and agreements need the contract's own active card. A contract listed
 * through a merged duplicate can only be read (or terminated) from this card.
 */
export function canDraftOrAgree(
  contract: { counterparty_id: string; state: string } | null,
  counterpartyId: string,
  cardActive: boolean,
): boolean {
  return (
    cardActive &&
    (contract === null ||
      (contract.counterparty_id === counterpartyId &&
        contract.state !== "terminated"))
  );
}

/**
 * The document reference a saved draft keeps. A new amendment of an agreed
 * version starts without that version's signed copy.
 */
export function draftDocument(
  contract: {
    state: string;
    document: { document_id: string; revision: number } | null;
  } | null,
): { document_id: string; revision: number } | null {
  return contract?.state === "draft" ? contract.document : null;
}

export function agreementResponseSchema(
  path: string,
  method: string,
): z.ZodType | null {
  if (/^\/counterparties\/[0-9a-f-]{36}\/agreements$/i.test(path))
    return method === "GET" ? agreementListSchema : null;
  const route =
    /^\/agreements\/[0-9a-f-]{36}(?:\/(versions|agree|terminate))?$/i.exec(
      path,
    );
  if (!route) return null;
  const suffix = route[1];
  if (!suffix && ["GET", "PUT"].includes(method)) return agreementSchema;
  if (suffix === "versions" && method === "GET") return agreementHistorySchema;
  if ((suffix === "agree" || suffix === "terminate") && method === "POST")
    return agreementSchema;
  return null;
}

export type Agreement = z.infer<typeof agreementSchema>;
export type AgreementPage = z.infer<typeof agreementListSchema>;
export type AgreementHistory = z.infer<typeof agreementHistorySchema>;
export interface AgreementDraft {
  schema_version: 1;
  expected_revision: number;
  counterparty_id: string;
  legal_entity_id: string | null;
  title: string;
  number: string | null;
  summary: string | null;
  effective_from: string | null;
  effective_until: string | null;
  document: { document_id: string; revision: number } | null;
}
export type AgreementCommand =
  | { type: "draft"; id: string; key: string; body: AgreementDraft }
  | {
      type: "agree";
      id: string;
      key: string;
      body: {
        schema_version: 1;
        expected_revision: number;
        signed_on: string;
        attestation: "signed_outside_platform";
      };
    }
  | {
      type: "terminate";
      id: string;
      key: string;
      body: {
        schema_version: 1;
        expected_revision: number;
        terminated_on: string;
      };
    };
