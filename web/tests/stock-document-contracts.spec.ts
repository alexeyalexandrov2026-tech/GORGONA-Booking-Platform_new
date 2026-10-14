import { expect, test } from "@playwright/test";
import {
  amountFits,
  commandReference,
  documentListSchema,
  documentSchema,
  inventoryResponseSchema,
  quantityFits,
  type InventoryCommand,
} from "../lib/inventory-contracts";
import { managementResponseSchema } from "../lib/management-contracts";

const uuid = (n: number) =>
  `00000000-0000-4000-8000-${n.toString().padStart(12, "0")}`;
const business = uuid(1);
const owner = uuid(2);
const place = uuid(3);
const branch = uuid(4);
const material = uuid(5);
const book = uuid(6);
const summary = {
  document_id: uuid(10),
  kind: "receipt",
  reason: "purchase",
  legal_entity_id: owner,
  place_id: place,
  location_id: branch,
  to_place_id: null,
  to_location_id: null,
  source_document_id: null,
  document_date: "2026-10-01",
  line_count: 1,
  created_at: "2026-10-14T08:00:00.123456Z",
};
const receipt = {
  schema_version: 1,
  business_id: business,
  document_id: summary.document_id,
  kind: "receipt",
  reason: "purchase",
  legal_entity_id: owner,
  place_id: place,
  location_id: branch,
  to_place_id: null,
  to_location_id: null,
  source_document_id: null,
  document_date: "2026-10-01",
  supplier_id: null,
  supplier_document: "FAKE-INV-1",
  created_at: summary.created_at,
  lines: [
    {
      line_no: 1,
      item_id: material,
      quantity: "10.0",
      amount: "25.00",
      source_line_no: null,
      source_amount: null,
    },
  ],
  money: {
    book_id: book,
    rule_revision: 1,
    currency: "USD",
    total: "25.00",
    entry_id: uuid(11),
  },
};
// What a branch manager reads of the same receipt: quantities only.
const quantities = {
  ...receipt,
  supplier_document: null,
  lines: receipt.lines.map((line) => ({ ...line, amount: null })),
  money: null,
};

test("a document list is closed, unique and names a transfer's destination", () => {
  const list = { schema_version: 1, items: [summary], next_cursor: null };
  expect(documentListSchema.safeParse(list).success).toBe(true);
  const transfer = {
    ...summary,
    document_id: uuid(12),
    kind: "transfer",
    reason: "relocation",
    to_place_id: uuid(13),
    to_location_id: branch,
  };
  const returned = {
    ...summary,
    document_id: uuid(14),
    kind: "return",
    reason: "supplier_return",
    source_document_id: summary.document_id,
  };
  expect(
    documentListSchema.safeParse({
      ...list,
      items: [summary, transfer, returned],
    }).success,
  ).toBe(true);
  for (const refused of [
    { ...list, items: [summary, summary] },
    { ...list, items: [{ ...summary, kind: "sale" }] },
    { ...list, items: [{ ...transfer, to_place_id: null }] },
    { ...list, items: [{ ...summary, to_place_id: uuid(13) }] },
    { ...list, items: [{ ...returned, source_document_id: null }] },
    { ...list, items: [{ ...summary, line_count: 0 }] },
    { ...list, items: [{ ...summary, total: "25.00" }] },
    { ...list, business_id: business },
  ])
    expect(
      documentListSchema.safeParse(refused).success,
      JSON.stringify(refused),
    ).toBe(false);
});

test("amounts come together with the money, or not at all", () => {
  expect(documentSchema.safeParse(receipt).success).toBe(true);
  expect(documentSchema.safeParse(quantities).success).toBe(true);
  for (const refused of [
    // An amount without the money of the document, and the reverse.
    { ...quantities, lines: receipt.lines },
    { ...receipt, lines: quantities.lines },
    // A transfer moves no money.
    {
      ...receipt,
      kind: "transfer",
      reason: "relocation",
      to_place_id: uuid(13),
      to_location_id: branch,
    },
    { ...receipt, lines: [] },
    { ...receipt, lines: [{ ...receipt.lines[0], quantity: 10 }] },
    { ...receipt, money: { ...receipt.money, total: "25.5.0" } },
    { ...receipt, cost: "25.00" },
  ])
    expect(
      documentSchema.safeParse(refused).success,
      JSON.stringify(refused).slice(0, 120),
    ).toBe(false);
});

test("every document route has exactly one response contract", () => {
  const id = summary.document_id;
  for (const [method, path] of [
    ["GET", "/documents"],
    ["GET", `/documents/${id}`],
    ["PUT", `/documents/${id}`],
  ] as const)
    expect(
      inventoryResponseSchema(`/inventory${path}`, method),
      `${method} ${path}`,
    ).not.toBeNull();
  for (const [method, path] of [
    ["POST", "/documents"],
    ["DELETE", `/documents/${id}`],
    ["PUT", "/documents"],
    ["GET", `/documents/${id}/lines`],
  ] as const)
    expect(
      inventoryResponseSchema(`/inventory${path}`, method),
      `${method} ${path}`,
    ).toBeNull();
  const root = `/v1/businesses/${business}/inventory`;
  expect(
    managementResponseSchema(
      `${root}/documents?place_id=${place}`,
      "GET",
    ).safeParse({ schema_version: 1, items: [summary], next_cursor: null })
      .success,
  ).toBe(true);
  expect(
    managementResponseSchema(`${root}/documents/${id}`, "PUT").safeParse(
      receipt,
    ).success,
  ).toBe(true);
});

test("a document command names no version", () => {
  const command: InventoryCommand = {
    type: "document",
    id: uuid(20),
    key: "FAKE-command-1",
    body: {
      schema_version: 1,
      kind: "transfer",
      legal_entity_id: owner,
      place_id: place,
      to_place_id: uuid(13),
      document_date: "2026-10-01",
      lines: [{ item_id: material, quantity: "1.5" }],
    },
  };
  expect(commandReference(command)).toEqual({
    schema_version: 1,
    operation: "document",
    subject_id: uuid(20),
    revision: 0,
  });
});

test("a quantity fits the material and an amount fits the currency", () => {
  expect(quantityFits("10.5", 1)).toBe(true);
  expect(quantityFits("3", 0)).toBe(true);
  expect(quantityFits("999999999999", 0)).toBe(true);
  for (const [text, scale] of [
    ["1.25", 1],
    ["0", 0],
    ["0.0", 1],
    ["01", 0],
    ["-1", 0],
    ["1e3", 0],
    ["1,5", 1],
    ["", 0],
    ["1000000000000", 0],
  ] as const)
    expect(quantityFits(text, scale), `${text} @${scale}`).toBe(false);
  expect(amountFits("25.00", 2)).toBe(true);
  expect(amountFits("0", 2)).toBe(true);
  expect(amountFits("25", 0)).toBe(true);
  for (const [text, scale] of [
    ["25.001", 2],
    ["2.5", 0],
    ["-1", 2],
    ["", 2],
    ["1000000000000000", 0],
  ] as const)
    expect(amountFits(text, scale), `${text} @${scale}`).toBe(false);
});
