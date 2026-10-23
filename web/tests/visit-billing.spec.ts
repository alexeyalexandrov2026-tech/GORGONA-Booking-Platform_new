import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// L7b2a (package L): bill a visit, then accrue the specialist's commission once it is paid.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const OWNER = "FAKE user l7b2-owner";
const BOOKING = {
  desktop: process.env.GBA_L7B2_DESKTOP_BOOKING ?? "",
  mobile: process.env.GBA_L7B2_MOBILE_BOOKING ?? "",
};
const ARTIST = { desktop: "FAKE artist A1", mobile: "FAKE artist A2" };

const CONFIGURATION = "**/v1/businesses/*/configuration";

// L8 decision 70: the desk follows the business's modules; switch some off in the answer.
async function withoutModules(page: Page, off: string[]) {
  await page.route(CONFIGURATION, async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as { effective_module_ids: string[] };
    body.effective_module_ids = body.effective_module_ids.filter(
      (id) => !off.includes(id),
    );
    await route.fulfill({ response, json: body });
  });
}

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

async function openDesk(page: Page, booking: string) {
  await page.getByRole("link", { name: "Bookings", exact: true }).click();
  await page
    .locator(`tr[data-booking-id="${booking}"]`)
    .getByRole("button", { name: /^Visit desk/ })
    .click();
  const desk = page.getByRole("dialog", { name: "Visit desk" });
  await expect(desk).toBeVisible();
  return desk;
}

test("a visit is billed and its commission accrued once paid", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name as "desktop" | "mobile";
  const booking = BOOKING[project];
  expect(booking).not.toBe("");
  await signIn(page);

  // The specialist's plan: 10 % of every service.
  await page.getByRole("link", { name: "Staff", exact: true }).click();
  await page
    .getByRole("button", { name: `Commission plan of ${ARTIST[project]}` })
    .click();
  const plan = page.getByRole("dialog", {
    name: `Commission plan: ${ARTIST[project]}`,
  });
  await plan
    .getByLabel("Paid to")
    .selectOption({ label: `FAKE Specialist ${project}` });
  await plan.getByRole("button", { name: "Add rule" }).click();
  const rule = plan.getByRole("group", { name: "Rule 1" });
  await rule
    .getByLabel("Service")
    .selectOption({ label: "All other services" });
  await rule.getByLabel("Percentage").fill("10");
  await plan.getByRole("button", { name: "Save plan" }).click();
  await expect(
    plan.getByRole("status").filter({ hasText: "Plan saved." }),
  ).toBeVisible();
  await accessible(page, testInfo, ".commission-plan", "plan-saved");
  await plan.getByRole("button", { name: "Close" }).click();

  // With invoices off the desk shows no billing form, only a plain line.
  await withoutModules(page, ["finance_documents"]);
  let desk = await openDesk(page, booking);
  await expect(
    desk.getByText("Billing is turned off in this business's configuration."),
  ).toBeVisible();
  await expect(desk.getByRole("form", { name: "Invoice" })).toHaveCount(0);
  await accessible(page, testInfo, ".visit-desk", "billing-off");
  await desk.getByRole("button", { name: "Close" }).click();
  await page.unroute(CONFIGURATION);

  // Bill the visit from its desk.
  desk = await openDesk(page, booking);
  const billing = desk.getByRole("form", { name: "Invoice" });
  await billing.getByLabel("Book").selectOption({ label: "FAKE Billing LLC" });
  await billing.getByLabel("Customer").selectOption({ label: "FAKE Customer" });
  await billing
    .getByLabel("Receivable account")
    .selectOption({ label: "1200 Accounts receivable" });
  await billing
    .getByLabel("Revenue account")
    .selectOption({ label: "4100 Services" });
  await billing.getByLabel("Number").fill(`FAKE-V-${project}`);
  await billing.getByRole("button", { name: "Create invoice" }).click();
  await expect(
    desk.getByRole("status").filter({ hasText: "Invoice saved as a draft." }),
  ).toBeVisible();
  await expect(
    desk.getByText(`Invoice FAKE-V-${project}: draft`),
  ).toBeVisible();
  await accessible(page, testInfo, ".visit-desk", "invoice-draft");
  await desk.getByRole("button", { name: "Close" }).click();

  // Finance issues the invoice and records the full payment (FIN-03 routes).
  const paid = await page.request.post(`${issuer}/fixture/pay/${project}`);
  expect(paid.ok()).toBe(true);

  await page.reload();
  await signIn(page);
  desk = await openDesk(page, booking);
  // The desk reads the visit, its materials and its billing at once; wait for the billing
  // explicitly and name any refusal instead of timing out on the paid line.
  await expect(desk.getByText("Loading the billing…")).toBeHidden({
    timeout: 15000,
  });
  const refused = desk.getByText(/^Billing is not available here/);
  if (await refused.count()) throw new Error(await refused.first().innerText());
  await expect(desk.getByText("Paid 50.00 of 50.00")).toBeVisible();

  // With workforce off the paid visit shows no commission form.
  await desk.getByRole("button", { name: "Close" }).click();
  await withoutModules(page, ["workforce"]);
  desk = await openDesk(page, booking);
  await expect(
    desk.getByText(
      "Commissions are turned off in this business's configuration.",
    ),
  ).toBeVisible();
  await expect(desk.getByRole("form", { name: "Commission" })).toHaveCount(0);
  await accessible(page, testInfo, ".visit-desk", "commission-off");
  await desk.getByRole("button", { name: "Close" }).click();
  await page.unroute(CONFIGURATION);
  desk = await openDesk(page, booking);
  await expect(desk.getByText("Loading the billing…")).toBeHidden({
    timeout: 15000,
  });
  const commission = desk.getByRole("form", { name: "Commission" });
  await commission
    .getByLabel("Expense account")
    .selectOption({ label: "6000 Wages and salaries" });
  await commission
    .getByLabel("Payable account")
    .selectOption({ label: "2200 Wages payable" });
  await commission.getByLabel("Number").fill(`FAKE-C-${project}`);
  await commission.getByRole("button", { name: "Accrue commission" }).click();
  await expect(
    desk.getByRole("status").filter({ hasText: "Commission accrued: 5.00" }),
  ).toBeVisible();
  await accessible(page, testInfo, ".visit-desk", "commission");

  // L9b: finance refunds the service; the desk reverses the commission's share.
  const refunded = await page.request.post(
    `${issuer}/fixture/refund/${project}`,
  );
  expect(refunded.ok()).toBe(true);
  await page.reload();
  await signIn(page);
  desk = await openDesk(page, booking);
  await expect(desk.getByText("Loading the billing…")).toBeHidden({
    timeout: 15000,
  });
  const reversal = desk.getByRole("form", { name: "Reverse commission" });
  await expect(reversal).toContainText("5.00 of the commission");
  await reversal.getByLabel("Number").fill(`FAKE-CR-${project}`);
  await reversal.getByRole("button", { name: "Reverse commission" }).click();
  await expect(
    desk.getByRole("status").filter({ hasText: "Commission reversed: 5.00" }),
  ).toBeVisible();
  await expect(
    desk.getByRole("list", { name: "Commission reversals" }),
  ).toContainText("Refund reversed: 5.00");
  await expect(reversal).toHaveCount(0);
  await accessible(page, testInfo, ".visit-desk", "reversed");

  // Keyboard only: close.
  await desk.getByRole("button", { name: "Close" }).focus();
  await page.keyboard.press("Enter");
  await expect(desk).toBeHidden();
});
