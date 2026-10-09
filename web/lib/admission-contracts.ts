import { z } from "zod";

const revision = z.number().int().min(1).max(2147483647);
const operation = z.enum(["charge", "refund", "transfer", "payout"]);
export const admissionInputSchema = z.strictObject({
  schema_version: z.literal(1),
  expected_revision: z.number().int().min(0).max(2147483646),
  provider: z.literal("stripe_connect"),
  country: z.string().regex(/^[A-Z]{2}$/),
  business_activity: z.string().trim().min(1).max(500),
  requested_operation: operation,
  account_reference: z.string().trim().min(1).max(160).nullable(),
  evidence_references: z.array(z.string().trim().min(1).max(256)).max(8),
  notes: z.string().trim().min(1).max(2000).nullable(),
  assessment: z.enum(["not_checked", "suspended", "unsupported"]),
});
export type AdmissionInput = z.infer<typeof admissionInputSchema>;
export const admissionViewSchema = admissionInputSchema
  .omit({ expected_revision: true })
  .extend({
    business_id: z.uuid(),
    book_id: z.uuid(),
    request_id: z.uuid(),
    revision,
    state: z.enum(["draft", "submitted", "withdrawn"]),
    evidence_status: z.literal("manually_provided_unverified"),
    operational_capabilities: z.strictObject({
      charge: z.literal(false),
      refund: z.literal(false),
      transfer: z.literal(false),
      payout: z.literal(false),
    }),
    created_at: z.iso.datetime({ offset: true }),
  });
export type AdmissionView = z.infer<typeof admissionViewSchema>;
export const admissionReferenceSchema = z.strictObject({
  schema_version: z.literal(1),
  operation: z.enum([
    "admission_draft",
    "admission_submit",
    "admission_withdraw",
  ]),
  book_id: z.uuid(),
  subject_id: z.uuid(),
  revision,
});
export type AdmissionReference = z.infer<typeof admissionReferenceSchema>;
export const admissionStatusSchema = z.strictObject({
  schema_version: z.literal(1),
  business_id: z.uuid(),
  key: z.string(),
  operation: admissionReferenceSchema.shape.operation,
  state: z.enum(["committed", "unresolved", "cancelled"]),
});
export const admissionListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: z.uuid(),
    book_id: z.uuid(),
    items: z.array(admissionViewSchema).max(100),
    next_after: z.uuid().nullable(),
  })
  .refine(
    (v) =>
      new Set(v.items.map((x) => x.request_id)).size === v.items.length &&
      v.items.every(
        (x) => x.business_id === v.business_id && x.book_id === v.book_id,
      ),
  );

export function admissionResponseSchema(
  path: string,
  method: string,
): z.ZodType | undefined {
  if (
    /^\/provider-admission\/commands\/[A-Za-z0-9._:-]{8,255}\/(resolve|cancel)$/.test(
      path,
    ) &&
    method === "POST"
  )
    return admissionStatusSchema;
  const match =
    /^\/provider-admission\/books\/[0-9a-f-]{36}\/requests(.*)$/i.exec(path);
  if (!match) return undefined;
  if (!match[1] && method === "GET") return admissionListSchema;
  if (
    /^\/[0-9a-f-]{36}$/i.test(match[1] ?? "") &&
    ["GET", "PUT"].includes(method)
  )
    return admissionViewSchema;
  if (
    /^\/[0-9a-f-]{36}\/(submit|withdraw)$/i.test(match[1] ?? "") &&
    method === "POST"
  )
    return admissionViewSchema;
  return undefined;
}
