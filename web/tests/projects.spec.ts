import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
test.describe.configure({ mode: "serial" });

const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const samplePdfPath = process.env.GBA_TEST_SAMPLE_PDF_PATH ?? "";
const NAME = {
  owner: "FAKE user pro-ui-owner",
  outsider: "FAKE user pro-ui-outsider",
} as const;
type Person = keyof typeof NAME;

async function signIn(page: Page, who: Person) {
  const switched = await page.request.post(`${issuer}/fixture/user/${who}`);
  expect(switched.ok()).toBe(true);
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(NAME[who], { exact: true }),
  ).toBeVisible();
}

async function openProjects(page: Page) {
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Projects & Legal Matters",
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

test("end-to-end legal matter lifecycle, stages, tasks, files, time, recurring, FIN-03 invoice, export and ethical-wall isolation", async ({
  page,
}, testInfo) => {
  const tag = testInfo.project.name.toUpperCase();
  const code = `MAT_${tag}`;
  const secretTitle = `SecretVault ${tag}`;

  // 1. Owner creates a restricted legal case, records conflict check, activates it
  await signIn(page, "owner");
  await openProjects(page);
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel("Matter code").fill(code);
  await page.getByLabel("Matter title").fill(secretTitle);
  await page.getByRole("button", { name: "Save matter", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Matter ${code} saved (restricted).`,
  );

  await page.getByLabel("Checked parties").fill(`Acme vs Rival ${tag}`);
  await page.getByLabel("Rationale").fill("No adverse conflict found.");
  await page
    .getByRole("button", { name: "Record conflict check", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Conflict check recorded (clear).",
  );

  await page
    .getByRole("button", { name: "Activate matter", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Matter ${code} activated (rev 2).`,
  );

  // 2. Keyboard switch to Stages, Tasks, Files & Search tab
  const mattersTab = page.getByRole("tab", { name: "Matters & Ethical Wall" });
  await mattersTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Stages, Tasks, Files & Search" }),
  ).toHaveAttribute("aria-selected", "true");
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel("Stage title").fill(`Due Diligence ${tag}`);
  await page.getByRole("button", { name: "Save stage", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Stage 1 (Due Diligence ${tag}) saved.`,
  );

  await page
    .getByRole("button", { name: "Submit deliverable", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Stage 1 submitted for acceptance.",
  );

  await page.getByRole("button", { name: "Accept stage", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Stage 1 accepted.");

  await page.getByLabel("Task title").fill(`${secretTitle} Filing`);
  await page.getByRole("button", { name: "Save task", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Task ${secretTitle} Filing saved.`,
  );

  await page.getByLabel("File title").fill(`${secretTitle} Brief`);
  await page.getByLabel("PDF/PNG/JPEG file").setInputFiles(samplePdfPath);
  await page
    .getByRole("button", { name: "Upload matter file", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `File ${secretTitle} Brief uploaded`,
  );

  await page.getByLabel("Search query").fill(secretTitle);
  await page
    .getByRole("button", { name: "Search projects", exact: true })
    .click();
  await expect(page.getByTestId("projects-search-summary")).toContainText(
    "1 matter(s), 0 stage(s), 1 task(s), 1 file(s).",
  );

  // 3. Time & Recurring tab
  await page.getByRole("tab", { name: "Time & Recurring" }).click();
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel("Work description").fill(`Claim construction ${tag}`);
  await page
    .getByRole("button", { name: "Submit time entry", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Time entry submitted (450.00 USD).",
  );

  await page.getByRole("button", { name: "Approve time", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Time entry approved for billing.",
  );

  await page.getByLabel("Schedule title").fill(`Monthly Retainer ${tag}`);
  await page.getByLabel("Cycle task title").fill(`Docket Check ${tag}`);
  await page
    .getByRole("button", { name: "Save recurring schedule", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Recurring schedule Monthly Retainer ${tag} saved.`,
  );

  await page.getByRole("button", { name: "Run cycle", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Recurring cycle 2026-11-01..2026-11-30 materialized.",
  );

  // 4. Billing & Exports tab ($1,200 stage + $450 time + $2,000 recurring = $3,650.00)
  await page.getByRole("tab", { name: "Billing & Exports" }).click();
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel("Invoice number").fill(`PRO-INV-${tag}`);
  await page
    .getByRole("button", { name: "Issue FIN-03 invoice", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "FIN-03 invoice created (3650.00 USD).",
  );

  await page
    .getByRole("button", { name: "Export selected matter", exact: true })
    .click();
  await expect(page.getByTestId("projects-export-summary")).toContainText(
    "Matter export: 1 matter, 1 stage(s), 2 task(s), 1 file(s), 1 invoice(s).",
  );

  // 5. Ethical-wall browser proof: company-wide manager outsider sees 0 restricted items
  await signIn(page, "outsider");
  await openProjects(page);
  await checkA11yAndViewport(page, testInfo);
  await expect(page.getByText("No authorized matters visible.")).toBeVisible();

  await page
    .getByRole("tab", { name: "Stages, Tasks, Files & Search" })
    .click();
  await page.getByLabel("Search query").fill(secretTitle);
  await page
    .getByRole("button", { name: "Search projects", exact: true })
    .click();
  await expect(page.getByTestId("projects-search-summary")).toContainText(
    "0 matter(s), 0 stage(s), 0 task(s), 0 file(s).",
  );

  await page.getByRole("tab", { name: "Billing & Exports" }).click();
  await page
    .getByRole("button", { name: "Export branch portfolio", exact: true })
    .click();
  await expect(page.getByTestId("projects-export-summary")).toContainText(
    "Portfolio export: 0 visible matter(s), 0 invoice(s).",
  );
});
