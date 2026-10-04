import { z } from "zod";

const reference = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[A-Z0-9][A-Z0-9_-]*$/);
export const legalEntitySchema = z.strictObject({
  schema_version: z.literal(1),
  business_id: z.uuid(),
  legal_entity_id: z.uuid(),
  code: reference,
  legal_name: z.string().min(1).max(200),
  revision: z.number().int().positive(),
  state: z.literal("draft"),
  created_at: z.iso.datetime({ offset: true }),
});
export const legalEntityListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: z.uuid(),
    items: z.array(legalEntitySchema).max(100),
    next_cursor: reference.nullable(),
  })
  .refine(
    (page) =>
      page.items.every((item) => item.business_id === page.business_id) &&
      new Set(page.items.map((item) => item.legal_entity_id)).size ===
        page.items.length &&
      new Set(page.items.map((item) => item.code)).size === page.items.length,
  );
export type LegalEntity = z.infer<typeof legalEntitySchema>;
export type LegalEntityPage = z.infer<typeof legalEntityListSchema>;
export interface LegalEntityInput {
  schema_version: 1;
  expected_revision: number;
  code: string;
  legal_name: string;
}
