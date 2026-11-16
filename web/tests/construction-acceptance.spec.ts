import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  project: string;
  project_number: string;
  too_early: string;
  accept_phase: string;
  release_phase: string;
  accept_final: string;
  release_final: string;
  warranty_end: string;
};

test("records phase and final acceptance and releases each amount exactly once", async ({
  page,
}, testInfo) => {
  const fixtures = JSON.parse(
    process.env.GBA_ACCEPTANCE_FIXTURES ?? "{}",
  ) as Record<string, Fixture>;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_o7c2_construction_acceptance_browser.py.");
  async function signIn() {
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.locator(".mgmt-header-actions")).toContainText(
      "FAKE user o7c2-owner",
    );
    await page.getByRole("link", { name: "Construction", exact: true }).click();
  }
  await page.goto("/overview/");
  await signIn();
  const selectProject = () =>
    page
      .getByRole("table", { name: "Projects" })
      .getByRole("button", { name: fixture.project_number })
      .click();
  await selectProject();

  const acceptance = page.getByRole("region", {
    name: "Acceptance and retainage releases",
    exact: true,
  });
  const applications = page.getByRole("region", {
    name: "Pay applications",
    exact: true,
  });
  await expect(acceptance).toContainText("Still held 31.00 USD");
  await expect(
    applications.getByRole("button", { name: "New pay application" }),
  ).toBeVisible();
  await acceptance
    .getByRole("button", { name: "Record acceptance for Framing" })
    .press("Enter");
  const phase = acceptance.getByRole("form", { name: "Accept Framing" });
  await phase.getByLabel("Acceptance date").fill(fixture.too_early);
  await phase
    .getByRole("textbox", { name: "Customer signatory" })
    .fill("FAKE Site Owner");
  await phase
    .getByRole("combobox", { name: "Acceptance source" })
    .selectOption("paper");
  const save = phase.getByRole("button", { name: "Save acceptance" });
  await save.press("Enter");
  await expect(acceptance.getByRole("alert")).toBeVisible();
  await phase.getByLabel("Acceptance date").fill(fixture.accept_phase);
  await save.press("Enter");
  const records = acceptance.getByRole("table", { name: "Acceptance records" });
  await expect(records).toContainText("FAKE Site Owner");

  const keys: string[] = [];
  await page.route(
    `**/construction/projects/${fixture.project}/acceptances/1/release`,
    async (route) => {
      keys.push(route.request().headers()["idempotency-key"] ?? "");
      expect(route.request().postDataJSON()).toEqual({
        schema_version: 1,
        released_on: fixture.release_phase,
        note: "FAKE signed release",
      });
      if (keys.length === 1) {
        expect((await route.fetch()).ok()).toBe(true);
        await route.abort();
        return;
      }
      await route.continue();
    },
  );
  async function release(number: number, date: string) {
    const label = `Release retainage for record ${number}`;
    await acceptance.getByRole("button", { name: label }).click();
    const form = acceptance.getByRole("form", { name: label });
    await form.getByLabel("Release date").fill(date);
    await form
      .getByRole("textbox", { name: "Release note" })
      .fill("FAKE signed release");
    const confirm = form.getByRole("button", { name: "Confirm release" });
    await confirm.click();
    return confirm;
  }
  const retry = await release(1, fixture.release_phase);
  await expect(acceptance.getByRole("alert")).toBeVisible();
  await retry.click();
  await expect(acceptance).toContainText("Still held 6.00 USD");
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
  await expect(records).toContainText(`25.00 USD on ${fixture.release_phase}`);

  await applications
    .getByRole("button", { name: "New pay application" })
    .click();
  const openApplication = applications.getByRole("form", {
    name: "New pay application",
  });
  await expect(openApplication).toBeVisible();
  await acceptance
    .getByRole("button", { name: "Record final acceptance" })
    .click();
  const final = acceptance.getByRole("form", { name: "Final acceptance" });
  await final.getByLabel("Acceptance date").fill(fixture.accept_final);
  await final.getByLabel("Warranty end date").fill(fixture.warranty_end);
  await final
    .getByRole("textbox", { name: "Customer signatory" })
    .fill("FAKE Final Signatory");
  await final
    .getByRole("combobox", { name: "Acceptance source" })
    .selectOption("email");
  await final.getByRole("button", { name: "Save acceptance" }).click();
  await expect(applications).toContainText("Final acceptance closed billing.");
  await expect(
    applications.getByRole("button", { name: "New pay application" }),
  ).toHaveCount(0);
  await expect(openApplication).toHaveCount(0);
  await release(2, fixture.release_final);
  await expect(acceptance).toContainText("Still held 0.00 USD");
  await expect(records).toContainText(`6.00 USD on ${fixture.release_final}`);
  await expect(records).toContainText(
    `${fixture.accept_final} to ${fixture.warranty_end}`,
  );

  await page.unrouteAll({ behavior: "wait" });
  await page.reload();
  await signIn();
  await selectProject();
  await expect(acceptance).toContainText("Released 31.00 USD");
  await expect(
    acceptance.getByRole("button", { name: /Release retainage for record/ }),
  ).toHaveCount(0);
  const audit = await new AxeBuilder({ page })
    .include(".construction-screen")
    .analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
