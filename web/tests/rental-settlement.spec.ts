import {
  test,
  expect,
  type Locator,
  type Page,
  type TestInfo,
} from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// R8c (package R): after the agreement, the handover and return inspections, the usage, the
// settlement, a damage charge, an external refund and the reconciliation of a booking in a real
// browser. FAKE data seeded by test_r8c_rental_settlement_browser.py.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const OWNER = "FAKE user r8c-owner";
const book = process.env.GBA_R8C_BOOK!;
const receivable = process.env.GBA_R8C_RECEIVABLE!;
const revenue = process.env.GBA_R8C_REVENUE!;

async function signIn(page: Page) {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(OWNER, { exact: true }),
  ).toBeVisible();
}

async function accessible(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".rental-screen")
    .analyze();
  expect(axe.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
}

async function period(form: Locator, from: string, to: string) {
  await form.getByLabel("From date").fill(from);
  await form.getByLabel("From time").fill("10:00");
  await form.getByLabel("To date").fill(to);
  await form.getByLabel("To time").fill("10:00");
}

async function money(form: Locator, number: string) {
  await form.getByLabel("Book").selectOption({ label: book });
  await form
    .getByLabel("Receivable account")
    .selectOption({ label: receivable });
  await form.getByLabel("Revenue account").selectOption({ label: revenue });
  await form.getByLabel("Invoice date").fill("2026-11-02");
  await form.getByLabel("Number").fill(number);
}

test("an owner hands over, takes back, settles, charges and refunds a booking", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name as "desktop" | "mobile";
  const code = `FAKE-ST-${project.toUpperCase()}`;
  const label = `${code} FAKE car ${project}`;
  const unitId = `FAKE-ST-U-${project}`;
  const [from, to] =
    project === "desktop"
      ? ["2031-10-01", "2031-10-03"]
      : ["2031-12-01", "2031-12-03"];
  await signIn(page);
  await page.getByRole("link", { name: "Rental", exact: true }).click();
  await expect(page.getByText("Loading the rental catalogue…")).toBeHidden({
    timeout: 15000,
  });

  // A car with an odometer, its unit, a rate card (50.00 a day, 100 a day included, 0.25 over).
  const classForm = page.getByRole("form", { name: "Class" });
  await classForm.getByLabel("Code").fill(code);
  await classForm.getByLabel("Name").fill(`FAKE car ${project}`);
  await classForm.getByLabel("Meter").selectOption({ label: "Odometer" });
  await classForm.getByRole("button", { name: "Save class" }).click();
  await expect(page.getByText(`Class ${code} saved.`)).toBeVisible();
  const unitForm = page.getByRole("form", { name: "Unit" });
  await unitForm.getByLabel("Class").selectOption({ label });
  await unitForm.getByLabel("Identifier").fill(unitId);
  await unitForm.getByLabel("Branch").selectOption({ index: 1 });
  await unitForm.getByRole("button", { name: "Save unit" }).click();
  await expect(page.getByText(`Unit ${unitId} saved.`)).toBeVisible();
  const cardForm = page.getByRole("form", { name: "Rate card" });
  await cardForm.getByLabel("Class").selectOption({ label });
  await cardForm.getByLabel("Branch").selectOption({ index: 1 });
  await cardForm.getByLabel("Currency").fill("USD");
  await cardForm.getByLabel("Day rate").fill("50.00");
  await cardForm.getByLabel("Meter allowance per day").fill("100");
  await cardForm.getByLabel("Excess rate").fill("0.25");
  await cardForm.getByRole("button", { name: "Save rate card" }).click();
  await expect(
    page.getByText(`Rate card version 1 for ${code} saved.`),
  ).toBeVisible();

  // A booking of two days, its agreement and its unit.
  const bookForm = page.getByRole("form", { name: "Booking" });
  await bookForm.getByLabel("Class").selectOption({ label });
  await bookForm.getByLabel("Customer").selectOption({ label: "FAKE Renter" });
  await bookForm.getByLabel("Pickup branch").selectOption({ index: 1 });
  await bookForm.getByLabel("Return branch").selectOption({ index: 1 });
  await period(bookForm, from, to);
  await bookForm.getByRole("button", { name: "Save booking" }).click();
  const saved = page.getByText(/^Booking \d+ saved\.$/);
  await expect(saved).toBeVisible();
  const number = ((await saved.textContent()) ?? "").match(/\d+/)?.[0] ?? "";
  await page
    .getByRole("table", { name: "Bookings" })
    .getByRole("button", { name: `Booking ${number}`, exact: true })
    .click();
  const accept = page.getByRole("form", { name: "Accept the agreement" });
  await accept.getByLabel("Source").selectOption({ label: "Paper" });
  await accept.getByLabel("Accepted by").fill("FAKE Renter");
  await accept.getByLabel("Accepted on").fill("2026-11-01");
  await accept.getByLabel("Accepted at").fill("10:00");
  await accept.getByRole("button", { name: "Accept agreement" }).click();
  await expect(page.getByText("Agreement accepted.")).toBeVisible();
  const assign = page.getByRole("form", { name: "Assign a unit" });
  await assign.getByLabel("Unit").selectOption({ label: unitId });
  await assign.getByRole("button", { name: "Assign unit" }).click();
  await expect(page.getByText(`Unit ${unitId} assigned.`)).toBeVisible();

  // Handover at 1000 with a known scratch; return at 1300 with a new dent.
  const inspect = page.getByRole("form", { name: "Inspection" });
  await inspect.getByLabel("Meter").fill("1000");
  await inspect.getByLabel("Level (%)").fill("80");
  await inspect.getByLabel("Mark area").fill("FAKE front bumper");
  await inspect.getByLabel("Mark severity").selectOption({ label: "Minor" });
  await inspect.getByRole("button", { name: "Add mark" }).click();
  await inspect.getByRole("button", { name: "Record handover" }).click();
  await expect(page.getByText("Handover recorded.")).toBeVisible();
  await expect(page.getByText("Usage: out")).toBeVisible();
  await inspect.getByLabel("Meter").fill("1300");
  await inspect.getByLabel("Mark area").fill("FAKE rear door");
  await inspect.getByLabel("Mark severity").selectOption({ label: "Major" });
  await inspect.getByLabel("Mark note").fill(`FAKE dent ${project}`);
  await inspect.getByLabel("New since the handover").check();
  await inspect.getByRole("button", { name: "Add mark" }).click();
  await inspect.getByRole("button", { name: "Record return" }).click();
  await expect(page.getByText("Return recorded.")).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "Inspection marks" })
      .getByRole("row")
      .filter({ hasText: "FAKE rear door" }),
  ).toContainText("Yes");
  await expect(
    page.getByText(
      "Usage: returned; overdue 0 h; distance 300, allowance 200, excess 100 (25.00 USD)",
    ),
  ).toBeVisible();

  // The settlement: rental 100.00 and excess 25.00.
  const settle = page.getByRole("form", { name: "Settle" });
  await money(settle, `FAKE-RS-${project}`);
  await settle.getByRole("button", { name: "Settle" }).click();
  await expect(page.getByText("Settlement recorded.")).toBeVisible();
  await expect(
    page.getByText(
      "Settlement: rental 100.00, excess 25.00, late 0.00, total 125.00 USD",
    ),
  ).toBeVisible();

  // A damage charge on the new mark, then an external refund.
  const charge = page.getByRole("form", { name: "Damage charge" });
  await charge.getByLabel("Mark 1: FAKE rear door (major)").check();
  await charge.getByLabel("Amount").fill("80.00");
  await charge.getByLabel("Reason").fill(`FAKE dent ${project}`);
  await money(charge, `FAKE-RD-${project}`);
  await charge.getByRole("button", { name: "Charge" }).click();
  await expect(page.getByText("Damage charge 1 recorded.")).toBeVisible();
  const refund = page.getByRole("form", { name: "Refund" });
  await refund.getByLabel("Method").selectOption({ label: "External" });
  await refund.getByLabel("Amount").fill("10.00");
  await refund.getByLabel("Reason").fill("FAKE goodwill");
  await refund.getByLabel("Reference").fill(`FAKE-REF-${project}`);
  await refund.getByLabel("Refunded on").fill("2026-11-03");
  await refund.getByLabel("Refunded at").fill("09:00");
  await refund.getByRole("button", { name: "Record refund" }).click();
  await expect(page.getByText("Refund 1 recorded.")).toBeVisible();

  // The reconciliation, all drafts in FIN-03 until issued there.
  const documents = page.getByRole("table", {
    name: "Reconciliation documents",
  });
  await expect(
    documents.getByRole("row").filter({ hasText: "Settlement" }),
  ).toContainText("125.00");
  await expect(
    documents.getByRole("row").filter({ hasText: "Damage charge" }),
  ).toContainText("80.00");
  await expect(
    page.getByText(
      "Totals: charged 205.00, invoiced 0.00, paid 0.00, credited 0.00, open 0.00, " +
        "refunded externally 10.00, refund owed 0.00 USD",
    ),
  ).toBeVisible();
  await accessible(page, testInfo, `${project}-settlement`);
});
