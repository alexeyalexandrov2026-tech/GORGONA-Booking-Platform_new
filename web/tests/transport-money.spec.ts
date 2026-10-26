import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

// M7b (package M): an owner sets an order's rate, creates its customer invoice, registers a trip's pay
// components and accrues the driver's pay. Issuing and payment stay on the finance screens. FAKE data only.
const book = process.env.GBA_M7B_BOOK!;
const receivable = process.env.GBA_M7B_RECEIVABLE!;
const revenue = process.env.GBA_M7B_REVENUE!;
const expense = process.env.GBA_M7B_EXPENSE!;
const payable = process.env.GBA_M7B_PAYABLE!;

const screen = (page: Page) => page.locator(".transport-screen");
const statusOf = (page: Page) =>
  screen(page).locator(".transport-status[role=status]");

async function signIn(page: Page) {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText("FAKE user m7b-owner", {
      exact: true,
    }),
  ).toBeVisible();
}

async function check(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".transport-screen")
    .analyze();
  expect(axe.violations).toEqual([]);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
}

test("an owner sets the rate, invoices the order and accrues the trip's pay", async ({
  page,
}, testInfo) => {
  const p = testInfo.project.name as "desktop" | "mobile";
  await signIn(page);
  await page.getByRole("link", { name: "Transport", exact: true }).click();
  await expect(page.getByText("Loading the trips…")).toBeHidden();

  // Order money: a per-mile rate, then the customer invoice with an extra.
  await page.getByRole("button", { name: `Money for FAKE-SO-${p}` }).click();
  const money = page.getByRole("region", { name: `Money for FAKE-SO-${p}` });
  await expect(money).toContainText("No rate yet.");
  const rate = money.getByRole("form", { name: "Rate" });
  await rate.getByLabel("Basis").selectOption({ label: "Per mile" });
  await rate.getByLabel("Amount").fill("2.35");
  await rate.getByRole("button", { name: "Save rate" }).click();
  await expect(statusOf(page)).toHaveText("Rate saved.");
  await expect(money).toContainText("Per mile 2.35 USD (version 1)");
  const invoice = money.getByRole("form", { name: "Customer invoice" });
  await invoice.getByLabel("Book").selectOption({ label: book });
  await invoice
    .getByLabel("Receivable account")
    .selectOption({ label: receivable });
  await invoice.getByLabel("Revenue account").selectOption({ label: revenue });
  await invoice.getByLabel("Invoice date").fill("2026-10-25");
  await invoice.getByLabel("Number").fill(`FAKE-TI-${p}`);
  await invoice.getByRole("button", { name: "Add an extra" }).click();
  const extra = invoice.getByRole("group", { name: "Extra 1" });
  await extra.getByLabel("Description").fill("FAKE detention");
  await extra.getByLabel("Amount").fill("75.00");
  await extra.getByLabel("Account").selectOption({ label: revenue });
  // A per-mile rate needs the billed miles: refused in words, the form keeps what was entered.
  await invoice.getByRole("button", { name: "Create invoice" }).click();
  await expect(money.getByRole("alert")).toContainText("billed miles");
  await invoice.getByLabel("Miles").fill("412.5");
  await invoice.getByRole("button", { name: "Create invoice" }).click();
  await expect(statusOf(page)).toHaveText("Invoice draft created.");
  const lines = money.getByRole("table", { name: "Invoice lines" });
  await expect(lines).toContainText("969.38");
  await expect(lines).toContainText("75.00");
  await expect(money).toContainText("Total 1044.38 USD");
  await expect(
    money.getByRole("form", { name: "Customer invoice" }),
  ).toHaveCount(0);

  // Trip pay: a driver's per-mile pay and a dispatch fee, then the driver's accrual.
  await page
    .getByRole("table", { name: "Trips" })
    .getByRole("button", { name: `FAKE-TR-${p}` })
    .click();
  const pay = page.getByRole("region", { name: "Trip pay" });
  const component = pay.getByRole("form", { name: "Pay component" });
  await component
    .getByLabel("Recipient")
    .selectOption({ label: `FAKE Driver Pay ${p}` });
  await component.getByLabel("Role").selectOption({ label: "Driver" });
  await component.getByLabel("Formula").selectOption({ label: "Per mile" });
  await component.getByLabel("Rate per mile").fill("0.55");
  await component.getByRole("button", { name: "Register" }).click();
  await expect(statusOf(page)).toHaveText("Pay component registered.");
  await component
    .getByLabel("Recipient")
    .selectOption({ label: "FAKE Dispatch Co" });
  await component.getByLabel("Role").selectOption({ label: "Dispatch fee" });
  await component
    .getByLabel("Formula")
    .selectOption({ label: "Percent of an agreed base" });
  await component.getByLabel("Percent").fill("7.5");
  await component.getByLabel("Agreed base").fill("1250.00");
  await component.getByRole("button", { name: "Register" }).click();
  await expect(statusOf(page)).toHaveText("Pay component registered.");
  const table = pay.getByRole("table", { name: "Pay components" });
  await expect(table).toContainText("7.5% of 1250.00 USD");
  const accrue = pay.getByRole("form", { name: "Accrue" });
  await accrue
    .getByLabel("Component")
    .selectOption({ label: `Driver · FAKE Driver Pay ${p}` });
  await accrue.getByLabel("Book").selectOption({ label: book });
  await accrue.getByLabel("Expense account").selectOption({ label: expense });
  await accrue.getByLabel("Payable account").selectOption({ label: payable });
  await accrue.getByLabel("Accrual date").fill("2026-10-25");
  await accrue.getByLabel("Number").fill(`FAKE-TP-${p}`);
  await accrue.getByLabel("Miles").fill("412.5");
  await accrue.getByRole("button", { name: "Accrue" }).click();
  await expect(statusOf(page)).toHaveText("Pay accrued.");
  await expect(
    table.getByRole("row").filter({ hasText: "Driver" }),
  ).toContainText("226.88 USD · Draft");
  await check(page, testInfo, "money");
});
