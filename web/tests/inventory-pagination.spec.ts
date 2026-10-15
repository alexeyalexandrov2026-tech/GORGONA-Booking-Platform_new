import { test, expect, type Page, type Locator } from "@playwright/test";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const region = (page: Page, name: string) =>
  page.getByRole("region", { name, exact: true });
async function chooseLast(select: Locator) {
  const option = select.locator("option").filter({ hasText: "PAGE-100" });
  await expect(option).toHaveCount(1);
  await select.selectOption((await option.getAttribute("value"))!);
}
async function signIn(page: Page) {
  expect((await page.request.post(`${issuer}/fixture/user/owner`)).ok()).toBe(
    true,
  );
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page
      .locator(".mgmt-header-actions")
      .getByText("FAKE user j5b-owner", { exact: true }),
  ).toBeVisible();
}

test("a repeated catalogue cursor refuses a partial material list", async ({
  page,
}) => {
  await signIn(page);
  let cursor: string | null = null;
  await page.route("**/inventory/items?*", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    cursor ??= new URL(route.request().url()).searchParams.get("after");
    body.next_cursor = cursor;
    await route.fulfill({ response, json: body });
  });
  await page.getByRole("link", { name: "Materials", exact: true }).click();
  await expect(page.locator(".materials").getByRole("alert")).toContainText(
    "Unable to load the complete materials list safely.",
  );
  await expect(region(page, "Material list").getByRole("row")).toHaveCount(0);
});

test("both screens follow every catalogue cursor and keep the 101st material after save", async ({
  page,
}) => {
  await signIn(page);
  await page.getByRole("link", { name: "Materials", exact: true }).click();
  const list = region(page, "Material list");
  await expect(list.getByRole("row")).toHaveCount(102);
  await expect(
    region(page, "Storage places").getByRole("listitem"),
  ).toHaveCount(101);
  await expect(region(page, "Balances").getByRole("row")).toHaveCount(102);
  await expect(region(page, "Cost of materials").getByRole("row")).toHaveCount(
    102,
  );
  const editor = page.getByRole("form", { name: "Material editor" });
  await chooseLast(
    editor.getByRole("combobox", { name: "Material to change", exact: true }),
  );
  const editedName = `FAKE last material edited ${test.info().project.name}`;
  await editor.getByLabel("Material name", { exact: true }).fill(editedName);
  await editor
    .getByRole("button", { name: "Save material", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Material saved." }),
  ).toBeVisible();
  await expect(list).toContainText(editedName);
  await page
    .getByRole("link", { name: "Stock documents", exact: true })
    .click();
  const form = page.getByRole("form", { name: "New stock document" });
  await expect(
    form
      .getByRole("combobox", { name: "Material 1", exact: true })
      .locator("option"),
  ).toHaveCount(102);
  await expect(
    form
      .getByRole("combobox", { name: "Place", exact: true })
      .locator("option"),
  ).toHaveCount(102);
  await chooseLast(
    form.getByRole("combobox", { name: "Material 1", exact: true }),
  );
  await chooseLast(form.getByRole("combobox", { name: "Place", exact: true }));
  await page
    .getByRole("button", { name: "Show more documents", exact: true })
    .click();
  await expect(
    region(page, "Document list").getByRole("row", { name: /PAGE-100/ }),
  ).toBeVisible();
  await form
    .getByRole("combobox", { name: "Document kind", exact: true })
    .selectOption("return");
  await chooseLast(
    form.getByRole("combobox", { name: "Source document", exact: true }),
  );
  await form.getByLabel("Document date", { exact: true }).fill("2026-10-02");
  await form
    .getByLabel("Quantity to return, line 1", { exact: true })
    .fill("0.5");
  await expect(
    form.getByRole("button", { name: "Post document", exact: true }),
  ).toBeEnabled();
});

test("a return refuses a source line whose material is not loaded", async ({
  page,
}) => {
  await signIn(page);
  await page
    .getByRole("link", { name: "Stock documents", exact: true })
    .click();
  await page.route("**/inventory/documents/*", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.lines[0].item_id = "00000000-0000-4000-8000-000000000999";
    await route.fulfill({ response, json: body });
  });
  const form = page.getByRole("form", { name: "New stock document" });
  await form
    .getByRole("combobox", { name: "Document kind", exact: true })
    .selectOption("return");
  await form
    .getByRole("combobox", { name: "Source document", exact: true })
    .selectOption({ index: 1 });
  await form.getByLabel("Document date", { exact: true }).fill("2026-10-02");
  await form
    .getByLabel("Quantity to return, line 1", { exact: true })
    .fill("1");
  await expect(form).toContainText("A material");
  await expect(
    form.getByRole("button", { name: "Post document", exact: true }),
  ).toBeDisabled();
});

for (const kind of ["item", "place", "posting_rules", "document"] as const) {
  test(`a ${kind} command refuses a response for another subject`, async ({
    page,
  }) => {
    await signIn(page);
    await page
      .getByRole("link", {
        name: kind === "document" ? "Stock documents" : "Materials",
        exact: true,
      })
      .click();
    const endpoint = {
      item: "items",
      place: "places",
      posting_rules: "posting-rules",
      document: "documents",
    }[kind];
    await page.route(`**/inventory/${endpoint}/*`, async (route) => {
      if (route.request().method() !== "PUT") return route.continue();
      const response = await route.fetch();
      const body = await response.json();
      body[
        {
          item: "item_id",
          place: "place_id",
          posting_rules: "book_id",
          document: "document_id",
        }[kind]
      ] = "00000000-0000-4000-8000-000000000999";
      await route.fulfill({ response, json: body });
    });
    if (kind === "item") {
      const form = page.getByRole("form", { name: "Material editor" });
      await form
        .getByRole("combobox", { name: "Material to change", exact: true })
        .selectOption({ index: 1 });
      await form
        .getByLabel("Material name", { exact: true })
        .fill("FAKE subject");
      await form
        .getByRole("button", { name: "Save material", exact: true })
        .click();
    } else if (kind === "place") {
      const form = page.getByRole("form", { name: "Storage place editor" });
      await form
        .getByRole("combobox", { name: "Place to change", exact: true })
        .selectOption({ index: 1 });
      await form.getByLabel("Place name", { exact: true }).fill("FAKE subject");
      await form
        .getByRole("button", { name: "Save storage place", exact: true })
        .click();
    } else if (kind === "posting_rules") {
      const form = page.getByRole("form", { name: "Accounts of this book" });
      await form
        .getByRole("button", { name: "Save accounts", exact: true })
        .click();
    } else {
      const form = page.getByRole("form", { name: "New stock document" });
      await form
        .getByRole("combobox", { name: "Place", exact: true })
        .selectOption({ index: 1 });
      await form
        .getByRole("combobox", { name: "Material 1", exact: true })
        .selectOption({ index: 1 });
      await form.getByLabel("Quantity 1", { exact: true }).fill("1.0");
      await form.getByLabel("Amount 1", { exact: true }).fill("1.00");
      await form
        .getByLabel("Document date", { exact: true })
        .fill("2026-10-02");
      await form
        .getByRole("button", { name: "Post document", exact: true })
        .click();
    }
    await expect(
      page.getByRole("heading", { name: "Result not confirmed", exact: true }),
    ).toBeVisible();
  });
}
