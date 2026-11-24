import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// O7a (package O): the construction list, the project form, estimate versions (the second after a
// lost answer), the proposal, the customer's acceptance and a change order answered by keyboard.
// FAKE data seeded by test_o7a_construction_browser.py.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const OWNER = "FAKE user o7a-owner";

async function signIn(page: Page) {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(OWNER, { exact: true }),
  ).toBeVisible();
}

async function accessible(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".construction-screen")
    .analyze();
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

const alert = (page: Page) =>
  page.locator(".construction-screen").getByRole("alert");

async function estimateLine(
  page: Page,
  n: number,
  values: {
    kind: string;
    description: string;
    phase: string;
    quantity: string;
    unit: string;
    cost: string;
    price: string;
  },
) {
  const form = page.getByRole("form", { name: "Estimate version" });
  await form.getByLabel(`Line ${n} kind`).selectOption({ label: values.kind });
  await form.getByLabel(`Line ${n} description`).fill(values.description);
  await form.getByLabel(`Line ${n} phase`).fill(values.phase);
  await form.getByLabel(`Line ${n} quantity`).fill(values.quantity);
  await form.getByLabel(`Line ${n} unit`, { exact: true }).fill(values.unit);
  await form.getByLabel(`Line ${n} unit cost`).fill(values.cost);
  await form.getByLabel(`Line ${n} unit price`).fill(values.price);
}

test("an owner prices a project, records the contract and answers a change order", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name as "desktop" | "mobile";
  const number = `FAKE-CP-${project}`;
  await signIn(page);
  await page.getByRole("link", { name: "Construction", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Construction", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Loading the projects…")).toBeHidden({
    timeout: 15000,
  });
  await accessible(page, testInfo, `${project}-list`);

  // A new project; the server checks the time zone and the branch.
  const form = page.getByRole("form", { name: "Project" });
  await form.getByLabel("Number").fill(number);
  await form.getByLabel("Name").fill(`FAKE kitchen remodel ${project}`);
  await form.getByLabel("Customer").selectOption({ label: "FAKE Homeowner" });
  await form.getByLabel("Branch").selectOption({ index: 1 });
  await form.getByLabel("Site address").fill("FAKE 1 Main St, Springfield");
  await form.getByLabel("Time zone").fill("America/Chicago");
  await form.getByLabel("Currency").fill("USD");
  await form.getByRole("button", { name: "Save project" }).click();
  await expect(page.getByText(`Project ${number} saved.`)).toBeVisible();
  const projects = page.getByRole("table", { name: "Projects" });
  const row = projects.getByRole("row").filter({ hasText: number });
  await expect(row).toContainText("FAKE Homeowner");
  await expect(row).toContainText("USD");

  await row.getByRole("button", { name: number }).click();
  await expect(
    page.getByRole("heading", { name: `Project ${number}`, exact: true }),
  ).toBeVisible();
  await expect(page.getByText("No estimate versions yet.")).toBeVisible();

  // Version 1: two lines; the totals are the server's.
  const editor = page.getByRole("form", { name: "Estimate version" });
  await estimateLine(page, 1, {
    kind: "Material",
    description: "FAKE drywall",
    phase: "Framing",
    quantity: "10",
    unit: "sheet",
    cost: "15",
    price: "25",
  });
  await editor.getByRole("button", { name: "Add a line" }).click();
  await estimateLine(page, 2, {
    kind: "Labor",
    description: "FAKE wiring",
    phase: "Electrical",
    quantity: "8",
    unit: "hour",
    cost: "40",
    price: "65",
  });
  await editor.getByLabel("Note").fill("FAKE scope");
  await editor.getByRole("button", { name: "Save version" }).click();
  const versions = page.getByRole("table", { name: "Estimate versions" });
  const first = versions.getByRole("row").filter({ hasText: "Version 1" });
  await expect(first).toContainText("470.00");
  await expect(first).toContainText("770.00");
  await expect(
    page.getByRole("table", { name: "Estimate lines" }),
  ).toContainText("FAKE wiring");

  // Version 2 after a lost answer: the server saved it, the retry saves nothing new.
  let lost = false;
  await page.route("**/construction/projects/*/estimates", async (route) => {
    if (!lost && route.request().method() === "POST") {
      lost = true;
      await route.fetch();
      await route.abort();
      return;
    }
    await route.continue();
  });
  await editor.getByLabel("Line 1 quantity").fill("12");
  await editor.getByRole("button", { name: "Save version" }).click();
  await expect(alert(page)).toBeVisible();
  await editor.getByRole("button", { name: "Save version" }).click();
  await expect(alert(page)).toBeHidden();
  await expect(versions.getByRole("row")).toHaveCount(3);
  const second = versions.getByRole("row").filter({ hasText: "Version 2" });
  await expect(second).toContainText("500.00");
  await expect(second).toContainText("820.00");

  await page
    .getByRole("button", { name: "Send version 2 as proposal" })
    .click();
  await expect(second).toContainText("Proposed");

  // The customer's acceptance freezes version 2 as the original contract.
  const acceptance = page.getByRole("form", { name: "Customer's acceptance" });
  await acceptance.getByLabel("Signatory").fill("FAKE Homeowner");
  await acceptance.getByLabel("Source").selectOption({ label: "Signed paper" });
  await acceptance.getByRole("button", { name: "Record acceptance" }).click();
  const contract = page.getByRole("region", { name: "Contract" });
  await expect(contract).toContainText("Version 2 accepted");
  const sums = contract.getByRole("table", { name: "Contract sums" });
  await expect(
    sums.getByRole("row").filter({ hasText: "Original" }),
  ).toContainText("820.00");
  await expect(editor).toHaveCount(0);
  await accessible(page, testInfo, `${project}-project`);

  // A change order: add outlets, remove two sheets of drywall.
  const change = page.getByRole("form", { name: "Propose a change order" });
  await change.getByLabel("Title").fill("FAKE extra outlets");
  await change.getByLabel("Days").fill("2");
  await change
    .getByLabel("Change line 1 action")
    .selectOption({ label: "Add scope" });
  await change
    .getByLabel("Change line 1 kind")
    .selectOption({ label: "Labor" });
  await change.getByLabel("Change line 1 description").fill("FAKE outlets");
  await change.getByLabel("Change line 1 phase").fill("Electrical");
  await change.getByLabel("Change line 1 quantity").fill("2");
  await change.getByLabel("Change line 1 unit", { exact: true }).fill("each");
  await change.getByLabel("Change line 1 unit cost").fill("30");
  await change.getByLabel("Change line 1 unit price").fill("50");
  await change.getByRole("button", { name: "Add a change line" }).click();
  await change
    .getByLabel("Change line 2 action")
    .selectOption({ label: "Remove scope" });
  await change
    .getByLabel("Change line 2 contract line")
    .selectOption({ label: "1 · FAKE drywall · 12 sheet" });
  await change.getByLabel("Change line 2 quantity").fill("2");
  await change.getByRole("button", { name: "Propose" }).click();
  const orders = page.getByRole("table", { name: "Change orders" });
  const order = orders
    .getByRole("row")
    .filter({ hasText: "FAKE extra outlets" });
  await expect(order).toContainText("Proposed");
  await expect(order).toContainText("30.00");
  await expect(order).toContainText("50.00");

  await order.getByRole("button", { name: "Change order 1" }).click();
  await expect(
    page.getByRole("table", { name: "Change order 1 lines" }),
  ).toContainText("Remove");
  const answer = page.getByRole("form", { name: "Answer change order 1" });
  await answer.getByLabel("Answer").selectOption({ label: "Approve" });
  await answer.getByLabel("Source").selectOption({ label: "Email" });
  const record = answer.getByRole("button", { name: "Record the answer" });
  await record.focus();
  await page.keyboard.press("Enter");
  await expect(order).toContainText("Approved");
  await expect(alert(page)).toBeHidden();
  const current = sums.getByRole("row").filter({ hasText: "Current" });
  await expect(current).toContainText("530.00");
  await expect(current).toContainText("870.00");
  await expect(contract).toContainText("Approved days: 2");
  await accessible(page, testInfo, `${project}-changes`);
});
