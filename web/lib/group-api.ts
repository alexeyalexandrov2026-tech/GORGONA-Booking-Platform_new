import { managementFetch, ManagementApiError } from "./management-api";
import {
  groupListSchema,
  groupSchema,
  invitationListSchema,
  invitationSchema,
  groupReportSchema,
  type CompanyGroup,
  type GroupInput,
  type ConsentInput,
} from "./group-contracts";

function requireMatch(valid: boolean) {
  if (!valid)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to read these company records safely.",
    );
}
const base = (business: string) => `/v1/businesses/${business}`;
const groupPath = (business: string, group: string) =>
  `${base(business)}/groups/${group}`;
const mutation = (body: unknown, key: string) => ({
  method: "PUT",
  body: JSON.stringify(body),
  headers: { "Idempotency-Key": key },
});

export async function fetchGroups(business: string, after?: string) {
  const p = groupListSchema.parse(
    await managementFetch(
      `${base(business)}/groups${after ? `?after=${encodeURIComponent(after)}` : ""}`,
    ),
  );
  requireMatch(p.business_id === business);
  return p;
}
export async function fetchGroup(
  business: string,
  group: string,
  revision?: number,
): Promise<CompanyGroup> {
  const p = groupSchema.parse(
    await managementFetch(
      `${groupPath(business, group)}${revision ? `?revision=${revision}` : ""}`,
    ),
  );
  requireMatch(
    p.business_id === business &&
      p.group_id === group &&
      (revision === undefined || p.revision === revision),
  );
  return p;
}
export async function saveGroup(
  business: string,
  group: string,
  body: GroupInput,
  key: string,
) {
  const p = groupSchema.parse(
    await managementFetch(groupPath(business, group), mutation(body, key)),
  );
  requireMatch(p.business_id === business && p.group_id === group);
  return p;
}
export async function fetchGroupInvitations(
  business: string,
  group?: string,
  after?: string,
) {
  const path = group
    ? `${groupPath(business, group)}/invitations`
    : `${base(business)}/group-invitations`;
  const p = invitationListSchema.parse(
    await managementFetch(`${path}${after ? `?after=${after}` : ""}`),
  );
  requireMatch(
    p.business_id === business &&
      p.items.every((i) =>
        group
          ? i.operator_business_id === business && i.group_id === group
          : i.participant_business_id === business,
      ),
  );
  return p;
}
export async function inviteToGroup(
  business: string,
  group: string,
  invitation: string,
  participant: string,
  key: string,
) {
  // The field accepts either UUID letter case; server UUIDs use canonical lower case.
  const participantId = participant.toLowerCase();
  const p = invitationSchema.parse(
    await managementFetch(
      `${groupPath(business, group)}/invitations/${invitation}`,
      mutation(
        { schema_version: 1, participant_business_id: participantId },
        key,
      ),
    ),
  );
  requireMatch(
    p.business_id === business &&
      p.operator_business_id === business &&
      p.participant_business_id === participantId &&
      p.group_id === group &&
      p.invitation_id === invitation,
  );
  return p;
}
export async function confirmGroupConsent(
  business: string,
  invitation: string,
  body: ConsentInput,
  key: string,
) {
  const p = invitationSchema.parse(
    await managementFetch(
      `${base(business)}/group-invitations/${invitation}/consent`,
      mutation(body, key),
    ),
  );
  requireMatch(
    p.business_id === business &&
      p.participant_business_id === business &&
      p.invitation_id === invitation,
  );
  return p;
}
export async function withdrawGroupInvitation(
  business: string,
  group: string,
  invitation: string,
  body: ConsentInput,
  key: string,
) {
  const p = invitationSchema.parse(
    await managementFetch(
      `${groupPath(business, group)}/invitations/${invitation}/withdraw`,
      { ...mutation(body, key), method: "POST" },
    ),
  );
  requireMatch(
    p.business_id === business &&
      p.operator_business_id === business &&
      p.group_id === group &&
      p.invitation_id === invitation,
  );
  return p;
}
export async function fetchGroupReport(
  business: string,
  group: string,
  from: string,
  until: string,
  after?: string,
) {
  const query = new URLSearchParams({ from_at: from, until_at: until });
  if (after) query.set("after", after);
  const p = groupReportSchema.parse(
    await managementFetch(
      `${groupPath(business, group)}/booking-report?${query}`,
    ),
  );
  requireMatch(
    p.business_id === business &&
      p.group_id === group &&
      Date.parse(p.from_at) === Date.parse(from) &&
      Date.parse(p.until_at) === Date.parse(until),
  );
  return p;
}
