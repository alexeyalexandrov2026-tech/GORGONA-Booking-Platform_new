import { expect, test } from "@playwright/test";
import {
  ConsolidatedGroupReportViewSchema,
  enterpriseResponseSchema,
  formatEnterpriseMinor,
} from "../lib/enterprise-contracts";

const UID = "0196f800-0000-7000-8000-000000000001";
const NOW = "2026-10-10T12:00:00Z";

test("enterpriseResponseSchema routes all ENTERPRISE-01 endpoints and rejects unknown paths", () => {
  expect(
    enterpriseResponseSchema("/enterprise/sso-providers", "GET"),
  ).toBeTruthy();
  expect(
    enterpriseResponseSchema(`/enterprise/sso-providers/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(
    enterpriseResponseSchema("/enterprise/directory-links", "GET"),
  ).toBeTruthy();
  expect(
    enterpriseResponseSchema(`/enterprise/directory-links/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(
    enterpriseResponseSchema(
      `/enterprise/directory-links/${UID}/deprovision`,
      "POST",
    ),
  ).toBeTruthy();
  expect(
    enterpriseResponseSchema("/enterprise/lifecycle-events", "GET"),
  ).toBeTruthy();
  expect(
    enterpriseResponseSchema("/enterprise/group-report-grants", "GET"),
  ).toBeTruthy();
  expect(
    enterpriseResponseSchema(`/enterprise/group-report-grants/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(
    enterpriseResponseSchema(
      `/enterprise/group-report-snapshots/${UID}`,
      "PUT",
    ),
  ).toBeTruthy();
  expect(
    enterpriseResponseSchema(
      `/enterprise/groups/${UID}/consolidated-report?period_key=2026-10`,
      "GET",
    ),
  ).toBeTruthy();
  expect(enterpriseResponseSchema("/enterprise/unknown", "GET")).toBeNull();
});

test("ConsolidatedGroupReportView parses currency-separated totals and attributed entries", () => {
  const report = ConsolidatedGroupReportViewSchema.parse({
    schema_version: 1,
    group_id: UID,
    organizer_business_id: UID,
    period_key: "2026-10",
    entries: [
      {
        schema_version: 1,
        snapshot_id: UID,
        owner_business_id: UID,
        organizer_business_id: UID,
        group_id: UID,
        legal_entity_id: UID,
        period_key: "2026-10",
        currency: "USD",
        report_set: "revenue_by_currency",
        metric_count: 12,
        metric_amount_minor: 50000,
        notes: "Monthly total",
        recorded_by: UID,
        recorded_at: NOW,
      },
    ],
    totals_by_currency: [
      {
        currency: "USD",
        report_set: "revenue_by_currency",
        total_count: 12,
        total_amount_minor: 50000,
        contributing_businesses: 1,
      },
    ],
  });
  expect(report.totals_by_currency).toHaveLength(1);
  expect(formatEnterpriseMinor(50000, "USD")).toBe("500.00 USD");
});
