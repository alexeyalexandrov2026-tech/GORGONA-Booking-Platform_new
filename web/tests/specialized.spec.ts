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

test("end-to-end /specialized/ 4-tab UI proves consent redaction, critical safety lock, and dual-review governance", async ({
  page,
}, testInfo) => {
  const tag = testInfo.project.name.toUpperCase();
  const progCode = `YOGA_${tag}`;
  const subjCode = `PAT_${tag}`;
  const assetCode = `SUB_${tag}`;
  const civCode = `GRANT_${tag}`;
  const caseCode = `CASE_${tag}`;
  const grantorName = `Guardian ${tag}`;

  await signInAs(page, "owner", "FAKE user spec-ui-owner");
  await page.getByRole("link", { name: "Specialized", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Specialized Industries (Stage 8 — Profiles 12–39)",
      exact: true,
    }),
  ).toBeVisible();
  await checkA11yAndViewport(page, testInfo);

  // Tab 1: Venues & Programs -> save program + enroll participant
  await page.getByLabel(/^Program code/).fill(progCode);
  await page.getByLabel(/^Program title/).fill(`Morning Reformer ${tag}`);
  await page.getByLabel(/^Program capacity/).fill("5");
  await page
    .getByRole("button", { name: "Save specialized program", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved specialized program ${progCode}`,
  );
  await page
    .getByRole("button", { name: "Enroll participant", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Enrolled participant in specialized program",
  );

  // Keyboard ArrowRight -> Care & Consents tab
  const venuesTab = page.getByRole("tab", { name: "Venues & Programs" });
  await venuesTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Care & Consents" }),
  ).toHaveAttribute("aria-selected", "true");
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel(/^Subject code/).fill(subjCode);
  await page.getByLabel(/^Subject display name/).fill(`Patient ${tag}`);
  await page
    .getByRole("button", { name: "Save care subject", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved care subject ${subjCode}`,
  );

  await page.getByLabel(/^Granted by name/).fill(grantorName);
  await page
    .getByRole("button", { name: "Grant active consent", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Granted care consent (care_records)",
  );

  await page.getByLabel(/^Encounter summary/).fill(`Assessment ${tag}`);
  await page.getByLabel(/^Clinical notes/).fill(`CONFIDENTIAL_NOTE_${tag}`);
  await page
    .getByRole("button", { name: "Record encounter", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Recorded consent-gated care encounter",
  );
  await expect(page.locator("main")).toContainText(`CONFIDENTIAL_NOTE_${tag}`);

  // Revoke consent -> clinical notes immediately redacted + new encounter blocked
  await page
    .getByRole("button", { name: `Revoke consent ${grantorName}`, exact: true })
    .click();
  await expect(page.locator("main")).toContainText("[REDACTED BY CONSENT]");
  await expect(page.locator("main")).not.toContainText(
    `CONFIDENTIAL_NOTE_${tag}`,
  );

  await page.getByLabel(/^Encounter summary/).fill(`Blocked ${tag}`);
  await page.getByLabel(/^Clinical notes/).fill("Should fail without consent");
  await page
    .getByRole("button", { name: "Record encounter", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "CARE_CONSENT_REQUIRED",
  );

  // Tab 3: Assets & Field Safety -> critical incident auto-locks asset out_of_service
  await page.getByRole("tab", { name: "Assets & Field Safety" }).click();
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel(/^Asset code/).fill(assetCode);
  await page.getByLabel(/^Asset name/).fill(`North Pump ${tag}`);
  await page
    .getByRole("button", { name: "Save managed asset", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Registered asset ${assetCode}`,
  );

  await page.getByLabel(/^Incident severity/).selectOption("critical");
  await page
    .getByLabel(/^Incident description/)
    .fill(`Coolant pressure breach ${tag}`);
  await page.getByRole("button", { name: "Log incident", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Logged critical safety incident",
  );

  await page
    .getByRole("button", {
      name: `Attempt reactivate ${assetCode}`,
      exact: true,
    })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "ASSET_CRITICAL_INCIDENT_OPEN",
  );

  // Tab 4: Civic & Dual-Review -> self-approval blocked & allocation gated by approval
  await page.getByRole("tab", { name: "Civic & Dual-Review" }).click();
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel(/^Civic program code/).fill(civCode);
  await page.getByLabel(/^Civic program title/).fill(`Municipal Grant ${tag}`);
  await page
    .getByRole("button", { name: "Save civic program", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved civic program ${civCode}`,
  );

  await page.getByLabel(/^Case number/).fill(caseCode);
  await page.getByLabel(/^Case summary/).fill(`Grant application ${tag}`);
  await page
    .getByRole("button", { name: "Submit civic case", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Submitted civic case ${caseCode}`,
  );

  await page
    .getByRole("button", {
      name: `Attempt self-approve ${caseCode}`,
      exact: true,
    })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "CIVIC_DUAL_REVIEW_REQUIRED",
  );

  await page.getByLabel(/^Allocation reference/).fill(`PRM_${tag}`);
  await page
    .getByRole("button", { name: "Issue allocation", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "CIVIC_CASE_NOT_APPROVED",
  );
});
