import {
  test,
  expect,
  type Locator,
  type Page,
  type TestInfo,
} from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// R8a (package R): the rental catalogue, availability and bookings in a real browser. An owner
// creates a class and a unit, reads availability, books, assigns the unit and cancels a second
// booking. FAKE data seeded by test_r8a_rental_browser.py.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const OWNER = "FAKE user r8a-owner";

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

async function booked(
  page: Page,
  form: Locator,
  label: string,
  from: string,
  to: string,
) {
  await form.getByLabel("Class").selectOption({ label });
  await form.getByLabel("Customer").selectOption({ label: "FAKE Renter" });
  await form.getByLabel("Pickup branch").selectOption({ index: 1 });
  await form.getByLabel("Return branch").selectOption({ index: 1 });
  await period(form, from, to);
  const saved = page.getByText(/^Booking \d+ saved\.$/);
  const before = (await saved.allTextContents()).join("");
  await form.getByRole("button", { name: "Save booking" }).click();
  await expect(saved).toBeVisible();
  // Wait for this booking's notice, not the one an earlier booking left.
  if (before) await expect(saved).not.toHaveText(before);
  return ((await saved.textContent()) ?? "").match(/\d+/)?.[0] ?? "";
}

test("an owner builds the catalogue, books a unit and cancels a booking", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name as "desktop" | "mobile";
  const code = `FAKE-${project.toUpperCase()}`;
  const label = `${code} FAKE van ${project}`;
  const unitId = `FAKE-U-${project}`;
  // Each project books its own days so the two runs never share a period.
  const [from, to, later, after] =
    project === "desktop"
      ? ["2031-06-01", "2031-06-03", "2031-06-10", "2031-06-12"]
      : ["2031-07-01", "2031-07-03", "2031-07-10", "2031-07-12"];
  await signIn(page);
  await page.getByRole("link", { name: "Rental", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Rental", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Loading the rental catalogue…")).toBeHidden({
    timeout: 15000,
  });
  await accessible(page, testInfo, `${project}-empty`);

  // A class with an odometer.
  const classForm = page.getByRole("form", { name: "Class" });
  await classForm.getByLabel("Code").fill(code);
  await classForm.getByLabel("Name").fill(`FAKE van ${project}`);
  await classForm.getByLabel("Meter").selectOption({ label: "Odometer" });
  await classForm.getByRole("button", { name: "Save class" }).click();
  await expect(page.getByText(`Class ${code} saved.`)).toBeVisible();
  const classes = page.getByRole("table", { name: "Classes" });
  await expect(
    classes.getByRole("row").filter({ hasText: code }),
  ).toContainText("Odometer");

  // A unit of that class at the first branch.
  const unitForm = page.getByRole("form", { name: "Unit" });
  await unitForm.getByLabel("Class").selectOption({ label });
  await unitForm.getByLabel("Identifier").fill(unitId);
  await unitForm.getByLabel("Branch").selectOption({ index: 1 });
  await unitForm.getByRole("button", { name: "Save unit" }).click();
  await expect(page.getByText(`Unit ${unitId} saved.`)).toBeVisible();
  const units = page.getByRole("table", { name: "Units" });
  await expect(
    units.getByRole("row").filter({ hasText: unitId }),
  ).toContainText("Active");

  // Availability is the server's.
  const check = page.getByRole("form", { name: "Availability" });
  await check.getByLabel("Class").selectOption({ label });
  await check.getByLabel("Branch").selectOption({ index: 1 });
  await period(check, from, to);
  await check.getByRole("button", { name: "Check availability" }).click();
  await expect(page.getByText("Available: 1 of 1 (booked 0)")).toBeVisible();

  // A booking; then the unit is assigned to it.
  const book = page.getByRole("form", { name: "Booking" });
  await book.getByLabel("Note").fill(`FAKE note ${project}`);
  const first = await booked(page, book, label, from, to);
  await check.getByRole("button", { name: "Check availability" }).click();
  await expect(page.getByText("Available: 0 of 1 (booked 1)")).toBeVisible();

  const bookings = page.getByRole("table", { name: "Bookings" });
  await bookings
    .getByRole("button", { name: `Booking ${first}`, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: `Booking ${first}`, exact: true }),
  ).toBeVisible();
  const assign = page.getByRole("form", { name: "Assign a unit" });
  await assign.getByLabel("Unit").selectOption({ label: unitId });
  await assign.getByRole("button", { name: "Assign unit" }).click();
  await expect(page.getByText(`Unit ${unitId} assigned.`)).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "Assignments" })
      .getByRole("row")
      .filter({ hasText: unitId }),
  ).toContainText("Current");
  await accessible(page, testInfo, `${project}-booking`);

  // A second booking, cancelled with a reason, by keyboard.
  await book.getByLabel("Note").fill("");
  const second = await booked(page, book, label, later, after);
  expect(second).not.toBe(first);
  await bookings
    .getByRole("button", { name: `Booking ${second}`, exact: true })
    .click();
  const cancel = page.getByRole("form", { name: "Cancel booking" });
  await cancel.getByLabel("Reason").fill(`FAKE plans changed ${project}`);
  await cancel.getByLabel("Reason").press("Enter");
  await expect(page.getByText(`Booking ${second} cancelled.`)).toBeVisible();
  await expect(
    bookings.getByRole("row").filter({ hasText: `Booking ${second}` }),
  ).toContainText("Cancelled");
  await accessible(page, testInfo, `${project}-cancelled`);
});
