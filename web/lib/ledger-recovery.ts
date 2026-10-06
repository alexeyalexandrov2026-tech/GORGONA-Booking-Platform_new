import { z } from "zod";
import {
  commandReferenceSchema,
  type CommandReference,
  type LedgerCommand,
} from "./ledger-contracts";

const recoverySchema = z.strictObject({
  schema_version: z.literal(1),
  actor_id: z.uuid(),
  business_id: z.uuid(),
  key: z.string().regex(/^[A-Za-z0-9._:-]{8,255}$/),
  reference: commandReferenceSchema,
  saved_at: z.iso.datetime({ offset: true }),
});
export type LedgerRecovery = z.infer<typeof recoverySchema>;
const storageKey = (actor: string, business: string) =>
  `gorgona.ledger.recovery.v1.${actor}.${business}`;

/** Session-scoped, minimal recovery references. Never tokens, amounts, memo or body. */
export function readLedgerRecovery(
  actor: string,
  business: string,
): LedgerRecovery | null {
  const raw = sessionStorage.getItem(storageKey(actor, business));
  if (raw === null) return null;
  if (raw.length > 4096)
    throw new Error("Unable to read this recovery reference safely.");
  const result = recoverySchema.parse(JSON.parse(raw));
  if (result.actor_id !== actor || result.business_id !== business)
    throw new Error("Unable to read this recovery reference safely.");
  return result;
}
function reference(command: LedgerCommand): CommandReference {
  const base = {
    schema_version: 1 as const,
    operation: command.type,
    book_id: command.book,
    subject_id: null as string | null,
    revision: null as number | null,
    period: null as string | null,
    sequence: null as number | null,
  };
  switch (command.type) {
    case "book":
      return { ...base, revision: command.body.expected_revision + 1 };
    case "account":
      return {
        ...base,
        subject_id: command.id,
        revision: command.body.expected_revision + 1,
      };
    case "entry":
      return { ...base, subject_id: command.id };
    case "reverse":
      return { ...base, subject_id: command.body.reversal_entry_id };
    case "close":
    case "reopen":
      return {
        ...base,
        period: command.period,
        sequence: command.body.expected_sequence + 1,
      };
  }
}
export function preserveLedgerRecovery(
  actor: string,
  business: string,
  command: LedgerCommand,
): LedgerRecovery {
  const existing = readLedgerRecovery(actor, business);
  if (existing && existing.key !== command.key)
    throw new Error(
      "Resolve the earlier ledger command before starting another.",
    );
  const recovery = recoverySchema.parse({
    schema_version: 1,
    actor_id: actor,
    business_id: business,
    key: command.key,
    reference: reference(command),
    saved_at: existing?.saved_at ?? new Date().toISOString(),
  });
  sessionStorage.setItem(storageKey(actor, business), JSON.stringify(recovery));
  return recovery;
}
export function clearLedgerRecovery(
  actor: string,
  business: string,
  key: string,
): void {
  const stored = readLedgerRecovery(actor, business);
  if (stored?.key === key)
    sessionStorage.removeItem(storageKey(actor, business));
}
