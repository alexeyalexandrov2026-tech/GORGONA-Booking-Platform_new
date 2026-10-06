import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

test("reservations: take resources, refuse an overlap, cancel and keep the record", async ({
  page,
}, testInfo) => {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Reservations", exact: true }).click();
  const panel = page.getByRole("region", {
    name: "Resource reservations",
    exact: true,
  });
  const status = panel.getByRole("status");
  const alert = panel.getByRole("alert");
  if (testInfo.project.name === "desktop") {
    await panel.getByLabel("FAKE artist A1", { exact: true }).check();
    await panel.getByLabel("FAKE artist A2", { exact: true }).check();
    await panel.getByLabel("Starts at", { exact: true }).fill("09:00");
    await panel.getByLabel("Ends at", { exact: true }).fill("10:00");
    await panel
      .getByLabel("Purpose", { exact: true })
      .fill("FAKE team training");
    await panel.getByRole("button", { name: "Reserve", exact: true }).click();
    await expect(status).toHaveText("Reservation saved.");
    await expect(panel).toContainText(
      "09:00–10:00 · FAKE artist A1, FAKE artist A2 · FAKE team training · active",
    );
    // The same resource cannot be reserved twice for an overlapping interval.
    await panel.getByLabel("FAKE artist A1", { exact: true }).check();
    await panel.getByLabel("Starts at", { exact: true }).fill("09:30");
    await panel.getByLabel("Ends at", { exact: true }).fill("10:30");
    await panel.getByRole("button", { name: "Reserve", exact: true }).click();
    await expect(alert).toContainText("already taken");
    await panel
      .getByRole("button", {
        name: "Cancel reservation 09:00 · FAKE artist A1, FAKE artist A2",
        exact: true,
      })
      .click();
    await expect(status).toHaveText("Reservation cancelled.");
  }
  await expect(panel).toContainText(
    "09:00–10:00 · FAKE artist A1, FAKE artist A2 · FAKE team training · cancelled",
  );
  const audit = await new AxeBuilder({ page }).analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
