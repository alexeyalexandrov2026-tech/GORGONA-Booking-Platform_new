import { z } from "zod";

const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
const revision = z.number().int().positive();
const unique = (items: string[]) => new Set(items).size === items.length;
export const groupSchema = z.strictObject({
  schema_version: z.literal(1),
  business_id: id,
  group_id: id,
  code: z
    .string()
    .min(1)
    .max(64)
    .regex(/^[A-Z0-9][A-Z0-9_-]*$/),
  name: z.string().min(1).max(200),
  revision,
  created_at: instant,
});
export const groupListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    items: z.array(groupSchema).max(100),
    next_cursor: z.string().nullable(),
  })
  .refine(
    (p) =>
      p.items.every((i) => i.business_id === p.business_id) &&
      unique(p.items.map((i) => i.group_id)) &&
      unique(p.items.map((i) => i.code)),
  );
export const invitationSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    operator_business_id: id,
    participant_business_id: id,
    group_id: id,
    group_name: z.string().min(1).max(200),
    invitation_id: id,
    state: z.enum(["active", "withdrawn"]),
    revision: z.union([z.literal(1), z.literal(2)]),
    consent_state: z.enum(["accepted", "withdrawn"]).nullable(),
    consent_revision: z.number().int().min(0).max(2),
    created_at: instant,
  })
  .refine(
    (i) =>
      i.operator_business_id !== i.participant_business_id &&
      [i.operator_business_id, i.participant_business_id].includes(
        i.business_id,
      ) &&
      i.revision === (i.state === "active" ? 1 : 2) &&
      i.consent_revision ===
        (i.consent_state === null ? 0 : i.consent_state === "accepted" ? 1 : 2),
  );
export const invitationListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    items: z.array(invitationSchema).max(100),
    next_cursor: id.nullable(),
  })
  .refine(
    (p) =>
      p.items.every((i) => i.business_id === p.business_id) &&
      unique(p.items.map((i) => i.invitation_id)),
  );
export const groupReportSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    group_id: id,
    from_at: instant,
    until_at: instant,
    sources: z
      .array(
        z.strictObject({
          owner_business_id: id,
          grant_id: id,
          grant_revision: revision,
          location_id: id.nullable(),
        }),
      )
      .max(25),
    items: z.array(
      z.strictObject({
        owner_business_id: id,
        legal_entity_id: z.null(),
        legal_entity_assignment: z.literal("unassigned"),
        location_id: id,
        status: z.enum(["HOLD", "CONFIRMED", "CANCELLED", "EXPIRED"]),
        booking_count: z.number().int().nonnegative(),
      }),
    ),
    excluded_business_ids: z.array(id).max(25),
    next_cursor: id.nullable(),
  })
  .refine(
    (p) =>
      unique(p.sources.map((s) => s.owner_business_id)) &&
      unique(p.excluded_business_ids) &&
      p.excluded_business_ids.every(
        (b) => !p.sources.some((s) => s.owner_business_id === b),
      ) &&
      p.items.every((i) =>
        p.sources.some(
          (s) =>
            s.owner_business_id === i.owner_business_id &&
            (s.location_id === null || s.location_id === i.location_id),
        ),
      ) &&
      unique(
        p.items.map(
          (i) => `${i.owner_business_id}:${i.location_id}:${i.status}`,
        ),
      ) &&
      Date.parse(p.until_at) > Date.parse(p.from_at),
  );
export type CompanyGroup = z.infer<typeof groupSchema>;
export type GroupPage = z.infer<typeof groupListSchema>;
export type GroupInvitation = z.infer<typeof invitationSchema>;
export type InvitationPage = z.infer<typeof invitationListSchema>;
export type GroupReport = z.infer<typeof groupReportSchema>;
export interface GroupInput {
  schema_version: 1;
  expected_revision: number;
  code: string;
  name: string;
}
export interface ConsentInput {
  schema_version: 1;
  expected_revision: number;
  state: "accepted" | "withdrawn";
}
