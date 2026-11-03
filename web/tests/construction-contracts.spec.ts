import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  budgetSchema,
  changeOrderListSchema,
  changeOrderSchema,
  commitmentListSchema,
  commitmentSchema,
  contractSchema,
  dailyReportListSchema,
  dailyReportSchema,
  estimateListSchema,
  estimateSchema,
  measurementListSchema,
  measurementSchema,
  progressSchema,
  projectListSchema,
  projectSchema,
  scheduleSchema,
} from "../lib/construction-contracts";
import {
  currencyPlaces,
  formatMinor,
  quantityText,
  toMinor,
  validQuantity,
} from "../lib/construction-rules";

// O7a (package O): strict response contracts of the O1-O2 construction routes and the money and
// quantity rules the estimate and change-order forms use.
const uuid = (n: number) =>
  `00000000-0000-4000-8000-${n.toString().padStart(12, "0")}`;
const business = uuid(1);
const base = `/v1/businesses/${business}/construction`;
const project = {
  project_id: uuid(2),
  revision: 1,
  number: "FAKE-CP-1",
  name: "FAKE kitchen remodel",
  customer_id: uuid(3),
  location_id: uuid(4),
  site_address: "FAKE 1 Main St, Springfield",
  time_zone: "America/Chicago",
  currency: "USD",
  latest_version: 2,
};
const line = {
  position: 1,
  kind: "material",
  description: "FAKE drywall",
  phase: "Framing",
  quantity: "10.0000",
  unit: "sheet",
  unit_cost_minor: 1500,
  unit_price_minor: 2500,
  material_id: null,
  cost_minor: 15000,
  price_minor: 25000,
};
const summary = {
  version: 2,
  based_on: 1,
  note: "FAKE scope",
  proposed_at: "2031-06-02T13:00:00Z",
  cost_total_minor: 15000,
  price_total_minor: 25000,
};
const estimate = {
  ...summary,
  project_id: uuid(2),
  currency: "USD",
  lines: [line],
};
const change = {
  number: 1,
  title: "FAKE extra outlets",
  reason: null,
  days_delta: -2,
  state: "approved",
  source: "email",
  decided_at: "2031-06-03T15:00:00Z",
  cost_minor: -1000,
  price_minor: -2500,
};
const removal = {
  ...line,
  action: "remove",
  contract_position: 1,
  quantity: "1.0000",
  cost_minor: -1500,
  price_minor: -2500,
};
const addition = {
  ...line,
  position: 2,
  action: "add",
  contract_position: null,
  kind: "labor",
  quantity: "0.5000",
  unit: "hour",
  unit_cost_minor: 1000,
  unit_price_minor: 0,
  cost_minor: 500,
  price_minor: 0,
};
const order = {
  ...change,
  project_id: uuid(2),
  currency: "USD",
  lines: [removal, addition],
};
const contract = {
  project_id: uuid(2),
  version: 2,
  signatory: "FAKE Homeowner",
  source: "paper",
  note: null,
  recorded_at: "2031-06-02T14:00:00Z",
  currency: "USD",
  original_cost_minor: 15000,
  original_price_minor: 25000,
  approved_cost_minor: -1000,
  approved_price_minor: -2500,
  approved_days: -2,
  current_cost_minor: 14000,
  current_price_minor: 22500,
  change_orders: [change],
};

test("every O1-O2 response has a strict contract", () => {
  expect(projectSchema.parse(project)).toEqual(project);
  expect(
    projectListSchema.parse({ items: [project], next_cursor: null }),
  ).toBeTruthy();
  expect(estimateSchema.parse(estimate)).toEqual(estimate);
  expect(estimateListSchema.parse({ items: [summary] })).toBeTruthy();
  expect(
    estimateListSchema.parse({ items: [{ ...summary, proposed_at: null }] }),
  ).toBeTruthy();
  expect(changeOrderSchema.parse(order)).toEqual(order);
  expect(changeOrderListSchema.parse({ items: [change] })).toBeTruthy();
  expect(
    changeOrderSchema.parse({
      ...order,
      state: "proposed",
      source: null,
      decided_at: null,
    }),
  ).toBeTruthy();
  expect(contractSchema.parse(contract)).toEqual(contract);
});

test("the contracts refuse what the server never sends", () => {
  for (const bad of [
    { ...project, extra: 1 },
    { ...project, project_id: "nope" },
    { ...project, currency: "usd" },
    { ...project, latest_version: -1 },
  ])
    expect(projectSchema.safeParse(bad).success).toBe(false);
  for (const bad of [
    { ...estimate, lines: [{ ...line, quantity: "-1" }] },
    { ...estimate, lines: [{ ...line, quantity: "1.23456" }] },
    { ...estimate, lines: [{ ...line, unit_cost_minor: -1 }] },
    { ...estimate, lines: [{ ...line, kind: "fuel" }] },
    { ...estimate, cost_total_minor: 1.5 },
  ])
    expect(estimateSchema.safeParse(bad).success).toBe(false);
  for (const bad of [
    { ...order, state: "maybe" },
    { ...order, lines: [{ ...removal, action: "swap" }] },
    { ...order, lines: [{ ...addition, unit_price_minor: -5 }] },
  ])
    expect(changeOrderSchema.safeParse(bad).success).toBe(false);
  expect(contractSchema.safeParse({ ...contract, source: "fax" }).success).toBe(
    false,
  );
});

test("the management client knows which contract each route answers with", () => {
  const p = `${base}/projects/${uuid(2)}`;
  const cases: [string, string, unknown][] = [
    [`${base}/projects`, "GET", projectListSchema],
    [`${base}/projects?after=${uuid(9)}`, "GET", projectListSchema],
    [p, "GET", projectSchema],
    [p, "PUT", projectSchema],
    [`${p}/estimates`, "GET", estimateListSchema],
    [`${p}/estimates`, "POST", estimateSchema],
    [`${p}/estimates/2`, "GET", estimateSchema],
    [`${p}/estimates/2/proposal`, "POST", estimateSchema],
    [`${p}/contract`, "GET", contractSchema],
    [`${p}/contract`, "POST", contractSchema],
    [`${p}/change-orders`, "GET", changeOrderListSchema],
    [`${p}/change-orders`, "POST", changeOrderSchema],
    [`${p}/change-orders/3`, "GET", changeOrderSchema],
    [`${p}/change-orders/3/decision`, "POST", changeOrderSchema],
  ];
  for (const [path, method, schema] of cases)
    expect(managementResponseSchema(path, method), `${method} ${path}`).toBe(
      schema,
    );
});

test("money is typed in major units and sent as exact minor units", () => {
  expect(currencyPlaces("USD")).toBe(2);
  expect(currencyPlaces("JPY")).toBe(0);
  expect(currencyPlaces("BHD")).toBe(3);
  expect(toMinor("15", 2)).toBe(1500);
  expect(toMinor("15.5", 2)).toBe(1550);
  expect(toMinor("0.07", 2)).toBe(7);
  expect(toMinor("1200", 0)).toBe(1200);
  expect(toMinor("1.234", 3)).toBe(1234);
  expect(toMinor("10000000000", 2)).toBe(1_000_000_000_000);
  for (const [text, places] of [
    ["1.234", 2],
    ["1.5", 0],
    ["-1", 2],
    ["", 2],
    ["1e3", 2],
    ["01", 2],
    ["10000000000.01", 2],
  ] as const)
    expect(toMinor(text, places), `${text} at ${places}`).toBeNull();
  expect(formatMinor(1550, 2)).toBe("15.50");
  expect(formatMinor(7, 2)).toBe("0.07");
  expect(formatMinor(-2500, 2)).toBe("-25.00");
  expect(formatMinor(1200, 0)).toBe("1200");
  expect(formatMinor(1234, 3)).toBe("1.234");
});

test("quantities keep at most four decimal places and are shown without padding", () => {
  expect(quantityText("10.0000")).toBe("10");
  expect(quantityText("2.5000")).toBe("2.5");
  expect(quantityText("2.3333")).toBe("2.3333");
  expect(quantityText("0.0100")).toBe("0.01");
  for (const ok of ["1", "0.5", "2.3333", "999999999.9999"])
    expect(validQuantity(ok), ok).toBe(true);
  for (const bad of ["0", "-1", "1.23456", "1e2", "", "1000000000", ".5"])
    expect(validQuantity(bad), bad).toBe(false);
});

// O7b: the budget, commitments, schedule, daily reports and completed quantities.

const flags = {
  budget_minor: 32000,
  committed_minor: 34000,
  uncommitted_minor: -2000,
  over_committed: true,
  actual_minor: 0,
  remaining_minor: 32000,
  over_budget: false,
};
const budget = {
  project_id: uuid(2),
  currency: "USD",
  budget_minor: 32000,
  committed_minor: 34000,
  uncommitted_minor: -2000,
  actual_minor: 0,
  remaining_minor: 32000,
  lines: [
    {
      change_order: null,
      position: 2,
      phase: "Electrical",
      kind: "labor",
      description: "FAKE wiring",
      unit: "hour",
      quantity: "8.0000",
      unit_cost_minor: 4000,
      ...flags,
    },
  ],
  phases: [{ phase: "Electrical", ...flags }],
};
const commitment = {
  number: 1,
  revision: 2,
  kind: "subcontract",
  counterparty_id: uuid(5),
  state: "open",
  title: "FAKE wiring subcontract",
  reference: null,
  note: null,
  revised_at: "2031-06-02T13:00:00Z",
  total_minor: 34000,
};
const schedule = {
  schema_version: 1,
  project_id: uuid(2),
  revision: 1,
  note: null,
  recorded_at: "2031-06-02T13:00:00Z",
  planned_finish: "2031-06-09",
  phases: [
    {
      phase: "Electrical",
      planned_start: "2031-06-06",
      planned_finish: "2031-06-09",
      depends_on: ["Framing"],
      conflict: false,
      critical: true,
      percent: "0.00",
    },
  ],
  unscheduled: [],
};
const report = {
  schema_version: 1,
  project_id: uuid(2),
  report_date: "2026-10-01",
  revision: 1,
  weather: "FAKE sunny",
  notes: null,
  crew: [
    { position: 1, label: "FAKE framers", headcount: 3, counterparty_id: null },
  ],
  photos: [],
  recorded_at: "2026-10-01T20:00:00Z",
};
const measurement = {
  schema_version: 1,
  project_id: uuid(2),
  number: 1,
  change_order: null,
  position: 1,
  measured_on: "2026-10-01",
  quantity_to_date: "4.0000",
  note: null,
  recorded_at: "2026-10-01T20:00:00Z",
};
const progress = {
  schema_version: 1,
  project_id: uuid(2),
  currency: "USD",
  contract_minor: 30000,
  completed_minor: 10000,
  percent: "33.33",
  lines: [
    {
      change_order: null,
      position: 1,
      phase: "Framing",
      kind: "material",
      description: "FAKE drywall",
      unit: "sheet",
      quantity: "10.0000",
      completed: "4.0000",
      percent: "40.00",
      unit_price_minor: 2500,
      contract_minor: 25000,
      completed_minor: 10000,
    },
  ],
  phases: [
    {
      phase: "Framing",
      contract_minor: 25000,
      completed_minor: 10000,
      percent: "40.00",
    },
  ],
};

test("every O3a and O4a response the screens read has a strict contract", () => {
  expect(budgetSchema.parse(budget)).toEqual(budget);
  const view = {
    ...commitment,
    project_id: uuid(2),
    currency: "USD",
    lines: [{ change_order: null, position: 2, amount_minor: 34000 }],
  };
  expect(commitmentSchema.parse(view)).toEqual(view);
  expect(commitmentListSchema.parse({ items: [commitment] })).toBeTruthy();
  expect(scheduleSchema.parse(schedule)).toEqual(schedule);
  const empty = {
    ...schedule,
    revision: 0,
    recorded_at: null,
    planned_finish: null,
    phases: [],
    unscheduled: ["Framing"],
  };
  expect(scheduleSchema.parse(empty)).toEqual(empty);
  expect(dailyReportSchema.parse(report)).toEqual(report);
  const summary = {
    report_date: "2026-10-01",
    revision: 1,
    weather: null,
    headcount: 3,
    photo_count: 0,
    recorded_at: "2026-10-01T20:00:00Z",
  };
  expect(
    dailyReportListSchema.parse({
      schema_version: 1,
      project_id: uuid(2),
      items: [summary],
    }),
  ).toBeTruthy();
  expect(measurementSchema.parse(measurement)).toEqual(measurement);
  expect(
    measurementListSchema.parse({
      schema_version: 1,
      project_id: uuid(2),
      items: [measurement],
    }),
  ).toBeTruthy();
  expect(progressSchema.parse(progress)).toEqual(progress);

  for (const [schema, bad] of [
    [budgetSchema, { ...budget, extra: 1 }],
    [commitmentListSchema, { items: [{ ...commitment, kind: "loan" }] }],
    [commitmentListSchema, { items: [{ ...commitment, state: "closed" }] }],
    [scheduleSchema, { ...schedule, planned_finish: "2031-13-01" }],
    [
      dailyReportSchema,
      { ...report, crew: [{ ...report.crew[0], headcount: 0 }] },
    ],
    [measurementSchema, { ...measurement, quantity_to_date: "-1" }],
    [progressSchema, { ...progress, percent: "40" }],
  ] as const)
    expect(schema.safeParse(bad).success).toBe(false);

  const p = `${base}/projects/${uuid(2)}`;
  const cases: [string, string, unknown][] = [
    [`${p}/budget`, "GET", budgetSchema],
    [`${p}/commitments`, "GET", commitmentListSchema],
    [`${p}/commitments`, "POST", commitmentSchema],
    [`${p}/commitments/1`, "GET", commitmentSchema],
    [`${p}/commitments/1`, "PUT", commitmentSchema],
    [`${p}/schedule`, "GET", scheduleSchema],
    [`${p}/schedule?revision=2`, "GET", scheduleSchema],
    [`${p}/schedule`, "PUT", scheduleSchema],
    [`${p}/daily-reports`, "GET", dailyReportListSchema],
    [`${p}/daily-reports/2026-10-01`, "GET", dailyReportSchema],
    [`${p}/daily-reports/2026-10-01`, "PUT", dailyReportSchema],
    [`${p}/progress`, "GET", progressSchema],
    [`${p}/progress`, "POST", measurementSchema],
    [`${p}/progress/measurements`, "GET", measurementListSchema],
  ];
  for (const [path, method, schema] of cases)
    expect(managementResponseSchema(path, method), `${method} ${path}`).toBe(
      schema,
    );
});
