import { z } from "zod";
import {
  financialReferenceSchema,
  type FinancialReference,
  type FinancialCommand,
} from "./financial-contracts";

export const financialRecoverySchema = z.strictObject({
  schema_version: z.literal(1),
  actor_id: z.uuid(),
  business_id: z.uuid(),
  key: z.string().regex(/^[A-Za-z0-9._:-]{8,255}$/),
  reference: financialReferenceSchema,
  saved_at: z.iso.datetime({ offset: true }),
});
export type FinancialRecovery = z.infer<typeof financialRecoverySchema>;
const storageKey = (actor: string, business: string) =>
  `gorgona.financial.recovery.v1.${actor}.${business}`;
export function financialReference(
  command: FinancialCommand,
): FinancialReference {
  return financialReferenceSchema.parse({
    schema_version: 1,
    operation: command.operation,
    book_id: command.book,
    subject_id: command.subject,
    revision:
      ("expected_revision" in command.body
        ? command.body.expected_revision
        : command.body.expected_sequence) + 1,
  });
}
/** Persist identifiers only. Never financial content, amount, account alias, tokens or PII. */
export function readFinancialRecovery(
  actor: string,
  business: string,
): FinancialRecovery | null {
  const raw = sessionStorage.getItem(storageKey(actor, business));
  if (raw === null) return null;
  if (raw.length > 4096)
    throw new Error("Unable to read the financial recovery reference safely.");
  const saved = financialRecoverySchema.parse(JSON.parse(raw));
  if (saved.actor_id !== actor || saved.business_id !== business)
    throw new Error("Recovery belongs to another account or business.");
  return saved;
}
export function preserveFinancialRecovery(
  actor: string,
  business: string,
  command: FinancialCommand,
): FinancialRecovery {
  const old = readFinancialRecovery(actor, business),
    reference = financialReference(command);
  if (
    old &&
    (old.key !== command.key ||
      JSON.stringify(old.reference) !== JSON.stringify(reference))
  )
    throw new Error(
      "Resolve the earlier financial command before starting another.",
    );
  const saved = financialRecoverySchema.parse({
    schema_version: 1,
    actor_id: actor,
    business_id: business,
    key: command.key,
    reference,
    saved_at: old?.saved_at ?? new Date().toISOString(),
  });
  sessionStorage.setItem(storageKey(actor, business), JSON.stringify(saved));
  return saved;
}
export function clearFinancialRecovery(
  actor: string,
  business: string,
  key: string,
) {
  const saved = readFinancialRecovery(actor, business);
  if (saved?.key === key)
    sessionStorage.removeItem(storageKey(actor, business));
}
