import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// L7a (package L): stages and materials of a service, and equipment as a resource kind.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const OWNER = "FAKE user l7a-owner";

async function signIn(page: Page) {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(OWNER, { exact: true }),
  ).toBeVisible();
}

async function accessible(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".service-catalog-dialog")
    .analyze();
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

async function openCatalog(page: Page, service: string) {
  await page.getByRole("link", { name: "Services", exact: true }).click();
  await page
    .getByRole("button", { name: `Stages and materials of ${service}` })
    .click();
  const dialog = page.getByRole("dialog", {
    name: `Stages and materials: ${service}`,
  });
  await expect(dialog).toBeVisible();
  return dialog;
}

test("a manager edits the stages and materials of a service", async ({
  page,
}, testInfo) => {
  // Desktop and mobile share one database: each edits its own service.
  const desktop = testInfo.project.name === "desktop";
  const service = desktop ? "FAKE FAKE_BASE" : "FAKE FAKE_GEL";
  const variant = desktop ? "base" : "gel";
  await signIn(page);
  let dialog = await openCatalog(page, service);

  // Three stages: the specialist works, the colour develops, the specialist finishes.
  const plan = [
    { kind: "Active work", minutes: "30", uses: ["Specialist", "Chair"] },
    {
      kind: "Processing (specialist free)",
      minutes: "40",
      uses: ["Chair", "Equipment"],
    },
    { kind: "Finish", minutes: "20", uses: ["Specialist", "Chair"] },
  ];
  for (const [index, stage] of plan.entries()) {
    await dialog.getByRole("button", { name: "Add stage" }).click();
    const row = dialog.getByRole("group", { name: `Stage ${index + 1}` });
    await row.getByLabel("Kind").selectOption({ label: stage.kind });
    await row.getByLabel("Minutes").fill(stage.minutes);
    for (const resource of ["Specialist", "Chair", "Room", "Equipment"]) {
      const box = row.getByRole("checkbox", { name: resource });
      if (stage.uses.includes(resource)) await box.check();
      else await box.uncheck();
    }
  }
  await expect(dialog.getByText("90 min")).toBeVisible();

  // A change made elsewhere while the dialog is open: the save reloads and says so.
  const touched = await page.request.post(`${issuer}/fixture/touch/${variant}`);
  expect(touched.ok()).toBe(true);
  await dialog.getByRole("button", { name: "Save stages" }).click();
  await expect(
    dialog
      .getByRole("status")
      .filter({ hasText: "changed since it was opened" }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Save stages" }).click();
  await expect(
    dialog
      .getByRole("status")
      .filter({ hasText: "Stages saved. The service now takes 90 minutes." }),
  ).toBeVisible();
  await accessible(page, testInfo, "stages-saved");

  // Materials: a quantity finer than the material allows is refused, then saved.
  await dialog.getByRole("button", { name: "Add material" }).click();
  const material = dialog.getByRole("group", { name: "Material 1" });
  await material
    .getByLabel("Material")
    .selectOption({ label: "FAKE dye (ml)" });
  await material.getByLabel(/Quantity/).fill("2.55");
  await dialog.getByRole("button", { name: "Save materials" }).click();
  await expect(
    dialog
      .getByRole("alert")
      .filter({ hasText: "The materials were not saved" }),
  ).toBeVisible();
  await material.getByLabel(/Quantity/).fill("2.5");
  await dialog.getByRole("button", { name: "Save materials" }).click();
  await expect(
    dialog.getByRole("status").filter({ hasText: "Materials saved." }),
  ).toBeVisible();
  await accessible(page, testInfo, "materials-saved");

  // Keyboard only: close the dialog from the keyboard.
  await dialog.getByRole("button", { name: "Close" }).focus();
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  await expect(
    page.getByRole("row").filter({ hasText: service }).getByText("· 3 stages"),
  ).toBeVisible();

  // Read back from the API after a reload.
  await page.reload();
  await signIn(page);
  dialog = await openCatalog(page, service);
  await expect(dialog.getByRole("group", { name: /^Stage \d$/ })).toHaveCount(
    3,
  );
  await expect(
    dialog.getByRole("group", { name: "Material 1" }).getByLabel(/Quantity/),
  ).toHaveValue("2.5");
  await dialog.getByRole("button", { name: "Close" }).click();
});

test("equipment is added as a resource kind", async ({ page }, testInfo) => {
  await signIn(page);
  await page.getByRole("link", { name: "Staff", exact: true }).click();
  await page
    .getByRole("button", { name: "+ Add Staff Member" })
    .first()
    .click();
  const name = `FAKE processor ${testInfo.project.name}`;
  await page.getByLabel("Display Name").fill(name);
  await page.getByLabel("Resource Kind").selectOption({ label: "Equipment" });
  await page
    .getByRole("button", { name: "Add Staff Member", exact: true })
    .click();
  // The staff list reloads after the add; give a slow CI machine time for it.
  await expect(
    page.getByRole("row").filter({ hasText: name }).getByText("equipment"),
  ).toBeVisible({ timeout: 15000 });
});
