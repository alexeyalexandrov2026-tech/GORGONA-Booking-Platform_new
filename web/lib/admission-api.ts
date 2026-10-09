import { z } from "zod";
import { managementFetch, ManagementApiError } from "./management-api";
import {
  admissionViewSchema,
  admissionReferenceSchema,
  admissionStatusSchema,
  admissionListSchema as listSchema,
  type AdmissionInput,
  type AdmissionReference,
} from "./admission-contracts";
export * from "./admission-contracts";

const base = (business: string) =>
  `/v1/businesses/${business}/provider-admission`;
async function scoped<T extends { business_id: string; book_id?: string }>(
  business: string,
  book: string | null,
  schema: z.ZodType<T>,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const value = schema.parse(await managementFetch(path, init));
  if (value.business_id !== business || (book && value.book_id !== book))
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this admission record safely.",
    );
  return value;
}
export function fetchAdmissions(
  business: string,
  book: string,
  after?: string,
) {
  return scoped(
    business,
    book,
    listSchema,
    `${base(business)}/books/${book}/requests?limit=100${after ? `&after=${encodeURIComponent(after)}` : ""}`,
  );
}
export async function fetchAdmission(
  business: string,
  book: string,
  id: string,
  revision?: number,
) {
  const result = await scoped(
    business,
    book,
    admissionViewSchema,
    `${base(business)}/books/${book}/requests/${id}${revision ? `?revision=${revision}` : ""}`,
  );
  if (result.request_id !== id || (revision && result.revision !== revision))
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected admission revision.",
    );
  return result;
}
export async function saveAdmission(
  business: string,
  book: string,
  id: string,
  key: string,
  body: AdmissionInput | { schema_version: 1; expected_revision: number },
  action?: "submit" | "withdraw",
) {
  const result = await scoped(
    business,
    book,
    admissionViewSchema,
    `${base(business)}/books/${book}/requests/${id}${action ? `/${action}` : ""}`,
    {
      method: action ? "POST" : "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(body),
    },
  );
  if (
    result.request_id !== id ||
    result.revision !== body.expected_revision + 1
  )
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected saved admission revision.",
    );
  return result;
}
export async function resolveAdmission(
  business: string,
  key: string,
  reference: AdmissionReference,
  cancel = false,
) {
  const result = await scoped(
    business,
    null,
    admissionStatusSchema,
    `${base(business)}/commands/${encodeURIComponent(key)}/${cancel ? "cancel" : "resolve"}`,
    { method: "POST", body: JSON.stringify(reference) },
  );
  if (result.key !== key || result.operation !== reference.operation)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected admission recovery response.",
    );
  return result;
}

const savedSchema = z.strictObject({
  schema_version: z.literal(1),
  actor_id: z.uuid(),
  business_id: z.uuid(),
  key: z.string().regex(/^[A-Za-z0-9._:-]{8,255}$/),
  reference: admissionReferenceSchema,
});
export type AdmissionRecovery = z.infer<typeof savedSchema>;
const storageKey = (actor: string, business: string) =>
  `gorgona.admission.recovery.v1.${actor}.${business}`;
export function readAdmissionRecovery(
  actor: string,
  business: string,
): AdmissionRecovery | null {
  const raw = sessionStorage.getItem(storageKey(actor, business));
  if (!raw) return null;
  if (raw.length > 4096)
    throw new Error("Invalid admission recovery reference.");
  const value = savedSchema.parse(JSON.parse(raw));
  if (value.actor_id !== actor || value.business_id !== business)
    throw new Error("Invalid admission recovery scope.");
  return value;
}
export function preserveAdmissionRecovery(
  actor: string,
  business: string,
  key: string,
  reference: AdmissionReference,
) {
  const current = readAdmissionRecovery(actor, business);
  if (current && current.key !== key)
    throw new Error("Resolve the earlier admission request first.");
  const value = savedSchema.parse({
    schema_version: 1,
    actor_id: actor,
    business_id: business,
    key,
    reference,
  });
  sessionStorage.setItem(storageKey(actor, business), JSON.stringify(value));
  return value;
}
export function clearAdmissionRecovery(
  actor: string,
  business: string,
  key: string,
) {
  if (readAdmissionRecovery(actor, business)?.key === key)
    sessionStorage.removeItem(storageKey(actor, business));
}
