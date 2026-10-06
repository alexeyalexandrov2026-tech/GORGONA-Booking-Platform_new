import { z } from "zod";
import { managementFetch, ManagementApiError } from "./management-api";
import {
  reservationListSchema,
  reservationSchema,
  type ReservationCommand,
} from "./reservation-contracts";

const base = (business: string) =>
  `/v1/businesses/${business}/resource-reservations`;

async function read<T extends { business_id: string }>(
  business: string,
  schema: z.ZodType<T>,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const result = schema.parse(await managementFetch(path, init));
  if (result.business_id !== business)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load reservations safely.",
    );
  return result;
}

export function fetchReservations(
  business: string,
  starts: string,
  ends: string,
  location?: string,
) {
  const query = new URLSearchParams({ starts, ends });
  if (location) query.set("location_id", location);
  return read(business, reservationListSchema, `${base(business)}?${query}`);
}

export async function executeReservationCommand(
  business: string,
  command: ReservationCommand,
) {
  const path =
    command.type === "create"
      ? `${base(business)}/${command.id}`
      : `${base(business)}/${command.id}/cancel`;
  const result = await read(business, reservationSchema, path, {
    method: command.type === "create" ? "PUT" : "POST",
    body: JSON.stringify(command.body),
    headers: { "Idempotency-Key": command.key },
  });
  if (result.reservation_id !== command.id)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to confirm this reservation safely.",
    );
  return result;
}
