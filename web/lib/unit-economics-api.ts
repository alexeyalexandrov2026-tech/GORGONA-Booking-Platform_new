import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const unitEconomicsSchema = z.object({
  gross_revenue_cents: z.number().int(),
  bookings_count_30d: z.number().int(),
  material_cogs_cents: z.number().int(),
  net_margin_cents: z.number().int(),
  margin_percent: z.number().nullable(),
  average_ticket_cents: z.number().int().nullable(),
  currency: z.literal("USD"),
  window_days: z.number().int(),
});
export type UnitEconomics = z.infer<typeof unitEconomicsSchema>;

/** `null` when this backend does not provide the route yet (HTTP 404). */
export async function fetchUnitEconomics(
  businessId: string,
): Promise<UnitEconomics | null> {
  let response: Response;
  try {
    response = await authorizedResponse(
      `/v1/businesses/${encodeURIComponent(businessId)}/growth/unit-economics`,
      { headers: { Accept: "application/json" } },
    );
  } catch (error) {
    if (
      error instanceof ManagementApiError &&
      (error.status === 404 || error.status === 405)
    )
      return null;
    throw error;
  }
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  const parsed = unitEconomicsSchema.safeParse(data);
  if (!parsed.success)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unit economics returned incomplete information. Please retry.",
      response.status,
    );
  return parsed.data;
}

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export function formatUsdCents(cents: number): string {
  return usd.format(cents / 100);
}

const percent = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

export function formatMarginPercent(value: number | null): string {
  return value === null ? "—" : `${percent.format(value)}%`;
}
