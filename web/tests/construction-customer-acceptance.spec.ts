import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

test("rechecks changed work and records phase and final customer acceptance", async ({
  page,
}, testInfo) => {
  const fixtures = JSON.parse(process.env.GBA_CUSTOMER_WORK ?? "{}") as Record<
    string,
    {
      business: string;
      project: string;
      grant: string;
      warranty: string;
      invalid_warranty: string;
    }
  >;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_o9_customer_acceptance_browser.py.");
  const { business, project, grant } = fixture;
  await page.goto(
    `/construction/customer/acceptance/?${new URLSearchParams({ business, project, grant })}`,
  );
  const main = page.getByRole("main");
  const signIn = main.getByRole("button", { name: "Sign in", exact: true });
  await expect(signIn).toBeVisible();
  await signIn.press("Enter");
  const work = page.getByRole("combobox", { name: "Work to accept" });
  await expect(work).toBeVisible();
  expect(new URL(page.url()).pathname).toBe(
    "/construction/customer/acceptance/",
  );
  await expect(main).toContainText("The full contract has been billed.");
  await expect(main).toContainText("USD 250.00");
  await expect(main).not.toContainText("USD 150.00");
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await work.selectOption("phase:Framing");
  await page
    .getByRole("textbox", { name: "Signatory name" })
    .fill("FAKE work delegate");
  const changed = await page.request.post(
    `${process.env.GBA_TEST_OIDC_ISSUER}/browser/revise/${project}`,
  );
  expect(changed.ok()).toBe(true);
  await page
    .getByRole("button", { name: "Accept work", exact: true })
    .press("Enter");
  await expect(main.getByRole("alert")).toContainText(
    "Reload this work acceptance before answering.",
  );
  await expect(work).toHaveCount(0);
  await page.getByRole("button", { name: "Reload document" }).press("Enter");
  await expect(work).toBeVisible();

  const keys: string[] = [];
  const bodies: string[] = [];
  await page.route(`**/customer-acceptance/${grant}`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    keys.push(route.request().headers()["idempotency-key"] ?? "");
    bodies.push(route.request().postData() ?? "");
    if (keys.length === 1) {
      expect((await route.fetch()).ok()).toBe(true);
      return route.abort();
    }
    if (keys.length === 2) {
      const response = await route.fetch();
      const actual = (await response.json()) as Record<string, unknown>;
      return route.fulfill({
        response,
        json: { ...actual, review_hash: "0".repeat(64) },
      });
    }
    return route.continue();
  });
  await work.selectOption("phase:Framing");
  const note = page.getByRole("textbox", { name: "Note (optional)" });
  await note.focus();
  await page.keyboard.type("FAKE work reviewed");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Accept work", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(main.getByRole("alert")).toContainText(
    "could not confirm your answer",
  );
  await expect(work).toBeDisabled();
  await expect(note).toBeDisabled();
  await page.getByRole("button", { name: "Retry acceptance" }).press("Enter");
  await expect(main.getByRole("alert")).toContainText(
    "could not confirm your answer",
  );
  await expect(work).toBeDisabled();
  await page.getByRole("button", { name: "Retry acceptance" }).press("Enter");
  await expect(main.getByRole("status")).toHaveText("Phase Framing accepted.");
  await expect(main.getByRole("status")).toBeFocused();
  expect(keys).toHaveLength(3);
  expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
  expect(keys[1]).toBe(keys[0]);
  expect(keys[2]).toBe(keys[0]);
  expect(bodies[1]).toBe(bodies[0]);
  expect(bodies[2]).toBe(bodies[0]);
  await page
    .getByRole("button", { name: "Review remaining work" })
    .press("Enter");
  await expect(work).toBeVisible();
  await work.selectOption("final");
  await page.getByLabel("Warranty end date").fill(fixture.invalid_warranty);
  await page
    .getByRole("button", { name: "Accept work", exact: true })
    .press("Enter");
  await expect(main.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Warranty end date")).toBeEnabled();
  await expect(work).toBeEnabled();
  await page.getByLabel("Warranty end date").fill(fixture.warranty);
  await page
    .getByRole("button", { name: "Accept work", exact: true })
    .press("Enter");
  await expect(main.getByRole("status")).toHaveText(
    "Final acceptance recorded.",
  );
  await expect(main).toContainText(`Warranty ends ${fixture.warranty}.`);
  await expect(work).toHaveCount(0);
});
