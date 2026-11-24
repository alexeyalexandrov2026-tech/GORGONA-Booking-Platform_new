import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  project: string;
  project_number: string;
  document_number: string;
  period: string;
  book: string;
  receivable: string;
  revenue: string;
  retainage: string;
  currency: "USD" | "JPY";
};

test("closes one billing period and shows its separate FIN-03 drafts", async ({
  page,
  browser,
}, testInfo) => {
  const fixtures = JSON.parse(
    process.env.GBA_PAY_APPLICATION_FIXTURES ?? "{}",
  ) as Record<string, Fixture>;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_o7c1_construction_billing_browser.py.");
  const origin = process.env.GBA_MGMT_BROWSER_URL!;
  const issuer = process.env.GBA_TEST_OIDC_ISSUER!;
  expect((await page.request.post(`${issuer}/fixture/user/owner`)).ok()).toBe(
    true,
  );
  const minor = (amount: number) =>
    fixture.currency === "JPY" ? String(amount) : (amount / 100).toFixed(2);
  const money = (amount: number) => `${minor(amount)} ${fixture.currency}`;

  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator(".mgmt-header-actions")).toContainText(
    "FAKE user o7c1-owner",
  );
  await page.getByRole("link", { name: "Construction", exact: true }).click();
  await page
    .getByRole("table", { name: "Projects" })
    .getByRole("button", { name: fixture.project_number })
    .click();
  const billing = page.getByRole("region", {
    name: "Pay applications",
    exact: true,
  });
  const editRate = billing.getByRole("button", { name: "Edit retainage rate" });
  const saveRate = billing.getByRole("button", { name: "Save retainage rate" });
  const rate = billing.getByRole("textbox", { name: "Retainage percent" });
  await expect(billing).toContainText("Current retainage rate 0.00%");
  await editRate.click();
  await rate.fill("10.00");
  await saveRate.click();
  await expect(billing).toContainText("Current retainage rate 10.00%");

  const keys: string[] = [];
  await page.route(
    `**/construction/projects/${fixture.project}/pay-applications`,
    async (route) => {
      if (route.request().method() === "POST") {
        keys.push(route.request().headers()["idempotency-key"] ?? "");
        if (keys.length === 1) {
          const committed = await route.fetch();
          expect(committed.ok()).toBe(true);
          await route.abort();
          return;
        }
      }
      await route.continue();
    },
  );
  await billing.getByRole("button", { name: "New pay application" }).click();
  const form = billing.getByRole("form", { name: "New pay application" });
  await form.getByLabel("Period end", { exact: true }).fill(fixture.period);
  await form.getByLabel("Invoice date", { exact: true }).fill(fixture.period);
  await form
    .getByRole("textbox", { name: "Invoice number", exact: true })
    .fill(fixture.document_number);
  const pick = (label: string) =>
    form.getByRole("combobox", { name: label, exact: true });
  await pick("Ledger book").selectOption(fixture.book);
  await pick("Receivable account").selectOption(fixture.receivable);
  await pick("Revenue account").selectOption(fixture.revenue);
  await expect(
    pick("Retainage account").locator(`option[value="${fixture.receivable}"]`),
  ).toHaveCount(0);
  await pick("Retainage account").selectOption(fixture.retainage);
  const create = form.getByRole("button", { name: "Create pay application" });
  await create.click();
  await expect(billing.getByRole("alert")).toBeVisible();
  await create.click();
  const history = billing.getByRole("table", { name: "Billing periods" });
  await expect(history).toContainText(money(9000));
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);

  await editRate.click();
  await rate.fill("12.50");
  await saveRate.click();
  await expect(billing).toContainText("Current retainage rate 12.50%");
  await history.getByRole("button", { name: "Application 1" }).click();
  const detail = billing.getByRole("region", { name: "Application 1 detail" });
  await expect(detail).toContainText("Retainage rate 10.00%");
  await expect(detail).toContainText(
    `${fixture.document_number} · draft · ${money(9000)}`,
  );
  await expect(detail).toContainText(
    `${fixture.document_number}-R · draft · ${money(1000)}`,
  );
  await expect(
    detail.getByRole("row").filter({
      has: page.getByRole("cell", { name: "4 sheet", exact: true }),
    }),
  ).toContainText(minor(10000));
  await expect(billing).toContainText(`Remaining to bill ${money(21007)}`);
  const audit = await new AxeBuilder({ page })
    .include(".construction-screen")
    .analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  const branch = await browser.newPage();
  try {
    const reconciliationRequests: string[] = [];
    branch.on("request", (request) => {
      if (
        request
          .url()
          .includes(`/construction/projects/${fixture.project}/reconciliation`)
      )
        reconciliationRequests.push(request.method());
    });
    expect(
      (await branch.request.post(`${issuer}/fixture/user/branch`)).ok(),
    ).toBe(true);
    await branch.goto(`${origin}/overview/`);
    await branch.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(branch.locator(".mgmt-header-actions")).toContainText(
      "FAKE user o7c1-branch",
    );
    await branch
      .getByRole("link", { name: "Construction", exact: true })
      .click();
    await branch
      .getByRole("table", { name: "Projects" })
      .getByRole("button", { name: fixture.project_number })
      .click();
    const rateOnly = branch.getByRole("region", {
      name: "Pay applications",
      exact: true,
    });
    await expect(rateOnly).toContainText("Current retainage rate 12.50%");
    await expect(rateOnly).toContainText("require company-wide Finance access");
    await expect(
      rateOnly.getByRole("button", { name: "New pay application" }),
    ).toHaveCount(0);
    await expect(
      rateOnly.getByRole("table", { name: "Billing periods" }),
    ).toHaveCount(0);
    await rateOnly.getByRole("button", { name: "Edit retainage rate" }).click();
    await expect(
      rateOnly.getByRole("textbox", { name: "Retainage percent" }),
    ).toHaveValue("12.50");
    await expect(
      branch.getByRole("region", { name: "Project reconciliation" }),
    ).toHaveCount(0);
    expect(reconciliationRequests).toEqual([]);
  } finally {
    await branch.close();
  }
});
