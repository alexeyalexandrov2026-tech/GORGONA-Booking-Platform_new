import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

test("ledger: book, accounts, response loss, entry, report, reversal and periods", async ({
  page,
}, testInfo) => {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Ledger", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Legal entity", exact: true })
    .selectOption({
      label: `FAKE_${testInfo.project.name.toUpperCase()} · FAKE ${testInfo.project.name} Ledger LLC`,
    });
  const book = page.getByRole("form", { name: "Book settings" });
  await book
    .getByRole("combobox", { name: "Base currency", exact: true })
    .selectOption("USD");
  await book.getByLabel("Accounting start", { exact: true }).fill("2026-01-01");
  await book.getByRole("button", { name: "Create book", exact: true }).click();
  const chart = page
    .locator("summary")
    .filter({ hasText: "Chart of accounts" });
  await chart.click();
  await expect(
    page.getByRole("region", { name: "Chart of accounts" }),
  ).toContainText("Cash");
  const account = page.getByRole("form", { name: "Account editor" });
  await account.getByLabel("Account code", { exact: true }).fill("FAKE-1");
  await account
    .getByLabel("Account name", { exact: true })
    .fill("FAKE Custom account");
  await account
    .getByRole("button", { name: "Save account", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Chart of accounts" }),
  ).toContainText("FAKE Custom account");
  await chart.click();
  const entry = page.getByRole("form", { name: "Post journal entry" });
  await entry.getByLabel("Entry date", { exact: true }).fill("2026-10-01");
  await entry
    .getByRole("combobox", { name: "Entry currency", exact: true })
    .selectOption("USD");
  await entry
    .getByLabel("Business operation ID (optional)", { exact: true })
    .fill(`FAKE-${testInfo.project.name}`);
  await entry
    .getByRole("combobox", { name: "Account 1", exact: true })
    .selectOption({ label: "1000 · Cash" });
  await entry
    .getByRole("combobox", { name: "Account 2", exact: true })
    .selectOption({ label: "4100 · Services" });
  await entry.getByLabel("Amount 1", { exact: true }).fill("12.30");
  await entry.getByLabel("Amount 2", { exact: true }).fill("12.31");
  await expect(
    entry.getByRole("button", { name: "Post entry", exact: true }),
  ).toBeDisabled();
  await entry.getByLabel("Amount 2", { exact: true }).fill("12.30");
  // Real server persists the command, then only its response is lost.
  const keys: string[] = [];
  let lose = true;
  let saved = 0;
  const pattern = "**/ledger/books/*/entries/*";
  await page.route(pattern, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    keys.push(route.request().headers()["idempotency-key"]!);
    if (lose) {
      lose = false;
      saved = (await route.fetch()).status();
      await route.abort("failed");
    } else await route.continue();
  });
  await entry.getByRole("button", { name: "Post entry", exact: true }).click();
  await page
    .getByRole("button", { name: "Retry same ledger command", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Journal", exact: true }),
  ).toContainText("USD 12.30");
  expect(saved).toBe(200);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  await page.unroute(pattern);
  const report = page.getByRole("region", {
    name: "Trial balance",
    exact: true,
  });
  await report.getByLabel("From month", { exact: true }).fill("2026-10");
  await report.getByLabel("To month", { exact: true }).fill("2026-10");
  await report
    .getByRole("combobox", { name: "Report currency", exact: true })
    .selectOption("USD");
  await report
    .getByRole("button", { name: "Read trial balance", exact: true })
    .click();
  await expect(report.getByRole("row", { name: /Total USD/ })).toContainText(
    "12.30",
  );
  await page
    .getByRole("button", {
      name: `Read entry FAKE-${testInfo.project.name}`,
      exact: true,
    })
    .click();
  const reversal = page.getByRole("form", { name: "Reverse journal entry" });
  await reversal
    .getByLabel("Reversal date", { exact: true })
    .fill("2026-10-02");
  await reversal
    .getByLabel("Reversal note", { exact: true })
    .fill("FAKE correction");
  await reversal
    .getByRole("button", { name: "Post reversal", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Journal", exact: true }),
  ).toContainText("reversal");
  const periods = page.getByRole("region", {
    name: "Ledger periods",
    exact: true,
  });
  await periods.getByLabel("Ledger month", { exact: true }).fill("2026-10");
  await periods
    .getByRole("button", { name: "Read month", exact: true })
    .click();
  await periods
    .getByRole("button", { name: "Close month", exact: true })
    .click();
  await expect(
    page.getByText("Ledger command saved.", { exact: true }),
  ).toBeVisible();
  await periods
    .getByRole("button", { name: "Read month", exact: true })
    .click();
  await expect(periods).toContainText("Month 2026-10: closed");
  await expect(
    periods.getByRole("button", { name: "Reopen month", exact: true }),
  ).toBeDisabled();
  await periods
    .getByLabel("Period reason", { exact: true })
    .fill("FAKE review");
  await periods
    .getByRole("button", { name: "Reopen month", exact: true })
    .click();
  await expect(
    page.getByText("Ledger command saved.", { exact: true }),
  ).toBeVisible();
  await periods
    .getByRole("button", { name: "Read month", exact: true })
    .click();
  await expect(periods).toContainText("Month 2026-10: open");
  await report
    .getByRole("button", { name: "Read trial balance", exact: true })
    .click();
  const total = report.getByRole("row", { name: /Total USD/ });
  await expect(total).toContainText("24.60");
  expect(await total.getByRole("cell").allTextContents()).toEqual([
    "0.00",
    "0.00",
    "24.60",
    "24.60",
    "0.00",
    "0.00",
  ]);
  const axe = await new AxeBuilder({ page }).include(".ledger").analyze();
  expect(axe.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("ledger.png"),
    fullPage: true,
  });
});

test("unknown entry identity survives reload and safe cancellation rejects a delayed request", async ({
  page,
}, testInfo) => {
  const login = async () => {
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("link", { name: "Ledger", exact: true }),
    ).toBeVisible();
    await page.getByRole("link", { name: "Ledger", exact: true }).click();
  };
  await page.goto("/overview/");
  await login();
  await page
    .getByRole("combobox", { name: "Legal entity", exact: true })
    .selectOption({
      label: `FAKE_${testInfo.project.name.toUpperCase()} · FAKE ${testInfo.project.name} Ledger LLC`,
    });
  const fill = async () => {
    const form = page.getByRole("form", { name: "Post journal entry" });
    await form.getByLabel("Entry date", { exact: true }).fill("2026-10-03");
    await form
      .getByRole("combobox", { name: "Entry currency", exact: true })
      .selectOption("USD");
    await form
      .getByLabel("Entry note (optional)", { exact: true })
      .fill("FAKE PRIVATE recovery note");
    await form
      .getByRole("combobox", { name: "Account 1", exact: true })
      .selectOption({ label: "1000 · Cash" });
    await form
      .getByRole("combobox", { name: "Account 2", exact: true })
      .selectOption({ label: "4100 · Services" });
    await form.getByLabel("Amount 1", { exact: true }).fill("12.30");
    await form.getByLabel("Amount 2", { exact: true }).fill("12.30");
    // Deliberately no business operation ID; recovery must preserve the automatic identity.
    await form.getByRole("button", { name: "Post entry", exact: true }).click();
  };
  const selectedEntity = await page
    .getByRole("combobox", { name: "Legal entity", exact: true })
    .inputValue();
  const requests: {
    url: string;
    headers: Record<string, string>;
    data: string;
  }[] = [];
  let reached = true;
  const pattern = "**/ledger/books/*/entries/*";
  await page.route(pattern, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    requests.push({
      url: route.request().url(),
      headers: route.request().headers(),
      data: route.request().postData()!,
    });
    if (reached) {
      expect((await route.fetch()).status()).toBe(200);
    }
    await route.abort("failed");
  });
  await fill();
  await expect(
    page.getByRole("button", {
      name: "Retry same ledger command",
      exact: true,
    }),
  ).toBeVisible();
  const stored = await page.evaluate(() =>
    Object.entries(sessionStorage).filter(([key]) =>
      key.startsWith("gorgona.ledger.recovery."),
    ),
  );
  expect(stored).toHaveLength(1);
  expect(stored[0]![1]).not.toContain("FAKE PRIVATE");
  expect(stored[0]![1]).not.toContain("12.30");
  expect(stored[0]![1]).not.toContain("Bearer");
  await page.unroute(pattern);
  await page.reload();
  await login();
  await expect(
    page.getByText("Recovered a saved ledger command.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Legal entity", exact: true }),
  ).toHaveValue(selectedEntity);
  const saved = requests[0]!;
  const bookBase = saved.url.split("/entries/")[0]!;
  const id = saved.url.split("/entries/")[1]!;
  const journal = await page.request.get(`${bookBase}/entries`, {
    headers: saved.headers,
  });
  expect(journal.status()).toBe(200);
  const rows = (await journal.json()).items as { entry_id: string }[];
  expect(rows.filter((row) => row.entry_id === id)).toHaveLength(1);
  expect(
    await page.evaluate(() =>
      Object.keys(sessionStorage).filter((key) =>
        key.startsWith("gorgona.ledger.recovery."),
      ),
    ),
  ).toHaveLength(0);
  // An operation that never reached the server is resolved without allowing a later arrival.
  reached = false;
  await page.route(pattern, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    requests.push({
      url: route.request().url(),
      headers: route.request().headers(),
      data: route.request().postData()!,
    });
    await route.abort("failed");
  });
  await fill();
  await expect(
    page.getByRole("button", {
      name: "Retry same ledger command",
      exact: true,
    }),
  ).toBeVisible();
  await page.unroute(pattern);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page.getByRole("link", { name: "Ledger", exact: true }).click();
  const recovery = page.getByRole("region", {
    name: "Ledger command recovery",
  });
  await expect(recovery).toBeVisible();
  await expect(
    page
      .getByRole("form", { name: "Post journal entry" })
      .getByLabel("Entry date", { exact: true }),
  ).toBeDisabled();
  await recovery
    .getByRole("button", { name: "Cancel unresolved request", exact: true })
    .click();
  await expect(
    page.getByText("The unresolved request was cancelled.", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("form", { name: "Post journal entry" })
      .getByLabel("Entry date", { exact: true }),
  ).toBeEnabled();
  const delayed = requests[1]!;
  const refused = await page.request.put(delayed.url, {
    headers: delayed.headers,
    data: delayed.data,
  });
  expect(refused.status()).toBe(409);
  expect((await refused.json()).error.code).toBe("LEDGER_COMMAND_CANCELLED");
});
