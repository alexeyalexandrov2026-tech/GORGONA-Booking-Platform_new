import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { join } from "node:path";
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
test("admission metadata, lost response, history and withdrawal never enable payments", async ({
  page,
}, testInfo) => {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Provider admission", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Admission book", exact: true })
    .selectOption({
      label: `FAKE_${testInfo.project.name.toUpperCase()} · FAKE ${testInfo.project.name} Finance LLC`,
    });
  await page.getByLabel("Country code").fill("US");
  await page
    .getByLabel("Business activity")
    .fill("FAKE declared business activity");
  await page.getByLabel("Account reference", { exact: true }).fill("acct_FAKE");
  await page
    .getByLabel("Evidence references (one per line)")
    .fill("FAKE-EVIDENCE-1");
  await page.getByLabel("Review notes").fill("FAKE manually supplied context");
  let lost = false;
  await page.route(
    "**/provider-admission/books/*/requests/*",
    async (route) => {
      if (!lost && route.request().method() === "PUT") {
        lost = true;
        await route.fetch();
        await route.abort("failed");
      } else await route.continue();
    },
  );
  await page
    .getByRole("button", { name: "Save admission draft", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Admission recovery" }),
  ).toBeVisible();
  const saved = await page.evaluate(() =>
    Object.keys(sessionStorage)
      .filter((k) => k.startsWith("gorgona.admission.recovery."))
      .map((k) => sessionStorage.getItem(k)),
  );
  expect(JSON.stringify(saved)).not.toContain("acct_FAKE");
  expect(JSON.stringify(saved)).not.toContain("FAKE-EVIDENCE");
  expect(JSON.stringify(saved)).not.toContain("FAKE manually");
  await page.unrouteAll({ behavior: "wait" });
  await page.reload();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Provider admission", exact: true })
    .click();
  await expect(
    page.getByText("Recovered a saved admission request.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("region", { name: "Admission requests" })
    .getByRole("button", { name: /US · charge · draft · revision 1/ })
    .click();
  const book = page.getByRole("combobox", {
    name: "Admission book",
    exact: true,
  });
  await book.selectOption(await book.inputValue());
  await expect(
    page
      .getByRole("region", { name: "Admission requests" })
      .getByRole("button", { name: /US · charge · draft · revision 1/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Admission details" }),
  ).toContainText("State: draft");
  await page
    .getByRole("button", { name: "Submit admission request", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Admission details" }),
  ).toContainText("State: submitted");
  await expect(
    page.getByRole("region", { name: "Admission details" }),
  ).toContainText("All payment capabilities: disabled");
  await page.getByLabel("Admission revision", { exact: true }).fill("1");
  await page
    .getByRole("button", { name: "Read admission revision", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Admission history" }),
  ).toContainText("Revision 1: draft");
  await page
    .getByRole("button", { name: "Withdraw admission request", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Admission details" }),
  ).toContainText("State: withdrawn");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  if (process.env.GBA_H4_SCREENSHOT_DIR)
    await page.screenshot({
      path: join(
        process.env.GBA_H4_SCREENSHOT_DIR,
        `${testInfo.project.name}-admission.png`,
      ),
      fullPage: true,
    });
});
