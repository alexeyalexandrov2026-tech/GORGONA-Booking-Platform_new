import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
test.describe.configure({ mode: "serial" });

const issuer = process.env.GBA_TEST_OIDC_ISSUER;

async function signInAs(page: Page, key: string, expectedDisplayName: string) {
  const switched = await page.request.post(`${issuer}/fixture/user/${key}`);
  expect(switched.ok()).toBe(true);
  await page.goto("/overview/");
  const signOut = page.getByRole("button", { name: "Sign out", exact: true });
  if (await signOut.isVisible().catch(() => false)) {
    await signOut.click();
  }
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page
      .locator(".mgmt-header-actions")
      .getByText(expectedDisplayName, { exact: true }),
  ).toBeVisible();
}

async function openEnterprise(page: Page) {
  await page.getByRole("link", { name: "Enterprise", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Enterprise SSO, Lifecycle & Group Reporting",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole("tabpanel")).toBeVisible();
}

async function checkA11yAndViewport(page: Page, testInfo: TestInfo) {
  const axe = await new AxeBuilder({ page }).include("main").analyze();
  expect(axe.violations).toEqual([]);
  if (testInfo.project.name === "mobile") {
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    );
    expect(overflow).toBe(false);
  }
}

test("end-to-end atomic SSO employee deprovisioning and consent-based consolidated group reporting", async ({
  page,
}, testInfo) => {
  const tag = testInfo.project.name.toUpperCase();
  const low = testInfo.project.name.toLowerCase();
  const provCode = `OKTA_${tag}`;
  const empCode = `EMP_${tag}`;
  const period = low === "desktop" ? "2026-10" : "2026-11";

  // 1. Organizer Tenant A: configure corporate SSO, link employee, atomically deprovision
  await signInAs(page, "owner_a", "FAKE user ent-ui-owner-a");
  await openEnterprise(page);
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel(/^Provider code/).fill(provCode);
  await page.getByLabel(/^Provider display name/).fill(`Okta Corp ${tag}`);
  await page.getByLabel(/^Corporate email domain/).fill(`corp-${low}.example`);
  await page
    .getByRole("button", { name: "Save SSO provider", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved SSO provider ${provCode}`,
  );

  await page
    .getByLabel(/^Directory provider/)
    .selectOption({ label: `${provCode} — Okta Corp ${tag}` });
  await page
    .getByLabel(/^Business member/)
    .selectOption({ label: `FAKE user ent-ui-emp-${low} (manager / active)` });
  await page.getByLabel(/^External subject/).fill(`okta|emp-${low}`);
  await page.getByLabel(/^Employee code/).fill(empCode);
  await page
    .getByRole("button", { name: "Save directory link", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Linked directory employee ${empCode}`,
  );

  await page
    .getByRole("button", { name: `Deprovision ${empCode}`, exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Deprovisioned ${empCode} (1 membership suspended)`,
  );

  // 2. Member Tenant B: publish consented (revenue_by_currency) & unconsented (headcount) snapshots + grant consent
  await signInAs(page, "owner_b", "FAKE user ent-ui-owner-b");
  await openEnterprise(page);

  const ssoTab = page.getByRole("tab", { name: "Corporate SSO & Lifecycle" });
  await ssoTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Group Reporting Consents" }),
  ).toHaveAttribute("aria-selected", "true");
  await checkA11yAndViewport(page, testInfo);

  // Grant consent ONLY for revenue_by_currency (default checked)
  await page
    .getByRole("button", { name: "Save report consent", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Saved active report consent for HOLDING_UI (revenue_by_currency)",
  );

  // Publish revenue_by_currency ($500.00)
  await page.getByLabel(/^Period \(YYYY-MM\)/).fill(period);
  await page.getByLabel(/^Report set/).selectOption("revenue_by_currency");
  await page.getByLabel(/^Metric count/).fill("10");
  await page.getByLabel(/^Metric amount minor/).fill("50000");
  await page
    .getByRole("button", { name: "Publish report snapshot", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Published revenue_by_currency snapshot (${period}, 500.00 USD)`,
  );

  // Publish unconsented headcount (25) — MUST NOT appear in organizer's report
  await page.getByLabel(/^Report set/).selectOption("headcount");
  await page.getByLabel(/^Metric count/).fill("25");
  await page.getByLabel(/^Metric amount minor/).fill("0");
  await page
    .getByRole("button", { name: "Publish report snapshot", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Published headcount snapshot (${period}, 0.00 USD)`,
  );

  // 3. Organizer Tenant A: load consolidated report -> sees ONLY revenue_by_currency, NOT headcount!
  await signInAs(page, "owner_a", "FAKE user ent-ui-owner-a");
  await openEnterprise(page);
  await page.getByRole("tab", { name: "Consolidated Group Analytics" }).click();
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel(/^Report period \(YYYY-MM\)/).fill(period);
  await page
    .getByRole("button", { name: "Load consolidated report", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Loaded consolidated group report (1 attributed member entries)",
  );
  const reportText = await page
    .getByTestId("consolidated-report-result")
    .innerText();
  expect(reportText).toContain("revenue_by_currency");
  expect(reportText).toContain("500.00 USD");
  expect(reportText).not.toContain("headcount");

  // 4. Member Tenant B revokes consent -> Organizer immediately sees 0 entries!
  await signInAs(page, "owner_b", "FAKE user ent-ui-owner-b");
  await openEnterprise(page);
  await page.getByRole("tab", { name: "Group Reporting Consents" }).click();
  await page
    .getByRole("button", { name: "Revoke consent HOLDING_UI", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Revoked report consent for HOLDING_UI",
  );

  await signInAs(page, "owner_a", "FAKE user ent-ui-owner-a");
  await openEnterprise(page);
  await page.getByRole("tab", { name: "Consolidated Group Analytics" }).click();
  await page.getByLabel(/^Report period \(YYYY-MM\)/).fill(period);
  await page
    .getByRole("button", { name: "Load consolidated report", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Loaded consolidated group report (0 attributed member entries)",
  );
});
