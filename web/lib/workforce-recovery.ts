import { z } from "zod";
import {
  commandKeySchema,
  commandReference,
  commandReferenceSchema,
  type WorkforceCommand,
} from "./workforce-contracts";

export const workforceRecoverySchema = z.strictObject({
  schema_version: z.literal(1),
  actor_id: z.uuid(),
  business_id: z.uuid(),
  key: commandKeySchema,
  reference: commandReferenceSchema,
  saved_at: z.iso.datetime({ offset: true }),
});
export type WorkforceRecovery = z.infer<typeof workforceRecoverySchema>;
const storageKey = (actor: string, business: string) =>
  `gorgona.workforce.recovery.v1.${actor}.${business}`;

/** Identifiers only. Never a reason, a name, a position, a time or a token. */
export function readWorkforceRecovery(
  actor: string,
  business: string,
): WorkforceRecovery | null {
  const raw = sessionStorage.getItem(storageKey(actor, business));
  if (raw === null) return null;
  if (raw.length > 4096)
    throw new Error("Unable to read the saved command reference safely.");
  const saved = workforceRecoverySchema.parse(JSON.parse(raw));
  if (saved.actor_id !== actor || saved.business_id !== business)
    throw new Error("This reference belongs to another account or business.");
  return saved;
}
export function preserveWorkforceRecovery(
  actor: string,
  business: string,
  command: WorkforceCommand,
): WorkforceRecovery {
  const earlier = readWorkforceRecovery(actor, business);
  const reference = commandReference(command);
  if (
    earlier &&
    (earlier.key !== command.key ||
      JSON.stringify(earlier.reference) !== JSON.stringify(reference))
  )
    throw new Error("Resolve the earlier action before starting another.");
  const saved = workforceRecoverySchema.parse({
    schema_version: 1,
    actor_id: actor,
    business_id: business,
    key: command.key,
    reference,
    saved_at: earlier?.saved_at ?? new Date().toISOString(),
  });
  sessionStorage.setItem(storageKey(actor, business), JSON.stringify(saved));
  return saved;
}
export function clearWorkforceRecovery(
  actor: string,
  business: string,
  key: string,
) {
  const saved = readWorkforceRecovery(actor, business);
  if (saved?.key === key)
    sessionStorage.removeItem(storageKey(actor, business));
}
/** Remove a record that can no longer be read, so the screen is not blocked. */
export function discardUnreadableRecovery(actor: string, business: string) {
  sessionStorage.removeItem(storageKey(actor, business));
}
