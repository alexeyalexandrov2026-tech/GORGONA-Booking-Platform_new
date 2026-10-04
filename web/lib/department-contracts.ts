import { z } from "zod";

const reference = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[A-Z0-9][A-Z0-9_-]*$/);
export const departmentSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: z.uuid(),
    department_id: z.uuid(),
    code: reference,
    name: z.string().min(1).max(200),
    parent_department_id: z.uuid().nullable(),
    legal_entity_id: z.uuid().nullable(),
    location_id: z.uuid().nullable(),
    archived: z.boolean(),
    revision: z.number().int().positive(),
    state: z.literal("draft"),
    created_at: z.iso.datetime({ offset: true }),
  })
  .refine((item) => item.parent_department_id !== item.department_id);
export const departmentListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: z.uuid(),
    items: z.array(departmentSchema).max(100),
    next_cursor: reference.nullable(),
  })
  .refine(
    (page) =>
      page.items.every((item) => item.business_id === page.business_id) &&
      new Set(page.items.map((item) => item.department_id)).size ===
        page.items.length &&
      new Set(page.items.map((item) => item.code)).size === page.items.length,
  );
export type Department = z.infer<typeof departmentSchema>;
export type DepartmentPage = z.infer<typeof departmentListSchema>;
export interface DepartmentInput {
  schema_version: 1;
  expected_revision: number;
  code: string;
  name: string;
  parent_department_id: string | null;
  legal_entity_id: string | null;
  location_id: string | null;
  archived: boolean;
}
