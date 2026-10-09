import { z } from "zod";
import { minorUnits } from "./ledger-contracts";

const id = z.uuid();
const rev = z.number().int().min(1).max(2147483647);
const expected = z.number().int().min(0).max(2147483646);
const instant = z.iso.datetime({ offset: true });
const day = z.iso.date();
const currency = z.string().regex(/^[A-Z]{3}$/);
const scale = z.union([z.literal(0), z.literal(2), z.literal(3)]);
const amount = z
  .string()
  .max(64)
  .regex(/^(0|[1-9]\d*)(\.\d{1,3})?$/);
const inputAmount = z
  .string()
  .max(24)
  .regex(/^(0|[1-9]\d{0,17})(\.\d{1,3})?$/);
const text = (max: number) =>
  z
    .string()
    .refine(
      (v) =>
        Array.from(v).length <= max &&
        v.trim().length > 0 &&
        !Array.from(v).some(
          (c) =>
            c.charCodeAt(0) < 32 ||
            (c.charCodeAt(0) >= 127 && c.charCodeAt(0) <= 159),
        ),
    );
const direction = z.enum(["receivable", "payable"]);
const envelope = { schema_version: z.literal(1), business_id: id, book_id: id };
const unique = <T>(items: T[], key: (value: T) => string) =>
  new Set(items.map(key)).size === items.length;
const sum = (items: string[], places: number) =>
  items.reduce<bigint | null>((result, value) => {
    const n = minorUnits(value, places);
    return result === null || n === null ? null : result + n;
  }, 0n);
const positiveLines = (lines: { amount: string }[], places: number) =>
  lines.every((v) => (minorUnits(v.amount, places) ?? 0n) > 0n);

export const financialOverviewSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    write_enabled: z.boolean(),
    blocked_reason: z.enum(["not_ready", "module_disabled"]).nullable(),
  })
  .refine((v) => v.write_enabled === (v.blocked_reason === null));
const invoiceLine = z.strictObject({
  line_id: id,
  counter_account_id: id,
  description: text(500),
  amount: inputAmount,
});
export const invoiceDraftSchema = z
  .strictObject({
    schema_version: z.literal(1),
    expected_revision: expected,
    direction,
    counterparty_id: id,
    counterparty_revision: rev.max(2147483646),
    currency,
    invoice_date: day,
    due_date: day.nullable(),
    control_account_id: id,
    title: text(200),
    number: text(64),
    lines: z.array(invoiceLine).min(1).max(199),
  })
  .refine(
    (v) =>
      (!v.due_date || v.due_date >= v.invoice_date) &&
      unique(v.lines, (x) => x.line_id),
  );
export const invoiceIssueSchema = z.strictObject({
  schema_version: z.literal(1),
  expected_revision: expected.min(1),
  entry_date: day,
  attestation: z.literal("confirmed_account_treatment"),
});
const invoiceRecord = z.strictObject({
  ...envelope,
  document_id: id,
  kind: z.enum(["invoice", "manual_accrual"]),
  revision: rev,
  state: z.enum(["draft", "issued"]),
  direction,
  counterparty_id: id,
  counterparty_revision: rev,
  currency,
  minor_units: scale,
  invoice_date: day,
  due_date: day.nullable(),
  control_account_id: id,
  title: text(200),
  number: text(64),
  lines: z.array(invoiceLine).min(1).max(199),
  total: amount,
  entry_id: id.nullable(),
  obligation_id: id.nullable(),
  issued_on: day.nullable(),
  attestation: z.literal("confirmed_account_treatment").nullable(),
  created_at: instant,
});
export const invoiceSchema = invoiceRecord.refine(
  (v) =>
    (!v.due_date || v.due_date >= v.invoice_date) &&
    unique(v.lines, (x) => x.line_id) &&
    positiveLines(v.lines, v.minor_units) &&
    sum(
      v.lines.map((x) => x.amount),
      v.minor_units,
    ) === minorUnits(v.total, v.minor_units) &&
    [v.entry_id, v.obligation_id, v.issued_on, v.attestation].every(
      (x) => (x !== null) === (v.state === "issued"),
    ) &&
    (v.state !== "issued" || v.revision >= 2),
);
const invoiceSummary = invoiceRecord
  .omit({
    schema_version: true,
    business_id: true,
    book_id: true,
    kind: true,
    counterparty_revision: true,
    minor_units: true,
    control_account_id: true,
    lines: true,
    issued_on: true,
    attestation: true,
  })
  .refine(
    (v) =>
      (!v.due_date || v.due_date >= v.invoice_date) &&
      [v.entry_id, v.obligation_id].every(
        (x) => (x !== null) === (v.state === "issued"),
      ),
  );
export const invoiceListSchema = z
  .strictObject({
    ...envelope,
    items: z.array(invoiceSummary).max(100),
    next_cursor: id.nullable(),
  })
  .refine((v) => unique(v.items, (x) => x.document_id));

const creditLine = z
  .strictObject({
    line_id: id,
    credited_line_id: id,
    counter_account_id: id,
    description: text(500),
    amount: inputAmount,
    reason: text(500).nullable(),
    reference_entry_id: id.nullable(),
  })
  .refine((v) => v.reference_entry_id === null || v.reason !== null);
export const creditDraftSchema = z
  .strictObject({
    schema_version: z.literal(1),
    expected_revision: expected,
    credited_obligation_id: id,
    counterparty_revision: rev.max(2147483646),
    credit_date: day,
    due_date: day.nullable(),
    title: text(200),
    number: text(64),
    lines: z.array(creditLine).min(1).max(198),
  })
  .refine(
    (v) =>
      (!v.due_date || v.due_date >= v.credit_date) &&
      unique(v.lines, (x) => x.line_id),
  );
export const creditIssueSchema = invoiceIssueSchema.extend({
  refund_control_account_id: id.nullable(),
});
export const creditVoidSchema = z.strictObject({
  schema_version: z.literal(1),
  expected_revision: expected.min(2),
  entry_date: day,
  attestation: z.literal("attested_erroneous_credit"),
  reason: text(500),
  evidence_source: text(200),
});
const creditRecord = z.strictObject({
  ...envelope,
  document_id: id,
  revision: rev,
  state: z.enum(["draft", "issued", "voided"]),
  credited_obligation_id: id,
  direction,
  counterparty_id: id,
  counterparty_revision: rev,
  currency,
  minor_units: scale,
  credit_date: day,
  due_date: day.nullable(),
  control_account_id: id,
  title: text(200),
  number: text(64),
  lines: z.array(creditLine).min(1).max(198),
  total: amount,
  entry_id: id.nullable(),
  issued_on: day.nullable(),
  attestation: z.literal("confirmed_account_treatment").nullable(),
  applied: amount.nullable(),
  refund: amount.nullable(),
  refund_control_account_id: id.nullable(),
  refund_obligation_id: id.nullable(),
  created_at: instant,
  void_entry_id: id.nullable(),
  voided_on: day.nullable(),
  void_reason: text(500).nullable(),
  void_evidence_source: text(200).nullable(),
});
export const creditSchema = creditRecord.refine((v) => {
  if (
    (!v.due_date || v.due_date >= v.credit_date) === false ||
    !unique(v.lines, (x) => x.line_id) ||
    !positiveLines(v.lines, v.minor_units) ||
    sum(
      v.lines.map((x) => x.amount),
      v.minor_units,
    ) !== minorUnits(v.total, v.minor_units)
  )
    return false;
  if (
    ![
      v.void_entry_id,
      v.voided_on,
      v.void_reason,
      v.void_evidence_source,
    ].every((x) => (x !== null) === (v.state === "voided"))
  )
    return false;
  const issued = [v.entry_id, v.issued_on, v.attestation, v.applied, v.refund];
  if (v.state === "draft")
    return [
      ...issued,
      v.refund_control_account_id,
      v.refund_obligation_id,
    ].every((x) => x === null);
  if (v.state === "voided" && v.revision < 3) return false;
  const a = v.applied === null ? null : minorUnits(v.applied, v.minor_units),
    r = v.refund === null ? null : minorUnits(v.refund, v.minor_units);
  return (
    v.revision >= 2 &&
    issued.every((x) => x !== null) &&
    a !== null &&
    r !== null &&
    a + r === minorUnits(v.total, v.minor_units) &&
    [v.refund_control_account_id, v.refund_obligation_id].every(
      (x) => (x !== null) === r > 0n,
    )
  );
});
const creditSummary = creditRecord.omit({
  schema_version: true,
  business_id: true,
  book_id: true,
  counterparty_revision: true,
  minor_units: true,
  due_date: true,
  control_account_id: true,
  lines: true,
  issued_on: true,
  attestation: true,
  refund_control_account_id: true,
  void_entry_id: true,
  void_reason: true,
  void_evidence_source: true,
});
export const creditListSchema = z
  .strictObject({
    ...envelope,
    items: z.array(creditSummary).max(100),
    next_cursor: id.nullable(),
  })
  .refine((v) => unique(v.items, (x) => x.document_id));

const obligationRecord = z.strictObject({
  obligation_id: id,
  source_kind: z.enum(["invoice", "manual", "credit_refund"]),
  source_id: id,
  source_revision: rev,
  component: z.literal("principal"),
  counterparty_id: id,
  counterparty_revision: rev,
  direction,
  currency,
  minor_units: scale,
  control_account_id: id,
  principal: amount,
  paid: amount,
  credited: amount,
  reserved: amount,
  available: amount,
  created_at: instant,
});
const validObligation = (v: z.infer<typeof obligationRecord>) => {
  const values = [v.principal, v.paid, v.credited, v.reserved, v.available].map(
    (x) => minorUnits(x, v.minor_units),
  );
  const [a, p, c, r, available] = values;
  return (
    values.every((x) => x !== null) &&
    a !== undefined &&
    a !== null &&
    a > 0n &&
    p !== undefined &&
    p !== null &&
    c !== undefined &&
    c !== null &&
    r !== undefined &&
    r !== null &&
    available !== undefined &&
    available !== null &&
    p + c + r <= a &&
    a - p - c - r === available
  );
};
export const obligationSchema = obligationRecord
  .extend(envelope)
  .refine(validObligation);
export const obligationListSchema = z
  .strictObject({
    ...envelope,
    items: z.array(obligationRecord.refine(validObligation)).max(100),
    next_cursor: id.nullable(),
  })
  .refine((v) => unique(v.items, (x) => x.obligation_id));
const allocationInput = z.strictObject({
  obligation_id: id,
  amount: inputAmount,
});
const allocations = z
  .array(allocationInput)
  .min(1)
  .max(50)
  .refine((v) => unique(v, (x) => x.obligation_id));
export const settlementPrepareSchema = z.strictObject({
  schema_version: z.literal(1),
  expected_sequence: z.literal(0),
  direction,
  counterparty_id: id,
  currency,
  allocations,
});
export const settlementActionSchema = z.strictObject({
  schema_version: z.literal(1),
  expected_sequence: expected.min(1),
});
export const settlementReleaseSchema = settlementActionSchema
  .extend({
    resolution: z.literal("attested_no_payment").nullable(),
    reason: text(500).nullable(),
    evidence_source: text(200).nullable(),
  })
  .refine((v) =>
    v.resolution === null
      ? v.reason === null && v.evidence_source === null
      : v.reason !== null && v.evidence_source !== null,
  );
export const settlementCancelSchema = settlementActionSchema.extend({
  reason: text(500).nullable(),
});
export const paymentConfirmSchema = settlementActionSchema.extend({
  amount: inputAmount,
  actual_external_date: day,
  entry_date: day,
  cash_account_id: id,
  source_account_alias: text(100),
  external_reference: text(200),
  attestation: z.literal("manual_attestation"),
  allocations,
});
export const paymentVoidSchema = settlementActionSchema.extend({
  attestation: z.literal("attested_erroneous_confirmation"),
  entry_date: day,
  reason: text(500),
  evidence_source: text(200),
});
export const paymentCorrectSchema = paymentVoidSchema.extend({
  amount: inputAmount,
  actual_external_date: day,
  cash_account_id: id,
  allocations,
});
const settlementStatus = z.enum([
  "prepared",
  "approved",
  "reserved",
  "sent",
  "partially_confirmed",
  "confirmed",
  "released",
  "cancelled",
]);
const event = z.strictObject({
  sequence: rev,
  kind: z.enum([
    "prepared",
    "approved",
    "reserved",
    "sent",
    "confirmed",
    "released",
    "cancelled",
    "payment_voided",
    "payment_corrected",
  ]),
  created_by: id,
  created_at: instant,
  resolution: z.literal("attested_no_payment").nullable(),
  reason: text(500).nullable(),
  evidence_source: text(200).nullable(),
  payment_id: id.nullable(),
});
const settlementRecord = z.strictObject({
  ...envelope,
  settlement_id: id,
  sequence: rev,
  status: settlementStatus,
  direction,
  counterparty_id: id,
  currency,
  minor_units: scale,
  total: amount,
  confirmed: amount,
  reserved: amount,
  prepared_by: id,
  approved_by: id.nullable(),
  approved_by_preparer: z.boolean().nullable(),
  outcome_unresolved: z.boolean(),
  allocations: z
    .array(
      z.strictObject({
        obligation_id: id,
        amount,
        confirmed: amount,
        reserved: amount,
      }),
    )
    .min(1)
    .max(50),
  events: z.array(event).min(1),
  created_at: instant,
});
export const settlementSchema = settlementRecord.refine((v) => {
  const total = minorUnits(v.total, v.minor_units),
    confirmed = minorUnits(v.confirmed, v.minor_units),
    reserved = minorUnits(v.reserved, v.minor_units);
  const phase = (
    [
      "cancelled",
      "released",
      "sent",
      "reserved",
      "approved",
      "prepared",
    ] as const
  ).find((kind) => v.events.some((x) => x.kind === kind));
  if (!phase || total === null || confirmed === null || reserved === null)
    return false;
  const holding = phase === "reserved" || phase === "sent";
  const status =
    holding && confirmed > 0n
      ? confirmed === total
        ? "confirmed"
        : "partially_confirmed"
      : phase;
  if (
    v.status !== status ||
    v.outcome_unresolved !== (phase === "sent" && confirmed < total) ||
    reserved !== (holding ? total - confirmed : 0n)
  )
    return false;
  return (
    total !== null &&
    total > 0n &&
    confirmed !== null &&
    reserved !== null &&
    confirmed + reserved <= total &&
    unique(v.allocations, (x) => x.obligation_id) &&
    positiveLines(v.allocations, v.minor_units) &&
    sum(
      v.allocations.map((x) => x.amount),
      v.minor_units,
    ) === total &&
    sum(
      v.allocations.map((x) => x.confirmed),
      v.minor_units,
    ) === confirmed &&
    sum(
      v.allocations.map((x) => x.reserved),
      v.minor_units,
    ) === reserved &&
    v.allocations.every((x) => {
      const a = minorUnits(x.amount, v.minor_units),
        p = minorUnits(x.confirmed, v.minor_units),
        r = minorUnits(x.reserved, v.minor_units);
      return a !== null && p !== null && r !== null && p + r <= a;
    }) &&
    v.events.length === v.sequence &&
    v.events.every(
      (x, i) =>
        x.sequence === i + 1 &&
        (x.payment_id !== null) ===
          ["confirmed", "payment_voided", "payment_corrected"].includes(x.kind),
    ) &&
    v.events[0]?.kind === "prepared" &&
    (v.approved_by === null
      ? v.approved_by_preparer === null
      : v.approved_by_preparer === (v.approved_by === v.prepared_by))
  );
});
const settlementSummary = settlementRecord.omit({
  schema_version: true,
  business_id: true,
  book_id: true,
  minor_units: true,
  prepared_by: true,
  approved_by: true,
  approved_by_preparer: true,
  outcome_unresolved: true,
  allocations: true,
  events: true,
});
export const settlementListSchema = z
  .strictObject({
    ...envelope,
    items: z.array(settlementSummary).max(100),
    next_cursor: id.nullable(),
  })
  .refine((v) => unique(v.items, (x) => x.settlement_id));
const paymentAllocation = z.strictObject({ obligation_id: id, amount });
const paymentRevision = z.strictObject({
  revision: rev.min(2),
  sequence: rev,
  kind: z.enum(["voided", "corrected"]),
  amount: amount.nullable(),
  actual_external_date: day.nullable(),
  entry_date: day,
  cash_account_id: id.nullable(),
  attestation: z.literal("attested_erroneous_confirmation"),
  reason: text(500),
  evidence_source: text(200),
  reversal_entry_id: id,
  entry_id: id.nullable(),
  recorded_by: id,
  recorded_at: instant,
  allocations: z.array(paymentAllocation).max(50),
});
const paymentRecord = z.strictObject({
  ...envelope,
  payment_id: id,
  settlement_id: id,
  sequence: rev,
  direction,
  currency,
  minor_units: scale,
  amount,
  actual_external_date: day,
  entry_date: day,
  cash_account_id: id,
  source_account_alias: text(100),
  external_reference: text(200),
  attestation: z.literal("manual_attestation"),
  entry_id: id,
  recorded_by: id,
  recorded_at: instant,
  allocations: z.array(paymentAllocation).min(1).max(50),
  state: z.enum(["confirmed", "corrected", "voided"]),
  revision: rev,
  effective_amount: amount,
  effective_allocations: z.array(paymentAllocation).max(50),
  revisions: z.array(paymentRevision),
});
export const paymentSchema = paymentRecord.refine((v) => {
  const valid = (
    a: { obligation_id: string; amount: string }[],
    total: string,
  ) =>
    unique(a, (x) => x.obligation_id) &&
    positiveLines(a, v.minor_units) &&
    sum(
      a.map((x) => x.amount),
      v.minor_units,
    ) === minorUnits(total, v.minor_units);
  if (
    !valid(v.allocations, v.amount) ||
    !valid(v.effective_allocations, v.effective_amount) ||
    v.revisions.length !== v.revision - 1
  )
    return false;
  if (
    !v.revisions.every(
      (x, i) =>
        x.revision === i + 2 &&
        (i === 0 || v.revisions[i - 1]!.kind !== "voided") &&
        x.sequence > (i === 0 ? v.sequence : v.revisions[i - 1]!.sequence) &&
        (x.kind === "voided"
          ? x.amount === null &&
            x.actual_external_date === null &&
            x.cash_account_id === null &&
            x.entry_id === null &&
            x.allocations.length === 0
          : x.amount !== null &&
            (minorUnits(x.amount, v.minor_units) ?? 0n) > 0n &&
            x.allocations.length > 0 &&
            x.actual_external_date !== null &&
            x.cash_account_id !== null &&
            x.entry_id !== null &&
            valid(x.allocations, x.amount)),
    )
  )
    return false;
  const latest = v.revisions.at(-1);
  const effective =
    latest?.kind === "voided" ? "0" : (latest?.amount ?? v.amount);
  const effectiveLines = latest ? latest.allocations : v.allocations;
  return (
    v.state === (latest?.kind ?? "confirmed") &&
    minorUnits(v.effective_amount, v.minor_units) ===
      minorUnits(effective, v.minor_units) &&
    v.effective_allocations.length === effectiveLines.length &&
    v.effective_allocations.every(
      (x, i) =>
        x.obligation_id === effectiveLines[i]?.obligation_id &&
        minorUnits(x.amount, v.minor_units) ===
          minorUnits(effectiveLines[i]!.amount, v.minor_units),
    )
  );
});

export const financialOperationSchema = z.enum([
  "invoice_draft",
  "invoice_issue",
  "accrual_draft",
  "accrual_issue",
  "credit_draft",
  "credit_issue",
  "credit_void",
  "settlement_prepare",
  "settlement_approve",
  "settlement_reserve",
  "settlement_sent",
  "settlement_confirm",
  "settlement_release",
  "settlement_cancel",
  "settlement_payment_void",
  "settlement_payment_correct",
]);
export const financialReferenceSchema = z
  .strictObject({
    schema_version: z.literal(1),
    operation: financialOperationSchema,
    book_id: id,
    subject_id: id,
    revision: rev,
  })
  .refine((v) =>
    v.operation === "settlement_prepare"
      ? v.revision === 1
      : ["invoice_draft", "accrual_draft", "credit_draft"].includes(
          v.operation,
        ) || v.revision >= 2,
  );
export const financialStatusSchema = z.strictObject({
  schema_version: z.literal(1),
  business_id: id,
  key: z.string().regex(/^[A-Za-z0-9._:-]{8,255}$/),
  operation: financialOperationSchema,
  state: z.enum(["committed", "unresolved", "cancelled"]),
});
const commandBase = {
  book: id,
  subject: id,
  key: z.string().regex(/^[A-Za-z0-9._:-]{8,255}$/),
};
export const financialCommandSchema = z.discriminatedUnion("operation", [
  z.strictObject({
    ...commandBase,
    operation: z.literal("invoice_draft"),
    body: invoiceDraftSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("accrual_draft"),
    body: invoiceDraftSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("invoice_issue"),
    body: invoiceIssueSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("accrual_issue"),
    body: invoiceIssueSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("credit_draft"),
    body: creditDraftSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("credit_issue"),
    body: creditIssueSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("credit_void"),
    body: creditVoidSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("settlement_prepare"),
    body: settlementPrepareSchema,
  }),
  ...(
    ["settlement_approve", "settlement_reserve", "settlement_sent"] as const
  ).map((operation) =>
    z.strictObject({
      ...commandBase,
      operation: z.literal(operation),
      body: settlementActionSchema,
    }),
  ),
  z.strictObject({
    ...commandBase,
    operation: z.literal("settlement_release"),
    body: settlementReleaseSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("settlement_cancel"),
    body: settlementCancelSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("settlement_confirm"),
    payment: id,
    body: paymentConfirmSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("settlement_payment_void"),
    payment: id,
    body: paymentVoidSchema,
  }),
  z.strictObject({
    ...commandBase,
    operation: z.literal("settlement_payment_correct"),
    payment: id,
    body: paymentCorrectSchema,
  }),
]);
export type FinancialCommand = z.infer<typeof financialCommandSchema>;
export type FinancialReference = z.infer<typeof financialReferenceSchema>;
export type Invoice = z.infer<typeof invoiceSchema>;
export type Credit = z.infer<typeof creditSchema>;
export type Settlement = z.infer<typeof settlementSchema>;
export type Payment = z.infer<typeof paymentSchema>;
export type Obligation = z.infer<typeof obligationRecord>;
export type InvoiceDraft = z.infer<typeof invoiceDraftSchema>;
export type CreditDraft = z.infer<typeof creditDraftSchema>;
export type FinancialOverview = z.infer<typeof financialOverviewSchema>;

/** Closed route/method contract for the existing management transport. */
export function financialResponseSchema(
  path: string,
  method: string,
): z.ZodType | undefined {
  if (path === "/financial-documents/overview" && method === "GET")
    return financialOverviewSchema;
  if (
    /^\/financial-documents\/commands\/[A-Za-z0-9._:-]{8,255}\/(resolve|cancel)$/.test(
      path,
    ) &&
    method === "POST"
  )
    return financialStatusSchema;
  const match =
    /^\/financial-documents\/books\/[0-9a-f-]{36}\/(invoices|accruals|credits|obligations|settlements|payments)(.*)$/i.exec(
      path,
    );
  if (!match) return undefined;
  const [, family, suffix] = match;
  const uuid = /^\/[0-9a-f-]{36}$/i;
  if (!suffix && method === "GET")
    return family === "credits"
      ? creditListSchema
      : family === "obligations"
        ? obligationListSchema
        : family === "settlements"
          ? settlementListSchema
          : family !== "payments"
            ? invoiceListSchema
            : undefined;
  if (uuid.test(suffix ?? "") && method === "GET")
    return family === "credits"
      ? creditSchema
      : family === "obligations"
        ? obligationSchema
        : family === "settlements"
          ? settlementSchema
          : family === "payments"
            ? paymentSchema
            : invoiceSchema;
  if (uuid.test(suffix ?? "") && method === "PUT")
    return family === "credits"
      ? creditSchema
      : family === "settlements"
        ? settlementSchema
        : ["invoices", "accruals"].includes(family ?? "")
          ? invoiceSchema
          : undefined;
  if (method === "POST") {
    if (
      ["invoices", "accruals", "credits"].includes(family ?? "") &&
      /^\/[0-9a-f-]{36}\/issue$/i.test(suffix ?? "")
    )
      return family === "credits" ? creditSchema : invoiceSchema;
    if (family === "credits" && /^\/[0-9a-f-]{36}\/void$/i.test(suffix ?? ""))
      return creditSchema;
    if (
      family === "settlements" &&
      /^\/[0-9a-f-]{36}\/(approve|reserve|sent|release|cancel|confirmations\/[0-9a-f-]{36}(\/(void|correct))?)$/i.test(
        suffix ?? "",
      )
    )
      return settlementSchema;
  }
  return undefined;
}
/** Historical recognition is context, never an automatic current account selection. */
export function newCreditDraftLine(
  original: Invoice["lines"][number],
): CreditDraft["lines"][number] {
  return {
    line_id: crypto.randomUUID(),
    credited_line_id: original.line_id,
    counter_account_id: "",
    description: original.description,
    amount: "",
    reason: null,
    reference_entry_id: null,
  };
}
