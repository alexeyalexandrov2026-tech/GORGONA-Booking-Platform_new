import { z } from "zod";

const instant = z.iso.datetime({ offset: true });
const membership = z.strictObject({
  membership_id: z.uuid(),
  member_business_id: z.uuid(),
  member_name: z.string().min(1).nullable(),
  status: z.enum(["invited", "active", "declined", "left", "removed"]),
  revision: z.number().int().positive(),
  invited_at: instant,
  decided_at: instant.nullable(),
  ended_at: instant.nullable(),
});
export const businessGroupSchema = z.strictObject({
  schema_version: z.literal(1),
  group_id: z.uuid(),
  organizer_business_id: z.uuid(),
  organizer_name: z.string().min(1),
  code: z
    .string()
    .min(1)
    .max(64)
    .regex(/^[A-Z0-9][A-Z0-9_-]*$/),
  name: z.string().min(1).max(200),
  role: z.enum(["organizer", "member"]),
  memberships: z.array(membership),
  created_at: instant,
});
export const businessGroupListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: z.uuid(),
    items: z.array(businessGroupSchema).max(100),
    next_cursor: z.uuid().nullable(),
  })
  .refine(
    (page) =>
      page.items.every((group) =>
        group.role === "organizer"
          ? group.organizer_business_id === page.business_id
          : group.memberships.every(
              (item) => item.member_business_id === page.business_id,
            ),
      ) &&
      new Set(page.items.map((group) => group.group_id)).size ===
        page.items.length,
  );
export type BusinessGroup = z.infer<typeof businessGroupSchema>;
export type BusinessGroupPage = z.infer<typeof businessGroupListSchema>;
export type GroupMembership = z.infer<typeof membership>;
