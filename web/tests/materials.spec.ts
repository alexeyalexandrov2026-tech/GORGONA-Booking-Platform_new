import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const phase = process.env.GBA_J5_PHASE;
const NAME = {
  owner: "FAKE user j5-owner",
  branch: "FAKE user j5-branch",
} as const;
type Person = keyof typeof NAME;
const RECOVERY = "gorgona.inventory.recovery.";

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
async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "You’re signed out." }),
  ).toBeVisible();
}
async function openMaterials(page: Page) {
  await page.getByRole("link", { name: "Materials", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Materials", exact: true }),
  ).toBeVisible();
}
const notice = (page: Page, text: string) =>
  page.getByRole("status").filter({ hasText: text });
const region = (page: Page, name: string) =>
  page.getByRole("region", { name, exact: true });
const saved = (page: Page) =>
  page.evaluate(
    (prefix) =>
      Object.entries(sessionStorage).filter(([key]) => key.startsWith(prefix)),
    RECOVERY,
  );
async function accessible(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page }).include(".materials").analyze();
  expect(axe.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  // A phone widens its layout viewport to fit a wider page: compare with the screen too.
  expect(await page.evaluate(() => innerWidth <= screen.width)).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
}

test("before any ledger book the screen says where accounts come from", async ({
  page,
}, testInfo) => {
  test.skip(phase !== "nobook", "runs before the books are created");
  await signIn(page, "owner");
  await openMaterials(page);
  await expect(region(page, "Material list")).toContainText(
    "No materials yet.",
  );
  await expect(region(page, "Balances")).toContainText("Nothing is held here.");
  await expect(region(page, "Cost of materials")).toContainText(
    "No cost recorded yet.",
  );
  const accounts = region(page, "Accounts of materials");
  await expect(accounts).toContainText(
    "Materials post to the ledger book of the company that owns them. Create a book first, then choose its accounts here.",
  );
  await expect(
    accounts.getByRole("combobox", { name: "Owner", exact: true }),
  ).toHaveCount(0);
  await accessible(page, testInfo, "materials-no-book");
  await accounts
    .getByRole("link", { name: "Open the ledger", exact: true })
    .click();
  await expect(page).toHaveURL(/\/ledger\/$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Ledger", exact: true }),
  ).toBeVisible();
});

test("owner: materials, places, lost answers and the accounts of materials", async ({
  page,
}, testInfo) => {
  test.skip(phase !== "enabled", "runs once the books exist");
  const p = testInfo.project.name;
  const P = p.toUpperCase();
  await signIn(page, "owner");
  await openMaterials(page);
  const list = region(page, "Material list");
  await expect(list).toContainText("SEED-OIL");

  // A new material; the code is typed in any case and saved in capitals.
  const editor = page.getByRole("form", { name: "Material editor" });
  const name = editor.getByLabel("Material name", { exact: true });
  const save = editor.getByRole("button", {
    name: "Save material",
    exact: true,
  });
  await editor.getByLabel("Material code", { exact: true }).fill(`gel-${p}`);
  await name.fill(`FAKE gel ${p}`);
  await editor.getByLabel("Unit", { exact: true }).fill("ml");
  await editor
    .getByRole("combobox", { name: "Decimal places", exact: true })
    .selectOption("2");
  await save.click();
  await expect(notice(page, "Material saved.")).toBeVisible();
  await expect(
    list.getByRole("row", { name: new RegExp(`GEL-${P}`) }),
  ).toContainText(`FAKE gel ${p}`);
  const choose = async () => {
    const select = editor.getByRole("combobox", {
      name: "Material to change",
      exact: true,
    });
    const value = await select
      .locator("option", { hasText: `GEL-${P} ·` })
      .getAttribute("value");
    await select.selectOption(value!);
    // A saved material keeps its code, unit and decimal places.
    await expect(
      editor.getByLabel("Material code", { exact: true }),
    ).toBeDisabled();
    await expect(editor.getByLabel("Unit", { exact: true })).toBeDisabled();
  };
  const pattern = "**/inventory/items/*";
  const recovery = region(page, "Materials change recovery");

  // 1. The server records the change and only its answer is lost. A reload keeps only
  // identifiers, and the screen settles the change by its original key.
  const committed: string[] = [];
  await page.route(pattern, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    committed.push(route.request().headers()["idempotency-key"]!);
    expect((await route.fetch()).status()).toBe(200);
    await route.abort("failed");
  });
  await choose();
  await name.fill(`FAKE gel ${p} two`);
  await save.click();
  await expect(
    recovery.getByRole("heading", {
      name: "Result not confirmed",
      exact: true,
    }),
  ).toBeVisible();
  await expect(save).toBeDisabled();
  const stored = await saved(page);
  expect(stored).toHaveLength(1);
  for (const secret of ["FAKE", "two", "GEL", "Bearer"])
    expect(stored[0]![1]).not.toContain(secret);
  await page.unroute(pattern);
  await page.reload();
  await signIn(page, "owner", false);
  await openMaterials(page);
  await expect(notice(page, "Your earlier change was recorded.")).toBeVisible();
  await expect(list).toContainText(`FAKE gel ${p} two`);
  expect(committed).toHaveLength(1);
  expect(await saved(page)).toHaveLength(0);

  // 2. The change never reached the server: the server knows nothing of it, and the
  // same change is sent again under the same key.
  const sent: { key: string }[] = [];
  let reach = false;
  await page.route(pattern, async (route) => {
    if (route.request().method() === "PUT") {
      sent.push({ key: route.request().headers()["idempotency-key"]! });
      if (!reach) return route.abort("failed");
    }
    await route.continue();
  });
  await choose();
  await name.fill(`FAKE gel ${p} three`);
  await save.click();
  await expect(recovery).toBeVisible();
  reach = true;
  await recovery
    .getByRole("button", { name: "Check the result", exact: true })
    .click();
  await expect(recovery).toContainText(
    "The server has no record of your last change yet.",
  );
  await recovery
    .getByRole("button", { name: "Send the same change again", exact: true })
    .click();
  await expect(notice(page, "Material saved.")).toBeVisible();
  await expect(recovery).toBeHidden();
  await expect(list).toContainText(`FAKE gel ${p} three`);
  expect(sent).toHaveLength(2);
  expect(sent[1]!.key).toBe(sent[0]!.key);
  await page.unroute(pattern);

  // 3. Another change never reached the server and is discarded; its late copy is refused.
  const late: { url: string; headers: Record<string, string>; data: string }[] =
    [];
  await page.route(pattern, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    late.push({
      url: route.request().url(),
      headers: route.request().headers(),
      data: route.request().postData()!,
    });
    await route.abort("failed");
  });
  await choose();
  await name.fill(`FAKE gel ${p} four`);
  await save.click();
  await expect(recovery).toBeVisible();
  await page.unroute(pattern);
  await recovery
    .getByRole("button", { name: "Check the result", exact: true })
    .click();
  await recovery
    .getByRole("button", { name: "Discard this change", exact: true })
    .click();
  await expect(
    notice(page, "The earlier change was discarded. Nothing was recorded."),
  ).toBeVisible();
  await expect(save).toBeEnabled();
  const refused = await page.request.put(late[0]!.url, {
    headers: late[0]!.headers,
    data: late[0]!.data,
  });
  expect(refused.status()).toBe(422);
  expect((await refused.json()).error.code).toBe("IDEMPOTENCY_KEY_REUSED");
  await page.reload();
  await signIn(page, "owner", false);
  await openMaterials(page);
  await expect(list).toContainText(`FAKE gel ${p} three`);
  await expect(list).not.toContainText(`FAKE gel ${p} four`);

  // A storage place in a branch the owner chooses.
  const places = page.getByRole("form", { name: "Storage place editor" });
  await expect(
    places
      .getByRole("combobox", { name: "Branch", exact: true })
      .locator("option"),
  ).toHaveCount(2);
  await places.getByLabel("Place code", { exact: true }).fill(`shelf-${p}`);
  await places
    .getByLabel("Place name", { exact: true })
    .fill(`FAKE shelf ${p}`);
  await places
    .getByRole("button", { name: "Save storage place", exact: true })
    .click();
  await expect(notice(page, "Storage place saved.")).toBeVisible();
  await expect(region(page, "Storage places")).toContainText(
    `SHELF-${P} · FAKE shelf ${p}`,
  );

  // Balances of every branch, filtered by place; the cost at the moving average.
  const balances = region(page, "Balances");
  await expect(balances.getByRole("row", { name: /SEED-OIL/ })).toHaveCount(2);
  await balances
    .getByRole("combobox", { name: "Place", exact: true })
    .selectOption({ label: "SEED-SHELF · FAKE seed shelf" });
  const home = balances.getByRole("row", { name: /SEED-OIL/ });
  await expect(home).toHaveCount(1);
  await expect(home).toContainText("FAKE_SEED · FAKE seed Materials LLC");
  await expect(home).toContainText("2.5");
  await expect(
    region(page, "Cost of materials").getByRole("row", { name: /SEED-OIL/ }),
  ).toContainText("14.00 USD");

  // The accounts of materials of this project's company.
  const accounts = region(page, "Accounts of materials");
  await accounts
    .getByRole("combobox", { name: "Owner", exact: true })
    .selectOption({ label: `FAKE_${P} · FAKE ${p} Materials LLC` });
  const rules = accounts.getByRole("form", { name: "Accounts of this book" });
  await expect(rules).toContainText("No accounts are chosen for this book yet");
  const pick = (field: string, label: string) =>
    rules
      .getByRole("combobox", { name: field, exact: true })
      .selectOption({ label });
  await pick("Inventory", "1300 · Inventory and materials");
  await pick("Receipts", "1300 · Inventory and materials");
  await pick("Opening balances", "3900 · Opening balances");
  await pick("Surplus", "4900 · Other income");
  await pick("Material consumption", "5000 · Cost of goods and materials");
  await pick("Losses", "6900 · Other expenses");
  await pick("Price differences", "6900 · Other expenses");
  const submit = rules.getByRole("button", {
    name: "Save accounts",
    exact: true,
  });
  await expect(rules.getByRole("alert")).toHaveText(
    "The inventory account must differ from the other six accounts.",
  );
  await expect(submit).toBeDisabled();
  await pick("Receipts", "1400 · Prepaid expenses");
  await expect(rules.getByRole("alert")).toHaveCount(0);
  await submit.click();
  await expect(notice(page, "Accounts of materials saved.")).toBeVisible();
  await expect(rules).not.toContainText("No accounts are chosen");
  await expect(
    rules
      .getByRole("combobox", { name: "Receipts", exact: true })
      .locator("option:checked"),
  ).toHaveText("1400 · Prepaid expenses");
  await accessible(page, testInfo, "materials-owner");
  await signOut(page);
});

test("branch manager: one branch, no cost, no accounts and no material changes", async ({
  page,
}, testInfo) => {
  test.skip(phase !== "enabled", "runs once the books exist");
  const p = testInfo.project.name;
  const P = p.toUpperCase();
  await signIn(page, "branch");
  await openMaterials(page);
  await expect(region(page, "Material list")).toContainText("SEED-OIL");
  await expect(page.getByRole("form", { name: "Material editor" })).toHaveCount(
    0,
  );
  await expect(region(page, "Cost of materials")).toHaveCount(0);
  await expect(region(page, "Accounts of materials")).toHaveCount(0);
  const balances = region(page, "Balances");
  const row = balances.getByRole("row", { name: /SEED-OIL/ });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("SEED-SHELF · FAKE seed shelf");
  await expect(row).toContainText("Company");
  await expect(balances).not.toContainText("AWAY-SHELF");
  await expect(region(page, "Storage places")).not.toContainText("AWAY-SHELF");
  const places = page.getByRole("form", { name: "Storage place editor" });
  await expect(
    places
      .getByRole("combobox", { name: "Branch", exact: true })
      .locator("option"),
  ).toHaveCount(1);
  await places.getByLabel("Place code", { exact: true }).fill(`br-${p}`);
  await places
    .getByLabel("Place name", { exact: true })
    .fill(`FAKE branch ${p}`);
  await places
    .getByRole("button", { name: "Save storage place", exact: true })
    .click();
  await expect(notice(page, "Storage place saved.")).toBeVisible();
  await expect(region(page, "Storage places")).toContainText(
    `BR-${P} · FAKE branch ${p}`,
  );
  await accessible(page, testInfo, "materials-branch");
  await signOut(page);
});
