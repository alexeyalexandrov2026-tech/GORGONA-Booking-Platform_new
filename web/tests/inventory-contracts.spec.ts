import { expect, test } from "@playwright/test";
import {
  balanceListSchema,
  commandReference,
  commandReferenceSchema,
  commandStatusSchema,
  costListSchema,
  inventoryResponseSchema,
  itemListSchema,
  placeListSchema,
  postingRulesSchema,
  RULE_ACCOUNTS,
  type MaterialsCommand,
} from "../lib/inventory-contracts";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  clearInventoryRecovery,
  inventoryRecoverySchema,
  preserveInventoryRecovery,
  readInventoryRecovery,
} from "../lib/inventory-recovery";

const uuid = (n: number) =>
  `00000000-0000-4000-8000-${n.toString().padStart(12, "0")}`;
const business = uuid(1);
const user = uuid(2);
const other = uuid(3);
const book = uuid(4);
const item = {
  schema_version: 1,
  business_id: business,
  item_id: uuid(10),
  code: "FAKE-GEL",
  unit: "ml",
  quantity_scale: 2,
  revision: 1,
  name: "FAKE gel",
  archived: false,
};
const place = {
  schema_version: 1,
  business_id: business,
  place_id: uuid(11),
  location_id: uuid(12),
  code: "SHELF_1",
  revision: 1,
  name: "FAKE shelf",
  archived: false,
};
const rules = {
  schema_version: 1,
  business_id: business,
  book_id: book,
  revision: 1,
  ...Object.fromEntries(
    RULE_ACCOUNTS.map(([field], n) => [field, uuid(20 + n)]),
  ),
};

test("lists of materials and places are closed and unique", () => {
  const items = { schema_version: 1, items: [item], next_cursor: null };
  expect(itemListSchema.safeParse(items).success).toBe(true);
  for (const refused of [
    { ...items, items: [item, item] },
    { ...items, business_id: business },
    { ...items, items: [{ ...item, quantity_scale: 4 }] },
    { ...items, items: [{ ...item, code: "fake gel" }] },
    { ...items, items: [{ ...item, revision: 0 }] },
    { ...items, items: [{ ...item, price: "1.00" }] },
  ])
    expect(
      itemListSchema.safeParse(refused).success,
      JSON.stringify(refused),
    ).toBe(false);
  const places = { schema_version: 1, items: [place], next_cursor: null };
  expect(placeListSchema.safeParse(places).success).toBe(true);
  expect(
    placeListSchema.safeParse({ ...places, items: [place, place] }).success,
  ).toBe(false);
  expect(
    placeListSchema.safeParse({
      ...places,
      items: [{ ...place, location_id: "branch" }],
    }).success,
  ).toBe(false);
});

test("quantities and amounts stay exact decimal text", () => {
  const row = {
    item_id: item.item_id,
    place_id: place.place_id,
    location_id: place.location_id,
    legal_entity_id: uuid(13),
    quantity: "999999999999999.125",
  };
  const balances = { schema_version: 1, items: [row], next_cursor: null };
  expect(balanceListSchema.safeParse(balances).success).toBe(true);
  for (const quantity of [12.5, "-1", "1.2345", "01", "1e3", ""])
    expect(
      balanceListSchema.safeParse({
        ...balances,
        items: [{ ...row, quantity }],
      }).success,
      String(quantity),
    ).toBe(false);
  const cost = {
    legal_entity_id: uuid(13),
    item_id: item.item_id,
    quantity: "3",
    value: "-0.010",
    currency: "USD",
  };
  const costs = { schema_version: 1, items: [cost], next_cursor: null };
  expect(costListSchema.safeParse(costs).success).toBe(true);
  for (const refused of [
    { ...cost, value: 1.5 },
    { ...cost, currency: "usd" },
    { ...cost, place_id: place.place_id },
  ])
    expect(
      costListSchema.safeParse({ ...costs, items: [refused] }).success,
      JSON.stringify(refused),
    ).toBe(false);
});

test("accounts of materials name all seven accounts of one book", () => {
  expect(RULE_ACCOUNTS).toHaveLength(7);
  expect(postingRulesSchema.safeParse(rules).success).toBe(true);
  const missing: Record<string, unknown> = { ...rules };
  delete missing.difference_account_id;
  expect(postingRulesSchema.safeParse(missing).success).toBe(false);
  expect(
    postingRulesSchema.safeParse({ ...rules, loss_account_id: "4100" }).success,
  ).toBe(false);
});

test("every inventory route of this screen has exactly one response contract", () => {
  const known: [string, string][] = [
    ["GET", "/items"],
    ["GET", `/items/${item.item_id}`],
    ["PUT", `/items/${item.item_id}`],
    ["GET", "/places"],
    ["GET", `/places/${place.place_id}`],
    ["PUT", `/places/${place.place_id}`],
    ["GET", "/balances"],
    ["GET", "/costs"],
    ["GET", `/posting-rules/${book}`],
    ["PUT", `/posting-rules/${book}`],
    ["POST", "/commands/FAKE-command-1/resolve"],
    ["POST", "/commands/FAKE-command-1/cancel"],
  ];
  for (const [method, path] of known)
    expect(
      inventoryResponseSchema(`/inventory${path}`, method),
      `${method} ${path}`,
    ).not.toBeNull();
  for (const [method, path] of [
    ["DELETE", `/items/${item.item_id}`],
    ["POST", "/items"],
    ["PUT", "/balances"],
    ["GET", "/posting-rules"],
    ["POST", "/commands/short/resolve"],
    ["POST", "/commands/FAKE-command-1/replay"],
    ["GET", "/commands/FAKE-command-1/resolve"],
  ] as const)
    expect(
      inventoryResponseSchema(`/inventory${path}`, method),
      `${method} ${path}`,
    ).toBeNull();
  const root = `/v1/businesses/${business}/inventory`;
  expect(
    managementResponseSchema(`${root}/items?after=${uuid(9)}`, "GET").safeParse(
      { schema_version: 1, items: [item], next_cursor: null },
    ).success,
  ).toBe(true);
  expect(
    managementResponseSchema(`${root}/items/${item.item_id}`, "GET").safeParse(
      place,
    ).success,
  ).toBe(false);
  // An inventory route this screen does not use has no contract and is never read.
  expect(() => managementResponseSchema(`${root}/valuation`, "GET")).toThrow(
    /Unrecognized/,
  );
});

const command: MaterialsCommand = {
  type: "posting_rules",
  book,
  key: "FAKE-command-1",
  body: {
    schema_version: 1,
    expected_revision: 1,
    ...(Object.fromEntries(
      RULE_ACCOUNTS.map(([field], n) => [field, uuid(30 + n)]),
    ) as Record<(typeof RULE_ACCOUNTS)[number][0], string>),
  },
};

test("a command names the version it produces, never a document revision", () => {
  expect(commandReference(command)).toEqual({
    schema_version: 1,
    operation: "posting_rules",
    subject_id: book,
    revision: 2,
  });
  expect(
    commandReference({
      type: "item",
      id: item.item_id,
      key: "FAKE-command-2",
      body: {
        schema_version: 1,
        expected_revision: 0,
        code: item.code,
        name: item.name,
        unit: item.unit,
        quantity_scale: 2,
        archived: false,
      },
    }),
  ).toEqual({
    schema_version: 1,
    operation: "item",
    subject_id: item.item_id,
    revision: 1,
  });
  const reference = commandReference(command);
  expect(commandReferenceSchema.safeParse(reference).success).toBe(true);
  for (const refused of [
    { ...reference, revision: 0 },
    { ...reference, operation: "document" },
    { ...reference, operation: "payroll" },
    { ...reference, name: "FAKE" },
  ])
    expect(
      commandReferenceSchema.safeParse(refused).success,
      JSON.stringify(refused),
    ).toBe(false);
  expect(
    commandReferenceSchema.safeParse({
      ...reference,
      operation: "document",
      revision: 0,
    }).success,
  ).toBe(true);
  const status = {
    schema_version: 1,
    business_id: business,
    key: "FAKE-command-1",
    operation: "posting_rules",
    state: "cancelled",
  };
  expect(commandStatusSchema.safeParse(status).success).toBe(true);
  expect(
    commandStatusSchema.safeParse({ ...status, state: "lost" }).success,
  ).toBe(false);
  expect(
    commandStatusSchema.safeParse({ ...status, key: "short" }).success,
  ).toBe(false);
});

test("recovery keeps identifiers only, for one person and business", () => {
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
    expect(readInventoryRecovery(user, business)).toBeNull();
    const saved = preserveInventoryRecovery(user, business, command);
    expect(inventoryRecoverySchema.safeParse(saved).success).toBe(true);
    const serialized = Array.from(values.values())[0]!;
    for (const secret of ["inventory_account_id", uuid(30), "body"])
      expect(serialized).not.toContain(secret);
    expect(readInventoryRecovery(user, business)?.reference.revision).toBe(2);
    // Another person, or the same person in another business, sees nothing.
    expect(readInventoryRecovery(other, business)).toBeNull();
    expect(readInventoryRecovery(user, uuid(16))).toBeNull();
    // The same command may be preserved again; another must wait.
    expect(preserveInventoryRecovery(user, business, command).saved_at).toBe(
      saved.saved_at,
    );
    expect(() =>
      preserveInventoryRecovery(user, business, {
        ...command,
        key: "FAKE-command-9",
      }),
    ).toThrow(/earlier/);
    clearInventoryRecovery(user, business, "FAKE-command-9");
    expect(values.size).toBe(1);
    const storageKey = Array.from(values.keys())[0]!;
    expect(storageKey).toBe(
      `gorgona.inventory.recovery.v1.${user}.${business}`,
    );
    store.setItem(
      storageKey,
      JSON.stringify({ ...JSON.parse(serialized), actor_id: other }),
    );
    expect(() => readInventoryRecovery(user, business)).toThrow(/another/);
    store.setItem(
      storageKey,
      JSON.stringify({ ...JSON.parse(serialized), name: "FAKE" }),
    );
    expect(() => readInventoryRecovery(user, business)).toThrow();
    store.setItem(storageKey, "x".repeat(5000));
    expect(() => readInventoryRecovery(user, business)).toThrow(/safely/);
    store.setItem(storageKey, serialized);
    clearInventoryRecovery(user, business, command.key);
    expect(values.size).toBe(0);
  } finally {
    if (descriptor)
      Object.defineProperty(globalThis, "sessionStorage", descriptor);
    else Reflect.deleteProperty(globalThis, "sessionStorage");
  }
});
