import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// PROPERTY-01 (5c/6 UI) in a real browser on the real API and PostgreSQL:
// 1) Company-wide owner records a unit move-out condition report and photo.
// 2) Owner creates, approves, assigns a maintenance request and binds Company B.
// 3) Contractor delegate signs into /property/contractor/, sees only the single bound work
//    order (zero budget/lease/party leak), submits a progress update across a dropped
//    network retry (same Idempotency-Key), and gets 403 on an unbound request.
// 4) Owner refreshes updates, completes the request; branch manager sees a read-only list
//    with zero forms and zero property.manage requests.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
test.describe.configure({ mode: "serial" });

const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const NAME = {
  owner: "FAKE user prop-maint-owner",
  branch: "FAKE user prop-maint-branch",
  contractor: "FAKE user prop-maint-contractor",
} as const;
type Person = keyof typeof NAME;

type Fixture = {
  business_id: string;
  company_b_id: string;
  grant_id: string;
  move_out_on: string;
  projects: Record<
    string,
    {
      unit_name: string;
      move_in_report_title: string;
      move_out_report_title: string;
      move_out_photo_title: string;
      unbound_request_id: string;
      unbound_request_title: string;
    }
  >;
};

async function signIn(page: Page, who: Person) {
  const switched = await page.request.post(`${issuer}/fixture/user/${who}`);
  expect(switched.ok()).toBe(true);
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(NAME[who], { exact: true }),
  ).toBeVisible();
}

async function openProperty(page: Page) {
  await page.getByRole("link", { name: "Property", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Property", exact: true }),
  ).toBeVisible();
}

async function accessible(
  page: Page,
  testInfo: TestInfo,
  selector: string,
  name: string,
) {
  const axe = await new AxeBuilder({ page }).include(selector).analyze();
  expect(axe.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
}

const catalog = (page: Page) =>
  page.getByRole("table", { name: "Property catalog", exact: true });
const notice = (page: Page, text: string) =>
  page.getByRole("status").filter({ hasText: text });

test("move-out, maintenance lifecycle, contractor work order isolation and branch read-only view", async ({
  page,
  browser,
}, testInfo) => {
  const raw = process.env.GBA_PROPERTY_MAINT_FIXTURE;
  if (!raw) throw new Error("GBA_PROPERTY_MAINT_FIXTURE is missing");
  const data = JSON.parse(raw) as Fixture;
  const project = testInfo.project.name;
  const spec = data.projects[project];
  if (!spec) throw new Error(`No fixture for ${project}`);

  await signIn(page, "owner");
  await openProperty(page);
  await catalog(page)
    .getByRole("button", { name: spec.unit_name, exact: true })
    .click();

  // 1) Record move-out on the unit lease
  const lease = page.getByRole("region", { name: "Unit lease", exact: true });
  const moveOutForm = lease.getByRole("form", { name: "Record move-out" });
  await expect(moveOutForm).toBeVisible();

  // Reusing the move-in report version is refused before sending.
  await moveOutForm
    .getByRole("combobox", { name: "Move-out report", exact: true })
    .selectOption({ label: spec.move_in_report_title });
  await expect(moveOutForm.getByRole("alert")).toContainText(
    "different condition report version than move-in",
  );

  await moveOutForm.getByLabel("Move-out date").fill(data.move_out_on);
  await moveOutForm
    .getByLabel("Condition summary")
    .selectOption("damage_noted");
  await moveOutForm
    .getByLabel("Move-out note (optional)")
    .fill("FAKE scuffed wall near entry");
  await moveOutForm
    .getByRole("combobox", { name: "Move-out report", exact: true })
    .selectOption({ label: spec.move_out_report_title });
  await moveOutForm
    .getByRole("combobox", { name: "Move-out report version", exact: true })
    .selectOption({ label: "Version 1" });
  await moveOutForm
    .getByRole("combobox", { name: "Move-out photo 1", exact: true })
    .selectOption({ label: spec.move_out_photo_title });
  await moveOutForm
    .getByRole("combobox", { name: "Move-out photo 1 version", exact: true })
    .selectOption({ label: "Version 1" });

  const moveOutSubmit = moveOutForm.getByRole("button", {
    name: "Record move-out",
  });
  await moveOutSubmit.focus();
  await page.keyboard.press("Enter");
  await expect(notice(page, "Move-out recorded.")).toBeVisible();
  await expect(lease.getByText("Damage noted", { exact: true })).toBeVisible();
  await expect(
    lease.getByText("FAKE scuffed wall near entry", { exact: true }),
  ).toBeVisible();
  const reportDownload = page.waitForEvent("download");
  await lease.getByRole("button", { name: "Download move-out report" }).click();
  expect((await reportDownload).suggestedFilename().length).toBeGreaterThan(0);
  const photoDownload = page.waitForEvent("download");
  await lease
    .getByRole("button", { name: "Download move-out photo 1" })
    .click();
  expect((await photoDownload).suggestedFilename().length).toBeGreaterThan(0);
  await accessible(page, testInfo, ".property-screen", "property-move-out");

  // 2) Create -> Approve -> Assign -> Bind contractor company
  const title = `FAKE sink leak ${project}`;
  const createForm = page.getByRole("form", {
    name: "New maintenance request",
  });
  await createForm.getByLabel("Request title").fill(title);
  await createForm.getByLabel("Category").selectOption("plumbing");
  await createForm.getByLabel("Priority").selectOption("urgent");
  await createForm
    .getByLabel("Issue description")
    .fill("FAKE pipe dripping under kitchen sink");
  const createBtn = createForm.getByRole("button", {
    name: "Create maintenance request",
  });
  await createBtn.focus();
  await page.keyboard.press("Enter");
  await expect(
    notice(page, `Maintenance request ${title} created.`),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      level: 4,
      name: `Maintenance request: ${title}`,
      exact: true,
    }),
  ).toBeVisible();

  const approveForm = page.getByRole("form", {
    name: "Approve maintenance request",
  });
  await approveForm.getByLabel("Approved limit").fill("350.00");
  await approveForm.getByLabel("Approval currency").fill("USD");
  await approveForm
    .getByLabel("Approval note (optional)")
    .fill("FAKE approved budget");
  await approveForm.getByRole("button", { name: "Approve request" }).click();
  await expect(
    notice(page, `Maintenance request ${title} approved.`),
  ).toBeVisible();
  await expect(page.getByText("350.00 USD").first()).toBeVisible();

  const assignForm = page.getByRole("form", { name: "Assign contractor" });
  await assignForm
    .getByLabel("Contractor counterparty")
    .selectOption({ label: "FAKE Plumbing Contractor" });
  await assignForm
    .getByLabel("Assignment note (optional)")
    .fill("FAKE dispatched");
  await assignForm.getByRole("button", { name: "Assign contractor" }).click();
  await expect(
    notice(page, `Maintenance request ${title} assigned.`),
  ).toBeVisible();

  const companyForm = page.getByRole("form", {
    name: "Contractor company access",
  });
  await companyForm
    .getByLabel("Contractor company")
    .selectOption(data.company_b_id);
  await companyForm
    .getByRole("button", { name: "Save contractor company" })
    .click();
  await expect(notice(page, "Contractor company access bound.")).toBeVisible();
  const workOrderLink = companyForm.getByRole("link", {
    name: "Open contractor work order",
    exact: true,
  });
  await expect(workOrderLink).toBeVisible();
  const contractorHref = await workOrderLink.getAttribute("href");
  expect(contractorHref).toBeTruthy();
  await accessible(
    page,
    testInfo,
    ".property-screen",
    "property-maintenance-assigned",
  );

  // 3) Contractor delegate opens the single-assignment portal, verifies strict privacy,
  //    submits an update across a dropped network retry, and is refused on an unbound request.
  const switchedContractor = await page.request.post(
    `${issuer}/fixture/user/contractor`,
  );
  expect(switchedContractor.ok()).toBe(true);
  const contractorCtx = await browser.newContext({
    baseURL: process.env.GBA_MGMT_BROWSER_URL,
    viewport: page.viewportSize() ?? undefined,
  });
  const cPage = await contractorCtx.newPage();
  await cPage.goto(contractorHref!);
  await expect(
    cPage.getByRole("status").filter({ hasText: "Sign in to view" }),
  ).toBeVisible();
  await cPage.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    cPage.getByRole("heading", { level: 2, name: title, exact: true }),
  ).toBeVisible();
  await expect(cPage.getByText(`${spec.unit_name} (unit)`)).toBeVisible();

  // Private company fields never appear on the contractor portal.
  const portalText = await cPage.locator("main").innerText();
  expect(portalText).not.toContain("350.00");
  expect(portalText).not.toContain("USD");
  expect(portalText).not.toContain("FAKE approved budget");
  expect(portalText).not.toContain("FAKE Tenant");
  expect(portalText).not.toContain("FAKE Plumbing Contractor");

  const updateKeys: string[] = [];
  await cPage.route(
    /\/property\/maintenance\/[0-9a-f-]+\/contractor-work\/[0-9a-f-]+\/updates$/,
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      updateKeys.push(route.request().headers()["idempotency-key"] ?? "");
      if (updateKeys.length === 1) await route.abort("failed");
      else await route.continue();
    },
  );
  const updateForm = cPage.getByRole("form", {
    name: "Post contractor update",
  });
  await updateForm.getByLabel("Update status").selectOption("in_progress");
  await updateForm
    .getByLabel("Update note")
    .fill("FAKE shut off valve and replaced trap");
  const sendBtn = updateForm.getByRole("button", { name: "Send update" });
  await sendBtn.focus();
  await cPage.keyboard.press("Enter");
  await expect(cPage.locator("main").getByRole("alert")).toContainText(
    "We could not confirm your update",
  );
  const retryBtn = updateForm.getByRole("button", { name: "Retry update" });
  await expect(retryBtn).toBeVisible();
  await retryBtn.focus();
  await cPage.keyboard.press("Enter");
  await expect(
    cPage.getByRole("status").filter({ hasText: "Work update 1 sent." }),
  ).toBeVisible();
  expect(updateKeys).toEqual([updateKeys[0], updateKeys[0]]);
  await expect(
    cPage.getByRole("heading", {
      level: 3,
      name: "Update 1: In progress",
      exact: true,
    }),
  ).toBeVisible();
  await accessible(
    cPage,
    testInfo,
    ".customer-proposal",
    "property-contractor-portal",
  );

  // Single-assignment isolation: unbound request returns 403/unavailable.
  const unboundUrl = `/property/contractor/?business=${data.business_id}&request=${spec.unbound_request_id}&grant=${data.grant_id}`;
  await cPage.goto(unboundUrl);
  await cPage.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(cPage.locator("main").getByRole("alert")).toContainText(
    "unavailable for your account",
  );
  await expect(cPage.getByText(spec.unbound_request_title)).toHaveCount(0);
  await contractorCtx.close();

  // 4) Owner refreshes contractor updates and completes the maintenance request
  await page
    .getByRole("button", { name: "Refresh updates", exact: true })
    .click();
  const updateList = page.getByRole("list", {
    name: "Contractor updates",
    exact: true,
  });
  await expect(updateList).toContainText("Update 1: In progress");
  await expect(updateList).toContainText(
    "FAKE shut off valve and replaced trap",
  );

  const completeForm = page.getByRole("form", {
    name: "Complete maintenance request",
  });
  await completeForm
    .getByLabel("Completion note (optional)")
    .fill("FAKE verified dry");
  await completeForm.getByRole("button", { name: "Complete request" }).click();
  await expect(
    notice(page, `Maintenance request ${title} completed.`),
  ).toBeVisible();
  const eventTable = page.getByRole("table", {
    name: "Maintenance event history",
    exact: true,
  });
  await expect(eventTable.locator("tbody tr")).toHaveCount(3);
  await accessible(
    page,
    testInfo,
    ".property-screen",
    "property-maintenance-completed",
  );

  // 5) Branch manager sees read-only maintenance list with zero forms and zero manage calls
  const branchCtx = await browser.newContext({
    baseURL: process.env.GBA_MGMT_BROWSER_URL,
    viewport: page.viewportSize() ?? undefined,
  });
  const bPage = await branchCtx.newPage();
  const manageCalls: string[] = [];
  bPage.on("request", (req) => {
    const url = req.url();
    if (
      /\/property\/maintenance\/[0-9a-f-]+\/(events|obligations|contractor-company|contractor-updates)/.test(
        url,
      ) ||
      url.includes("/property/leases")
    ) {
      manageCalls.push(url);
    }
  });
  await signIn(bPage, "branch");
  await openProperty(bPage);
  await catalog(bPage)
    .getByRole("button", { name: spec.unit_name, exact: true })
    .click();
  const branchTable = bPage.getByRole("table", {
    name: "Maintenance requests",
    exact: true,
  });
  await expect(branchTable).toContainText(title);
  await expect(branchTable).toContainText("Completed");
  await expect(bPage.locator(".property-screen").getByRole("form")).toHaveCount(
    0,
  );
  expect(manageCalls).toEqual([]);
  await accessible(
    bPage,
    testInfo,
    ".property-screen",
    "property-maintenance-branch-readonly",
  );
  await branchCtx.close();
});
