import { expect, test } from "@playwright/test";
import {
  agreementHistorySchema,
  agreementSchema,
  agreementListSchema,
  canDraftOrAgree,
  contractStatus,
  draftDocument,
} from "../lib/agreement-contracts";
import { managementResponseSchema } from "../lib/management-contracts";

const business = "00000000-0000-4000-8000-000000000001";
const subject = "00000000-0000-4000-8000-000000000002";
const partner = "00000000-0000-4000-8000-000000000003";
const draft = {
  schema_version: 1,
  business_id: business,
  agreement_id: subject,
  counterparty_id: partner,
  legal_entity_id: null,
  revision: 1,
  state: "draft",
  title: "FAKE Supply contract",
  number: null,
  summary: null,
  effective_from: "2026-01-01",
  effective_until: "2026-12-31",
  signed_on: null,
  attestation: null,
  document: null,
  terminated_on: null,
  in_force_revision: null,
  terminates_revision: null,
  created_at: "2026-10-05T12:00:00Z",
};
const agreed = {
  ...draft,
  revision: 2,
  state: "agreed",
  signed_on: "2026-10-01",
  attestation: "signed_outside_platform",
  in_force_revision: 2,
};
const amendment = { ...draft, revision: 3, in_force_revision: 2 };
const terminated = {
  ...agreed,
  state: "terminated",
  revision: 4,
  terminated_on: "2026-11-01",
  terminates_revision: 2,
};

test("a draft is never shown as signed and agreed versions are attested", () => {
  expect(agreementSchema.safeParse(draft).success).toBe(true);
  expect(agreementSchema.safeParse(agreed).success).toBe(true);
  expect(agreementSchema.safeParse(amendment).success).toBe(true);
  expect(agreementSchema.safeParse(terminated).success).toBe(true);
  // The version in force must be an earlier agreed revision; a termination names it.
  for (const invalid of [
    { ...agreed, in_force_revision: 1 },
    { ...agreed, terminates_revision: 2 },
    { ...amendment, in_force_revision: 3 },
    { ...amendment, terminates_revision: 2 },
    { ...terminated, terminates_revision: null },
    { ...terminated, in_force_revision: 3 },
    { ...terminated, terminates_revision: 4, in_force_revision: 4 },
  ])
    expect(agreementSchema.safeParse(invalid).success).toBe(false);
  for (const change of [
    { signed_on: "2026-10-01" },
    { attestation: "signed_outside_platform" },
    { state: "agreed" },
    { state: "signed" },
    { effective_from: "2027-01-01" },
    { title: "\u{1F600}".repeat(201) },
    { signature: "FAKE" },
  ])
    expect(agreementSchema.safeParse({ ...draft, ...change }).success).toBe(
      false,
    );
  expect(
    agreementSchema.safeParse({ ...agreed, attestation: "signed" }).success,
  ).toBe(false);
  expect(
    agreementSchema.safeParse({ ...agreed, terminated_on: "2026-10-02" })
      .success,
  ).toBe(false);
  expect(
    agreementSchema.safeParse({ ...draft, title: "\u{1F600}".repeat(200) })
      .success,
  ).toBe(true);
});

test("history rows keep the same state rules", () => {
  const row = {
    revision: 1,
    state: "draft",
    title: "FAKE",
    signed_on: null,
    terminated_on: null,
    abandoned: false,
    created_at: "2026-10-05T12:00:00Z",
  };
  const history = {
    schema_version: 1,
    business_id: business,
    agreement_id: subject,
    items: [row],
    next_cursor: null,
  };
  expect(agreementHistorySchema.safeParse(history).success).toBe(true);
  expect(
    agreementHistorySchema.safeParse({
      ...history,
      items: [{ ...row, signed_on: "2026-10-01" }],
    }).success,
  ).toBe(false);
  expect(
    agreementHistorySchema.safeParse({
      ...history,
      items: [{ ...row, abandoned: true }],
    }).success,
  ).toBe(true);
  expect(
    agreementHistorySchema.safeParse({
      ...history,
      items: [
        {
          ...row,
          state: "agreed",
          signed_on: "2026-10-01",
          abandoned: true,
        },
      ],
    }).success,
  ).toBe(false);
});

test("an agreed version stays in force until its termination takes effect", () => {
  const today = "2026-10-15";
  expect(contractStatus(draft, null, today)).toBe("draft");
  expect(contractStatus(agreed, agreed, today)).toBe("in_force");
  expect(contractStatus(amendment, agreed, today)).toBe(
    "in_force_amendment_draft",
  );
  // The term of the agreed version in force decides, not the draft's term.
  const longDraft = { ...amendment, effective_until: "2027-12-31" };
  const shortDraft = { ...amendment, effective_until: "2026-01-01" };
  const ended = { ...agreed, effective_until: "2026-10-14" };
  expect(contractStatus(longDraft, ended, today)).toBe("expired");
  expect(contractStatus(shortDraft, agreed, today)).toBe(
    "in_force_amendment_draft",
  );
  expect(contractStatus(terminated, agreed, today)).toBe(
    "termination_scheduled",
  );
  expect(contractStatus(terminated, agreed, "2026-11-01")).toBe("terminated");
  expect(contractStatus(terminated, agreed, "2026-12-01")).toBe("terminated");
  expect(
    contractStatus(agreed, { ...agreed, effective_until: "2026-10-14" }, today),
  ).toBe("expired");
  expect(
    contractStatus(agreed, { ...agreed, effective_until: "2026-10-15" }, today),
  ).toBe("in_force");
});

test("list rows describe the agreed version in force during an amendment", () => {
  const inForce = {
    revision: 2,
    title: "FAKE Supply contract",
    number: null,
    effective_from: "2026-01-01",
    effective_until: "2026-12-31",
    signed_on: "2026-10-01",
  };
  const row = {
    agreement_id: subject,
    counterparty_id: partner,
    revision: 3,
    state: "draft",
    title: "FAKE amended",
    number: null,
    effective_from: null,
    effective_until: "2027-12-31",
    terminated_on: null,
    in_force: inForce,
    updated_at: "2026-10-05T12:00:00Z",
  };
  const page = (items: object[]) => ({
    schema_version: 1,
    business_id: business,
    counterparty_id: partner,
    items,
    next_cursor: null,
  });
  expect(agreementListSchema.safeParse(page([row])).success).toBe(true);
  expect(
    agreementListSchema.safeParse(page([{ ...row, in_force: null }])).success,
  ).toBe(true);
  for (const invalid of [
    { ...row, in_force: { ...inForce, revision: 3 } },
    { ...row, state: "agreed" },
    { ...row, state: "terminated", terminated_on: "2026-09-01" },
    { ...row, in_force: { ...inForce, signed_on: null } },
  ])
    expect(agreementListSchema.safeParse(page([invalid])).success).toBe(false);
});

test("only the contract's own active card drafts or agrees; amendments drop the signed copy", () => {
  expect(canDraftOrAgree(null, partner, true)).toBe(true);
  expect(canDraftOrAgree(null, partner, false)).toBe(false);
  expect(canDraftOrAgree(amendment, partner, true)).toBe(true);
  // Listed through a merged duplicate: readable and terminable only.
  expect(canDraftOrAgree(amendment, business, true)).toBe(false);
  expect(canDraftOrAgree(terminated, partner, true)).toBe(false);
  const signed = { document_id: subject, revision: 1 };
  expect(draftDocument({ ...agreed, document: signed })).toBeNull();
  expect(draftDocument({ ...amendment, document: signed })).toEqual(signed);
  expect(draftDocument(null)).toBeNull();
});

test("contract routes have JSON contracts; unknown methods are refused", () => {
  const root = `/v1/businesses/${business}`;
  for (const [path, method] of [
    [`${root}/agreements/${subject}`, "GET"],
    [`${root}/agreements/${subject}`, "PUT"],
    [`${root}/agreements/${subject}/agree`, "POST"],
    [`${root}/agreements/${subject}/terminate`, "POST"],
  ] as const)
    expect(
      managementResponseSchema(path, method).safeParse(agreed).success,
    ).toBe(true);
  for (const [path, method] of [
    [`${root}/agreements/${subject}`, "DELETE"],
    [`${root}/agreements/${subject}/sign`, "POST"],
    [`${root}/counterparties/${partner}/agreements`, "POST"],
  ] as const)
    expect(() => managementResponseSchema(path, method)).toThrow(
      "Unrecognized business response contract",
    );
});
