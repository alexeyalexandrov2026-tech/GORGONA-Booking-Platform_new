import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// M6a (package M): the dispatch board and the trip page — assignments, stop events with a lost answer
// retried once, and clearance. FAKE data seeded by test_m6a_transport_browser.py.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const OWNER = "FAKE user m6a-owner";

async function signIn(page: Page) {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(OWNER, { exact: true }),
  ).toBeVisible();
}

async function accessible(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".transport-screen")
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

async function assign(
  page: Page,
  role: string,
  assignee: string,
  from?: { date: string; time: string },
) {
  const form = page.getByRole("form", { name: "Assign or replace" });
  await form.getByLabel("Role").selectOption({ label: role });
  await form.getByLabel("Assignee").selectOption({ label: assignee });
  await form.getByLabel("From date").fill(from?.date ?? "");
  await form.getByLabel("From time").fill(from?.time ?? "");
  await form.getByRole("button", { name: "Assign" }).click();
  // The form clears only after the server saved the assignment.
  await expect(form.getByLabel("Assignee")).toHaveValue("");
  await expect(
    page.locator(".transport-screen").getByRole("alert"),
  ).toBeHidden();
}

async function record(
  page: Page,
  stop: string,
  kind: string,
  time: string,
  quantities: Record<string, string> = {},
) {
  const form = page.getByRole("form", { name: "Record a stop event" });
  await form.getByLabel("Stop").selectOption({ label: stop });
  await form.getByLabel("Event").selectOption({ label: kind });
  for (const [leg, quantity] of Object.entries(quantities))
    await form.getByLabel(`Leg ${leg} quantity`).fill(quantity);
  await form.getByLabel("Date").fill("2031-06-02");
  await form.getByLabel("Time").fill(time);
  await form.getByRole("button", { name: "Record" }).click();
}

test("the dispatcher assigns a crew, records stop events and checks clearance", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name as "desktop" | "mobile";
  const reference = `FAKE-TR-${project}`;
  await signIn(page);
  await page.getByRole("link", { name: "Transport", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Transport", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Loading the trips…")).toBeHidden({
    timeout: 15000,
  });
  const board = page.getByRole("table", { name: "Trips" });
  const row = board.getByRole("row").filter({ hasText: reference });
  await expect(row).toContainText("Planned");
  await expect(row).toContainText("2031-06-02 08:00 (America/Chicago)");
  await accessible(page, testInfo, `${project}-board`);

  await row.getByRole("button", { name: reference }).click();
  await expect(
    page.getByRole("heading", { name: `Trip ${reference}`, exact: true }),
  ).toBeVisible();
  const stops = page.getByRole("table", { name: "Stops" });
  await expect(stops).toContainText("2031-06-02 08:00–10:00 (America/Chicago)");
  await expect(stops).toContainText(
    "2031-06-02 20:00–23:00 (America/New_York)",
  );

  // A crew, then a truck replaced at noon in Chicago; both trucks stay in the history.
  await assign(page, "Driver", `FAKE Driver ${project}`);
  await assign(page, "Truck", `FAKE-T-${project}-1`);
  await assign(page, "Truck", `FAKE-T-${project}-2`, {
    date: "2031-06-02",
    time: "12:00",
  });
  const crew = page.getByRole("table", { name: "Assignments" });
  await expect(crew).toContainText(`FAKE Driver ${project}`);
  await expect(
    crew.getByRole("row").filter({ hasText: `FAKE-T-${project}-1` }),
  ).toContainText("2031-06-02 12:00 (America/Chicago)");
  await expect(
    crew.getByRole("row").filter({ hasText: `FAKE-T-${project}-2` }),
  ).toContainText("open");

  await record(page, "1 · Pickup · FAKE dock, Chicago", "Arrived", "08:30");
  await expect(page.getByText("Status: In transit")).toBeVisible();
  await record(page, "1 · Pickup · FAKE dock, Chicago", "Loaded", "09:00", {
    "1": "10",
    "2": "6",
  });
  const legs = page.getByRole("table", { name: "Legs" });
  // Leg 1 loaded 10 (cell 2), before the next event is entered.
  await expect(
    legs.getByRole("row").nth(1).getByRole("cell").nth(2),
  ).toHaveText("10");

  // The first delivery answer is lost after the server recorded it; the retry records nothing new.
  let lost = false;
  await page.route("**/transport/trips/*/events", async (route) => {
    if (!lost && route.request().method() === "POST") {
      lost = true;
      await route.fetch();
      await route.abort();
      return;
    }
    await route.continue();
  });
  await record(
    page,
    "2 · Delivery · FAKE yard, Indianapolis",
    "Delivered",
    "14:30",
    { "1": "7" },
  );
  await expect(
    page.locator(".transport-screen").getByRole("alert"),
  ).toBeVisible();
  await page
    .getByRole("form", { name: "Record a stop event" })
    .getByRole("button", { name: "Record" })
    .click();
  await expect(
    page.locator(".transport-screen").getByRole("alert"),
  ).toBeHidden();
  const first = legs.getByRole("row").nth(1);
  await expect(first.getByRole("cell").nth(3)).toHaveText("7");
  await expect(first.getByRole("cell").nth(6)).toHaveText("3");
  const log = page.getByRole("table", { name: "Event log" });
  await expect(log.getByRole("row")).toHaveCount(4);
  await expect(log).toContainText(
    "2031-06-02 14:30 (America/Indiana/Indianapolis)",
  );

  // Clearance by keyboard: fresh data clears the desktop crew; the mobile driver has no records.
  const check = page.getByRole("button", { name: "Check clearance" });
  await check.focus();
  await page.keyboard.press("Enter");
  const result = page.locator(".transport-clearance");
  if (project === "desktop") {
    await expect(result).toContainText("Clearance: Cleared");
  } else {
    await expect(result).toContainText("Clearance: Unknown");
    await expect(result).toContainText("Driver: Unknown — no duty records");
  }
  await accessible(page, testInfo, `${project}-trip`);
});
