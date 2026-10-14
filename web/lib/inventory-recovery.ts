import { z } from "zod";
import {
  commandKeySchema,
  commandReference,
  commandReferenceSchema,
  type InventoryCommand,
} from "./inventory-contracts";

export const inventoryRecoverySchema = z.strictObject({
  schema_version: z.literal(1),
  actor_id: z.uuid(),
  business_id: z.uuid(),
  key: commandKeySchema,
  reference: commandReferenceSchema,
  saved_at: z.iso.datetime({ offset: true }),
});
export type InventoryRecovery = z.infer<typeof inventoryRecoverySchema>;
const storageKey = (actor: string, business: string) =>
  `gorgona.inventory.recovery.v1.${actor}.${business}`;

/** Identifiers only. Never a name, a code, a quantity, an amount or a token. */
export function readInventoryRecovery(
  actor: string,
  business: string,
): InventoryRecovery | null {
  const raw = sessionStorage.getItem(storageKey(actor, business));
  if (raw === null) return null;
  if (raw.length > 4096)
    throw new Error("Unable to read the saved command reference safely.");
  const saved = inventoryRecoverySchema.parse(JSON.parse(raw));
  if (saved.actor_id !== actor || saved.business_id !== business)
    throw new Error("This reference belongs to another account or business.");
  return saved;
}
export function preserveInventoryRecovery(
  actor: string,
  business: string,
  command: InventoryCommand,
): InventoryRecovery {
  const earlier = readInventoryRecovery(actor, business);
  const reference = commandReference(command);
  if (
    earlier &&
    (earlier.key !== command.key ||
      JSON.stringify(earlier.reference) !== JSON.stringify(reference))
  )
    throw new Error("Resolve the earlier action before starting another.");
  const saved = inventoryRecoverySchema.parse({
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
export function clearInventoryRecovery(
  actor: string,
  business: string,
  key: string,
) {
  const saved = readInventoryRecovery(actor, business);
  if (saved?.key === key)
    sessionStorage.removeItem(storageKey(actor, business));
}
/** Remove a record that can no longer be read, so the screen is not blocked. */
export function discardUnreadableInventoryRecovery(
  actor: string,
  business: string,
) {
  sessionStorage.removeItem(storageKey(actor, business));
}
