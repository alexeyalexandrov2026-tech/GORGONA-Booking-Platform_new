import { z } from "zod";

// PROPERTY-01 (catalog screen): strict response contracts of the internal catalog routes, the
// command body the screen sends and who sees which part of the screen. Times arrive in UTC.
const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
const revision = z.number().int().positive();

export const PROPERTY_KINDS = ["parcel", "building", "unit"] as const;
export type PropertyKind = (typeof PROPERTY_KINDS)[number];

export const propertyViewSchema = z.strictObject({
  schema_version: z.literal(1),
  object_id: id,
  location_id: id,
  kind: z.enum(PROPERTY_KINDS),
  name: z.string().min(1).max(200),
  parent_id: id.nullable(),
  revision,
  recorded_at: instant,
});
export const propertyRevisionSchema = propertyViewSchema.extend({
  recorded_by: id,
  owner_id: id.nullable(),
  manager_id: id.nullable(),
});
export const propertyListSchema = z.strictObject({
  schema_version: z.literal(1),
  items: z.array(propertyViewSchema),
  next_cursor: id.nullable(),
});
export const propertyHistorySchema = z.strictObject({
  schema_version: z.literal(1),
  items: z.array(propertyRevisionSchema),
  next_cursor: revision.nullable(),
});

export type PropertyView = z.infer<typeof propertyViewSchema>;
export type PropertyRevision = z.infer<typeof propertyRevisionSchema>;
export type PropertyList = z.infer<typeof propertyListSchema>;
export type PropertyHistory = z.infer<typeof propertyHistorySchema>;

const listingStates = ["draft", "published", "withdrawn"] as const;
export type ListingState = (typeof listingStates)[number];

export const listingViewSchema = z.strictObject({
  schema_version: z.literal(1),
  object_id: id,
  location_id: id,
  kind: z.enum(PROPERTY_KINDS),
  revision,
  state: z.enum(listingStates),
  headline: z.string().min(1).max(120),
  description: z.string().max(4000).nullable(),
  monthly_rent: z.number().int().min(1).max(1_000_000_000_000),
  currency: z.string().regex(/^[A-Z]{3}$/),
  available_from: z.iso.date(),
  recorded_at: instant,
});
const listingRevisionSchema = listingViewSchema.extend({ recorded_by: id });
export const showingViewSchema = z.strictObject({
  schema_version: z.literal(1),
  showing_id: id,
  object_id: id,
  location_id: id,
  host_resource_id: id.nullable(),
  starts_at: instant,
  ends_at: instant,
  recorded_at: instant,
  cancelled_at: instant.nullable(),
  status: z.enum(["active", "cancelled"]),
});
const showingListSchema = z.strictObject({
  schema_version: z.literal(1),
  items: z.array(showingViewSchema),
  next_cursor: id.nullable(),
});

export type ListingView = z.infer<typeof listingViewSchema>;
export type ListingRevision = z.infer<typeof listingRevisionSchema>;
export type ShowingView = z.infer<typeof showingViewSchema>;
export type ShowingList = z.infer<typeof showingListSchema>;
export type ListingBody = Pick<
  ListingView,
  | "schema_version"
  | "state"
  | "headline"
  | "description"
  | "monthly_rent"
  | "currency"
  | "available_from"
> & { expected_revision: number };
export type ShowingBody = Pick<
  ShowingView,
  "schema_version" | "object_id" | "host_resource_id" | "starts_at" | "ends_at"
> & { prospect_id: string };

const day = z.iso.date();
const documentReferenceSchema = z.strictObject({
  document_id: id,
  revision,
});
export const leaseViewSchema = z.strictObject({
  schema_version: z.literal(1),
  lease_id: id,
  object_id: id,
  agreement_id: id,
  agreement_revision: revision,
  document_id: id,
  document_revision: revision,
  signed_on: day,
  starts_on: day,
  ends_on: day,
  recorded_at: instant,
});
export const leaseListSchema = z.strictObject({
  schema_version: z.literal(1),
  items: z.array(leaseViewSchema),
  next_cursor: id.nullable(),
});
export const leaseTermSchema = z.strictObject({
  schema_version: z.literal(1),
  lease_id: id,
  revision,
  action: z.enum(["register", "extend", "release"]),
  agreement_revision: revision,
  document_id: id.nullable(),
  document_revision: revision.nullable(),
  terminated_on: day.nullable(),
  starts_on: day,
  ends_on: day.nullable(),
  recorded_at: instant,
});
export const leaseTermHistorySchema = z.strictObject({
  schema_version: z.literal(1),
  items: z.array(leaseTermSchema),
  next_before: revision.nullable(),
});
export const moveInSchema = z.strictObject({
  schema_version: z.literal(1),
  lease_id: id,
  term_revision: revision,
  moved_in_on: day,
  report: documentReferenceSchema,
  photos: z.array(documentReferenceSchema).min(1).max(50),
  recorded_by: id,
  recorded_at: instant,
});
export type LeaseView = z.infer<typeof leaseViewSchema>;
export type LeaseList = z.infer<typeof leaseListSchema>;
export type LeaseTerm = z.infer<typeof leaseTermSchema>;
export type LeaseTermHistory = z.infer<typeof leaseTermHistorySchema>;
export type MoveInView = z.infer<typeof moveInSchema>;
export type LeaseRegistration = {
  schema_version: 1;
  object_id: string;
  agreement_id: string;
  agreement_revision: number;
};
export type LeaseTermCommand = {
  schema_version: 1;
  action: "extend" | "release";
  expected_revision: number;
  agreement_revision: number;
};
export type MoveInCommand = {
  schema_version: 1;
  term_revision: number;
  moved_in_on: string;
  report: { document_id: string; revision: number };
  photos: { document_id: string; revision: number }[];
};

const routes: [RegExp, string[], z.ZodType][] = [
  [/^\/property\/leases$/i, ["GET"], leaseListSchema],
  [
    /^\/property\/leases\/[0-9a-f-]{36}\/terms$/i,
    ["GET"],
    leaseTermHistorySchema,
  ],
  [/^\/property\/leases\/[0-9a-f-]{36}\/terms$/i, ["POST"], leaseTermSchema],
  [
    /^\/property\/leases\/[0-9a-f-]{36}\/move-in$/i,
    ["GET", "PUT"],
    moveInSchema,
  ],
  [/^\/property\/leases\/[0-9a-f-]{36}$/i, ["GET", "PUT"], leaseViewSchema],
  [/^\/property\/listings\/[0-9a-f-]{36}$/i, ["GET"], listingViewSchema],
  [/^\/property\/listings\/[0-9a-f-]{36}$/i, ["PUT"], listingRevisionSchema],
  [/^\/property\/showings$/, ["GET"], showingListSchema],
  [/^\/property\/showings\/[0-9a-f-]{36}$/i, ["PUT"], showingViewSchema],
  [
    /^\/property\/showings\/[0-9a-f-]{36}\/cancel$/i,
    ["POST"],
    showingViewSchema,
  ],

  [/^\/property\/objects$/, ["GET"], propertyListSchema],
  [/^\/property\/objects\/[0-9a-f-]{36}$/i, ["GET"], propertyViewSchema],
  [/^\/property\/objects\/[0-9a-f-]{36}$/i, ["PUT"], propertyRevisionSchema],
  [
    /^\/property\/objects\/[0-9a-f-]{36}\/history$/i,
    ["GET"],
    propertyHistorySchema,
  ],
];

export function propertyResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  const path = suffix.split("?")[0] ?? "";
  for (const [pattern, methods, schema] of routes)
    if (pattern.test(path) && methods.includes(method)) return schema;
  return null;
}

type Member = {
  role: string;
  status: string;
  location_id?: string | null;
  delegation?: unknown;
};

/** Active owners and managers read the catalog of the branches they serve; delegates do not.
 * The server still decides every read; this only avoids a screen it refuses. */
export function canReadProperty(member: Member | undefined): boolean {
  return (
    member?.status === "active" &&
    !member.delegation &&
    ["owner", "manager"].includes(member.role)
  );
}

/** Writes and the private owner and manager history belong to company-wide owners and
 * managers (`property.manage`); a branch-scoped member sees catalog fields only. */
export function canManageProperty(member: Member | undefined): boolean {
  return canReadProperty(member) && member?.location_id == null;
}

/** A party select keeps the current value, clears it or names a counterparty. */
export const KEEP_PARTY = "";
export const NO_PARTY = "none";

/** Omitted keeps the stored party; null clears only that role (the server's contract). */
export function partyField(
  choice: string,
  isNew: boolean,
): string | null | undefined {
  if (choice === KEEP_PARTY) return undefined;
  if (choice === NO_PARTY) return isNew ? undefined : null;
  return choice;
}

export type PropertyBody = {
  schema_version: 1;
  expected_revision: number;
  location_id: string;
  kind: PropertyKind;
  name: string;
  parent_id: string | null;
  owner_id?: string | null;
  manager_id?: string | null;
};

export function propertyBody(input: {
  expectedRevision: number;
  locationId: string;
  kind: PropertyKind;
  name: string;
  parentId: string;
  owner: string;
  manager: string;
}): PropertyBody {
  const isNew = input.expectedRevision === 0;
  const body: PropertyBody = {
    schema_version: 1,
    expected_revision: input.expectedRevision,
    location_id: input.locationId,
    kind: input.kind,
    name: input.name.trim(),
    parent_id: input.kind === "parcel" ? null : input.parentId || null,
  };
  const owner = partyField(input.owner, isNew);
  if (owner !== undefined) body.owner_id = owner;
  const manager = partyField(input.manager, isNew);
  if (manager !== undefined) body.manager_id = manager;
  return body;
}

/** Who can be the parent: a building names a parcel, a unit names a building, both in the
 * same branch; a parcel has none. An object is never its own parent. */
export function parentOptions(
  items: PropertyView[],
  kind: PropertyKind,
  locationId: string,
  self?: string,
): PropertyView[] {
  const wanted =
    kind === "building" ? "parcel" : kind === "unit" ? "building" : null;
  if (!wanted || !locationId) return [];
  return items.filter(
    (item) =>
      item.kind === wanted &&
      item.location_id === locationId &&
      item.object_id !== self,
  );
}
