import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  delegationSchema,
  delegatedBusinessSchema,
} from "../lib/delegation-contracts";
import {
  customerDocumentLinks,
  customerGrantMatches,
} from "../lib/construction-customer-access";
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

test("customer proposal responses stay scoped and expose customer prices only", () => {
  const project = uuid(2);
  const path = `${base}/projects/${project}/customer-proposal/${uuid(3)}`;
  const line = {
    position: 1,
    description: "FAKE scope",
    phase: "Framing",
    quantity: "10.0000",
    unit: "sheet",
    unit_price_minor: 2500,
    price_minor: 25000,
  };
  const proposal = {
    schema_version: 1,
    project_id: project,
    version: 1,
    customer_generation: 1,
    currency: "USD",
    proposed_at: "2026-11-16T15:00:00Z",
    price_total_minor: 25000,
    accepted: false,
    lines: [line],
  };
  const read = managementResponseSchema(path, "GET");
  const accept = managementResponseSchema(path, "POST");
  expect(read.parse(proposal)).toEqual(proposal);
  expect(read.safeParse({ ...proposal, project_id: uuid(4) }).success).toBe(
    false,
  );
  expect(
    read.safeParse({ ...proposal, lines: [{ ...line, unit_cost_minor: 1500 }] })
      .success,
  ).toBe(false);
  expect(accept.safeParse(proposal).success).toBe(false);
  expect(accept.parse({ ...proposal, accepted: true })).toEqual({
    ...proposal,
    accepted: true,
  });
});

test("customer change answers bind the project and change number and refuse internal prices", () => {
  const project = uuid(2);
  const path = `${base}/projects/${project}/change-orders/2/customer-answer/${uuid(3)}`;
  const line = {
    position: 1,
    action: "remove",
    contract_position: 1,
    description: "FAKE removed scope",
    phase: "Framing",
    quantity: "2.0000",
    unit: "sheet",
    unit_price_minor: 2500,
    price_minor: -5000,
  };
  const change = {
    schema_version: 1,
    project_id: project,
    number: 2,
    customer_generation: 1,
    title: "FAKE scope change",
    reason: "FAKE request",
    currency: "USD",
    days_delta: -2,
    price_minor: -5000,
    state: "proposed",
    decided_at: null,
    lines: [line],
  };
  const read = managementResponseSchema(path, "GET");
  expect(read.parse(change)).toEqual(change);
  for (const invalid of [
    { ...change, project_id: uuid(4) },
    { ...change, number: 3 },
    { ...change, state: "approved" },
    { ...change, lines: [{ ...line, unit_cost_minor: 1500 }] },
  ])
    expect(read.safeParse(invalid).success).toBe(false);
  const answer = managementResponseSchema(path, "POST");
  expect(answer.safeParse(change).success).toBe(false);
  const rejected = {
    ...change,
    state: "rejected",
    decided_at: "2026-11-17T15:00:00Z",
  };
  expect(answer.parse(rejected)).toEqual(rejected);
});

test("customer work review and receipt keep scope, identity and proof without staff costs", () => {
  const project = uuid(2);
  const path = `${base}/projects/${project}/customer-acceptance/${uuid(3)}`;
  const review = {
    schema_version: 1,
    project_id: project,
    customer_generation: 1,
    customer_company_revision: 1,
    currency: "USD",
    site_today: "2026-11-17",
    fully_billed: true,
    open_items: 0,
    lines: [],
    phases: [],
    accepted: [],
    review_hash: "a".repeat(64),
  };
  const read = managementResponseSchema(path, "GET");
  expect(read.parse(review)).toEqual(review);
  expect(read.safeParse({ ...review, project_id: uuid(4) }).success).toBe(
    false,
  );
  expect(read.safeParse({ ...review, cost_minor: 15000 }).success).toBe(false);
  expect(read.safeParse({ ...review, review_hash: "invalid" }).success).toBe(
    false,
  );
  const receipt = {
    schema_version: 1,
    project_id: project,
    number: 1,
    scope: "phase",
    phase: "Framing",
    accepted_on: "2026-11-17",
    signatory: "FAKE customer",
    source: "platform",
    note: null,
    warranty_ends_on: null,
    recorded_at: "2026-11-17T15:00:00Z",
    review_hash: review.review_hash,
  };
  const accepted = managementResponseSchema(path, "POST");
  expect(accepted.parse(receipt)).toEqual(receipt);
  expect(accepted.safeParse({ ...receipt, phase: null }).success).toBe(false);
  expect(accepted.safeParse({ ...receipt, source: "paper" }).success).toBe(
    false,
  );
  expect(accepted.safeParse({ ...receipt, release: null }).success).toBe(false);
});

test("project customer-company history is scoped and requires ordered revisions", () => {
  const project = uuid(2);
  const path = `${base}/projects/${project}/customer-company`;
  const company = {
    schema_version: 1,
    project_id: project,
    customer_id: uuid(4),
    customer_generation: 1,
    revision: 0,
    company_id: null,
    versions: [],
  };
  for (const method of ["GET", "PUT"]) {
    const schema = managementResponseSchema(path, method);
    expect(schema.parse(company)).toEqual(company);
    expect(schema.safeParse({ ...company, project_id: uuid(5) }).success).toBe(
      false,
    );
    expect(schema.safeParse({ ...company, revision: 1 }).success).toBe(false);
  }
});

test("customer links require the live grant of the linked company and project branch", () => {
  const company = uuid(3);
  const location = uuid(4);
  const permissions = [
    "booking.read",
    "booking.write",
    "catalog.read",
    "staff.read",
    "transport.read",
    "transport.plan",
    "transport.assign",
    "transport.events",
    "construction.customer_answer",
  ];
  const grant = delegationSchema.parse({
    schema_version: 1,
    grant_id: uuid(5),
    owner_business_id: business,
    owner_name: "FAKE builder",
    servicer_business_id: company,
    servicer_name: "FAKE customer",
    permissions,
    location_id: location,
    expires_at: "2099-01-01T00:00:00Z",
    status: "active",
    expired: false,
    revision: 2,
    revoked_by_side: null,
    delegates: [
      {
        user_id: uuid(6),
        display_name: "FAKE delegate",
        added_at: "2026-11-17T15:00:00Z",
      },
    ],
    created_at: "2026-11-17T15:00:00Z",
  });
  expect(
    delegatedBusinessSchema.safeParse({
      business_id: business,
      business_name: "FAKE builder",
      grant_id: grant.grant_id,
      servicer_business_id: company,
      servicer_name: "FAKE customer",
      permissions,
      location_id: location,
      expires_at: grant.expires_at,
    }).success,
  ).toBe(true);
  const now = Date.parse("2026-11-17T15:00:00Z");
  const matches = (candidate: typeof grant) =>
    customerGrantMatches(candidate, business, company, location, now);
  expect(matches(grant)).toBe(true);
  expect(matches({ ...grant, location_id: null })).toBe(true);
  for (const changed of [
    { ...grant, owner_business_id: uuid(7) },
    { ...grant, servicer_business_id: uuid(7) },
    { ...grant, location_id: uuid(7) },
    { ...grant, permissions: [] },
    { ...grant, expired: true },
    { ...grant, expires_at: "2026-11-17T14:59:59Z" },
    { ...grant, delegates: [] },
    { ...grant, status: "revoked" as const },
    { ...grant, status: "pending" as const },
  ])
    expect(matches(changed)).toBe(false);
  const links = customerDocumentLinks(
    { business, project: uuid(2), grant: grant.grant_id },
    [1, 2],
  );
  expect(
    new URL(links.proposal, "https://platform.example.test").searchParams.get(
      "grant",
    ),
  ).toBe(grant.grant_id);
  expect(
    links.changes.map((item) =>
      new URL(item.href, "https://platform.example.test").searchParams.get(
        "number",
      ),
    ),
  ).toEqual(["1", "2"]);
  expect(links.acceptance).toContain("/construction/customer/acceptance/");
});

test("warranty history preserves ordered transitions and excludes reversed costs from totals", () => {
  const projectId = uuid(2);
  const path = `${base}/projects/${projectId}/warranty-claims`;
  const recorded = "2026-10-02T12:00:00Z";
  const detail = {
    schema_version: 1,
    project_id: projectId,
    number: 1,
    title: "FAKE tile",
    description: null,
    phase: "Finishes",
    location: null,
    reported_by: "FAKE customer",
    raised_on: "2026-10-02",
    state: "open",
    events: [
      { sequence: 1, state: "repaired", note: null, recorded_at: recorded },
      {
        sequence: 2,
        state: "open",
        note: "FAKE reopened",
        recorded_at: recorded,
      },
    ],
    repairs: [
      {
        cost_link: 1,
        amount_minor: 2500,
        reversed: false,
        recorded_at: recorded,
      },
      {
        cost_link: 2,
        amount_minor: 900,
        reversed: true,
        recorded_at: recorded,
      },
    ],
    repair_minor: 2500,
    recorded_at: recorded,
  };
  const schema = managementResponseSchema(`${path}/1`, "GET");
  expect(schema.safeParse(detail).success).toBe(true);
  expect(schema.safeParse({ ...detail, title: "🧱".repeat(70) }).success).toBe(
    true,
  );
  expect(schema.safeParse({ ...detail, repair_minor: 3400 }).success).toBe(
    false,
  );
  expect(
    schema.safeParse({ ...detail, events: detail.events.toReversed() }).success,
  ).toBe(false);
  expect(
    schema.safeParse({
      ...detail,
      events: [{ ...detail.events[0], state: "closed" }],
      state: "closed",
    }).success,
  ).toBe(false);
  expect(
    managementResponseSchema(`${path}/1/events`, "POST").safeParse(detail)
      .success,
  ).toBe(true);
  expect(
    managementResponseSchema(`${path}/2/repairs`, "POST").safeParse(detail)
      .success,
  ).toBe(false);
  const list = {
    schema_version: 1,
    project_id: projectId,
    currency: "USD",
    warranty_starts_on: "2026-10-01",
    warranty_ends_on: "2027-10-01",
    repair_minor: 2500,
    items: [
      {
        number: 1,
        title: detail.title,
        phase: detail.phase,
        raised_on: detail.raised_on,
        state: detail.state,
        repair_minor: 2500,
      },
    ],
  };
  const listSchema = managementResponseSchema(path, "GET");
  expect(listSchema.safeParse(list).success).toBe(true);
  expect(
    listSchema.safeParse({ ...list, warranty_starts_on: null }).success,
  ).toBe(false);
});

test("reconciliation keeps a signed difference and binds money to the requested project", () => {
  const projectId = uuid(2);
  const result = {
    schema_version: 1,
    project_id: projectId,
    currency: "USD",
    contract_minor: 31007,
    completed_minor: 29000,
    budget_minor: 20000,
    committed_minor: 8000,
    actual_minor: 6500,
    warranty_repair_minor: 2500,
    billed_minor: 31007,
    retained_minor: 3100,
    due_minor: 27907,
    released_minor: 0,
    held_minor: 3100,
    due_paid_minor: 10000,
    due_credited_minor: 700,
    retainage_paid_minor: 1500,
    retainage_credited_minor: 0,
    unissued_documents: 0,
    contract_minus_billed_minor: 0,
    completed_minus_billed_minor: -2007,
    billed_minus_settled_minor: 18807,
    retainage_settled_before_release_minor: 1500,
    budget_minus_actual_minor: 13500,
    contract_minus_actual_minor: 24507,
    claims: { open: 1, repaired: 0, closed: 0, rejected: 0 },
  };
  const schema = managementResponseSchema(
    `${base}/projects/${projectId}/reconciliation`,
    "GET",
  );
  expect(schema.safeParse(result).success).toBe(true);
  expect(schema.safeParse({ ...result, project_id: uuid(3) }).success).toBe(
    false,
  );
  expect(
    schema.safeParse({ ...result, billed_minus_settled_minor: 0 }).success,
  ).toBe(false);
  expect(
    schema.safeParse({ ...result, claims: { ...result.claims, cancelled: 0 } })
      .success,
  ).toBe(false);
});

test("acceptance history binds signed scopes and releases to the right project", () => {
  const projectId = uuid(2);
  const path = `${base}/projects/${projectId}/acceptances`;
  const phase = {
    schema_version: 1,
    project_id: projectId,
    number: 1,
    scope: "phase",
    phase: "Framing",
    accepted_on: "2026-10-01",
    signatory: "FAKE signatory",
    source: "paper",
    note: null,
    warranty_starts_on: null,
    warranty_ends_on: null,
    recorded_at: "2026-10-02T12:00:00Z",
    release: {
      released_on: "2026-10-01",
      amount_minor: 2500,
      note: null,
      recorded_at: "2026-10-02T12:01:00Z",
    },
  };
  const final = {
    ...phase,
    number: 2,
    scope: "final",
    phase: null,
    accepted_on: "2026-10-02",
    warranty_starts_on: "2026-10-02",
    warranty_ends_on: "2027-10-02",
    release: null,
  };
  const list = {
    schema_version: 1,
    project_id: projectId,
    currency: "USD",
    retained_minor: 3100,
    released_minor: 2500,
    held_minor: 600,
    phases: [
      {
        phase: "Framing",
        finished: true,
        open_items: 0,
        billed_in_full: true,
        retained_minor: 2500,
        acceptance: 1,
        released_minor: 2500,
      },
    ],
    final,
    items: [phase, final],
  };
  const schema = managementResponseSchema(path, "GET");
  expect(schema.safeParse(list).success).toBe(true);
  expect(schema.safeParse({ ...list, held_minor: 601 }).success).toBe(false);
  expect(
    schema.safeParse({
      ...list,
      items: [phase, { ...final, project_id: uuid(3) }],
    }).success,
  ).toBe(false);
  expect(
    schema.safeParse({
      ...list,
      phases: [{ ...list.phases[0], acceptance: 2 }],
    }).success,
  ).toBe(false);
  expect(managementResponseSchema(path, "POST").safeParse(final).success).toBe(
    true,
  );
  const detail = managementResponseSchema(`${path}/1`, "GET");
  expect(detail.safeParse(phase).success).toBe(true);
  expect(detail.safeParse(final).success).toBe(false);
  expect(detail.safeParse({ ...phase, source: "platform" }).success).toBe(true);
  expect(detail.safeParse({ ...phase, source: "unknown" }).success).toBe(false);
  const release = managementResponseSchema(`${path}/1/release`, "POST");
  expect(release.safeParse(phase).success).toBe(true);
  expect(release.safeParse({ ...phase, release: null }).success).toBe(false);
  expect(
    release.safeParse({
      ...phase,
      release: { ...phase.release, released_on: "2026-09-30" },
    }).success,
  ).toBe(false);
});

test("billing responses bind rates, totals and periods to the selected project", () => {
  const projectId = uuid(2);
  const path = `${base}/projects/${projectId}`;
  const rate = {
    schema_version: 1,
    project_id: projectId,
    revision: 0,
    rate_bp: 0,
    recorded_at: null,
  };
  for (const method of ["GET", "PUT"]) {
    const schema = managementResponseSchema(`${path}/retainage`, method);
    expect(schema.safeParse(rate).success).toBe(true);
    expect(schema.safeParse({ ...rate, project_id: uuid(3) }).success).toBe(
      false,
    );
    expect(schema.safeParse({ ...rate, rate_bp: 5001 }).success).toBe(false);
  }
  const application = {
    number: 1,
    period_end: "2026-10-01",
    billed_to_date_minor: 10000,
    this_period_minor: 10000,
    retained_minor: 1000,
    due_minor: 9000,
    invoice_state: "draft",
    retainage_state: "draft",
  };
  const list = {
    schema_version: 1,
    project_id: projectId,
    currency: "USD",
    contract_minor: 25000,
    billed_to_date_minor: 10000,
    retained_minor: 1000,
    due_minor: 9000,
    remaining_minor: 15000,
    items: [application],
  };
  const schema = managementResponseSchema(`${path}/pay-applications`, "GET");
  expect(schema.safeParse(list).success).toBe(true);
  expect(schema.safeParse({ ...list, project_id: uuid(3) }).success).toBe(
    false,
  );
  expect(schema.safeParse({ ...list, remaining_minor: 15001 }).success).toBe(
    false,
  );
  expect(
    schema.safeParse({ ...list, items: [application, application] }).success,
  ).toBe(false);
  expect(
    schema.safeParse({
      ...list,
      items: [{ ...application, retainage_state: null }],
    }).success,
  ).toBe(false);
});

test("pay application history survives a change to the current contract line", () => {
  const projectId = uuid(2);
  const invoice = {
    schema_version: 1,
    business_id: business,
    book_id: uuid(3),
    document_id: uuid(4),
    kind: "invoice",
    revision: 1,
    state: "draft",
    direction: "receivable",
    counterparty_id: uuid(5),
    counterparty_revision: 1,
    currency: "USD",
    minor_units: 2,
    invoice_date: "2026-10-01",
    due_date: null,
    control_account_id: uuid(6),
    title: "FAKE pay application",
    number: "FAKE-PA",
    lines: [
      {
        line_id: uuid(7),
        counter_account_id: uuid(8),
        description: "FAKE work",
        amount: "100.00",
      },
    ],
    total: "100.00",
    entry_id: null,
    obligation_id: null,
    issued_on: null,
    attestation: null,
    created_at: "2026-10-01T12:00:00Z",
  };
  const line = {
    change_order: null,
    position: 1,
    phase: "FAKE framing",
    description: "FAKE work removed after billing",
    unit: "sheet",
    quantity: "0.0000",
    contract_minor: 0,
    completed: "4.0000",
    value_to_date_minor: 10000,
    previous_minor: 0,
    this_period_minor: 10000,
  };
  const detail = {
    schema_version: 1,
    project_id: projectId,
    currency: "USD",
    number: 1,
    period_end: "2026-10-01",
    rate_revision: null,
    rate_bp: 0,
    previous_billed_minor: 0,
    billed_to_date_minor: 10000,
    this_period_minor: 10000,
    retained_minor: 0,
    due_minor: 10000,
    lines: [line],
    invoice,
    retainage: null,
    recorded_at: "2026-10-01T12:00:00Z",
  };
  const path = `${base}/projects/${projectId}/pay-applications`;
  const schema = managementResponseSchema(`${path}/1`, "GET");
  expect(schema.safeParse(detail).success).toBe(true);
  expect(managementResponseSchema(path, "POST").safeParse(detail).success).toBe(
    true,
  );
  expect(
    managementResponseSchema(`${path}/2`, "GET").safeParse(detail).success,
  ).toBe(false);
  expect(
    schema.safeParse({
      ...detail,
      lines: [{ ...line, this_period_minor: 9000 }],
    }).success,
  ).toBe(false);
  expect(
    schema.safeParse({ ...detail, invoice: { ...invoice, total: "50.00" } })
      .success,
  ).toBe(false);
});

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

test("actual costs validate source fields, response identity, and the reversal", () => {
  const path = `${base}/projects/${project.project_id}/costs`;
  const cost = {
    schema_version: 1,
    project_id: project.project_id,
    number: 1,
    kind: "stock_write_off",
    change_order: null,
    position: 1,
    amount_minor: 4500,
    currency: "USD",
    note: null,
    attempt: 1,
    stock_document_id: uuid(8),
    stock_line_no: 1,
    book_id: null,
    document_id: null,
    document_revision: null,
    line_id: null,
    time_entry_id: null,
    time_entry_revision: null,
    worked_microseconds: null,
    rate_per_hour_minor: null,
    linked_at: "2026-11-16T10:00:00Z",
    reversal: null,
  };
  const list = {
    schema_version: 1,
    project_id: project.project_id,
    items: [cost],
  };
  const read = managementResponseSchema(path, "GET");
  expect(read.safeParse(list).success).toBe(true);
  expect(
    read.safeParse({ ...list, items: [{ ...cost, project_id: uuid(99) }] })
      .success,
  ).toBe(false);
  expect(read.safeParse({ ...list, items: [cost, cost] }).success).toBe(false);
  expect(
    read.safeParse({ ...list, items: [{ ...cost, stock_line_no: null }] })
      .success,
  ).toBe(false);
  expect(
    read.safeParse({ ...list, items: [{ ...cost, book_id: uuid(12) }] })
      .success,
  ).toBe(false);
  expect(managementResponseSchema(path, "POST").safeParse(cost).success).toBe(
    true,
  );
  const reverse = managementResponseSchema(`${path}/1/reversal`, "POST");
  expect(
    reverse.safeParse({
      ...cost,
      reversal: {
        reason: "Wrong budget line",
        reversed_at: "2026-11-16T10:15:00Z",
      },
    }).success,
  ).toBe(true);
  expect(reverse.safeParse(cost).success).toBe(false);
  expect(
    reverse.safeParse({
      ...cost,
      number: 2,
      reversal: {
        reason: "Wrong budget line",
        reversed_at: "2026-11-16T10:15:00Z",
      },
    }).success,
  ).toBe(false);
});
