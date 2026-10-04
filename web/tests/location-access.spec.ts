import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

test("location manager completes a booking cycle without accessing another branch", async ({
  page,
}) => {
  await page.goto("/overview/");
  const staffRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/overview") &&
      request.headers()["authorization"] != null,
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  const request = await staffRequest;
  const headers = { authorization: request.headers()["authorization"]! };
  const path = new URL(request.url()).pathname.replace(/\/overview$/, "");
  await expect(
    page.getByText("You have access to your assigned location.", {
      exact: false,
    }),
  ).toBeVisible();
  for (const name of ["Business profile", "Settings", "Services"]) {
    await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0);
  }
  const foreign = await page.request.get(
    `${path}/bookings/${process.env.GBA_PRIVATE_BOOKING}`,
    { headers },
  );
  expect(foreign.status()).toBe(404);
  const forbidden = await page.request.post(
    `${path}/bookings/${process.env.GBA_PRIVATE_BOOKING}/cancel`,
    { headers, data: {} },
  );
  expect(forbidden.status()).toBe(404);
  const workspace = await page.request.get(`${path}/workspace`, { headers });
  const scope = await workspace.json();
  expect(scope.locations).toHaveLength(1);
  expect(scope.location_id).toBe(scope.locations[0].id);
  await page.getByRole("link", { name: "Calendar", exact: true }).click();
  await expect(page.getByLabel("Location:")).toContainText("America/New_York");
  await expect(page.getByLabel("Location:").locator("option")).toHaveCount(1);
  const day = process.env.GBA_MGMT_BROWSER_DAY!;
  await page.getByLabel("Selected Calendar Date").fill(day);
  await page.getByRole("button", { name: "+ Book Appointment" }).click();
  await page
    .getByRole("combobox", { name: "Service:", exact: true })
    .selectOption({ label: "FAKE FAKE_BASE (60m) • $50.00" });
  await expect(
    page.getByRole("combobox", { name: "Staff:", exact: true }),
  ).not.toContainText("private employee");
  await page.getByLabel("Date:", { exact: true }).fill(day);
  await page.getByLabel("Start Time:", { exact: true }).fill("11:00");
  await page.getByLabel("Client Name:").fill("FAKE Location Browser Guest");
  await page
    .getByLabel("Email:", { exact: true })
    .fill("branch-browser@example.test");
  await page.getByLabel("Phone:", { exact: true }).fill("+15551234568");
  await page
    .getByRole("button", { name: "Create Appointment", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("link", { name: "Staff", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "FAKE private employee" }),
  ).toHaveCount(0);
  const staffRow = page.getByRole("row").filter({ hasText: "FAKE artist A1" });
  await staffRow.getByRole("button", { name: "Schedule", exact: true }).click();
  await page
    .getByRole("textbox", { name: /^Sunday interval .* closes$/ })
    .fill("15:00");
  await page
    .getByRole("button", { name: "Save Working Hours", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await staffRow.getByRole("button", { name: "Schedule", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: /^Sunday interval .* closes$/ }),
  ).toHaveValue("15:00");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await page.getByRole("link", { name: "Bookings", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "FAKE private browser guest" }),
  ).toHaveCount(0);
  let row = page
    .getByRole("row")
    .filter({ hasText: "FAKE Location Browser Guest" })
    .filter({ hasText: "CONFIRMED" });
  await row.getByRole("button", { name: "Reschedule", exact: true }).click();
  await page.getByLabel("New Date", { exact: true }).fill(day);
  await page.getByLabel(/New Start Time/).fill("13:00");
  await page
    .getByRole("button", {
      name: /Confirm Reschedule|Save Changes|Reschedule Appointment/,
    })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  row = page
    .getByRole("row")
    .filter({ hasText: "FAKE Location Browser Guest" })
    .filter({ hasText: "CONFIRMED" });
  await row.getByRole("button", { name: "Cancel", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm Cancellation", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "FAKE Location Browser Guest" })
      .filter({ hasText: "CONFIRMED" }),
  ).toHaveCount(0);
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(await page.evaluate(() => window.innerWidth)).toBeLessThanOrEqual(
    page.viewportSize()!.width,
  );
  await page.screenshot({
    path: `test-results/location-access-${page.viewportSize()?.width}.png`,
    fullPage: true,
  });
});
