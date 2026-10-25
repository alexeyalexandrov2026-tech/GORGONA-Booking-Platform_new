import { z } from "zod";

const instant = z.iso.datetime({ offset: true });
export const delegablePermissionSchema = z.enum([
  "booking.read",
  "booking.write",
  "catalog.read",
  "staff.read",
  // ADR-0031: a carrier's dispatcher works by transport action.
  "transport.read",
  "transport.plan",
  "transport.assign",
  "transport.events",
]);
export const delegationSchema = z
  .strictObject({
    schema_version: z.literal(1),
    grant_id: z.uuid(),
    owner_business_id: z.uuid(),
    owner_name: z.string().min(1),
    servicer_business_id: z.uuid(),
    servicer_name: z.string().min(1).nullable(),
    permissions: z.array(delegablePermissionSchema).min(1).max(8),
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
  permissions: z.array(delegablePermissionSchema).min(1).max(8),
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
// M6b (ADR-0031): a carrier's dispatcher is granted transport actions; reading comes with any of them.
export const TRANSPORT_ACTIONS: [DelegablePermission, string][] = [
  ["transport.plan", "Plan trips"],
  ["transport.assign", "Assign crews"],
  ["transport.events", "Record stop events"],
];
const TRANSPORT_WORDS: Record<string, string> = {
  "transport.read": "view",
  "transport.plan": "plan trips",
  "transport.assign": "assign crews",
  "transport.events": "record stop events",
};

/** The granted rights in words, booking access first, then transport actions. */
export function describeAccess(permissions: DelegablePermission[]): string {
  const booking = permissions.filter((p) => !p.startsWith("transport.")).sort();
  const same = (level: DelegablePermission[]) =>
    booking.join(",") === [...level].sort().join(",");
  const parts: string[] = [];
  if (booking.length)
    parts.push(
      same(ACCESS_LEVELS.manage)
        ? "Manage bookings"
        : same(ACCESS_LEVELS.view)
          ? "View bookings"
          : booking.join(", "),
    );
  const transport = Object.keys(TRANSPORT_WORDS).filter((p) =>
    permissions.includes(p as DelegablePermission),
  );
  if (transport.length)
    parts.push(
      `Transport: ${transport.map((p) => TRANSPORT_WORDS[p]).join(", ")}`,
    );
  return parts.join("; ");
}
