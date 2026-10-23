import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// L7b1 (package L): complete a visit with actual quantities and write its materials off.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const OWNER = "FAKE user l7b-owner";
const BOOKING = {
  desktop: process.env.GBA_L7B_DESKTOP_BOOKING ?? "",
  mobile: process.env.GBA_L7B_MOBILE_BOOKING ?? "",
};

// L9a: a second started visit per project, booked under fee policy version 1 (no-show 50 %).
const MISSED = {
  desktop: process.env.GBA_L9A_DESKTOP_NO_SHOW ?? "",
  mobile: process.env.GBA_L9A_MOBILE_NO_SHOW ?? "",
};
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

async function accessible(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page }).include(".visit-desk").analyze();
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

test("a visit is completed and its materials are written off", async ({
  page,
}, testInfo) => {
  const booking = BOOKING[testInfo.project.name as "desktop" | "mobile"];
  expect(booking).not.toBe("");
  await signIn(page);
  let desk = await openDesk(page, booking);

  // The actual quantity of the dye replaces the recipe's 2.5 ml.
  await desk.getByRole("button", { name: "Add actual quantity" }).click();
  const actual = desk.getByRole("group", { name: "Actual quantity 1" });
  await actual.getByLabel("Material").selectOption({ label: "FAKE dye (ml)" });
  await actual.getByLabel(/Quantity/).fill("3.0");
  await desk.getByRole("button", { name: "Complete visit" }).click();
  const uses = desk.getByRole("table", { name: "Materials used" });
  await expect(uses.getByRole("row", { name: /FAKE dye/ })).toContainText(
    "2.5",
  );
  await expect(uses.getByRole("row", { name: /FAKE dye/ })).toContainText(
    "3.0",
  );
  await accessible(page, testInfo, "completed");

  // With inventory off the desk shows no write-off form, only a plain line.
  await desk.getByRole("button", { name: "Close" }).click();
  await withoutModules(page, ["inventory"]);
  desk = await openDesk(page, booking);
  await expect(
    desk.getByText(
      "Materials are turned off in this business's configuration.",
    ),
  ).toBeVisible();
  await expect(
    desk.getByRole("button", { name: "Write off materials" }),
  ).toHaveCount(0);
  await accessible(page, testInfo, "materials-off");
  await desk.getByRole("button", { name: "Close" }).click();
  await page.unroute(CONFIGURATION);
  desk = await openDesk(page, booking);

  // Write the actual quantities off from the branch's shelf.
  await desk.getByLabel("Owner").selectOption({ label: "FAKE Visit Desk LLC" });
  await desk.getByLabel("Storage place").selectOption({ label: "FAKE shelf" });
  await desk.getByRole("button", { name: "Write off materials" }).click();
  await expect(
    desk.getByRole("status").filter({ hasText: "Materials written off" }),
  ).toBeVisible();
  await accessible(page, testInfo, "written-off");

  // Keyboard only: close, then read back after a reload.
  await desk.getByRole("button", { name: "Close" }).focus();
  await page.keyboard.press("Enter");
  await expect(desk).toBeHidden();
  await page.reload();
  await signIn(page);
  desk = await openDesk(page, booking);
  await expect(
    desk.getByRole("table", { name: "Materials used" }).getByRole("row", {
      name: /FAKE dye/,
    }),
  ).toContainText("3.0");
  await expect(desk.getByText("Materials written off")).toBeVisible();
  await expect(
    desk.getByRole("button", { name: "Complete visit" }),
  ).toHaveCount(0);
  await desk.getByRole("button", { name: "Close" }).click();
});

test("a missed visit is a no-show billed under the policy it was booked with", async ({
  page,
}, testInfo) => {
  const booking = MISSED[testInfo.project.name as "desktop" | "mobile"];
  expect(booking).not.toBe("");
  await signIn(page);

  // Settings: publish a newer version; it does not change visits booked before it.
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  const fees = page.getByRole("region", {
    name: "Cancellation and no-show fees",
  });
  await expect(fees.getByText(/^Version \d+:/)).toBeVisible({ timeout: 15000 });
  const form = fees.getByRole("form", { name: "Publish a fee policy" });
  await form
    .getByLabel("No-show fee kind")
    .selectOption({ label: "Fixed amount" });
  await form.getByLabel("No-show fee amount").fill("10.00");
  await form.getByRole("button", { name: "Publish a new version" }).click();
  await expect(
    fees
      .getByRole("status")
      .filter({ hasText: /^Fee policy version \d+ published\.$/ }),
  ).toBeVisible();
  const axe = await new AxeBuilder({ page }).include(".fee-policy").analyze();
  expect(axe.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("fee-policy.png"),
    fullPage: true,
  });

  // The desk records the no-show once; the fee is the one of version 1 (50 % of 50.00).
  const desk = await openDesk(page, booking);
  await desk.getByRole("button", { name: "Mark as no-show" }).click();
  await expect(
    desk.getByRole("status").filter({ hasText: "Recorded as a no-show." }),
  ).toBeVisible();
  await expect(
    desk.getByText("No-show: fee under the policy 25.00."),
  ).toBeVisible();
  await expect(
    desk.getByRole("button", { name: "Complete visit" }),
  ).toHaveCount(0);
  await accessible(page, testInfo, "no-show");

  // Keyboard only: close.
  await desk.getByRole("button", { name: "Close" }).focus();
  await page.keyboard.press("Enter");
  await expect(desk).toBeHidden();
});
