// R8a (package R): the rental routes the catalogue, availability and booking screens use. Lists are
// read to their end through the server's cursor; a command keeps its Idempotency-Key until it
// succeeds, so a retry after a lost answer is the same request (ADR-0030).
import { ManagementApiError, managementFetch } from "./management-api";
import type {
  Assignment,
  AssignmentList,
  Agreement,
  Availability,
  Booking,
  BookingList,
  Charges,
  Inspections,
  Reconciliation,
  Settlement,
  Severity,
  Usage,
  ClassList,
  MeterKind,
  Quote,
  RateCard,
  RateCardList,
  RentalClass,
  Security,
  SecurityKind,
  SecurityMethod,
  Unit,
  UnitList,
} from "./rental-contracts";

/** The server's refusal, or what went wrong on the way, in words the screen can show. */
export function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

const base = (business: string) => `/v1/businesses/${business}/rental`;

async function readAll<T extends { next_cursor: string | null }, I>(
  path: string,
  items: (page: T) => I[],
): Promise<I[]> {
  const all: I[] = [];
  let after = "";
  for (;;) {
    const join = path.includes("?") ? "&" : "?";
    const page = await managementFetch<T>(
      after ? `${path}${join}after=${encodeURIComponent(after)}` : path,
    );
    all.push(...items(page));
    if (!page.next_cursor) return all;
    after = page.next_cursor;
  }
}

export const fetchClasses = (business: string) =>
  readAll<ClassList, RentalClass>(`${base(business)}/classes`, (p) => p.items);
export const fetchUnits = (business: string) =>
  readAll<UnitList, Unit>(`${base(business)}/units`, (p) => p.items);
export const fetchBookings = (business: string) =>
  readAll<BookingList, Booking>(`${base(business)}/bookings`, (p) => p.items);
export const fetchAssignments = (business: string, booking: string) =>
  managementFetch<AssignmentList>(
    `${base(business)}/bookings/${booking}/assignments`,
  );
export function fetchAvailability(
  business: string,
  query: {
    class_id: string;
    location_id: string;
    starts_at: string;
    ends_at: string;
  },
) {
  const params = new URLSearchParams(query);
  return managementFetch<Availability>(
    `${base(business)}/availability?${params}`,
  );
}

const pending = new Map<string, string>();
async function command<T>(
  path: string,
  method: string,
  body: unknown,
): Promise<T> {
  const payload = JSON.stringify(body);
  const signature = `${method} ${path} ${payload}`;
  let key = pending.get(signature);
  if (!key) {
    key = crypto.randomUUID();
    pending.set(signature, key);
  }
  const result = await managementFetch<T>(path, {
    method,
    body: payload,
    headers: { "Idempotency-Key": key },
  });
  pending.delete(signature);
  return result;
}

export type ClassBody = {
  schema_version: 1;
  expected_revision: number;
  code: string;
  name: string;
  meter_kind: MeterKind;
  attributes: RentalClass["attributes"];
};
export const saveClass = (business: string, id: string, body: ClassBody) =>
  command<RentalClass>(`${base(business)}/classes/${id}`, "PUT", body);

export type UnitBody = {
  schema_version: 1;
  expected_revision: number;
  class_id: string;
  identifier: string;
  location_id: string;
  state: Unit["state"];
  values: Record<string, string>;
};
export const saveUnit = (business: string, id: string, body: UnitBody) =>
  command<Unit>(`${base(business)}/units/${id}`, "PUT", body);

export type BookingBody = {
  schema_version: 1;
  class_id: string;
  customer_id: string;
  pickup_location_id: string;
  return_location_id: string;
  starts_at: string;
  ends_at: string;
  note: string | null;
};
export const book = (business: string, body: BookingBody) =>
  command<Booking>(`${base(business)}/bookings`, "POST", body);
export const cancelBooking = (
  business: string,
  booking: string,
  reason: string,
) =>
  command<Booking>(
    `${base(business)}/bookings/${booking}/cancellation`,
    "POST",
    {
      schema_version: 1,
      reason,
    },
  );
export const assignUnit = (business: string, booking: string, unit: string) =>
  command<Assignment>(
    `${base(business)}/bookings/${booking}/assignment`,
    "POST",
    {
      schema_version: 1,
      unit_id: unit,
    },
  );

// R8b (package R): rate cards, the quote, the agreement and the security.
export const fetchRateCards = (business: string, classId: string) =>
  managementFetch<RateCardList>(
    `${base(business)}/classes/${classId}/rate-cards`,
  );

export type RateCardBody = {
  schema_version: 1;
  location_id: string;
  currency: string;
  rates: { hour?: number; day?: number; week?: number; month?: number };
  meter_allowance_per_day: number | null;
  excess_rate: number | null;
  extras: [];
};
export const saveRateCard = (
  business: string,
  classId: string,
  body: RateCardBody,
) =>
  command<RateCard>(
    `${base(business)}/classes/${classId}/rate-cards`,
    "POST",
    body,
  );

/** A read that the server answers with NOT_FOUND while there is nothing yet. */
async function optional<T>(path: string): Promise<T | null> {
  try {
    return await managementFetch<T>(path);
  } catch (error) {
    if (error instanceof ManagementApiError && error.code === "NOT_FOUND")
      return null;
    throw error;
  }
}
export const fetchQuote = (business: string, booking: string) =>
  optional<Quote>(`${base(business)}/bookings/${booking}/quote`);
export const fetchAgreement = (business: string, booking: string) =>
  optional<Agreement>(`${base(business)}/bookings/${booking}/agreement`);
export const fetchSecurity = (business: string, booking: string) =>
  optional<Security>(`${base(business)}/bookings/${booking}/security`);

export type AcceptBody = {
  schema_version: 1;
  source: "paper" | "email";
  accepted_by: string;
  accepted_at: string;
  extras: [];
};
export const acceptAgreement = (
  business: string,
  booking: string,
  body: AcceptBody,
) =>
  command<Agreement>(
    `${base(business)}/bookings/${booking}/agreement`,
    "POST",
    body,
  );

export const requestSecurity = (
  business: string,
  booking: string,
  amount: number,
  method: SecurityMethod,
) =>
  command<Security>(`${base(business)}/bookings/${booking}/security`, "POST", {
    schema_version: 1,
    amount,
    method,
  });

export type SecurityEventBody = {
  schema_version: 1;
  kind: SecurityKind;
  amount: number;
  occurred_at: string;
  reference?: string;
  basis?: string;
};
export const recordSecurityEvent = (
  business: string,
  booking: string,
  body: SecurityEventBody,
) =>
  command<Security>(
    `${base(business)}/bookings/${booking}/security/events`,
    "POST",
    body,
  );

// R8c (package R): inspections, usage, the settlement, damage charges, refunds and the reconciliation.
export const fetchInspections = (business: string, booking: string) =>
  optional<Inspections>(`${base(business)}/bookings/${booking}/inspections`);
export const fetchUsage = (business: string, booking: string) =>
  optional<Usage>(`${base(business)}/bookings/${booking}/usage`);
export const fetchSettlement = (business: string, booking: string) =>
  optional<Settlement>(`${base(business)}/bookings/${booking}/settlement`);
export const fetchCharges = (business: string, booking: string) =>
  optional<Charges>(`${base(business)}/bookings/${booking}/charges`);
export const fetchReconciliation = (business: string, booking: string) =>
  optional<Reconciliation>(
    `${base(business)}/bookings/${booking}/reconciliation`,
  );

export type MarkBody = {
  area: string;
  severity: Severity;
  note?: string;
  new: boolean;
};
export type InspectionBody = {
  schema_version: 1;
  kind: "handover" | "return";
  meter?: number;
  level?: number;
  note?: string;
  marks: MarkBody[];
};
export const recordInspection = (
  business: string,
  booking: string,
  body: InspectionBody,
) =>
  command<Inspections>(
    `${base(business)}/bookings/${booking}/inspections`,
    "POST",
    body,
  );

/** The FIN-03 invoice a settlement or a damage charge drafts. */
export type InvoiceTerms = {
  book_id: string;
  receivable_account_id: string;
  revenue_account_id: string;
  invoice_date: string;
  due_date?: string;
  number: string;
};
export const settle = (
  business: string,
  booking: string,
  terms: InvoiceTerms,
) =>
  command<Settlement>(
    `${base(business)}/bookings/${booking}/settlement`,
    "POST",
    { schema_version: 1, ...terms },
  );
export const chargeDamage = (
  business: string,
  booking: string,
  body: { marks: number[]; amount: number; reason: string } & InvoiceTerms,
) =>
  command<Charges>(
    `${base(business)}/bookings/${booking}/damage-charges`,
    "POST",
    { schema_version: 1, ...body },
  );

export type RefundBody = {
  schema_version: 1;
  amount: number;
  reason: string;
} & (
  | { method: "external"; reference: string; refunded_at: string }
  | {
      method: "credit";
      invoice_document_id: string;
      credit_date: string;
      number: string;
    }
);
export const recordRefund = (
  business: string,
  booking: string,
  body: RefundBody,
) =>
  command<Charges>(
    `${base(business)}/bookings/${booking}/refunds`,
    "POST",
    body,
  );
