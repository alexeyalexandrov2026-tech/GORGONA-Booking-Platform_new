import {
  test,
  expect,
  type Locator,
  type Page,
  type TestInfo,
} from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// PROPERTY-01 (catalog screen) in a real browser on the real API and PostgreSQL. A company-wide
// owner recovers from a failed read, builds a parcel, building and unit, keeps and clears parties
// and meets a stale revision; a branch manager reads only their branch without history or edit
// controls; a manager of an empty branch sees the empty catalog. FAKE data seeded by
// test_property_browser.py.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
test.describe.configure({ mode: "serial" });
const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const BRANCH = process.env.GBA_PROPERTY_BRANCH ?? "";
const HIDDEN = "FAKE hidden parcel";
const NAME = {
  owner: "FAKE user property-owner",
  branch: "FAKE user property-branch",
  empty: "FAKE user property-empty",
} as const;
type Person = keyof typeof NAME;

async function signIn(page: Page, who: Person, choose = true) {
  if (choose) {
    const switched = await page.request.post(`${issuer}/fixture/user/${who}`);
    expect(switched.ok()).toBe(true);
  }
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

async function accessible(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".property-screen")
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

const screen = (page: Page) => page.locator(".property-screen");
const notice = (page: Page, text: string) =>
  page.getByRole("status").filter({ hasText: text });
const catalog = (page: Page) =>
  page.getByRole("table", { name: "Property catalog", exact: true });
const history = (page: Page) =>
  page.getByRole("region", { name: "Property history table", exact: true });
const fact = (page: Page, term: string) =>
  page.locator(".property-facts div").filter({
    has: page.getByText(term, { exact: true }),
  });

async function create(
  page: Page,
  kind: "Parcel" | "Building" | "Unit",
  name: string,
  parent?: string,
) {
  const form = page.getByRole("form", { name: "New property", exact: true });
  await form.getByLabel("Branch").selectOption({ label: BRANCH });
  await form.getByLabel("Type").selectOption({ label: kind });
  await form.getByLabel("Name").fill(name);
  if (parent)
    await form
      .getByLabel(kind === "Unit" ? "Building" : "Parcel")
      .selectOption({ label: parent });
  await form.getByLabel("Owner").selectOption({ label: "FAKE Owner" });
  await form.getByLabel("Manager").selectOption({ label: "FAKE Manager" });
  await form.getByRole("button", { name: "Save property" }).click();
  await expect(
    notice(page, `Property ${name} saved as revision 1.`),
  ).toBeVisible();
}

async function edit(page: Page, current: string): Promise<Locator> {
  const form = page.getByRole("form", {
    name: `Edit property ${current}`,
    exact: true,
  });
  await expect(form).toBeVisible();
  return form;
}

async function row(page: Page, revision: number) {
  return history(page)
    .getByRole("row")
    .filter({
      has: page.getByRole("rowheader", {
        name: String(revision),
        exact: true,
      }),
    });
}

test("an owner builds the catalog, keeps and clears parties and meets a stale revision", async ({
  page,
}, testInfo) => {
  const p = testInfo.project.name;
  const parcel = `FAKE parcel ${p}`;
  const building = `FAKE building ${p}`;
  const unit = `FAKE unit ${p}`;
  await signIn(page, "owner");

  // A failed read says so and offers a retry that reads the real catalog.
  const list = /\/v1\/businesses\/[0-9a-f-]{36}\/property\/objects$/;
  await page.route(list, (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "SERVICE_UNAVAILABLE", message: "FAKE outage" },
      }),
    }),
  );
  await openProperty(page);
  await expect(screen(page).getByRole("alert")).toContainText(
    "The property catalog could not be read",
  );
  await accessible(page, testInfo, "property-read-error");
  await page.unroute(list);
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Catalog", exact: true }),
  ).toBeVisible();
  await expect(screen(page).getByRole("alert")).toHaveCount(0);
  // The company-wide owner sees every branch, including one they did not build here.
  await expect(catalog(page).getByText(HIDDEN, { exact: true })).toBeVisible();

  await create(page, "Parcel", parcel);
  await create(page, "Building", building, parcel);
  await create(page, "Unit", unit, building);
  await expect(
    catalog(page).getByRole("row").filter({ hasText: unit }),
  ).toContainText(building);
  await accessible(page, testInfo, "property-catalog");

  // Keyboard: open from the table and land on the property.
  await catalog(page).getByRole("button", { name: unit, exact: true }).focus();
  await page.keyboard.press("Enter");
  const heading = page.getByRole("heading", {
    level: 2,
    name: `Property ${unit}`,
    exact: true,
  });
  await expect(heading).toBeFocused();
  await expect(fact(page, "Owner")).toContainText("FAKE Owner");
  await expect(fact(page, "Manager")).toContainText("FAKE Manager");
  await expect(history(page).getByRole("row")).toHaveCount(2);
  await accessible(page, testInfo, "property-detail");

  // A rename leaves both parties out of the command; the server keeps them.
  let form = await edit(page, unit);
  await expect(form.getByLabel("Owner")).toHaveValue("");
  await expect(form.getByLabel("Owner").locator("option:checked")).toHaveText(
    "Keep current (FAKE Owner)",
  );
  await form.getByLabel("Name").fill(`${unit} renamed`);
  await form.getByRole("button", { name: "Save changes" }).click();
  await expect(
    notice(page, `Property ${unit} renamed saved as revision 2.`),
  ).toBeVisible();
  await expect(await row(page, 2)).toContainText("FAKE Owner");
  await expect(await row(page, 2)).toContainText("FAKE Manager");

  // An explicit "No manager" clears only that role.
  form = await edit(page, `${unit} renamed`);
  await form.getByLabel("Manager").selectOption({ label: "No manager" });
  await form.getByRole("button", { name: "Save changes" }).click();
  await expect(
    notice(page, `Property ${unit} renamed saved as revision 3.`),
  ).toBeVisible();
  await expect(await row(page, 3)).toContainText("FAKE Owner");
  await expect(fact(page, "Manager")).toContainText("None");

  // Another tab saves first; this tab's save is refused, never retried silently.
  const other = await page.context().newPage();
  await signIn(other, "owner", false);
  await openProperty(other);
  await catalog(other)
    .getByRole("button", { name: `${unit} renamed`, exact: true })
    .click();
  const otherForm = await edit(other, `${unit} renamed`);
  await otherForm.getByLabel("Name").fill(`${unit} final`);
  await otherForm.getByRole("button", { name: "Save changes" }).click();
  await expect(
    notice(other, `Property ${unit} final saved as revision 4.`),
  ).toBeVisible();
  await other.close();

  form = await edit(page, `${unit} renamed`);
  await form.getByLabel("Name").fill(`${unit} stale`);
  await form.getByRole("button", { name: "Save changes" }).click();
  await expect(form.getByRole("alert")).toContainText(
    "saved by someone else after you opened it (now revision 4)",
  );
  await accessible(page, testInfo, "property-stale");
  await form.getByRole("button", { name: "Reload property" }).click();
  form = await edit(page, `${unit} final`);
  await expect(form.getByLabel("Name")).toHaveValue(`${unit} final`);
  await form.getByLabel("Name").fill(unit);
  await form.getByRole("button", { name: "Save changes" }).click();
  await expect(
    notice(page, `Property ${unit} saved as revision 5.`),
  ).toBeVisible();
  await expect(history(page).getByRole("row")).toHaveCount(6);
});

test("an owner publishes a listing and schedules and cancels a showing", async ({
  page,
}, testInfo) => {
  const unit = `FAKE unit ${testInfo.project.name}`;
  await signIn(page, "owner");
  await openProperty(page);
  await catalog(page).getByRole("button", { name: unit, exact: true }).click();

  const listing = page.getByRole("form", { name: "Edit listing" });
  await listing
    .getByLabel("Headline")
    .fill(`FAKE listing ${testInfo.project.name}`);
  await listing.getByLabel("Monthly rent").fill("1250.50");
  await listing.getByLabel("Currency").fill("USD");
  await listing.getByLabel("Available from").fill("2032-01-10");
  await listing.getByLabel("Listing status").selectOption("published");
  await listing.getByRole("button", { name: "Save listing" }).click();
  await expect(notice(page, "Listing saved as revision 1.")).toBeVisible();
  await expect(page.getByText("1250.50 USD", { exact: true })).toBeVisible();

  const form = page.getByRole("form", { name: "Schedule showing" });
  await form.getByLabel("Prospect").selectOption({ label: "FAKE Owner" });
  await form.getByLabel("Host").selectOption({ index: 1 });
  await form.getByLabel("Starts").fill("2032-01-12T10:00");
  await form.getByLabel("Ends").fill("2032-01-12T11:00");
  await form.getByRole("button", { name: "Schedule showing" }).click();
  await expect(notice(page, "Showing scheduled.")).toBeVisible();
  const showing = page
    .getByRole("region", { name: "Showings table" })
    .getByRole("row")
    .filter({ hasText: "Active" });
  await expect(showing).toContainText("2032-01-12 10:00");
  await form.getByRole("button", { name: "Schedule showing" }).click();
  await expect(form.getByRole("alert")).toContainText("already taken");
  await accessible(page, testInfo, "showing-conflict");
  await showing.getByRole("button", { name: "Cancel showing" }).focus();
  await page.keyboard.press("Enter");
  await expect(notice(page, "Showing cancelled.")).toBeVisible();
  await expect(form.getByRole("alert")).toHaveCount(0);
  await accessible(page, testInfo, "showing-cancelled");
});

test("a branch manager reads the branch without history or edit controls", async ({
  page,
}, testInfo) => {
  const unit = `FAKE unit ${testInfo.project.name}`;
  const historyReads: string[] = [];
  page.on("request", (request) => {
    if (/\/property\/objects\/[0-9a-f-]{36}\/history/.test(request.url()))
      historyReads.push(request.url());
  });
  await signIn(page, "branch");
  await openProperty(page);
  await expect(catalog(page).getByText(unit, { exact: true })).toBeVisible();
  await expect(catalog(page).getByText(HIDDEN, { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "New property", exact: true }),
  ).toHaveCount(0);
  await catalog(page).getByRole("button", { name: unit, exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: `Property ${unit}`, exact: true }),
  ).toBeFocused();
  await expect(fact(page, "Revision")).toContainText("5");
  await expect(fact(page, "Owner")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "History" })).toHaveCount(0);
  await expect(screen(page).getByRole("form")).toHaveCount(0);
  await expect(
    page.getByText(`FAKE listing ${testInfo.project.name}`, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Showings table" }),
  ).toContainText("Cancelled");
  await expect(
    page.getByRole("button", { name: "Cancel showing" }),
  ).toHaveCount(0);
  expect(historyReads).toEqual([]);
  await accessible(page, testInfo, "property-branch-detail");
});

test("a manager of an empty branch sees the empty catalog", async ({
  page,
}, testInfo) => {
  await signIn(page, "empty");
  await openProperty(page);
  await expect(
    page.getByText("No properties yet.", { exact: true }),
  ).toBeVisible();
  await expect(screen(page).getByRole("form")).toHaveCount(0);
  await accessible(page, testInfo, "property-empty");
});
