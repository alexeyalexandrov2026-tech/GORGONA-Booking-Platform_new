import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// O7b (package O): the budget, a subcontract revised above its budget line, the schedule with a
// dependency, a daily report saved by keyboard and a completed quantity recorded after a lost answer.
// FAKE data seeded by test_o7b_construction_browser.py (a contracted project per browser).
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const OWNER = "FAKE user o7b-owner";

async function accessible(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".construction-screen")
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

const alert = (page: Page) =>
  page.locator(".construction-screen").getByRole("alert");

test("an owner follows the budget, the schedule, the site diary and the progress", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name as "desktop" | "mobile";
  const number = `FAKE-CP-O7B-${project}`;
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(OWNER, { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Construction", exact: true }).click();
  await expect(page.getByText("Loading the projects…")).toBeHidden({
    timeout: 15000,
  });
  await page
    .getByRole("table", { name: "Projects" })
    .getByRole("button", { name: number })
    .click();
  await expect(
    page.getByRole("heading", { name: `Project ${number}`, exact: true }),
  ).toBeVisible();

  // The budget is the contract's cost side.
  const lines = page.getByRole("table", { name: "Budget lines" });
  const wiring = lines.getByRole("row").filter({ hasText: "FAKE wiring" });
  await expect(wiring).toContainText("320.00");

  // A subcontract, then a revision above the line's budget.
  const commitment = page.getByRole("form", { name: "Commitment" });
  await commitment.getByLabel("Kind").selectOption({ label: "Subcontract" });
  await commitment
    .getByLabel("Counterparty")
    .selectOption({ label: "FAKE Electric Co" });
  await commitment.getByLabel("Title").fill("FAKE wiring subcontract");
  await commitment
    .getByLabel("Commitment line 1 budget line")
    .selectOption({ label: "Contract line 2 · Electrical · FAKE wiring" });
  await commitment.getByLabel("Commitment line 1 amount").fill("300");
  await commitment.getByRole("button", { name: "Save commitment" }).click();
  const commitments = page.getByRole("table", { name: "Commitments" });
  const first = commitments
    .getByRole("row")
    .filter({ hasText: "FAKE wiring subcontract" });
  await expect(first).toContainText("300.00");
  await expect(first).toContainText("Open");
  await expect(wiring).toContainText("20.00");

  await first.getByRole("button", { name: "Commitment 1" }).click();
  const revise = page.getByRole("form", { name: "Revise commitment 1" });
  await revise.getByLabel("Commitment line 1 amount").fill("340");
  await revise.getByRole("button", { name: "Save commitment" }).click();
  await expect(first).toContainText("340.00");
  await expect(wiring).toContainText("Over committed");
  await expect(wiring).toContainText("-20.00");
  await accessible(page, testInfo, `${project}-budget`);

  // The schedule: electrical after framing.
  const schedule = page.getByRole("form", { name: "Schedule" });
  await schedule.getByLabel("Framing planned start").fill("2031-06-02");
  await schedule.getByLabel("Framing planned finish").fill("2031-06-05");
  await schedule.getByLabel("Electrical planned start").fill("2031-06-06");
  await schedule.getByLabel("Electrical planned finish").fill("2031-06-09");
  await schedule.getByLabel("Electrical depends on Framing").check();
  await schedule.getByRole("button", { name: "Save schedule" }).click();
  await expect(page.getByText("Planned finish: 2031-06-09")).toBeVisible();
  const planned = page.getByRole("table", { name: "Planned phases" });
  await expect(
    planned.getByRole("row").filter({ hasText: "Electrical" }),
  ).toContainText("Framing");

  // A daily report, saved by keyboard.
  const diary = page.getByRole("form", { name: "Daily report" });
  await diary.getByLabel("Report date").fill("2026-10-01");
  await diary.getByLabel("Weather").fill("FAKE sunny");
  await diary.getByLabel("Crew 1 label").fill("FAKE framers");
  await diary.getByLabel("Crew 1 headcount").fill("3");
  const save = diary.getByRole("button", { name: "Save report" });
  await save.focus();
  await page.keyboard.press("Enter");
  const reports = page.getByRole("table", { name: "Daily reports" });
  await expect(
    reports.getByRole("row").filter({ hasText: "2026-10-01" }),
  ).toContainText("FAKE sunny");
  await expect(alert(page)).toBeHidden();

  // A completed quantity after a lost answer: recorded once.
  let lost = false;
  await page.route("**/construction/projects/*/progress", async (route) => {
    if (!lost && route.request().method() === "POST") {
      lost = true;
      await route.fetch();
      await route.abort();
      return;
    }
    await route.continue();
  });
  const done = page.getByRole("form", { name: "Completed quantity" });
  await done
    .getByLabel("Line", { exact: true })
    .selectOption({ label: "Contract line 1 · Framing · FAKE drywall" });
  await done.getByLabel("Measured on").fill("2026-10-01");
  await done.getByLabel("Quantity to date").fill("4");
  await done.getByRole("button", { name: "Record quantity" }).click();
  await expect(alert(page)).toBeVisible();
  await done.getByRole("button", { name: "Record quantity" }).click();
  await expect(alert(page)).toBeHidden();
  await expect(
    page.getByRole("table", { name: "Measurements" }).getByRole("row"),
  ).toHaveCount(2);
  const drywall = page
    .getByRole("table", { name: "Progress lines" })
    .getByRole("row")
    .filter({ hasText: "FAKE drywall" });
  await expect(drywall).toContainText("40.00%");
  await expect(drywall).toContainText("100.00");
  await accessible(page, testInfo, `${project}-execution`);
});
