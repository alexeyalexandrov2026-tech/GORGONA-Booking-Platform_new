import { test, expect, type Locator, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  apply: string;
  apply_total: string;
  linked: string;
  linked_total: string;
  conflict: string;
  unregistered: string;
};
const fixtures = JSON.parse(process.env.GBA_K4A_FIXTURE ?? "{}") as Record<
  string,
  Fixture
>;
const total = Number(process.env.GBA_K4A_TOTAL),
  slow = Number(process.env.GBA_K4A_SLOW);
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
  await expect(list.getByRole("button")).toHaveCount(0);

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
  await choose(state, "Applied; later provider data disagrees");
  const conflict = list.getByRole("listitem").filter({ hasText: f.conflict });
  await expect(conflict).toContainText("Manual review needed.");
  await expect(conflict.getByRole("button")).toHaveCount(0);
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

  // The response is lost after the server committed: retry the same request safely.
  await allocation.fill(f.apply_total);
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

  // A server refusal is plain, keeps the input and claims nothing.
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
  await choose(
    apply.getByRole("combobox", { name: "Observed provider operation" }),
    f.linked,
  );
  await apply.getByLabel(/^Provider allocation /).fill("10.00");
  await apply.getByRole("checkbox").check();
  await apply
    .getByRole("button", { name: "Apply provider operation", exact: true })
    .click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "PROVIDER_PAYMENT_LINK_REQUIRED" }),
  ).toContainText("Linking it is not available yet, so nothing was applied.");
  await expect(apply.getByLabel(/^Provider allocation /)).toHaveValue("10.00");
  await accessible(page);
  await noSideScroll(page);

  // The applied operation now names its payment; the linked one is still observed.
  await page
    .getByRole("button", { name: "Provider operations", exact: true })
    .click();
  await choose(state, "Applied to a settlement");
  await loadAll(region, list);
  await expect(
    list.getByRole("listitem").filter({ hasText: f.apply }),
  ).toContainText(/Applied to a settlement · payment [0-9a-f-]{36}/);
  await choose(state, "Observed by the provider, not applied yet");
  await expect(
    list.getByRole("listitem").filter({ hasText: f.linked }),
  ).toHaveCount(1);
  await expect(
    list.getByRole("listitem").filter({ hasText: f.apply }),
  ).toHaveCount(0);
});
