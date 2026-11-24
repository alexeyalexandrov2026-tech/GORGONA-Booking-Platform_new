import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  project: string;
  project_number: string;
  release_date: string;
};

test("reconciles actual costs, confirmed payments and a release on the same project", async ({
  page,
}, testInfo) => {
  const fixtures = JSON.parse(
    process.env.GBA_RECONCILIATION_FIXTURES ?? "{}",
  ) as Record<string, Fixture>;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error(
      "Seed with test_o7c3_construction_reconciliation_browser.py.",
    );
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator(".mgmt-header-actions")).toContainText(
    "FAKE user o7c3-owner",
  );
  await page.getByRole("link", { name: "Construction", exact: true }).click();
  await page
    .getByRole("table", { name: "Projects" })
    .getByRole("button", { name: fixture.project_number })
    .click();

  const reconciliation = page.getByRole("region", {
    name: "Project reconciliation",
    exact: true,
  });
  const row = (name: string) =>
    reconciliation
      .getByRole("row")
      .filter({ has: page.getByRole("rowheader", { name, exact: true }) })
      .getByRole("cell");
  await expect(row("Actual cost")).toHaveText("65.00");
  await expect(row("Warranty repairs included in actual")).toHaveText("25.00");
  await expect(row("Contract less billed")).toHaveText("0.00");
  await expect(row("Invoice paid")).toHaveText("100.00");
  await expect(row("Retainage paid")).toHaveText("15.00");
  await expect(row("Settled retainage above the released amount")).toHaveText(
    "15.00",
  );
  await expect(row("Billed less paid and credited")).toHaveText("195.07");
  await expect(reconciliation).toContainText("Unissued documents 0");
  await expect(reconciliation).toContainText("Warranty claims · 1 open");

  const acceptance = page.getByRole("region", {
    name: "Acceptance and retainage releases",
    exact: true,
  });
  const release = "Release retainage for record 1";
  await acceptance.getByRole("button", { name: release }).click();
  const form = acceptance.getByRole("form", { name: release });
  await form.getByLabel("Release date").fill(fixture.release_date);
  await form.getByRole("button", { name: "Confirm release" }).click();
  await expect(row("Released")).toHaveText("31.00");
  await expect(row("Still held")).toHaveText("0.00");
  await expect(row("Retainage paid")).toHaveText("15.00");
  await expect(row("Settled retainage above the released amount")).toHaveText(
    "0.00",
  );

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
