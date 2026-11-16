import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  number: string;
  project: string;
  stock: string;
  book: string;
  payable: string;
  payable_line: string;
  time_entry: string;
};

test("links all three existing facts, retries safely, and reverses a cost", async ({
  page,
}, testInfo) => {
  const fixtures = JSON.parse(
    process.env.GBA_COST_BROWSER_FIXTURES ?? "{}",
  ) as Record<string, Fixture>;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error(
      "Seed actual costs with test_o7b2_construction_costs_browser.py.",
    );
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator(".mgmt-header-actions")).toContainText(
    "FAKE user o7b2-owner",
  );
  await page.getByRole("link", { name: "Construction", exact: true }).click();
  await page
    .getByRole("table", { name: "Projects" })
    .getByRole("button", { name: fixture.number })
    .click();
  const costs = page.getByRole("region", { name: "Actual costs", exact: true });
  const form = costs.getByRole("form", { name: "Link actual cost" });
  const newLink = costs.getByRole("button", {
    name: "Link actual cost",
    exact: true,
  });
  const select = (name: string) =>
    form.getByRole("combobox", { name, exact: true });
  const save = form.getByRole("button", { name: "Save cost link" });
  const budget = page.getByRole("region", { name: "Budget", exact: true });
  const history = costs.getByRole("table", { name: "Actual cost history" });

  const keys: string[] = [];
  let failHistoryRefresh = true;
  await page.route(
    `**/construction/projects/${fixture.project}/costs`,
    async (route) => {
      if (
        route.request().method() === "GET" &&
        keys.length === 2 &&
        failHistoryRefresh
      ) {
        failHistoryRefresh = false;
        await route.abort();
        return;
      }
      if (route.request().method() === "POST") {
        keys.push(route.request().headers()["idempotency-key"] ?? "");
        if (keys.length === 1) {
          const response = await route.fetch();
          expect(response.ok()).toBe(true);
          await route.abort();
          return;
        }
      }
      await route.continue();
    },
  );

  await newLink.click();
  await select("Budget line").selectOption("0:1");
  await select("Stock place").selectOption({ index: 1 });
  await select("Stock write-off").selectOption(fixture.stock);
  await select("Write-off line").selectOption("1");
  await save.click();
  await expect(costs.getByRole("alert")).toBeVisible();
  await save.click();
  await expect(history).toContainText("10.00 USD");
  await expect(budget).toContainText("actual 10.00");
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toEqual(keys[0]);
  await expect(costs.getByRole("alert")).toContainText("Cost saved.");
  await expect(newLink).toBeDisabled();
  await costs.getByRole("button", { name: "Retry actual costs" }).click();
  await expect(newLink).toBeEnabled();
  expect(keys).toHaveLength(2);

  await newLink.click();
  await select("Budget line").selectOption("0:1");
  await select("Cost source").selectOption("payable");
  await select("Ledger book").selectOption(fixture.book);
  await select("Payable type").selectOption("manual_accrual");
  await select("Issued payable").selectOption(fixture.payable);
  await select("Payable line").selectOption(fixture.payable_line);
  await save.click();
  await expect(history).toContainText("40.00 USD");

  await newLink.click();
  await select("Budget line").selectOption("0:1");
  await select("Cost source").selectOption("time_entry");
  await select("Approved time entry").selectOption(fixture.time_entry);
  await form.getByRole("textbox", { name: "Hourly rate (USD)" }).fill("72.00");
  await save.click();
  await expect(history).toContainText("60.00 USD");
  await expect(budget).toContainText("actual 110.00");

  await costs.getByRole("button", { name: "Reverse cost 1" }).click();
  await costs
    .getByRole("textbox", { name: "Reversal reason" })
    .fill("Wrong budget line");
  await costs.getByRole("button", { name: "Confirm reversal" }).click();
  await expect(
    history.getByRole("row").filter({ hasText: "10.00 USD" }),
  ).toContainText("Reversed · Wrong budget line");
  await expect(budget).toContainText("actual 100.00");
  const axe = await new AxeBuilder({ page })
    .include(".construction-screen")
    .analyze();
  expect(axe.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
