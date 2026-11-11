// R8a (package R): the rental routes the catalogue, availability and booking screens use. Lists are
// read to their end through the server's cursor; a command keeps its Idempotency-Key until it
// succeeds, so a retry after a lost answer is the same request (ADR-0030).
import { ManagementApiError, managementFetch } from "./management-api";
import type {
  Assignment,
  AssignmentList,
  Availability,
  Booking,
  BookingList,
  ClassList,
  MeterKind,
  RentalClass,
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
