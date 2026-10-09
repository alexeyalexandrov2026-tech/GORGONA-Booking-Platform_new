import { test, expect, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { join } from "node:path";
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
async function choose(select: Locator, text: string | RegExp) {
  const value = await select
    .locator("option")
    .filter({ hasText: text })
    .first()
    .getAttribute("value");
  expect(value).toBeTruthy();
  await select.selectOption(value!);
}
test("financial documents: real gates, recovery, partial settlement, correction, credit and historical void", async ({
  page,
}, testInfo) => {
  test.setTimeout(240000);
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Financial documents", exact: true })
    .click();
  // Wait for the initial book before explicitly selecting it again. A same-book
  // selection must keep loaded state and its gate instead of clearing them.
  await expect(
    page.getByRole("region", { name: "Invoices and accruals", exact: true }),
  ).toBeVisible();
  await choose(
    page.getByRole("combobox", { name: "Financial book", exact: true }),
    `FAKE ${testInfo.project.name} Finance LLC`,
  );
  const newInvoice = page.getByRole("button", {
    name: "New invoice",
    exact: true,
  });
  if (process.env.GBA_H4_BROWSER_PHASE === "closed") {
    await expect(newInvoice).toBeDisabled();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    return;
  }
  await expect(newInvoice).toBeEnabled();
  await newInvoice.click();
  const draft = page.getByRole("form", { name: "New invoice", exact: true });
  await choose(
    draft.getByRole("combobox", { name: "Counterparty version", exact: true }),
    "FAKE Finance Customer",
  );
  await draft
    .getByRole("combobox", { name: "Currency", exact: true })
    .selectOption("USD");
  await draft.getByLabel("Document date", { exact: true }).fill("2026-10-01");
  await draft
    .getByLabel("Title", { exact: true })
    .fill("FAKE financial browser invoice");
  const invoiceNumber = `FAKE-INV-${testInfo.project.name}`;
  await draft
    .getByLabel("Document number", { exact: true })
    .fill(invoiceNumber);
  await choose(
    draft.getByRole("combobox", { name: "Control account", exact: true }),
    /^1200/,
  );
  await draft
    .getByLabel("Line 1 description", { exact: true })
    .fill("FAKE invoiced service");
  await choose(
    draft.getByRole("combobox", {
      name: "Line 1 counter account",
      exact: true,
    }),
    /^4100/,
  );
  await draft.getByLabel("Line 1 amount", { exact: true }).fill("100.00");
  await draft.getByRole("button", { name: "Save draft", exact: true }).click();
  const issue = page.getByRole("form", {
    name: "Issue saved draft",
    exact: true,
  });
  await issue.getByLabel("Posting date", { exact: true }).fill("2026-10-01");
  await issue.getByRole("checkbox").check();
  let lostIssue = false;
  await page.route(
    "**/financial-documents/books/*/invoices/*/issue",
    async (route) => {
      if (!lostIssue) {
        lostIssue = true;
        await route.fetch();
        await route.abort("failed");
      } else await route.continue();
    },
  );
  await issue
    .getByRole("button", { name: "Issue document", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Financial command recovery" }),
  ).toBeVisible();
  const storage = await page.evaluate(() =>
    Object.keys(sessionStorage)
      .filter((k) => k.startsWith("gorgona.financial.recovery."))
      .map((k) => sessionStorage.getItem(k)),
  );
  expect(JSON.stringify(storage)).not.toContain("100.00");
  expect(JSON.stringify(storage)).not.toContain(invoiceNumber);
  await page.unrouteAll({ behavior: "wait" });
  await page.reload();
  // Tokens intentionally live only in memory. Reauthenticate after reload;
  // command recovery survives separately as minimal actor-bound metadata.
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Financial documents", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Financial command recovery" }),
  ).toHaveCount(0);
  await choose(
    page.getByRole("combobox", { name: "Financial book", exact: true }),
    `FAKE ${testInfo.project.name} Finance LLC`,
  );
  await page.getByRole("button", { name: new RegExp(invoiceNumber) }).click();
  await expect(
    page.getByRole("region", { name: "Financial document detail" }),
  ).toContainText("issued");
  await page
    .getByRole("button", { name: "Obligations and settlements", exact: true })
    .click();
  const table = page.getByRole("table", { name: "Obligation balances" });
  const invoiceRow = table
    .getByRole("row")
    .filter({ hasText: "invoice" })
    .first();
  await expect(invoiceRow).toContainText("100.00 USD");
  await invoiceRow
    .getByRole("button", { name: "Prepare settlement", exact: true })
    .click();
  const prepare = page.getByRole("form", {
    name: "Prepare settlement",
    exact: true,
  });
  await prepare.getByRole("textbox").fill("100.00");
  await prepare
    .getByRole("button", { name: "Prepare settlement", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Approve settlement", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Reserve settlement", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Settlement detail" }),
  ).toContainText("reserved 100.00");
  await page
    .getByRole("button", { name: "Record external payment", exact: true })
    .click();
  const payment = page.getByRole("form", {
    name: "Record external payment",
    exact: true,
  });
  await payment
    .getByLabel("Payment posting date", { exact: true })
    .fill("2026-10-02");
  await payment
    .getByLabel("Actual external payment date", { exact: true })
    .fill("2026-10-02");
  await payment.getByLabel("Payment amount", { exact: true }).fill("70.00");
  await choose(
    payment.getByRole("combobox", {
      name: "Cash or bank account",
      exact: true,
    }),
    /^1000/,
  );
  await payment
    .getByLabel("Source account alias", { exact: true })
    .fill("FAKE-CASH");
  await payment
    .getByLabel("External receipt or transaction reference", { exact: true })
    .fill(`FAKE-RECEIPT-${testInfo.project.name}`);
  await payment.getByLabel(/^Payment allocation /).fill("70.00");
  await payment.getByRole("checkbox").check();
  const confirmationKeys: string[] = [];
  let lostPayment = false;
  await page.route(
    "**/financial-documents/books/*/settlements/*/confirmations/*",
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      confirmationKeys.push(route.request().headers()["idempotency-key"]!);
      if (!lostPayment) {
        lostPayment = true;
        await route.fetch();
        await route.abort("failed");
      } else await route.continue();
    },
  );
  await payment
    .getByRole("button", { name: "Confirm external payment", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Financial command recovery" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Retry same financial command", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Financial command recovery" }),
  ).toHaveCount(0);
  expect(confirmationKeys).toHaveLength(2);
  expect(confirmationKeys[0]).toBe(confirmationKeys[1]);
  await page.unrouteAll({ behavior: "wait" });
  const settlement = page.getByRole("region", {
    name: "Settlement detail",
    exact: true,
  });
  await expect(settlement).toContainText("confirmed 70.00, reserved 30.00");
  await settlement
    .getByRole("button", { name: /^View payment / })
    .last()
    .click();
  await expect(
    page.getByRole("region", { name: "External payment detail" }),
  ).toContainText("Manually attested");
  await page
    .getByRole("button", { name: "Correct payment confirmation", exact: true })
    .click();
  const correction = page.getByRole("form", {
    name: "Correct erroneous confirmation",
    exact: true,
  });
  await correction.getByLabel("Payment amount", { exact: true }).fill("60.00");
  await correction.getByLabel(/^Payment allocation /).fill("60.00");
  await correction
    .getByLabel("Payment posting date", { exact: true })
    .fill("2026-10-03");
  await correction
    .getByLabel("Payment correction reason", { exact: true })
    .fill("FAKE corrected amount");
  await correction
    .getByLabel("Payment correction evidence source", { exact: true })
    .fill("FAKE correction reference");
  await correction.getByRole("checkbox").check();
  await correction
    .getByRole("button", { name: "Record payment correction", exact: true })
    .click();
  await expect(settlement).toContainText("confirmed 60.00, reserved 40.00");
  await settlement
    .getByRole("button", { name: /^View payment / })
    .last()
    .click();
  await page
    .getByRole("button", { name: "Correct payment confirmation", exact: true })
    .click();
  await correction.getByLabel("Payment amount", { exact: true }).fill("70.00");
  await correction.getByLabel(/^Payment allocation /).fill("70.00");
  await correction
    .getByLabel("Payment posting date", { exact: true })
    .fill("2026-10-04");
  await correction
    .getByLabel("Payment correction reason", { exact: true })
    .fill("FAKE second correction");
  await correction
    .getByLabel("Payment correction evidence source", { exact: true })
    .fill("FAKE corrected source");
  await correction.getByRole("checkbox").check();
  await correction
    .getByRole("button", { name: "Record payment correction", exact: true })
    .click();
  await expect(settlement).toContainText("confirmed 70.00, reserved 30.00");
  const release = page.getByRole("form", {
    name: "Release remaining reserve",
    exact: true,
  });
  await release
    .getByRole("button", { name: "Release reserve", exact: true })
    .click();
  await expect(settlement).toContainText("reserved 0.00");
  await invoiceRow
    .getByRole("button", { name: "Create credit", exact: true })
    .click();
  const credit = page.getByRole("form", {
    name: "New credit note",
    exact: true,
  });
  await credit.getByLabel("Credit date", { exact: true }).fill("2026-10-05");
  await credit
    .getByLabel("Credit title", { exact: true })
    .fill("FAKE partial credit");
  await credit
    .getByLabel("Credit number", { exact: true })
    .fill(`FAKE-CN-${testInfo.project.name}`);
  await credit
    .getByLabel("Credit line 1 amount", { exact: true })
    .fill("50.00");
  await credit
    .getByRole("combobox", { name: "Credit counterparty version", exact: true })
    .selectOption("1");
  await expect(
    credit.getByRole("combobox", {
      name: "Credit line 1 counter account",
      exact: true,
    }),
  ).toHaveValue("");
  // Counter-account is selected explicitly rather than inferred from the invoice.
  await choose(
    credit.getByRole("combobox", {
      name: "Credit line 1 counter account",
      exact: true,
    }),
    /^4100/,
  );
  await credit
    .getByRole("button", { name: "Save credit draft", exact: true })
    .click();
  const issueCredit = page.getByRole("form", {
    name: "Issue saved draft",
    exact: true,
  });
  await issueCredit
    .getByLabel("Posting date", { exact: true })
    .fill("2026-10-05");
  await choose(
    issueCredit.getByRole("combobox", {
      name: "Refund control account",
      exact: true,
    }),
    /^2100/,
  );
  await issueCredit.getByRole("checkbox").check();
  await issueCredit
    .getByRole("button", { name: "Issue document", exact: true })
    .click();
  const creditDetail = page.getByRole("region", {
    name: "Credit note detail",
    exact: true,
  });
  await expect(creditDetail).toContainText(
    "Applied unpaid credit: 30.00; separate refund: 20.00",
  );
  const voidCredit = page.getByRole("form", {
    name: "Void erroneous credit",
    exact: true,
  });
  await voidCredit
    .getByLabel("Credit void posting date", { exact: true })
    .fill("2026-10-06");
  await voidCredit
    .getByLabel("Credit void reason", { exact: true })
    .fill("FAKE erroneous credit");
  await voidCredit
    .getByLabel("Credit void evidence source", { exact: true })
    .fill("FAKE review evidence");
  await voidCredit.getByRole("checkbox").check();
  await voidCredit
    .getByRole("button", { name: "Void credit", exact: true })
    .click();
  await expect(creditDetail).toContainText("voided");
  await expect(creditDetail).toContainText("untouched refund claim cancelled");
  await expect(creditDetail).not.toContainText("can be settled");
  // A later credit creates a new refund claim. Settle that claim through the
  // same real UI, then verify the original credit cannot fake an undo of cash.
  await page
    .getByRole("button", { name: "Obligations and settlements", exact: true })
    .click();
  await invoiceRow
    .getByRole("button", { name: "Create credit", exact: true })
    .click();
  await credit.getByLabel("Credit date", { exact: true }).fill("2026-10-07");
  await credit
    .getByLabel("Credit title", { exact: true })
    .fill("FAKE refundable credit");
  const paidCreditNumber = `FAKE-REFUND-${testInfo.project.name}`;
  await credit
    .getByLabel("Credit number", { exact: true })
    .fill(paidCreditNumber);
  await credit
    .getByRole("combobox", { name: "Credit counterparty version", exact: true })
    .selectOption("1");
  await credit
    .getByLabel("Credit line 1 amount", { exact: true })
    .fill("50.00");
  await choose(
    credit.getByRole("combobox", {
      name: "Credit line 1 counter account",
      exact: true,
    }),
    /^4100/,
  );
  await credit
    .getByRole("button", { name: "Save credit draft", exact: true })
    .click();
  await issueCredit
    .getByLabel("Posting date", { exact: true })
    .fill("2026-10-07");
  await choose(
    issueCredit.getByRole("combobox", {
      name: "Refund control account",
      exact: true,
    }),
    /^2100/,
  );
  await issueCredit.getByRole("checkbox").check();
  await issueCredit
    .getByRole("button", { name: "Issue document", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Obligations and settlements", exact: true })
    .click();
  const refundRow = table
    .getByRole("row")
    .filter({ hasText: "credit refund" })
    .last();
  await refundRow
    .getByRole("button", { name: "Prepare settlement", exact: true })
    .click();
  await prepare.getByLabel(/available 20\.00 USD$/).fill("20.00");
  await prepare
    .getByRole("button", { name: "Prepare settlement", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Approve settlement", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Reserve settlement", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Record external payment", exact: true })
    .click();
  await payment
    .getByLabel("Payment posting date", { exact: true })
    .fill("2026-10-07");
  await payment
    .getByLabel("Actual external payment date", { exact: true })
    .fill("2026-10-07");
  await payment.getByLabel("Payment amount", { exact: true }).fill("20.00");
  await choose(
    payment.getByRole("combobox", {
      name: "Cash or bank account",
      exact: true,
    }),
    /^1000/,
  );
  await payment
    .getByLabel("Source account alias", { exact: true })
    .fill("FAKE-CASH");
  await payment
    .getByLabel("External receipt or transaction reference", { exact: true })
    .fill(`FAKE-REFUND-PAY-${testInfo.project.name}`);
  await payment.getByLabel(/^Payment allocation /).fill("20.00");
  await payment.getByRole("checkbox").check();
  await payment
    .getByRole("button", { name: "Confirm external payment", exact: true })
    .click();
  await expect(settlement).toContainText("confirmed 20.00, reserved 0.00");
  await page.getByRole("button", { name: "Credit notes", exact: true }).click();
  await page
    .getByRole("button", { name: new RegExp(paidCreditNumber) })
    .click();
  await voidCredit
    .getByLabel("Credit void posting date", { exact: true })
    .fill("2026-10-08");
  await voidCredit
    .getByLabel("Credit void reason", { exact: true })
    .fill("FAKE attempted error correction");
  await voidCredit
    .getByLabel("Credit void evidence source", { exact: true })
    .fill("FAKE after refund review");
  await voidCredit.getByRole("checkbox").check();
  await voidCredit
    .getByRole("button", { name: "Void credit", exact: true })
    .click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "FINANCIAL_RECONCILIATION_REQUIRED" }),
  ).toBeVisible();
  await expect(creditDetail).toContainText("issued");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  const layout = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(layout.width, JSON.stringify(layout)).toBeLessThanOrEqual(
    layout.viewport,
  );
  if (process.env.GBA_H4_SCREENSHOT_DIR)
    await page.screenshot({
      path: join(
        process.env.GBA_H4_SCREENSHOT_DIR,
        `${testInfo.project.name}-finance.png`,
      ),
      fullPage: true,
    });
});
