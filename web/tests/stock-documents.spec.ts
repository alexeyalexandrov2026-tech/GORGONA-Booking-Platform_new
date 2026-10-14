import { test, expect, type Locator, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const NAME = {
  owner: "FAKE user j5b-owner",
  branch: "FAKE user j5b-branch",
} as const;
type Person = keyof typeof NAME;
const OWNER = "FAKE_STOCK · FAKE stock Materials LLC";
// Seeded names follow one pattern: the code, then "FAKE" and the code in lower case.
const label = (code: string) => `${code} · FAKE ${code.toLowerCase()}`;
const NO_AMOUNTS =
  "Amounts are shown only to finance managers of the whole company.";

async function signIn(page: Page, who: Person) {
  const switched = await page.request.post(`${issuer}/fixture/user/${who}`);
  expect(switched.ok()).toBe(true);
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(NAME[who], { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Stock documents", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Stock documents",
      exact: true,
    }),
  ).toBeVisible();
}
async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "You’re signed out." }),
  ).toBeVisible();
}
const notice = (page: Page, text: string) =>
  page.getByRole("status").filter({ hasText: text });
const region = (page: Page, name: string) =>
  page.getByRole("region", { name, exact: true });
const field = (form: Locator, name: string) =>
  form.getByRole("combobox", { name, exact: true });
async function line(
  form: Locator,
  n: number,
  material: string,
  quantity: string,
  amount?: string,
) {
  await field(form, `Material ${n}`).selectOption({ label: label(material) });
  await form.getByLabel(`Quantity ${n}`, { exact: true }).fill(quantity);
  if (amount !== undefined)
    await form.getByLabel(`Amount ${n}`, { exact: true }).fill(amount);
}
async function open(page: Page, row: RegExp) {
  const found = region(page, "Document list").getByRole("row", { name: row });
  await expect(found).toHaveCount(1);
  await found.getByRole("button", { name: "Open", exact: true }).click();
  return region(page, "Document");
}
async function accessible(page: Page, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".stock-documents")
    .analyze();
  expect(axe.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  // A phone widens its layout viewport to fit a wider page: compare with the screen too.
  expect(await page.evaluate(() => innerWidth <= screen.width)).toBe(true);
  await page.screenshot({
    path: test.info().outputPath(`${name}.png`),
    fullPage: true,
  });
}

test("owner: receipt with a lost answer, write-off, transfer, return and a discarded write-off", async ({
  page,
}, testInfo) => {
  const P = testInfo.project.name.toUpperCase();
  await signIn(page, "owner");
  const form = page.getByRole("form", { name: "New stock document" });
  const kind = field(form, "Document kind");
  const post = form.getByRole("button", { name: "Post document", exact: true });
  const recovery = region(page, "Stock document recovery");
  const pattern = "**/inventory/documents/*";
  const start = async (what: string, place: string, day: string) => {
    await kind.selectOption({ label: what });
    await field(form, "Owner").selectOption({ label: OWNER });
    await field(form, "Place").selectOption({ label: label(place) });
    await form.getByLabel("Document date", { exact: true }).fill(day);
  };

  // A receipt of two lines. The server records it and only its answer is lost: the
  // browser keeps identifiers only, and the screen settles the document by its key.
  await start("Receipt", `A-${P}`, "2026-10-01");
  await field(form, "Reason").selectOption({ label: "Purchase" });
  await form
    .getByLabel("Supplier document number (optional)", { exact: true })
    .fill(`FAKE-INV-${P}`);
  await line(form, 1, `OIL-${P}`, "10.0", "25.00");
  await form.getByRole("button", { name: "Add line", exact: true }).click();
  await line(form, 2, `FOIL-${P}`, "4", "8.00");
  const sent: string[] = [];
  await page.route(pattern, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    sent.push(route.request().headers()["idempotency-key"]!);
    expect((await route.fetch()).status()).toBe(200);
    await route.abort("failed");
  });
  await post.click();
  await expect(
    recovery.getByRole("heading", {
      name: "Result not confirmed",
      exact: true,
    }),
  ).toBeVisible();
  await expect(post).toBeDisabled();
  const stored = await page.evaluate(() =>
    Object.entries(sessionStorage).filter(([key]) =>
      key.startsWith("gorgona.inventory.recovery."),
    ),
  );
  expect(stored).toHaveLength(1);
  for (const secret of ["FAKE", "25.00", "OIL", "Bearer"])
    expect(stored[0]![1]).not.toContain(secret);
  await page.unroute(pattern);
  await recovery
    .getByRole("button", { name: "Check the result", exact: true })
    .click();
  await expect(notice(page, "Your earlier change was recorded.")).toBeVisible();
  expect(sent).toHaveLength(1);
  let view = await open(page, new RegExp(`Receipt.*A-${P}`));
  await expect(
    view.getByRole("heading", { name: "Receipt of 2026-10-01", exact: true }),
  ).toBeVisible();
  await expect(view).toContainText(`FAKE-INV-${P}`);
  await expect(
    view.getByRole("row", { name: new RegExp(` OIL-${P}`) }),
  ).toContainText("25.00");
  await expect(view).toContainText("Total 33.00 USD");

  // More than the place holds is refused with a named reason; less is posted at the
  // moving average.
  await start("Write-off", `A-${P}`, "2026-10-02");
  await field(form, "Reason").selectOption({ label: "Used" });
  await line(form, 1, `OIL-${P}`, "11.0");
  await post.click();
  await expect(form.getByRole("alert")).toHaveText(
    "There is not enough of this material at this place.",
  );
  await form.getByLabel("Quantity 1", { exact: true }).fill("4.0");
  await post.click();
  await expect(notice(page, "Stock document posted.")).toBeVisible();
  view = await open(page, new RegExp(`Write-off.*A-${P}`));
  await expect(view).toContainText("Total 10.00 USD");

  // A transfer to another branch moves quantities only.
  await start("Transfer", `A-${P}`, "2026-10-03");
  await field(form, "To place").selectOption({ label: label(`AWAY-${P}`) });
  await line(form, 1, `FOIL-${P}`, "1");
  await post.click();
  await expect(notice(page, "Stock document posted.")).toBeVisible();
  view = await open(page, new RegExp(`Transfer.*A-${P}.*AWAY-${P}`));
  await expect(view).toContainText(label(`AWAY-${P}`));
  await expect(view).not.toContainText("USD");

  // A return to the supplier names a line of the receipt and the quantity going back.
  await kind.selectOption({ label: "Return" });
  await field(form, "Owner").selectOption({ label: OWNER });
  await field(form, "Reason").selectOption({ label: "Return to supplier" });
  await field(form, "Source document").selectOption({
    label: `Receipt of 2026-10-01 at A-${P} · 2 lines`,
  });
  // The place defaults to the place of the source document.
  await expect(field(form, "Place").locator("option:checked")).toHaveText(
    label(`A-${P}`),
  );
  await form.getByLabel("Document date", { exact: true }).fill("2026-10-04");
  await form
    .getByLabel("Quantity to return, line 1", { exact: true })
    .fill("2.0");
  await post.click();
  await expect(notice(page, "Stock document posted.")).toBeVisible();
  view = await open(page, new RegExp(`Return.*A-${P}`));
  await expect(
    view.getByRole("heading", { name: "Return of 2026-10-04", exact: true }),
  ).toBeVisible();
  await expect(
    view.getByRole("row", { name: new RegExp(` OIL-${P}`) }),
  ).toContainText("5.00");

  // A write-off that never reached the server is discarded; its late copy is refused.
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
  await start("Write-off", `A-${P}`, "2026-10-05");
  await field(form, "Reason").selectOption({ label: "Damaged" });
  await line(form, 1, `OIL-${P}`, "1.0");
  await post.click();
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
  const refused = await page.request.put(late[0]!.url, {
    headers: late[0]!.headers,
    data: late[0]!.data,
  });
  expect(refused.status()).toBe(422);
  expect((await refused.json()).error.code).toBe("IDEMPOTENCY_KEY_REUSED");
  await expect(
    region(page, "Document list").getByRole("row", {
      name: new RegExp(`Write-off.*A-${P}`),
    }),
  ).toHaveCount(1);
  await accessible(page, "stock-documents-owner");
  await signOut(page);
});

test("branch manager: own branch, quantities only, transfers only", async ({
  page,
}, testInfo) => {
  const P = testInfo.project.name.toUpperCase();
  await signIn(page, "branch");
  const view = await open(page, new RegExp(`Receipt.*A-${P}`));
  await expect(view).toContainText(NO_AMOUNTS);
  await expect(view).not.toContainText("USD");
  await expect(view).not.toContainText(`FAKE-INV-${P}`);
  const form = page.getByRole("form", { name: "New stock document" });
  const kind = field(form, "Document kind");
  await expect(kind.locator("option")).toHaveCount(1);
  await expect(kind).toHaveValue("transfer");
  // A branch manager reads no company names: the one owner of the stock is "Company".
  await expect(field(form, "Owner").locator("option")).toHaveText(["Company"]);
  await field(form, "Place").selectOption({ label: label(`A-${P}`) });
  const destination = field(form, "To place");
  await expect(destination.locator("option", { hasText: "AWAY-" })).toHaveCount(
    0,
  );
  await destination.selectOption({ label: label(`B-${P}`) });
  await form.getByLabel("Document date", { exact: true }).fill("2026-10-06");
  await line(form, 1, `OIL-${P}`, "1.0");
  await form
    .getByRole("button", { name: "Post document", exact: true })
    .click();
  await expect(notice(page, "Stock document posted.")).toBeVisible();
  await expect(
    region(page, "Document list").getByRole("row", {
      name: new RegExp(`Transfer.*A-${P}.*B-${P}`),
    }),
  ).toHaveCount(1);
  await accessible(page, "stock-documents-branch");
  await signOut(page);
});
