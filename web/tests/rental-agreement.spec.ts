import {
  test,
  expect,
  type Locator,
  type Page,
  type TestInfo,
} from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// R8b (package R): a rate card, the quote, the accepted agreement and the security of a booking in a
// real browser. FAKE data seeded by test_r8b_rental_agreement_browser.py.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const OWNER = "FAKE user r8b-owner";

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

test("an owner prices a booking, records the agreement and keeps its security", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name as "desktop" | "mobile";
  const code = `FAKE-AG-${project.toUpperCase()}`;
  const label = `${code} FAKE car ${project}`;
  const unitId = `FAKE-AG-U-${project}`;
  const [from, to] =
    project === "desktop"
      ? ["2031-08-01", "2031-08-03"]
      : ["2031-09-01", "2031-09-03"];
  await signIn(page);
  await page.getByRole("link", { name: "Rental", exact: true }).click();
  await expect(page.getByText("Loading the rental catalogue…")).toBeHidden({
    timeout: 15000,
  });

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

  // A rate card: 50.00 a day, 100 km a day included, 0.25 per km over.
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
  const cards = page.getByRole("table", { name: "Rate cards" });
  await expect(cards.getByRole("row").filter({ hasText: code })).toContainText(
    "50.00",
  );

  // A booking of two days.
  const book = page.getByRole("form", { name: "Booking" });
  await book.getByLabel("Class").selectOption({ label });
  await book.getByLabel("Customer").selectOption({ label: "FAKE Renter" });
  await book.getByLabel("Pickup branch").selectOption({ index: 1 });
  await book.getByLabel("Return branch").selectOption({ index: 1 });
  await period(book, from, to);
  await book.getByRole("button", { name: "Save booking" }).click();
  const saved = page.getByText(/^Booking \d+ saved\.$/);
  await expect(saved).toBeVisible();
  const number = ((await saved.textContent()) ?? "").match(/\d+/)?.[0] ?? "";
  await page
    .getByRole("table", { name: "Bookings" })
    .getByRole("button", { name: `Booking ${number}`, exact: true })
    .click();

  // The quote is the server's; the agreement freezes it.
  await expect(
    page.getByText("Quote: rental 100.00 USD for 2 days, total 100.00 USD"),
  ).toBeVisible();
  const accept = page.getByRole("form", { name: "Accept the agreement" });
  // R9 (R-09): no customer answers on the platform yet, so the source is paper or email.
  await expect(accept.getByLabel("Source").locator("option")).toHaveText([
    "Paper",
    "Email",
  ]);
  await accept.getByLabel("Source").selectOption({ label: "Paper" });
  await accept.getByLabel("Accepted by").fill("FAKE Renter");
  await accept.getByLabel("Accepted on").fill("2026-01-02");
  await accept.getByLabel("Accepted at").fill("10:00");
  await accept.getByRole("button", { name: "Accept agreement" }).click();
  await expect(page.getByText("Agreement accepted.")).toBeVisible();
  const versions = page.getByRole("table", { name: "Agreement versions" });
  await expect(
    versions.getByRole("row").filter({ hasText: "FAKE Renter" }),
  ).toContainText("100.00");

  // The security: requested, held in full, then part captured with a basis.
  const request = page.getByRole("form", { name: "Request security" });
  await request.getByLabel("Amount").fill("200.00");
  await request.getByLabel("Method").selectOption({ label: "Card hold" });
  await request.getByRole("button", { name: "Request security" }).click();
  await expect(page.getByText("Security requested.")).toBeVisible();
  const event = page.getByRole("form", { name: "Security event" });
  await event.getByLabel("Kind").selectOption({ label: "Held" });
  await event.getByLabel("Amount").fill("200.00");
  await event.getByLabel("Reference").fill(`FAKE-TERM-${project}`);
  await event.getByRole("button", { name: "Record event" }).click();
  await expect(
    page.getByText("Security: held; held 200.00, captured 0.00"),
  ).toBeVisible();
  await event.getByLabel("Kind").selectOption({ label: "Captured" });
  await event.getByLabel("Amount").fill("30.00");
  await event.getByLabel("Reference").fill("");
  await event.getByLabel("Basis").fill(`FAKE scratch ${project}`);
  await event.getByRole("button", { name: "Record event" }).click();
  await expect(
    page.getByText("Security: held; held 200.00, captured 30.00"),
  ).toBeVisible();
  await expect(page.getByText("remaining 170.00")).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "Security events" })
      .getByRole("row")
      .filter({ hasText: "Captured" }),
  ).toContainText(`FAKE scratch ${project}`);
  await accessible(page, testInfo, `${project}-agreement`);
});
