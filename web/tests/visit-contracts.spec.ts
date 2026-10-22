import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";

// L7b1: the visit desk reads a completion, never through the plain booking contract.
const salon = "a1111111-1111-4111-8111-111111111111";
const booking = "b1111111-1111-4111-8111-111111111111";
const completion = {
  booking_id: booking,
  location_id: "c1111111-1111-4111-8111-111111111111",
  completed_at: "2026-10-22T15:00:00Z",
  completed_by: "d1111111-1111-4111-8111-111111111111",
  materials: [
    {
      item_id: "e1111111-1111-4111-8111-111111111111",
      planned: "2.5",
      actual: "3.0",
    },
  ],
  stock_document_id: null,
  consumption_posted_at: null,
};

test("completion, consumption and the completion read share one strict contract", () => {
  for (const [suffix, method] of [
    ["complete", "POST"],
    ["consumption", "POST"],
    ["completion", "GET"],
  ] as const) {
    const schema = managementResponseSchema(
      `/v1/salons/${salon}/bookings/${booking}/${suffix}`,
      method,
    );
    expect(schema.parse(completion)).toEqual(completion);
    expect(schema.safeParse({ ...completion, extra: true }).success).toBe(
      false,
    );
    expect(
      schema.safeParse({ ...completion, materials: [{ item_id: booking }] })
        .success,
    ).toBe(false);
  }
});
