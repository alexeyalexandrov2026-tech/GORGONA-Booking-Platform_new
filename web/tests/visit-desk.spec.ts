import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// L7b1 (package L): complete a visit with actual quantities and write its materials off.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const OWNER = "FAKE user l7b-owner";
const BOOKING = {
  desktop: process.env.GBA_L7B_DESKTOP_BOOKING ?? "",
  mobile: process.env.GBA_L7B_MOBILE_BOOKING ?? "",
};

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
