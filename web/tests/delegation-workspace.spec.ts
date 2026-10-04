import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

test("designated employee books for the owner business within the grant", async ({
  page,
}) => {
  const owner = process.env.GBA_OWNER_BUSINESS!;
  await page.goto("/overview/");
  const signedRequest = page.waitForRequest(
    (request) =>
      request.url().includes("/v1/") &&
      request.headers()["authorization"] != null,
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  const headers = {
    authorization: (await signedRequest).headers()["authorization"]!,
  };
  await page
    .getByLabel("Active Salon")
    .selectOption({ label: "FAKE browser call centre (delegated)" });
  await expect(
    page.getByText(
      "You are working for another business: FAKE browser call centre.",
      { exact: false },
    ),
  ).toBeVisible();
  for (const name of ["Overview", "Calendar", "Bookings", "Clients"])
    await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  for (const name of ["Business profile", "Services", "Staff", "Settings"])
    await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0);
  for (const path of [
    `/v1/businesses/${owner}`,
    `/v1/businesses/${owner}/legal-entities`,
    `/v1/businesses/${owner}/delegations`,
    `/v1/salons/${owner}/settings`,
    `/v1/salons/${owner}/members`,
  ])
    expect((await page.request.get(path, { headers })).status()).toBe(403);

  await page.getByRole("link", { name: "Calendar", exact: true }).click();
  await expect(page.getByLabel("Location:")).toContainText("America/New_York");
  const day = process.env.GBA_MGMT_BROWSER_DAY!;
  await page.getByLabel("Selected Calendar Date").fill(day);
  await page.getByRole("button", { name: "+ Book Appointment" }).click();
  await page
    .getByRole("combobox", { name: "Service:", exact: true })
    .selectOption({ label: "FAKE FAKE_BASE (60m) • $50.00" });
  await page.getByLabel("Date:", { exact: true }).fill(day);
  await page.getByLabel("Start Time:", { exact: true }).fill("11:00");
  await page.getByLabel("Client Name:").fill("FAKE Delegated Browser Guest");
  await page
    .getByLabel("Email:", { exact: true })
    .fill("delegated-browser@example.test");
  await page.getByLabel("Phone:", { exact: true }).fill("+15551234570");
  await page
    .getByRole("button", { name: "Create Appointment", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByRole("link", { name: "Bookings", exact: true }).click();
  let row = page
    .getByRole("row")
    .filter({ hasText: "FAKE Delegated Browser Guest" })
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
    .filter({ hasText: "FAKE Delegated Browser Guest" })
    .filter({ hasText: "CONFIRMED" });
  await row.getByRole("button", { name: "Cancel", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm Cancellation", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "FAKE Delegated Browser Guest" })
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
    path: `test-results/delegation-workspace-${page.viewportSize()?.width}.png`,
    fullPage: true,
  });
});
