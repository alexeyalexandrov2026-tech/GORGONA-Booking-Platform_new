import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });
async function signIn(page: Page) {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
}

test("business profile persists, retries uncertain saves and recovers from conflicts", async ({
  page,
}) => {
  await signIn(page);
  await page
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: /^Beauty and personal care/ })
    .check();
  await page.getByLabel("Find an activity").fill("trucking");
  await page
    .getByRole("checkbox", { name: /^Transportation and logistics/ })
    .check();
  await page.getByLabel("Business customers (B2B)").check();
  await page
    .getByLabel("Your activity name (optional)")
    .fill("FAKE Hybrid Business");
  const attempts: string[] = [];
  let loseResponse = true;
  await page.route("**/v1/businesses/*/profile", async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    attempts.push(route.request().headers()["idempotency-key"]!);
    if (loseResponse) {
      loseResponse = false;
      await route.fetch(); // Real server commits; only its response is lost.
      await route.abort("failed");
    } else await route.continue();
  });
  await page
    .getByRole("button", { name: "Save business profile", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Retry same save" }),
  ).toBeVisible();
  const saved = page.waitForRequest(
    (request) =>
      request.method() === "PUT" && request.url().endsWith("/profile"),
  );
  await page.getByRole("button", { name: "Retry same save" }).click();
  const request = await saved;
  await expect(page.getByRole("status")).toContainText(
    "Business profile saved",
  );
  expect(attempts).toHaveLength(2);
  expect(attempts[0]).toBe(attempts[1]);
  await page.unroute("**/v1/businesses/*/profile");
  await page.getByRole("button", { name: "Reload saved profile" }).click();
  await expect(page.getByLabel("Your activity name (optional)")).toHaveValue(
    "FAKE Hybrid Business",
  );
  await page.getByLabel("Find an activity").fill("");
  await expect(
    page.getByRole("checkbox", { name: /^Beauty and personal care/ }),
  ).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: /^Transportation and logistics/ }),
  ).toBeChecked();
  const headers = { authorization: request.headers()["authorization"]! };
  const current = await page.request.get(
    request.url().replace(/\/profile$/, ""),
    { headers },
  );
  const business = await current.json();
  const competitor = await page.request.put(request.url(), {
    headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
    data: { expected_revision: business.profile.revision, industry_ids: [2] },
  });
  expect(competitor.status()).toBe(200);
  await page
    .getByRole("button", { name: "Save business profile", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "profile changed",
  );
  await expect(
    page.getByRole("button", { name: "Save business profile", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Reload saved profile" }).click();
  await expect(
    page.getByRole("checkbox", { name: /^Restaurants and food service/ }),
  ).toBeChecked();
  // An explicit proxy rejection is not an uncertain save and must not lock the form.
  await page.route("**/v1/businesses/*/profile", (route) =>
    route.fulfill({ status: 403, contentType: "text/html", body: "Forbidden" }),
  );
  await page
    .getByRole("button", { name: "Save business profile", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "permission",
  );
  await expect(
    page.getByRole("button", { name: "Reload saved profile" }),
  ).toBeEnabled();
  await expect(page.getByLabel("Your activity name (optional)")).toBeEnabled();
  await page.unroute("**/v1/businesses/*/profile");
  await page.getByRole("button", { name: "Reload saved profile" }).click();
  await page
    .getByRole("checkbox", { name: /^Beauty and personal care/ })
    .check();
  await page
    .getByRole("checkbox", { name: /^Transportation and logistics/ })
    .check();
  await page.getByLabel("Business customers (B2B)").check();
  await page
    .getByRole("button", { name: "Save business profile", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Business profile saved",
  );
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `test-results/business-${page.viewportSize()?.width}.png`,
    fullPage: true,
  });
  await page.getByLabel("Find an activity").fill("trucking");
  await page.screenshot({
    path: `test-results/business-${page.viewportSize()?.width}-viewport.png`,
  });
});

test("legal entities persist, replay a lost response, preserve history and detect stale edits", async ({
  page,
}, testInfo) => {
  await signIn(page);
  await page
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  const section = page.getByRole("region", { name: "Legal entities" });
  await expect(
    section.getByRole("button", { name: "New legal entity", exact: true }),
  ).toBeVisible();
  await section
    .getByLabel("Internal reference")
    .fill(`FAKE_${testInfo.project.name.toUpperCase()}`);
  await section
    .getByLabel("Legal name", { exact: true })
    .fill("FAKE Browser Company LLC");
  const attempts: string[] = [];
  const ids: string[] = [];
  let loseResponse = true;
  await page.route("**/v1/businesses/*/legal-entities/*", async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    attempts.push(route.request().headers()["idempotency-key"]!);
    ids.push(route.request().url());
    if (loseResponse) {
      loseResponse = false;
      await route.fetch(); // Real persistence; the client loses only the response.
      await route.abort("failed");
    } else await route.continue();
  });
  await section
    .getByRole("button", { name: "Save legal entity", exact: true })
    .click();
  await expect(
    section.getByRole("button", { name: "Retry same entity save" }),
  ).toBeVisible();
  const requestPromise = page.waitForRequest(
    (request) =>
      request.method() === "PUT" && request.url().includes("/legal-entities/"),
  );
  await section.getByRole("button", { name: "Retry same entity save" }).click();
  const request = await requestPromise;
  await expect(section.getByRole("status")).toHaveText(
    "Legal entity saved. Draft version 1.",
  );
  expect(attempts).toHaveLength(2);
  expect(attempts[0]).toBe(attempts[1]);
  expect(ids[0]).toBe(ids[1]);
  await page.unroute("**/v1/businesses/*/legal-entities/*");
  await section
    .getByLabel("Legal name", { exact: true })
    .fill("FAKE Browser Updated LLC");
  await section
    .getByRole("button", { name: "Save legal entity", exact: true })
    .click();
  await expect(section.getByRole("status")).toHaveText(
    "Legal entity saved. Draft version 2.",
  );
  await section
    .getByRole("button", { name: "View previous entity version" })
    .click();
  await expect(section.getByRole("note")).toContainText(
    "Previous entity version 1: FAKE Browser Company LLC",
  );
  const competitor = await page.request.put(request.url(), {
    headers: {
      authorization: request.headers()["authorization"]!,
      "Idempotency-Key": crypto.randomUUID(),
    },
    data: {
      expected_revision: 2,
      code: `FAKE_${testInfo.project.name.toUpperCase()}`,
      legal_name: "FAKE Concurrent LLC",
    },
  });
  expect(competitor.status()).toBe(200);
  await section
    .getByLabel("Legal name", { exact: true })
    .fill("FAKE Stale Edit LLC");
  await section
    .getByRole("button", { name: "Save legal entity", exact: true })
    .click();
  await expect(section.getByRole("alert")).toContainText(
    "legal entity changed",
  );
  await expect(
    section.getByRole("button", { name: "Save legal entity", exact: true }),
  ).toBeDisabled();
  await expect(section.getByLabel("Legal name", { exact: true })).toHaveValue(
    "FAKE Stale Edit LLC",
  );
  await section.getByRole("button", { name: "Reload selected entity" }).click();
  await expect(section.getByLabel("Legal name", { exact: true })).toHaveValue(
    "FAKE Concurrent LLC",
  );
  await expect(
    section.getByRole("button", { name: "Save legal entity", exact: true }),
  ).toBeEnabled();
  await section
    .getByLabel("Legal name", { exact: true })
    .fill("FAKE Final Browser LLC");
  await section
    .getByRole("button", { name: "Save legal entity", exact: true })
    .click();
  await expect(section.getByRole("status")).toHaveText(
    "Legal entity saved. Draft version 4.",
  );
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `test-results/legal-entities-${page.viewportSize()?.width}.png`,
    fullPage: true,
  });
});

test("existing staff appointment uses local time through creation, transfer and cancellation", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "One real database cycle; mobile business setup is tested above.",
  );
  await signIn(page);
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
  await page.getByLabel("Client Name:").fill("FAKE Management Browser Guest");
  await page
    .getByLabel("Email:", { exact: true })
    .fill("fake-browser@example.test");
  await page.getByLabel("Phone:", { exact: true }).fill("+15551234567");
  await page
    .getByRole("button", { name: "Create Appointment", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("link", { name: "Staff", exact: true }).click();
  const staffRow = page.getByRole("row").filter({ hasText: "FAKE artist A1" });
  await staffRow.getByRole("button", { name: "Schedule", exact: true }).click();
  const sundayOpens = page.getByRole("textbox", {
    name: /^Sunday interval .* opens$/,
  });
  const sundayCloses = page.getByRole("textbox", {
    name: /^Sunday interval .* closes$/,
  });
  await expect(sundayOpens).toHaveCount(1);
  await sundayCloses.fill("12:00");
  await page
    .getByRole("button", { name: "Add Sunday hours", exact: true })
    .click();
  await sundayOpens.nth(1).fill("13:00");
  await sundayCloses.nth(1).fill("16:00");
  await page
    .getByRole("button", { name: "Save Working Hours", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await staffRow.getByRole("button", { name: "Schedule", exact: true }).click();
  await expect(sundayOpens).toHaveCount(2);
  await expect(sundayOpens.nth(0)).toHaveValue("10:00");
  await expect(sundayCloses.nth(0)).toHaveValue("12:00");
  await expect(sundayOpens.nth(1)).toHaveValue("13:00");
  await expect(sundayCloses.nth(1)).toHaveValue("16:00");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await page.getByRole("link", { name: "Bookings", exact: true }).click();
  let row = page
    .getByRole("row")
    .filter({ hasText: "FAKE Management Browser Guest" })
    .filter({ hasText: "CONFIRMED" });
  await expect(row).toContainText("11:00");
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
    .filter({ hasText: "FAKE Management Browser Guest" })
    .filter({ hasText: "CONFIRMED" });
  await expect(row).toContainText("1:00");
  await row.getByRole("button", { name: "Cancel", exact: true }).click();
  await page
    .getByRole("button", { name: /Confirm Cancellation|Cancel Appointment/ })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "FAKE Management Browser Guest" })
      .filter({ hasText: "CONFIRMED" }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page
    .getByRole("button", { name: "+ New Appointment", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Service:", exact: true })
    .selectOption({ label: "FAKE FAKE_BASE (60m) • $50.00" });
  await page.getByLabel("Date:", { exact: true }).fill(day);
  await page.getByLabel("Start Time:", { exact: true }).fill("14:30");
  await page
    .getByLabel("Client Name:", { exact: true })
    .fill("FAKE Management Browser Guest");
  await page
    .getByLabel("Email:", { exact: true })
    .fill("fake-browser@example.test");
  await page.getByLabel("Phone:", { exact: true }).fill("+15551234567");
  await page
    .getByRole("button", { name: "Confirm Booking", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("link", { name: "Bookings", exact: true }).click();
  row = page
    .getByRole("row")
    .filter({ hasText: "FAKE Management Browser Guest" })
    .filter({ hasText: "CONFIRMED" });
  await expect(row).toContainText("2:30");
  await row.getByRole("button", { name: "Cancel", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm Cancellation", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
