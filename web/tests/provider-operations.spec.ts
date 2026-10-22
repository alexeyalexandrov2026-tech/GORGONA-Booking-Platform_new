import { test, expect, type Locator, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { businessDateTime } from "../lib/business-time";
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  apply: string;
  apply_total: string;
  linked: string;
  linked_total: string;
  conflict: string;
  unregistered: string;
  conflict_original: string;
  conflict_delivered: string;
  orphan: string;
  waiting: string;
  parked: string;
};
// Row actions other than "Details" (K4b): an operation row offers none.
const action = { name: /^(?!Details of )/ };
const fixtures = JSON.parse(process.env.GBA_K4A_FIXTURE ?? "{}") as Record<
  string,
  Fixture
>;
const total = Number(process.env.GBA_K4A_TOTAL),
  slow = Number(process.env.GBA_K4A_SLOW),
  timezone = process.env.GBA_K4A_TIMEZONE ?? "";
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
async function choose(select: Locator, text: string | RegExp) {
  const value = await select
    .locator("option")
    .filter({ hasText: text })
    .first()
    .getAttribute("value");
  expect(value).toBeTruthy();
  await select.selectOption(value!);
}
async function accessible(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
}
async function noSideScroll(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
}
/** Follow "Load more" to the end of the cursor. */
async function loadAll(region: Locator, list: Locator) {
  const more = region.getByRole("button", {
    name: "Load more provider operations",
    exact: true,
  });
  while (await more.isVisible()) {
    const before = await list.getByRole("listitem").count();
    await more.click();
    await expect
      .poll(() => list.getByRole("listitem").count())
      .toBeGreaterThan(before);
  }
}

test("provider operations: truthful states, clearing account, apply, recovery and refusal", async ({
  page,
}, testInfo) => {
  test.setTimeout(300000);
  const f = fixtures[testInfo.project.name];
  if (!f) throw new Error("No K4a fixture for this browser project.");
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Financial documents", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Invoices and accruals", exact: true }),
  ).toBeVisible();
  await choose(
    page.getByRole("combobox", { name: "Financial book", exact: true }),
    "FAKE Ledger LLC",
  );

  // Operations and connections of the book.
  await page
    .getByRole("button", { name: "Provider operations", exact: true })
    .click();
  const region = page.getByRole("region", {
    name: "Provider operations",
    exact: true,
  });
  const list = region.getByRole("list", { name: "Provider operation list" });
  await expect(list.getByRole("listitem")).toHaveCount(20);
  await accessible(page);
  await noSideScroll(page);
  await loadAll(region, list);
  await expect(list.getByRole("listitem")).toHaveCount(total);
  for (const text of await list.getByRole("listitem").allInnerTexts())
    expect(text).not.toMatch(/\b(paid|verified|payout)\b/i);
  await expect(list.getByRole("button", action)).toHaveCount(0);

  // Owner decision 2: registered once in the screen, after an explicit confirmation.
  const form = region.getByRole("form", {
    name: `Clearing account for ${f.unregistered}`,
  });
  await choose(
    form.getByRole("combobox", { name: "Clearing asset account" }),
    /^1000 · /,
  );
  await accessible(page);
  await form.getByRole("checkbox").check();
  await form
    .getByRole("button", { name: "Register clearing account", exact: true })
    .click();
  await expect(
    region
      .getByRole("listitem")
      .filter({ hasText: `Connection ${f.unregistered}` }),
  ).toContainText(/Clearing account 1000 · .*It cannot be changed\./);

  // States are filtered by the server, completely across pages.
  const state = region.getByRole("combobox", { name: "Operation state" });
  await choose(state, "No final provider success yet");
  await expect(list.getByRole("listitem")).toHaveCount(20);
  await loadAll(region, list);
  await expect(list.getByRole("listitem")).toHaveCount(slow);
  // K6b2: these processing payments were created long ago and are marked as stalled.
  await expect(
    list
      .getByRole("listitem")
      .filter({ hasText: "No final event for over 24 hours" }),
  ).toHaveCount(slow);
  await choose(state, "Applied; later provider data disagrees");
  const conflict = list.getByRole("listitem").filter({ hasText: f.conflict });
  await expect(conflict).toContainText("Manual review needed.");
  await expect(conflict.getByRole("button", action)).toHaveCount(0);
  await accessible(page);

  // Owner decision 1: applied from the reserved settlement; the amount is the provider's.
  await page
    .getByRole("button", { name: "Obligations and settlements", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: new RegExp(`· ${escape(f.apply_total)} USD · reserved ·`),
    })
    .click();
  const detail = page.getByRole("region", { name: "Settlement detail" });
  await detail
    .getByRole("button", { name: "Apply provider operation", exact: true })
    .click();
  const apply = detail.getByRole("form", { name: "Apply provider operation" });
  // K5a-fix (finding 14): "today" in the business time zone, not the UTC date.
  await expect(apply.getByLabel("Payment posting date")).toHaveValue(
    businessDateTime(new Date(), timezone).date,
  );
  await choose(
    apply.getByRole("combobox", { name: "Observed provider operation" }),
    f.apply,
  );
  await expect(apply).toContainText(
    `Amount from the provider: ${f.apply_total} USD (cannot be changed).`,
  );
  await expect(apply.getByLabel(/amount/i)).toHaveCount(0);
  const allocation = apply.getByLabel(/^Provider allocation /);
  await allocation.fill("1.00");
  await apply.getByRole("checkbox").check();
  await apply
    .getByRole("button", { name: "Apply provider operation", exact: true })
    .click();
  await expect(apply.getByRole("alert")).toHaveText(
    "Positive allocated amounts must equal the provider amount exactly.",
  );
  await accessible(page);

  // A server refusal is plain and keeps the input. The refusal paths are the API's tests;
  // here the browser shows one exactly as the server states it, and nothing reaches it.
  await allocation.fill(f.apply_total);
  await page.route("**/provider-confirmations/**", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "PROVIDER_OPERATION_NOT_READY",
          message: "This provider operation cannot move money yet",
          request_id: "FAKE-request",
          details: { reason: "pending" },
        },
      }),
    }),
  );
  await apply
    .getByRole("button", { name: "Apply provider operation", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "PROVIDER_OPERATION_NOT_READY" }),
  ).toContainText("still being decided");
  await expect(allocation).toHaveValue(f.apply_total);
  await accessible(page);
  await page.unrouteAll();

  // The response is lost after the server committed: retry the same request safely.
  await apply.getByRole("checkbox").check();
  await page.route("**/provider-confirmations/**", async (route) => {
    await route.fetch();
    await route.abort();
  });
  await apply
    .getByRole("button", { name: "Apply provider operation", exact: true })
    .click();
  const recovery = page.getByRole("region", {
    name: "Financial command recovery",
  });
  await expect(recovery).toContainText("settlement confirm");
  await accessible(page);
  await page.unrouteAll();
  await recovery
    .getByRole("button", { name: "Retry same financial command" })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Financial fact recorded." }),
  ).toBeVisible();
  await expect(detail.getByRole("heading", { level: 2 })).toContainText(
    "Settlement · confirmed",
  );

  // K3b: an operation a manual payment already recorded is never offered for applying.
  await page
    .getByRole("button", {
      name: new RegExp(
        `· ${escape(f.linked_total)} USD · partially confirmed ·`,
      ),
    })
    .click();
  await detail
    .getByRole("button", { name: "Apply provider operation", exact: true })
    .click();
  await expect(
    apply
      .getByRole("combobox", { name: "Observed provider operation" })
      .locator("option")
      .filter({ hasText: f.linked }),
  ).toHaveCount(0);
  await accessible(page);
  await noSideScroll(page);

  // The applied operation now names its payment; the recorded one needs linking.
  await page
    .getByRole("button", { name: "Provider operations", exact: true })
    .click();
  await choose(state, "Applied to a settlement");
  await loadAll(region, list);
  await expect(
    list.getByRole("listitem").filter({ hasText: f.apply }),
  ).toContainText(/Applied to a settlement · payment [0-9a-f-]{36}/);
  await choose(state, "Already recorded by hand");
  await expect(
    list.getByRole("listitem").filter({ hasText: f.linked }),
  ).toHaveCount(1);
  await choose(state, "Observed by the provider, not applied yet");
  for (const object of [f.apply, f.linked])
    await expect(
      list.getByRole("listitem").filter({ hasText: object }),
    ).toHaveCount(0);
});

test("provider review: what disagrees, needs attention and acknowledgement", async ({
  page,
}, testInfo) => {
  test.setTimeout(300000);
  const name = testInfo.project.name;
  const f = fixtures[name];
  if (!f) throw new Error("No K4a fixture for this browser project.");
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Financial documents", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Invoices and accruals", exact: true }),
  ).toBeVisible();
  await choose(
    page.getByRole("combobox", { name: "Financial book", exact: true }),
    "FAKE Ledger LLC",
  );
  await page
    .getByRole("button", { name: "Provider operations", exact: true })
    .click();
  const region = page.getByRole("region", {
    name: "Provider operations",
    exact: true,
  });

  // Owner decision 2: a decision without an operation is acknowledged with a note.
  const attention = region.getByRole("region", { name: "Needs attention" });
  const items = attention.getByRole("list", { name: "Attention list" });
  await expect(
    items.getByRole("listitem").filter({ hasText: f.waiting }),
  ).toContainText("Waiting for the receipt worker");
  await expect(
    items
      .getByRole("listitem")
      .filter({ hasText: f.waiting })
      .getByRole("button"),
  ).toHaveCount(0);
  const form = attention.getByRole("form", { name: `Acknowledge ${f.orphan}` });
  await expect(form).toContainText("no payment to attach it to");
  await accessible(page);
  const note = `FAKE ${name} checked with the provider`;
  await form.getByLabel("Acknowledgement note").fill(note);
  await form.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(
    items.getByRole("listitem").filter({ hasText: f.orphan }),
  ).toContainText(`Handled: ${note}`);
  await expect(form).toHaveCount(0);

  // K6a: an event stopped after five failed decisions is tried again only after a note.
  const stopped = attention.getByRole("form", {
    name: `Try again ${f.parked}`,
  });
  await expect(stopped).toContainText("Stopped after 5 failed attempts");
  await expect(stopped).toContainText("DivisionByZero");
  await expect(stopped).toContainText("Nothing was decided or booked");
  await accessible(page);
  await stopped
    .getByLabel("What was fixed")
    .fill(`FAKE ${name} fixed the cause`);
  await stopped.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(
    items.getByRole("listitem").filter({ hasText: f.parked }),
  ).toContainText("Waiting for the receipt worker");
  await expect(stopped).toHaveCount(0);

  // Owner decision 1: the fields that disagree, with both values.
  await choose(
    region.getByRole("combobox", { name: "Operation state" }),
    "Applied; later provider data disagrees",
  );
  await region
    .getByRole("button", { name: `Details of ${f.conflict}`, exact: true })
    .click();
  const detail = region.getByRole("region", {
    name: "Provider operation detail",
  });
  const disagrees = detail.getByRole("region", { name: "What disagrees" });
  await expect(disagrees).toContainText(
    `Amount received (minor units) ${f.conflict_original} → ${f.conflict_delivered}`,
  );
  await expect(disagrees).toContainText(
    "its facts disagree with earlier events of this operation",
  );
  await expect(detail).toContainText("same facts as the first delivery");
  for (const text of await detail.allInnerTexts())
    expect(text).not.toMatch(/whsec_|signature|secret/i);
  await accessible(page);
  await noSideScroll(page);
  await detail.getByRole("button", { name: "Close details" }).click();
  await expect(detail).toHaveCount(0);
});

test("provider link: an earlier manual payment is linked, never applied", async ({
  page,
}, testInfo) => {
  test.setTimeout(300000);
  const name = testInfo.project.name;
  const f = fixtures[name];
  if (!f) throw new Error("No K4a fixture for this browser project.");
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Financial documents", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Invoices and accruals", exact: true }),
  ).toBeVisible();
  await choose(
    page.getByRole("combobox", { name: "Financial book", exact: true }),
    "FAKE Ledger LLC",
  );
  await page
    .getByRole("button", { name: "Provider operations", exact: true })
    .click();
  const region = page.getByRole("region", {
    name: "Provider operations",
    exact: true,
  });
  await choose(
    region.getByRole("combobox", { name: "Operation state" }),
    "Already recorded by hand",
  );
  await region
    .getByRole("button", { name: `Details of ${f.linked}`, exact: true })
    .click();
  const detail = region.getByRole("region", {
    name: "Provider operation detail",
  });
  await expect(
    detail
      .getByRole("region", { name: "Manual payments naming this ID" })
      .getByRole("listitem"),
  ).toHaveCount(2);
  const form = detail.getByRole("form", { name: "Link to a manual payment" });
  await accessible(page);

  // Owner decision 2: the amounts must be equal; the refusal keeps the note.
  const note = `FAKE ${name} compared with the bank statement`;
  await choose(
    form.getByRole("combobox", { name: "Manual payment" }),
    /^9\.00 /,
  );
  await form.getByLabel("Link note").fill(note);
  await form.getByRole("checkbox").check();
  await form
    .getByRole("button", { name: "Link to manual payment", exact: true })
    .click();
  await expect(form.getByRole("alert")).toContainText(
    "Its amount differs from the provider's amount. (PROVIDER_LINK_MISMATCH)",
  );
  await expect(form.getByLabel("Link note")).toHaveValue(note);
  await accessible(page);

  // Owner decision 1: link only; no money moves and the operation is linked.
  await choose(
    form.getByRole("combobox", { name: "Manual payment" }),
    /^10\.00 /,
  );
  await form
    .getByRole("button", { name: "Link to manual payment", exact: true })
    .click();
  await expect(detail).toContainText(`Linked to manual payment`);
  await expect(detail).toContainText(note);
  await expect(detail.getByRole("heading", { level: 3 })).toContainText(
    "Linked to the manual payment that recorded it",
  );
  await expect(form).toHaveCount(0);
  await accessible(page);
  await noSideScroll(page);
});
