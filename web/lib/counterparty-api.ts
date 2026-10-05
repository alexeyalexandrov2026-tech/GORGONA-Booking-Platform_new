import { z } from "zod";
import { managementFetch, ManagementApiError } from "./management-api";
import {
  counterpartySchema,
  counterpartyListSchema,
  counterpartyHistorySchema,
  matchesSchema,
  matchDecisionSchema,
  matchDecisionListSchema,
  bookingCandidatesSchema,
  linkedBookingsSchema,
  bookingLinkHistorySchema,
  bookingLinkResultSchema,
  type CounterpartyCommand,
  type CounterpartyInput,
} from "./counterparty-contracts";

const base = (business: string) => `/v1/businesses/${business}/counterparties`;
async function read<
  T extends { business_id: string; counterparty_id?: string },
>(
  business: string,
  schema: z.ZodType<T>,
  path: string,
  subject?: string,
  init?: RequestInit,
): Promise<T> {
  const result = schema.parse(await managementFetch(path, init));
  if (
    result.business_id !== business ||
    (subject && result.counterparty_id !== subject)
  )
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this record safely.",
    );
  return result;
}

export function fetchCounterparties(
  business: string,
  q: string,
  state: string,
  after?: string,
) {
  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (state) query.set("state", state);
  if (after) query.set("after", after);
  return read(business, counterpartyListSchema, `${base(business)}?${query}`);
}
export async function fetchCounterparty(
  business: string,
  subject: string,
  revision?: number,
) {
  const result = await read(
    business,
    counterpartySchema,
    `${base(business)}/${subject}${revision ? `?revision=${revision}` : ""}`,
    subject,
  );
  if (revision && result.revision !== revision)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this saved version safely.",
    );
  return result;
}
export function fetchCounterpartyHistory(
  business: string,
  subject: string,
  before?: number,
) {
  return read(
    business,
    counterpartyHistorySchema,
    `${base(business)}/${subject}/versions${before ? `?before=${before}` : ""}`,
    subject,
  );
}
export function fetchCounterpartyFamily(
  business: string,
  subject: string,
  after?: string,
) {
  return read(
    business,
    counterpartyListSchema,
    `${base(business)}/${subject}/merged-from${after ? `?after=${after}` : ""}`,
  );
}
export function fetchCounterpartyDuplicates(business: string, subject: string) {
  return read(
    business,
    matchesSchema,
    `${base(business)}/${subject}/duplicates`,
  );
}
export function checkCounterpartyMatches(
  business: string,
  body: CounterpartyInput,
  exclude?: string,
) {
  return read(
    business,
    matchesSchema,
    `${base(business)}/match-check`,
    undefined,
    {
      method: "POST",
      body: JSON.stringify({
        schema_version: 1,
        display_name: body.display_name,
        tax_id: body.tax_id,
        registration_number: body.registration_number,
        exclude_id: exclude ?? null,
        emails: [body.email, ...body.contacts.map((c) => c.email)].filter(
          (x): x is string => Boolean(x),
        ),
        phones: [body.phone, ...body.contacts.map((c) => c.phone)].filter(
          (x): x is string => Boolean(x),
        ),
      }),
    },
  );
}
export function fetchCounterpartyDecisions(business: string, subject: string) {
  return read(
    business,
    matchDecisionListSchema,
    `${base(business)}/${subject}/match-decisions`,
    subject,
  );
}
export function fetchBookingCandidates(business: string, subject: string) {
  return read(
    business,
    bookingCandidatesSchema,
    `${base(business)}/${subject}/booking-candidates`,
    subject,
  );
}
export function fetchLinkedBookings(
  business: string,
  subject: string,
  after?: string,
) {
  return read(
    business,
    linkedBookingsSchema,
    `${base(business)}/${subject}/bookings${after ? `?after=${after}` : ""}`,
    subject,
  );
}
export function fetchBookingLinkHistory(
  business: string,
  subject: string,
  after?: string,
) {
  return read(
    business,
    bookingLinkHistorySchema,
    `${base(business)}/${subject}/booking-links${after ? `?after=${after}` : ""}`,
    subject,
  );
}
export function executeCounterpartyCommand(
  business: string,
  command: CounterpartyCommand,
) {
  const path = `${base(business)}/${command.id}`;
  const init = {
    body: JSON.stringify(command.body),
    headers: { "Idempotency-Key": command.key },
  };
  switch (command.type) {
    case "save":
      return read(business, counterpartySchema, path, command.id, {
        ...init,
        method: "PUT",
      });
    case "match":
      return read(
        business,
        matchDecisionSchema,
        `${path}/match-decisions`,
        command.id,
        { ...init, method: "POST" },
      );
    case "link":
      return read(
        business,
        bookingLinkResultSchema,
        `${path}/booking-links`,
        command.id,
        { ...init, method: "POST" },
      );
  }
}
