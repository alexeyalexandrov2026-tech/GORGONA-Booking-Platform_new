import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  admissionInputSchema,
  admissionReferenceSchema,
  admissionViewSchema,
} from "../lib/admission-api";
const id = "00000000-0000-4000-8000-000000000001";
const input = {
  schema_version: 1,
  expected_revision: 0,
  provider: "stripe_connect",
  country: "US",
  business_activity: "FAKE test business",
  requested_operation: "charge",
  account_reference: "acct_FAKE",
  evidence_references: ["FAKE-EVIDENCE-1"],
  notes: null,
  assessment: "not_checked",
};
const { expected_revision: omittedRevision, ...metadata } = input;
void omittedRevision;
const view = {
  ...metadata,
  business_id: id,
  book_id: id,
  request_id: id,
  revision: 1,
  state: "draft",
  evidence_status: "manually_provided_unverified",
  operational_capabilities: {
    charge: false,
    refund: false,
    transfer: false,
    payout: false,
  },
  created_at: "2026-10-09T00:00:00Z",
};
test("admission response never grants a provider capability", () => {
  expect(admissionViewSchema.safeParse(view).success).toBe(true);
  for (const capability of ["charge", "refund", "transfer", "payout"]) {
    expect(
      admissionViewSchema.safeParse({
        ...view,
        operational_capabilities: {
          ...view.operational_capabilities,
          [capability]: true,
        },
      }).success,
    ).toBe(false);
  }
  for (const assessment of ["approved", "test_access", "verified"])
    expect(admissionViewSchema.safeParse({ ...view, assessment }).success).toBe(
      false,
    );
  expect(
    admissionViewSchema.safeParse({ ...view, state: "active" }).success,
  ).toBe(false);
  expect(
    admissionViewSchema.safeParse({ ...view, schema_version: 2 }).success,
  ).toBe(false);
});
test("declared metadata and finite recovery references remain separate", () => {
  expect(admissionInputSchema.safeParse(input).success).toBe(true);
  expect(
    admissionInputSchema.safeParse({ ...input, api_key: "FAKE" }).success,
  ).toBe(false);
  const reference = {
    schema_version: 1,
    operation: "admission_draft",
    book_id: id,
    subject_id: id,
    revision: 1,
  };
  expect(admissionReferenceSchema.safeParse(reference).success).toBe(true);
  expect(
    admissionReferenceSchema.safeParse({
      ...reference,
      account_reference: "acct_FAKE",
    }).success,
  ).toBe(false);
  expect(
    admissionReferenceSchema.safeParse({
      ...reference,
      operation: "provider_activate",
    }).success,
  ).toBe(false);
});

test("shared transport recognizes only finite admission and financial operations", () => {
  for (const [suffix, method] of [
    [`provider-admission/books/${id}/requests`, "GET"],
    [`provider-admission/books/${id}/requests/${id}`, "PUT"],
    [`provider-admission/books/${id}/requests/${id}/submit`, "POST"],
    ["financial-documents/overview", "GET"],
    [`financial-documents/books/${id}/invoices/${id}`, "PUT"],
    [
      `financial-documents/books/${id}/settlements/${id}/confirmations/${id}/correct`,
      "POST",
    ],
  ]) {
    expect(() =>
      managementResponseSchema(`/v1/businesses/${id}/${suffix}`, method!),
    ).not.toThrow();
  }
  for (const suffix of [
    `provider-admission/books/${id}/requests/${id}/approve`,
    `financial-documents/books/${id}/payments/${id}/refund`,
  ])
    expect(() =>
      managementResponseSchema(`/v1/businesses/${id}/${suffix}`, "POST"),
    ).toThrow();
});
