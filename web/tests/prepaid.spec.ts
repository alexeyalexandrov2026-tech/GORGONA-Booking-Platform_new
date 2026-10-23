import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// L7b2b (package L): sell a prepaid package, then redeem it from the desk of an issued visit invoice.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const OWNER = "FAKE user l7b2b-owner";
const BOOKING = {
  desktop: process.env.GBA_L7B2B_DESKTOP_BOOKING ?? "",
  mobile: process.env.GBA_L7B2B_MOBILE_BOOKING ?? "",
};

async function signIn(page: Page) {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(OWNER, { exact: true }),
  ).toBeVisible();
}

async function accessible(
  page: Page,
  testInfo: TestInfo,
  selector: string,
  name: string,
) {
  const axe = await new AxeBuilder({ page }).include(selector).analyze();
  expect(axe.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(await page.evaluate(() => innerWidth <= screen.width)).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
}

async function openPrepaid(page: Page) {
  await page.getByRole("link", { name: "Prepaid", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Prepaid balances", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Loading the balances…")).toBeHidden({
    timeout: 15000,
  });
}

test("a prepaid package is sold and redeemed from the visit desk", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name as "desktop" | "mobile";
  const booking = BOOKING[project];
  expect(booking).not.toBe("");
  const customer = `FAKE Customer ${project}`;
  await signIn(page);

  // Sell one visit of the base service, paid in advance.
  await openPrepaid(page);
  const sale = page.getByRole("form", { name: "Sell a prepaid balance" });
  await sale.getByLabel("Kind").selectOption({ label: "Package" });
  await sale.getByLabel("Customer").selectOption({ label: customer });
  await sale.getByLabel("Service").selectOption({ label: "FAKE FAKE_BASE" });
  await sale.getByLabel("Units").fill("1");
  await sale.getByLabel("Price").fill("50.00");
  await sale.getByLabel("Book").selectOption({ label: "FAKE Prepaid LLC" });
  await sale
    .getByLabel("Receivable account")
    .selectOption({ label: "1200 Accounts receivable" });
  await sale
    .getByLabel("Prepayment account")
    .selectOption({ label: "2100 Customer prepayments" });
  await sale.getByLabel("Number").fill(`FAKE-P-${project}`);
  await sale.getByRole("button", { name: "Sell" }).click();
  await expect(
    page.getByRole("status").filter({
      hasText: "Prepaid balance saved; finance issues its invoice.",
    }),
  ).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: customer });
  await expect(row).toContainText("Waiting for payment");
  await accessible(page, testInfo, ".prepaid-screen", "sold");

  // Finance issues the sale invoice and records its full payment (FIN-03 routes).
  const paid = await page.request.post(`${issuer}/fixture/pay-sale/${project}`);
  expect(paid.ok()).toBe(true);
  await page.reload();
  await signIn(page);
  await openPrepaid(page);
  await expect(
    page.getByRole("row").filter({ hasText: customer }),
  ).toContainText("Usable");

  // Redeem it from the desk of the issued visit invoice.
  await page.getByRole("link", { name: "Bookings", exact: true }).click();
  await page
    .locator(`tr[data-booking-id="${booking}"]`)
    .getByRole("button", { name: /^Visit desk/ })
    .click();
  const desk = page.getByRole("dialog", { name: "Visit desk" });
  await expect(desk).toBeVisible();
  await expect(desk.getByText("Loading the billing…")).toBeHidden({
    timeout: 15000,
  });
  const refused = desk.getByText(/^Billing is not available here/);
  if (await refused.count()) throw new Error(await refused.first().innerText());
  await expect(desk.getByText("Paid 0.00 of 60.00")).toBeVisible();
  const redeem = desk.getByRole("form", { name: "Redeem a prepaid balance" });
  await redeem
    .getByLabel("Prepaid balance")
    .selectOption({ label: "Package: FAKE FAKE_BASE · 1 of 1 left" });
  await redeem.getByLabel("Number").fill(`FAKE-R-${project}`);
  await redeem.getByRole("button", { name: "Redeem" }).click();
  await expect(
    desk
      .getByRole("status")
      .filter({ hasText: "Redeemed 50.00 from the prepaid balance." }),
  ).toBeVisible();
  await expect(desk.getByText("Credited 50.00")).toBeVisible();
  // L8 decision 68: 10.00 is still open, but the used balance is no longer offered; with no
  // other usable balance the redemption form is gone.
  await expect(
    redeem.getByRole("option", { name: /FAKE FAKE_BASE/ }),
  ).toHaveCount(0);
  await expect(redeem).toHaveCount(0);
  await accessible(page, testInfo, ".visit-desk", "redeemed");

  // Keyboard only: close.
  await desk.getByRole("button", { name: "Close" }).focus();
  await page.keyboard.press("Enter");
  await expect(desk).toBeHidden();
});
