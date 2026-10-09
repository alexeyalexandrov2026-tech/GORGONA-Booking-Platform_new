import { test, expect } from "@playwright/test";
import {
  invoiceSchema,
  creditSchema,
  obligationSchema,
  settlementSchema,
  paymentSchema,
  financialOverviewSchema,
  financialCommandSchema,
  financialReferenceSchema,
  invoiceListSchema,
  obligationListSchema,
  newCreditDraftLine,
} from "../lib/financial-contracts";
import {
  financialRecoverySchema,
  financialReference,
  preserveFinancialRecovery,
  readFinancialRecovery,
  clearFinancialRecovery,
} from "../lib/financial-recovery";
import { parseFinancialResponse } from "../lib/financial-api";

const business = "00000000-0000-4000-8000-000000000001",
  book = "00000000-0000-4000-8000-000000000002",
  document = "00000000-0000-4000-8000-000000000003",
  account = "00000000-0000-4000-8000-000000000004",
  party = "00000000-0000-4000-8000-000000000005",
  line = "00000000-0000-4000-8000-000000000006",
  obligation = "00000000-0000-4000-8000-000000000007",
  actor = "00000000-0000-4000-8000-000000000008",
  entry = "00000000-0000-4000-8000-000000000009",
  settlement = "00000000-0000-4000-8000-000000000010",
  payment = "00000000-0000-4000-8000-000000000011";
const envelope = { schema_version: 1, business_id: business, book_id: book },
  instant = "2026-10-08T12:00:00Z",
  day = "2026-10-08";
const invoice = {
  ...envelope,
  document_id: document,
  kind: "invoice",
  revision: 2,
  state: "issued",
  direction: "receivable",
  counterparty_id: party,
  counterparty_revision: 1,
  currency: "USD",
  minor_units: 2,
  invoice_date: day,
  due_date: null,
  control_account_id: account,
  title: "FAKE fixture invoice",
  number: "FAKE-1",
  lines: [
    {
      line_id: line,
      counter_account_id: account,
      description: "FAKE service",
      amount: "90071992547409.93",
    },
  ],
  total: "90071992547409.93",
  entry_id: entry,
  obligation_id: obligation,
  issued_on: day,
  attestation: "confirmed_account_treatment",
  created_at: instant,
};
const claim = {
  ...envelope,
  obligation_id: obligation,
  source_kind: "invoice",
  source_id: document,
  source_revision: 2,
  component: "principal",
  counterparty_id: party,
  counterparty_revision: 1,
  direction: "receivable",
  currency: "USD",
  minor_units: 2,
  control_account_id: account,
  principal: "100.00",
  paid: "70.00",
  credited: "30.00",
  reserved: "0.00",
  available: "0.00",
  created_at: instant,
};
const credit = {
  ...envelope,
  document_id: document,
  revision: 2,
  state: "issued",
  credited_obligation_id: obligation,
  direction: "receivable",
  counterparty_id: party,
  counterparty_revision: 1,
  currency: "USD",
  minor_units: 2,
  credit_date: day,
  due_date: null,
  control_account_id: account,
  title: "FAKE credit",
  number: "FAKE-C1",
  lines: [
    {
      line_id: line,
      credited_line_id: line,
      counter_account_id: account,
      description: "FAKE partial credit",
      amount: "50.00",
      reason: null,
      reference_entry_id: null,
    },
  ],
  total: "50.00",
  entry_id: entry,
  issued_on: day,
  attestation: "confirmed_account_treatment",
  applied: "30.00",
  refund: "20.00",
  refund_control_account_id: account,
  refund_obligation_id: obligation,
  created_at: instant,
  void_entry_id: null,
  voided_on: null,
  void_reason: null,
  void_evidence_source: null,
};
const event = (
  sequence: number,
  kind: string,
  payment_id: string | null = null,
) => ({
  sequence,
  kind,
  payment_id,
  created_by: actor,
  created_at: instant,
  resolution: null,
  reason: null,
  evidence_source: null,
});
const settling = {
  ...envelope,
  settlement_id: settlement,
  sequence: 4,
  status: "sent",
  direction: "receivable",
  counterparty_id: party,
  currency: "USD",
  minor_units: 2,
  total: "100.00",
  confirmed: "0.00",
  reserved: "100.00",
  prepared_by: actor,
  approved_by: actor,
  approved_by_preparer: true,
  outcome_unresolved: true,
  allocations: [
    {
      obligation_id: obligation,
      amount: "100.00",
      confirmed: "0.00",
      reserved: "100.00",
    },
  ],
  events: [
    event(1, "prepared"),
    event(2, "approved"),
    event(3, "reserved"),
    event(4, "sent"),
  ],
  created_at: instant,
};
const external = {
  ...envelope,
  payment_id: payment,
  settlement_id: settlement,
  sequence: 5,
  direction: "receivable",
  currency: "USD",
  minor_units: 2,
  amount: "70.00",
  actual_external_date: day,
  entry_date: day,
  cash_account_id: account,
  source_account_alias: "FAKE bank",
  external_reference: "FAKE receipt",
  attestation: "manual_attestation",
  entry_id: entry,
  recorded_by: actor,
  recorded_at: instant,
  allocations: [{ obligation_id: obligation, amount: "70.00" }],
  state: "confirmed",
  revision: 1,
  effective_amount: "70.00",
  effective_allocations: [{ obligation_id: obligation, amount: "70.00" }],
  revisions: [],
};

test("financial invoices preserve exact money above safe integers", () => {
  expect(invoiceSchema.safeParse(invoice).success).toBe(true);
  expect(
    invoiceSchema.safeParse({ ...invoice, total: "90071992547409.92" }).success,
  ).toBe(false);
  expect(
    invoiceSchema.safeParse({ ...invoice, total: 90071992547409.93 }).success,
  ).toBe(false);
});
test("financial drafts cannot claim posted effects or unknown versions/kinds", () => {
  for (const patch of [
    { schema_version: 2 },
    { kind: "provider_charge" },
    { state: "draft" },
    { due_date: "2026-10-01" },
    { minor_units: 1 },
  ])
    expect(invoiceSchema.safeParse({ ...invoice, ...patch }).success).toBe(
      false,
    );
  expect(
    invoiceSchema.safeParse({ ...invoice, kind: "manual_accrual" }).success,
  ).toBe(true);
});
test("invoice line ids are unique and the currency scale is respected", () => {
  expect(
    invoiceSchema.safeParse({
      ...invoice,
      lines: [...invoice.lines, ...invoice.lines],
      total: "180143985094819.86",
    }).success,
  ).toBe(false);
  expect(invoiceSchema.safeParse({ ...invoice, minor_units: 0 }).success).toBe(
    false,
  );
  expect(
    invoiceSchema.safeParse({
      ...invoice,
      lines: [{ ...invoice.lines[0], amount: "0.00" }],
      total: "0.00",
    }).success,
  ).toBe(false);
});
test("obligation P+C+R cap and available balance fail closed", () => {
  expect(obligationSchema.safeParse(claim).success).toBe(true);
  for (const patch of [
    { reserved: "0.01" },
    { available: "1.00" },
    { paid: "70.001" },
    { source_kind: "payment" },
    { principal: "99.99" },
  ])
    expect(obligationSchema.safeParse({ ...claim, ...patch }).success).toBe(
      false,
    );
});
test("obligation list rejects duplicate source rows", () => {
  const item = obligationSchema.parse(claim);
  const { schema_version, business_id, book_id, ...summary } = item;
  expect(
    obligationListSchema.safeParse({
      schema_version,
      business_id,
      book_id,
      items: [summary, summary],
      next_cursor: null,
    }).success,
  ).toBe(false);
});
test("credit splits unpaid credit and a separate refund exactly", () => {
  expect(creditSchema.safeParse(credit).success).toBe(true);
  for (const patch of [
    { refund: "19.99" },
    { refund_obligation_id: null },
    { applied: null },
    { refund: "0.00", applied: "50.00" },
  ])
    expect(creditSchema.safeParse({ ...credit, ...patch }).success).toBe(false);
});
test("voided credit retains issued facts and requires all mirror evidence", () => {
  const voided = {
    ...credit,
    state: "voided",
    revision: 3,
    void_entry_id: entry,
    voided_on: day,
    void_reason: "FAKE mistake",
    void_evidence_source: "FAKE audit",
  };
  expect(creditSchema.safeParse(voided).success).toBe(true);
  expect(
    creditSchema.safeParse({ ...voided, void_entry_id: null }).success,
  ).toBe(false);
  expect(
    creditSchema.safeParse({ ...credit, void_reason: "FAKE" }).success,
  ).toBe(false);
});
test("credit accounts need reason for a cited entry and have 198-line maximum", () => {
  expect(
    creditSchema.safeParse({
      ...credit,
      lines: [{ ...credit.lines[0], reference_entry_id: entry }],
    }).success,
  ).toBe(false);
  const lines = Array.from({ length: 199 }, (_, i) => ({
    ...credit.lines[0],
    line_id: `00000000-0000-4000-8000-${String(i + 100).padStart(12, "0")}`,
  }));
  expect(
    creditSchema.safeParse({
      ...credit,
      lines,
      total: "9950.00",
      applied: "9930.00",
    }).success,
  ).toBe(false);
});
test("settlement reserved totals and sent unknown outcome match immutable history", () => {
  expect(settlementSchema.safeParse(settling).success).toBe(true);
  for (const patch of [
    { reserved: "99.99" },
    { outcome_unresolved: false },
    { status: "confirmed" },
    { approved_by_preparer: false },
    { sequence: 5 },
  ])
    expect(settlementSchema.safeParse({ ...settling, ...patch }).success).toBe(
      false,
    );
});
test("partial confirmation transfers exact reserve to confirmed and identifies its payment", () => {
  const partial = {
    ...settling,
    sequence: 5,
    status: "partially_confirmed",
    confirmed: "70.00",
    reserved: "30.00",
    allocations: [
      { ...settling.allocations[0], confirmed: "70.00", reserved: "30.00" },
    ],
    events: [...settling.events, event(5, "confirmed", payment)],
  };
  expect(settlementSchema.safeParse(partial).success).toBe(true);
  expect(
    settlementSchema.safeParse({
      ...partial,
      events: [...settling.events, event(5, "confirmed")],
    }).success,
  ).toBe(false);
  expect(
    settlementSchema.safeParse({ ...partial, confirmed: "70.01" }).success,
  ).toBe(false);
});
test("payment receipt is manual and exact effective allocations equal its money", () => {
  expect(paymentSchema.safeParse(external).success).toBe(true);
  for (const patch of [
    { attestation: "provider_verified" },
    { effective_amount: "69.99" },
    { state: "corrected" },
    { revision: 2 },
    { allocations: [{ obligation_id: obligation, amount: "69.00" }] },
  ])
    expect(paymentSchema.safeParse({ ...external, ...patch }).success).toBe(
      false,
    );
});
test("payment correction sequences strictly advance and void removes effective cash", () => {
  const correction = {
    revision: 2,
    sequence: 6,
    kind: "voided",
    amount: null,
    actual_external_date: null,
    entry_date: day,
    cash_account_id: null,
    attestation: "attested_erroneous_confirmation",
    reason: "FAKE error",
    evidence_source: "FAKE bank audit",
    reversal_entry_id: entry,
    entry_id: null,
    recorded_by: actor,
    recorded_at: instant,
    allocations: [],
  };
  const voided = {
    ...external,
    revision: 2,
    state: "voided",
    effective_amount: "0.00",
    effective_allocations: [],
    revisions: [correction],
  };
  expect(paymentSchema.safeParse(voided).success).toBe(true);
  expect(
    paymentSchema.safeParse({
      ...voided,
      revisions: [{ ...correction, sequence: 4 }],
    }).success,
  ).toBe(false);
  expect(
    paymentSchema.safeParse({
      ...voided,
      effective_allocations: external.allocations,
    }).success,
  ).toBe(false);
});
test("capability overview is finite, truthful and closed when blocked", () => {
  expect(
    financialOverviewSchema.safeParse({
      schema_version: 1,
      business_id: business,
      write_enabled: false,
      blocked_reason: "not_ready",
    }).success,
  ).toBe(true);
  expect(
    financialOverviewSchema.safeParse({
      schema_version: 1,
      business_id: business,
      write_enabled: true,
      blocked_reason: "not_ready",
    }).success,
  ).toBe(false);
  expect(
    financialOverviewSchema.safeParse({
      schema_version: 2,
      business_id: business,
      write_enabled: true,
      blocked_reason: null,
    }).success,
  ).toBe(false);
});
test("recovery references follow subject revision or settlement sequence and never bodies", () => {
  const command = financialCommandSchema.parse({
    book,
    subject: document,
    key: "FAKE-command-1",
    operation: "invoice_issue",
    body: {
      schema_version: 1,
      expected_revision: 1,
      entry_date: day,
      attestation: "confirmed_account_treatment",
    },
  });
  const reference = financialReference(command);
  expect(reference).toEqual({
    schema_version: 1,
    operation: "invoice_issue",
    book_id: book,
    subject_id: document,
    revision: 2,
  });
  const saved = {
    schema_version: 1,
    actor_id: actor,
    business_id: business,
    key: command.key,
    reference,
    saved_at: instant,
  };
  expect(financialRecoverySchema.safeParse(saved).success).toBe(true);
  for (const extra of [
    { body: command.body },
    { amount: "100.00" },
    { source_account_alias: "FAKE bank" },
    { token: "FAKE token" },
  ])
    expect(
      financialRecoverySchema.safeParse({ ...saved, ...extra }).success,
    ).toBe(false);
});
test("financial recovery operation and impossible first revisions reject", () => {
  for (const patch of [
    { operation: "pay_provider" },
    { operation: "settlement_prepare", revision: 2 },
    { operation: "credit_void", revision: 1 },
  ])
    expect(
      financialReferenceSchema.safeParse({
        schema_version: 1,
        book_id: book,
        subject_id: document,
        revision: 2,
        ...patch,
      }).success,
    ).toBe(false);
});
test("confirmation ids are explicit and sent release requires complete evidence", () => {
  const command = {
    book,
    subject: settlement,
    key: "FAKE-command-2",
    operation: "settlement_confirm",
    body: {
      schema_version: 1,
      expected_sequence: 4,
      amount: "70.00",
      actual_external_date: day,
      entry_date: day,
      cash_account_id: account,
      source_account_alias: "FAKE bank",
      external_reference: "FAKE receipt",
      attestation: "manual_attestation",
      allocations: [{ obligation_id: obligation, amount: "70.00" }],
    },
  };
  expect(financialCommandSchema.safeParse(command).success).toBe(false);
  expect(
    financialCommandSchema.safeParse({ ...command, payment }).success,
  ).toBe(true);
  expect(
    financialCommandSchema.safeParse({
      book,
      subject: settlement,
      key: "FAKE-command-3",
      operation: "settlement_release",
      body: {
        schema_version: 1,
        expected_sequence: 4,
        resolution: "attested_no_payment",
        reason: null,
        evidence_source: null,
      },
    }).success,
  ).toBe(false);
});
test("financial list envelopes are strict and duplicate documents fail", () => {
  const record = invoiceSchema.parse(invoice);
  const {
    schema_version,
    business_id,
    book_id,
    kind,
    counterparty_revision,
    minor_units,
    control_account_id,
    lines,
    issued_on,
    attestation,
    ...summary
  } = record;
  void kind;
  void counterparty_revision;
  void minor_units;
  void control_account_id;
  void lines;
  void issued_on;
  void attestation;
  expect(
    invoiceListSchema.safeParse({
      schema_version,
      business_id,
      book_id,
      items: [summary],
      next_cursor: null,
    }).success,
  ).toBe(true);
  expect(
    invoiceListSchema.safeParse({
      schema_version,
      business_id,
      book_id,
      items: [summary, summary],
      next_cursor: null,
    }).success,
  ).toBe(false);
});

test("API response context rejects foreign tenant and foreign financial book", () => {
  expect(
    parseFinancialResponse(invoiceSchema, invoice, business, book).document_id,
  ).toBe(document);
  expect(() =>
    parseFinancialResponse(
      invoiceSchema,
      { ...invoice, business_id: party },
      business,
      book,
    ),
  ).toThrow(/safely/);
  expect(() =>
    parseFinancialResponse(
      invoiceSchema,
      { ...invoice, book_id: party },
      business,
      book,
    ),
  ).toThrow(/safely/);
  expect(() =>
    parseFinancialResponse(
      financialOverviewSchema,
      {
        schema_version: 1,
        business_id: party,
        write_enabled: true,
        blocked_reason: null,
      },
      business,
    ),
  ).toThrow(/safely/);
});

test("session recovery binds actor business key and immutable reference without monetary body", () => {
  const values = new Map<string, string>();
  const store = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
  const descriptor = Object.getOwnPropertyDescriptor(
    globalThis,
    "sessionStorage",
  );
  Object.defineProperty(globalThis, "sessionStorage", {
    value: store,
    configurable: true,
  });
  try {
    const command = financialCommandSchema.parse({
      book,
      subject: document,
      key: "FAKE-command-1",
      operation: "invoice_issue",
      body: {
        schema_version: 1,
        expected_revision: 1,
        entry_date: day,
        attestation: "confirmed_account_treatment",
      },
    });
    preserveFinancialRecovery(actor, business, command);
    const serialized = Array.from(values.values())[0]!;
    expect(serialized).not.toContain("entry_date");
    expect(serialized).not.toContain("attestation");
    expect(serialized).not.toContain("body");
    expect(readFinancialRecovery(actor, business)?.reference.subject_id).toBe(
      document,
    );
    expect(readFinancialRecovery(party, business)).toBeNull();
    expect(() =>
      preserveFinancialRecovery(actor, business, {
        ...command,
        key: "FAKE-command-2",
      }),
    ).toThrow(/earlier/);
    clearFinancialRecovery(actor, business, "FAKE-command-2");
    expect(values.size).toBe(1);
    const storageKey = Array.from(values.keys())[0]!;
    store.setItem(
      storageKey,
      JSON.stringify({ ...JSON.parse(serialized), actor_id: party }),
    );
    expect(() => readFinancialRecovery(actor, business)).toThrow(/another/);
    store.setItem(storageKey, serialized);
    clearFinancialRecovery(actor, business, command.key);
    expect(values.size).toBe(0);
  } finally {
    if (descriptor)
      Object.defineProperty(globalThis, "sessionStorage", descriptor);
    else Reflect.deleteProperty(globalThis, "sessionStorage");
  }
});

test("historical invoice counter account cannot automatically become a new credit's current account", () => {
  const original = invoiceSchema.parse(invoice).lines[0]!;
  const draft = newCreditDraftLine(original);
  expect(draft.counter_account_id).toBe("");
  expect(draft.credited_line_id).toBe(original.line_id);
  expect(draft.amount).toBe("");
  expect(draft.reason).toBeNull();
  expect(draft.reference_entry_id).toBeNull();
  expect(draft.line_id).not.toBe(original.line_id);
  expect(original.counter_account_id).toBe(account);
  const another = newCreditDraftLine({
    ...original,
    counter_account_id: party,
  });
  expect(another.counter_account_id).toBe("");
  expect(another.line_id).not.toBe(draft.line_id);
});

test("financial text uses Unicode code-point bounds and rejects backend-forbidden control characters", () => {
  expect(
    invoiceSchema.safeParse({ ...invoice, title: "\u{1F600}".repeat(200) })
      .success,
  ).toBe(true);
  expect(
    invoiceSchema.safeParse({ ...invoice, title: "\u{1F600}".repeat(201) })
      .success,
  ).toBe(false);
  for (const title of [
    "FAKE\tcontrol",
    "FAKE\u0085control",
    "FAKE\u007Fcontrol",
  ])
    expect(invoiceSchema.safeParse({ ...invoice, title }).success).toBe(false);
});

test("void is at least the third credit version and a payment correction has positive real allocations", () => {
  const voided = {
    ...credit,
    state: "voided",
    revision: 2,
    void_entry_id: entry,
    voided_on: day,
    void_reason: "FAKE mistake",
    void_evidence_source: "FAKE audit",
  };
  expect(creditSchema.safeParse(voided).success).toBe(false);
  expect(creditSchema.safeParse({ ...voided, revision: 3 }).success).toBe(true);
  const correction = {
    revision: 2,
    sequence: 6,
    kind: "corrected",
    amount: "60.00",
    actual_external_date: day,
    entry_date: day,
    cash_account_id: account,
    attestation: "attested_erroneous_confirmation",
    reason: "FAKE correction",
    evidence_source: "FAKE audit",
    reversal_entry_id: entry,
    entry_id: entry,
    recorded_by: actor,
    recorded_at: instant,
    allocations: [{ obligation_id: obligation, amount: "60.00" }],
  };
  const corrected = {
    ...external,
    state: "corrected",
    revision: 2,
    effective_amount: "60.00",
    effective_allocations: correction.allocations,
    revisions: [correction],
  };
  expect(paymentSchema.safeParse(corrected).success).toBe(true);
  expect(
    paymentSchema.safeParse({
      ...corrected,
      effective_amount: "0.00",
      effective_allocations: [],
      revisions: [{ ...correction, amount: "0.00", allocations: [] }],
    }).success,
  ).toBe(false);
  expect(
    paymentSchema.safeParse({
      ...corrected,
      effective_allocations: [],
      revisions: [{ ...correction, allocations: [] }],
    }).success,
  ).toBe(false);
});
