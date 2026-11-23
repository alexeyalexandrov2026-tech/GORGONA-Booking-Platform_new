import { expect, test } from "@playwright/test";
import {
  CareEncounterViewSchema,
  specializedResponseSchema,
} from "../lib/specialized-contracts";

const UID = "0196f800-0000-7000-8000-000000000001";
const NOW = "2026-10-10T12:00:00Z";

test("specializedResponseSchema routes all Stage 8 endpoints and rejects unknown paths", () => {
  expect(
    specializedResponseSchema("/special-venues/programs", "GET"),
  ).toBeTruthy();
  expect(
    specializedResponseSchema(`/special-venues/programs/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(
    specializedResponseSchema(`/special-venues/enrollments/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(specializedResponseSchema("/care/subjects", "GET")).toBeTruthy();
  expect(
    specializedResponseSchema(`/care/subjects/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(specializedResponseSchema("/care/consents", "GET")).toBeTruthy();
  expect(
    specializedResponseSchema(`/care/consents/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(specializedResponseSchema("/care/encounters", "GET")).toBeTruthy();
  expect(
    specializedResponseSchema(`/care/encounters/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(specializedResponseSchema("/assets/items", "GET")).toBeTruthy();
  expect(specializedResponseSchema(`/assets/items/${UID}`, "PUT")).toBeTruthy();
  expect(specializedResponseSchema("/assets/incidents", "GET")).toBeTruthy();
  expect(
    specializedResponseSchema(`/assets/incidents/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(specializedResponseSchema("/civic/programs", "GET")).toBeTruthy();
  expect(
    specializedResponseSchema(`/civic/programs/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(specializedResponseSchema("/civic/cases", "GET")).toBeTruthy();
  expect(specializedResponseSchema(`/civic/cases/${UID}`, "PUT")).toBeTruthy();
  expect(specializedResponseSchema("/civic/allocations", "GET")).toBeTruthy();
  expect(
    specializedResponseSchema(`/civic/allocations/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(specializedResponseSchema("/specialized/unknown", "GET")).toBeNull();
});

test("CareEncounterView allows redacted null clinical_notes when consent_active is false", () => {
  const redacted = CareEncounterViewSchema.parse({
    schema_version: 1,
    encounter_id: UID,
    location_id: UID,
    subject_id: UID,
    consent_id: UID,
    plan_id: null,
    encounter_date: "2026-11-01",
    summary: "Follow-up visit",
    clinical_notes: null,
    consent_active: false,
    recorded_by: UID,
    recorded_at: NOW,
  });
  expect(redacted.consent_active).toBe(false);
  expect(redacted.clinical_notes).toBeNull();
});
