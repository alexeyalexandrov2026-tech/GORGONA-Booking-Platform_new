import { z } from "zod";

const instant = z.iso.datetime({ offset: true });
export const delegablePermissionSchema = z.enum([
  "booking.read",
  "booking.write",
  "catalog.read",
  "staff.read",
]);
export const delegationSchema = z
  .strictObject({
    schema_version: z.literal(1),
    grant_id: z.uuid(),
    owner_business_id: z.uuid(),
    owner_name: z.string().min(1),
    servicer_business_id: z.uuid(),
    servicer_name: z.string().min(1).nullable(),
    permissions: z.array(delegablePermissionSchema).min(1).max(4),
    location_id: z.uuid().nullable(),
    expires_at: instant,
    status: z.enum(["pending", "active", "declined", "revoked"]),
    expired: z.boolean(),
    revision: z.number().int().positive(),
    revoked_by_side: z.enum(["owner", "servicer"]).nullable(),
    delegates: z
      .array(
        z.strictObject({
          user_id: z.uuid(),
          display_name: z.string().min(1),
          added_at: instant,
        }),
      )
      .max(50),
    created_at: instant,
  })
  .refine(
    (grant) =>
      grant.owner_business_id !== grant.servicer_business_id &&
      (grant.status === "revoked") === (grant.revoked_by_side !== null),
  );
export const delegationListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: z.uuid(),
    items: z.array(delegationSchema).max(100),
    next_cursor: z.uuid().nullable(),
  })
  .refine(
    (page) =>
      page.items.every(
        (item) =>
          item.owner_business_id === page.business_id ||
          item.servicer_business_id === page.business_id,
      ) &&
      new Set(page.items.map((item) => item.grant_id)).size ===
        page.items.length,
  );
export const delegatedBusinessSchema = z.strictObject({
  business_id: z.uuid(),
  business_name: z.string().min(1),
  grant_id: z.uuid(),
  servicer_business_id: z.uuid(),
  servicer_name: z.string().nullable(),
  permissions: z.array(delegablePermissionSchema).min(1).max(4),
  location_id: z.uuid().nullable(),
  expires_at: instant,
});
export type Delegation = z.infer<typeof delegationSchema>;
export type DelegationPage = z.infer<typeof delegationListSchema>;
export type DelegatedBusiness = z.infer<typeof delegatedBusinessSchema>;
export type DelegablePermission = z.infer<typeof delegablePermissionSchema>;
export interface DelegationIssue {
  schema_version: 1;
  servicer_business_id: string;
  permissions: DelegablePermission[];
  location_id: string | null;
  expires_at: string;
}
export interface DelegationDecision {
  schema_version: 1;
  expected_revision: number;
  delegate_user_ids?: string[];
}
export const ACCESS_LEVELS: Record<"manage" | "view", DelegablePermission[]> = {
  manage: ["booking.read", "booking.write", "catalog.read", "staff.read"],
  view: ["booking.read", "catalog.read", "staff.read"],
};
