import { z } from "zod";

// Delegation between independent businesses (ADR-0016). A grant never moves data.
export const DELEGABLE_PERMISSIONS = [
  "booking.read",
  "booking.write",
  "catalog.read",
  "staff.read",
] as const;
export type DelegablePermission = (typeof DELEGABLE_PERMISSIONS)[number];
/** Creating or moving a booking needs the services, staff and bookings it refers to. */
export const WRITE_REQUIRES: readonly DelegablePermission[] = [
  "booking.read",
  "catalog.read",
  "staff.read",
];

const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
const permissions = z
  .array(z.enum(DELEGABLE_PERMISSIONS))
  .min(1)
  .max(4)
  .refine(
    (items) =>
      new Set(items).size === items.length &&
      (!items.includes("booking.write") ||
        WRITE_REQUIRES.every((item) => items.includes(item))),
  );
const terms = {
  revision: z.number().int().positive(),
  state: z.enum(["active", "revoked"]),
  effective_state: z.enum(["scheduled", "active", "expired", "revoked"]),
  purpose: z.string().min(1).max(200),
  permissions,
  location_id: id.nullable(),
  valid_from: instant,
  valid_until: instant,
};
const unique = (values: string[]) => new Set(values).size === values.length;

export const delegationGrantSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    grant_id: id,
    grantee_business_id: id,
    current_revision: z.number().int().positive(),
    created_at: instant,
    delegates: z.array(
      z.strictObject({
        designation_id: id,
        user_id: id,
        designated_at: instant,
      }),
    ),
    ...terms,
  })
  .refine(
    (grant) =>
      grant.grantee_business_id !== grant.business_id &&
      grant.revision <= grant.current_revision &&
      unique(grant.delegates.map((item) => item.designation_id)),
  );
export const delegationGrantListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    items: z.array(delegationGrantSchema).max(100),
    next_cursor: id.nullable(),
  })
  .refine(
    (page) =>
      page.items.every((item) => item.business_id === page.business_id) &&
      unique(page.items.map((item) => item.grant_id)),
  );

export const incomingDelegationSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    grant_id: id,
    grantor_business_id: id,
    delegates: z.array(
      z.strictObject({
        designation_id: id,
        membership_id: id,
        user_id: id,
        display_name: z.string().nullable(),
        designated_at: instant,
      }),
    ),
    ...terms,
  })
  .refine(
    (grant) =>
      grant.grantor_business_id !== grant.business_id &&
      unique(grant.delegates.map((item) => item.membership_id)),
  );
export const incomingDelegationListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    items: z.array(incomingDelegationSchema).max(100),
    next_cursor: id.nullable(),
  })
  .refine(
    (page) =>
      page.items.every((item) => item.business_id === page.business_id) &&
      unique(page.items.map((item) => item.grant_id)),
  );

export const delegatedAccessSchema = z.strictObject({
  schema_version: z.literal(1),
  business_id: id,
  serving_business_id: id,
  grant_id: id,
  revision: z.number().int().positive(),
  purpose: z.string().min(1).max(200),
  permissions,
  location_id: id.nullable(),
  valid_until: instant,
});

export const memberListSchema = z.array(
  z.object({
    membership_id: id,
    user_id: id,
    display_name: z.string().nullable(),
    role: z.string(),
    status: z.string(),
    location_id: id.nullable(),
  }),
);

export type DelegationGrant = z.infer<typeof delegationGrantSchema>;
export type DelegationGrantPage = z.infer<typeof delegationGrantListSchema>;
export type IncomingDelegation = z.infer<typeof incomingDelegationSchema>;
export type IncomingDelegationPage = z.infer<
  typeof incomingDelegationListSchema
>;
export type DelegatedAccess = z.infer<typeof delegatedAccessSchema>;
export type Member = z.infer<typeof memberListSchema>[number];
export interface DelegationGrantInput {
  schema_version: 1;
  expected_revision: number;
  grantee_business_id: string;
  purpose: string;
  permissions: DelegablePermission[];
  location_id: string | null;
  valid_from: string;
  valid_until: string;
}

export const PERMISSION_LABELS: Record<DelegablePermission, string> = {
  "booking.read": "View bookings and clients",
  "booking.write": "Create, move and cancel bookings",
  "catalog.read": "View services",
  "staff.read": "View staff and schedules",
};

/** Adds the reads that booking changes depend on and keeps a canonical order. */
export function withDependencies(
  selected: Iterable<DelegablePermission>,
): DelegablePermission[] {
  const result = new Set(selected);
  if (result.has("booking.write"))
    WRITE_REQUIRES.forEach((item) => result.add(item));
  return DELEGABLE_PERMISSIONS.filter((item) => result.has(item));
}
