import { z } from "zod";

const amount = z.int().nonnegative();
const difference = z.int();
export const reconciliationSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: z.uuid(),
    currency: z.string().regex(/^[A-Z]{3}$/),
    contract_minor: amount,
    completed_minor: amount,
    budget_minor: amount,
    committed_minor: amount,
    actual_minor: amount,
    warranty_repair_minor: amount,
    billed_minor: amount,
    retained_minor: amount,
    due_minor: amount,
    released_minor: amount,
    held_minor: difference,
    due_paid_minor: amount,
    due_credited_minor: amount,
    retainage_paid_minor: amount,
    retainage_credited_minor: amount,
    unissued_documents: amount,
    contract_minus_billed_minor: difference,
    completed_minus_billed_minor: difference,
    billed_minus_settled_minor: difference,
    retainage_settled_before_release_minor: amount,
    budget_minus_actual_minor: difference,
    contract_minus_actual_minor: difference,
    claims: z.strictObject({
      open: amount,
      repaired: amount,
      closed: amount,
      rejected: amount,
    }),
  })
  .refine((v) => {
    const billedSettled = v.due_paid_minor + v.due_credited_minor;
    const retainageSettled =
      v.retainage_paid_minor + v.retainage_credited_minor;
    return (
      v.billed_minor - v.retained_minor === v.due_minor &&
      v.contract_minor - v.billed_minor === v.contract_minus_billed_minor &&
      v.completed_minor - v.billed_minor === v.completed_minus_billed_minor &&
      v.billed_minor - billedSettled - retainageSettled ===
        v.billed_minus_settled_minor &&
      v.retained_minor - v.released_minor === v.held_minor &&
      Math.max(retainageSettled - v.released_minor, 0) ===
        v.retainage_settled_before_release_minor &&
      v.budget_minor - v.actual_minor === v.budget_minus_actual_minor &&
      v.contract_minor - v.actual_minor === v.contract_minus_actual_minor
    );
  });

export type Reconciliation = z.infer<typeof reconciliationSchema>;
