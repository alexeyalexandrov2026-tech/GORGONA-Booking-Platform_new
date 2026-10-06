import { test, expect } from "@playwright/test";
import {
  entrySchema,
  entryListSchema,
  periodSchema,
  trialBalanceSchema,
  minorUnits,
} from "../lib/ledger-contracts";
import { managementResponseSchema } from "../lib/management-contracts";
const business = "00000000-0000-4000-8000-000000000001";
const book = "00000000-0000-4000-8000-000000000002";
const entry = "00000000-0000-4000-8000-000000000003";
const account = "00000000-0000-4000-8000-000000000004";
const base = { schema_version: 1, business_id: business, book_id: book };
const posted = {
  ...base,
  entry_id: entry,
  entry_date: "2026-10-01",
  period: "2026-10",
  currency: "USD",
  minor_units: 2,
  source_kind: "manual",
  source_id: "FAKE-1",
  memo: null,
  total: "90071992547409.93",
  reverses_entry_id: null,
  reversed_by_entry_id: null,
  created_at: "2026-10-06T12:00:00Z",
  lines: [
    {
      line_no: 1,
      account_id: account,
      account_code: "1000",
      account_name: "FAKE Cash",
      side: "debit",
      amount: "90071992547409.93",
    },
    {
      line_no: 2,
      account_id: account,
      account_code: "1000",
      account_name: "FAKE Cash",
      side: "credit",
      amount: "90071992547409.93",
    },
  ],
};
test("invoice origins require negotiated v2 and retain exact money checks", () => {
  const invoice = { ...posted, schema_version: 2, source_kind: "invoice" };
  expect(entrySchema.safeParse(invoice).success).toBe(true);
  expect(entrySchema.safeParse({ ...invoice, schema_version: 1 }).success).toBe(
    false,
  );
  expect(entrySchema.safeParse({ ...invoice, schema_version: 3 }).success).toBe(
    false,
  );
  expect(
    entrySchema.safeParse({ ...invoice, source_kind: "unknown" }).success,
  ).toBe(false);
  expect(entrySchema.safeParse({ ...invoice, total: "1.00" }).success).toBe(
    false,
  );
  const summary = {
    entry_id: invoice.entry_id,
    entry_date: invoice.entry_date,
    period: invoice.period,
    currency: invoice.currency,
    source_kind: invoice.source_kind,
    source_id: invoice.source_id,
    memo: invoice.memo,
    total: invoice.total,
    reverses_entry_id: invoice.reverses_entry_id,
    reversed_by_entry_id: invoice.reversed_by_entry_id,
    created_at: invoice.created_at,
  };
  const page = {
    ...base,
    schema_version: 2,
    items: [summary],
    next_cursor: null,
  };
  expect(entryListSchema.safeParse(page).success).toBe(true);
  expect(
    entryListSchema.safeParse({ ...page, schema_version: 1 }).success,
  ).toBe(false);
});
test("ledger money remains exact beyond JavaScript safe integers", () => {
  expect(minorUnits("90071992547409.93", 2)).toBe(BigInt("9007199254740993"));
  expect(minorUnits("0.001", 3)).toBe(BigInt(1));
  expect(minorUnits("1.0", 0)).toBeNull();
  expect(entrySchema.safeParse(posted).success).toBe(true);
  for (const bad of [
    { ...posted, total: 90071992547409.93 },
    { ...posted, period: "2026-11" },
    {
      ...posted,
      lines: [
        posted.lines[0],
        { ...posted.lines[1], amount: "90071992547409.92" },
      ],
    },
    { ...posted, lines: [posted.lines[0], posted.lines[0]] },
    { ...posted, source_kind: "reversal" },
  ])
    expect(entrySchema.safeParse(bad).success).toBe(false);
});
test("ledger entry routes use the strict central contract", () => {
  for (const method of ["GET", "PUT"])
    expect(
      managementResponseSchema(
        `/v1/businesses/${business}/ledger/books/${book}/entries/${entry}`,
        method,
      ).parse(posted),
    ).toEqual(posted);
  expect(() =>
    managementResponseSchema(
      `/v1/businesses/${business}/ledger/books/${book}/entries/${entry}`,
      "DELETE",
    ),
  ).toThrow();
});
test("period state and recorded sequence must agree", () => {
  const open = {
    ...base,
    period: "2026-10",
    state: "open",
    sequence: 0,
    last_event: null,
    events: [],
  };
  expect(periodSchema.safeParse(open).success).toBe(true);
  expect(periodSchema.safeParse({ ...open, state: "closed" }).success).toBe(
    false,
  );
  expect(periodSchema.safeParse({ ...open, sequence: 1 }).success).toBe(false);
});
test("trial balance refuses mismatched rows, currency precision and totals", () => {
  const totals = {
    opening_debit: "0.00",
    opening_credit: "0.00",
    debit: "0.00",
    credit: "0.00",
    closing_debit: "0.00",
    closing_credit: "0.00",
  };
  const report = {
    ...base,
    currency: "USD",
    minor_units: 2,
    period_from: "2026-10",
    period_to: "2026-10",
    currencies: [],
    rows: [],
    totals,
  };
  expect(trialBalanceSchema.safeParse(report).success).toBe(true);
  expect(
    trialBalanceSchema.safeParse({
      ...report,
      totals: { ...totals, debit: "1.00" },
    }).success,
  ).toBe(false);
  expect(
    trialBalanceSchema.safeParse({ ...report, period_to: "2026-09" }).success,
  ).toBe(false);
});

test("matching column totals cannot hide incorrect account balances", () => {
  const zero = {
    opening_debit: "0.00",
    opening_credit: "0.00",
    debit: "0.00",
    credit: "0.00",
    closing_debit: "0.00",
    closing_credit: "0.00",
  };
  const cash = {
    account_id: account,
    code: "1000",
    name: "FAKE Cash",
    type: "asset",
    archived: false,
    ...zero,
    debit: "10.00",
  };
  const capital = {
    account_id: entry,
    code: "3000",
    name: "FAKE Capital",
    type: "equity",
    archived: false,
    ...zero,
    credit: "10.00",
  };
  const report = {
    ...base,
    currency: "USD",
    minor_units: 2,
    period_from: "2026-10",
    period_to: "2026-10",
    currencies: ["USD"],
    rows: [cash, capital],
    totals: { ...zero, debit: "10.00", credit: "10.00" },
  };
  expect(trialBalanceSchema.safeParse(report).success).toBe(false);
  expect(
    trialBalanceSchema.safeParse({
      ...report,
      rows: [
        { ...cash, closing_debit: "10.00" },
        { ...capital, closing_credit: "10.00" },
      ],
      totals: {
        ...report.totals,
        closing_debit: "10.00",
        closing_credit: "10.00",
      },
    }).success,
  ).toBe(true);
});
