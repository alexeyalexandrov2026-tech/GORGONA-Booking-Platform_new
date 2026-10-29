import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

// N6 (package N): an owner records the broker authority and a carrier's profile, tenders a leg to
// cover, records the carrier's acceptance, agrees a changed rate confirmation version, accrues the
// carrier's pay and reads the order's margin. FAKE data only.
const book = process.env.GBA_N6_BOOK!;
const expense = process.env.GBA_N6_EXPENSE!;
const payable = process.env.GBA_N6_PAYABLE!;

const screen = (page: Page) => page.locator(".transport-screen");
const statusOf = (page: Page) =>
  screen(page).locator(".transport-status[role=status]");
const section = (page: Page, name: string) =>
  screen(page)
    .locator("section")
    .filter({ has: page.getByRole("heading", { name, exact: true }) });

async function signIn(page: Page) {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText("FAKE user n6-owner", {
      exact: true,
    }),
  ).toBeVisible();
}

async function check(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".transport-screen")
    .analyze();
  expect(axe.violations).toEqual([]);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
}

test("an owner covers a leg through a carrier and sees the order margin", async ({
  page,
}, testInfo) => {
  const p = testInfo.project.name as "desktop" | "mobile";
  const carrier = `FAKE Carrier ${p}`;
  await signIn(page);
  await page.getByRole("link", { name: "Transport", exact: true }).click();
  await expect(page.getByText("Loading the trips…")).toBeHidden();

  // N6-01: the broker authority, saved as a new version; today's eligibility in words.
  const authority = section(page, "Broker authority");
  const form = authority.getByRole("form", { name: "Broker authority form" });
  await form.getByLabel("Authority number").fill(`MC-FAKE-${p}`);
  await form.getByLabel("Bond reference").fill(`BMC84-FAKE-${p}`);
  await form.getByLabel("Effective from").fill("2026-01-01");
  await form.getByLabel("Fact source").fill("fmcsa");
  await form.getByRole("button", { name: "Save authority" }).click();
  await expect(statusOf(page)).toHaveText("Broker authority saved.");
  await expect(authority).toContainText(`US MC-FAKE-${p}`);
  await expect(authority).toContainText("May tender loads today.");

  // N6-04: a carrier without a profile is refused in words; the form keeps what was entered.
  const carriers = section(page, "Carriers");
  const row = carriers.getByRole("row").filter({ hasText: carrier });
  await expect(row).toContainText(
    "Not eligible: no carrier profile is recorded.",
  );
  const board = section(page, "Loads to cover");
  await board
    .getByRole("button", { name: `Tender FAKE-TR-${p} leg 1`, exact: true })
    .click();
  let tender = board.getByRole("form", { name: "Tender" });
  await tender
    .getByLabel("Carrier")
    .selectOption({ label: `${carrier} (not eligible)` });
  await tender.getByLabel("Amount").fill("900.00");
  await tender.getByLabel("Terms").fill("FAKE terms");
  await tender.getByLabel("Offer expires").fill("2031-01-01T12:00");
  await tender.getByRole("button", { name: "Send tender" }).click();
  await expect(tender.getByRole("alert")).toContainText(
    "may not be tendered to",
  );
  await expect(tender.getByLabel("Amount")).toHaveValue("900.00");
  await tender.getByRole("button", { name: "Cancel" }).click();

  // N6-01: the carrier's profile makes it eligible.
  await row.getByRole("button", { name: `Profile for ${carrier}` }).click();
  const profile = carriers.getByRole("form", { name: `Profile of ${carrier}` });
  await profile.getByLabel("Authority number").fill(`MC-FAKE-C-${p}`);
  await profile.getByLabel("Liability insurance expires").fill("2032-01-01");
  await profile.getByLabel("Cargo insurance expires").fill("2032-01-01");
  await profile
    .getByLabel("Safety rating")
    .selectOption({ label: "Satisfactory" });
  await profile.getByLabel("Fact source").fill("fmcsa");
  await profile.getByRole("button", { name: "Save profile" }).click();
  await expect(statusOf(page)).toHaveText("Carrier profile saved.");
  await expect(row).toContainText("Eligible");
  await expect(row).toContainText("satisfactory (version 1)");
  await check(page, testInfo, "carriers");

  // N6-02: the leg is tendered and accepted; the board no longer lists it.
  await board
    .getByRole("button", { name: `Tender FAKE-TR-${p} leg 1`, exact: true })
    .click();
  tender = board.getByRole("form", { name: "Tender" });
  await tender.getByLabel("Carrier").selectOption({ label: carrier });
  await tender.getByLabel("Amount").fill("900.00");
  await tender.getByLabel("Terms").fill("FAKE terms");
  await tender.getByLabel("Offer expires").fill("2031-01-01T12:00");
  await tender.getByRole("button", { name: "Send tender" }).click();
  await expect(statusOf(page)).toHaveText("Tender sent.");
  const panel = board.getByRole("region", {
    name: `Tender to ${carrier} for FAKE-TR-${p} leg 1`,
  });
  await expect(panel).toContainText("Offered · 900.00 USD fixed");
  const answer = panel.getByRole("form", { name: "Carrier answer" });
  await answer.getByLabel("Answer").selectOption({ label: "Accepted" });
  await answer.getByLabel("Source").selectOption({ label: "Phone" });
  await answer.getByRole("button", { name: "Record answer" }).click();
  await expect(statusOf(page)).toHaveText("Answer recorded.");
  await expect(panel).toContainText("Accepted · 900.00 USD fixed");
  await expect(
    board.getByRole("button", {
      name: `Tender FAKE-TR-${p} leg 1`,
      exact: true,
    }),
  ).toHaveCount(0);

  // N6-03: a changed version is proposed and agreed; the old version stays.
  await expect(panel).toContainText("In force: version 1, 900.00 USD fixed");
  const proposal = panel.getByRole("form", { name: "New version" });
  await proposal.getByLabel("Amount").fill("950.00");
  await proposal.getByLabel("Terms").fill("FAKE terms with detention");
  await proposal.getByRole("button", { name: "Propose version" }).click();
  await expect(statusOf(page)).toHaveText("Version proposed.");
  const agree = panel.getByRole("form", { name: "Answer to version 2" });
  await agree.getByLabel("Answer").selectOption({ label: "Agreed" });
  await agree.getByRole("button", { name: "Record version answer" }).click();
  await expect(statusOf(page)).toHaveText("Version answer recorded.");
  await expect(panel).toContainText("In force: version 2, 950.00 USD fixed");
  const versions = panel.getByRole("table", {
    name: "Rate confirmation versions",
  });
  await expect(versions.getByRole("row")).toHaveCount(3);
  await check(page, testInfo, "tender");

  // N6-04: the carrier's pay on the closed leg, for the version in force.
  const accrue = panel.getByRole("form", { name: "Accrue carrier pay" });
  await accrue.getByLabel("Book").selectOption({ label: book });
  await accrue.getByLabel("Expense account").selectOption({ label: expense });
  await accrue.getByLabel("Payable account").selectOption({ label: payable });
  await accrue.getByLabel("Number").fill(`FAKE-CP-${p}`);
  await accrue.getByRole("button", { name: "Accrue carrier pay" }).click();
  await expect(statusOf(page)).toHaveText("Carrier pay accrued.");
  await expect(panel).toContainText(
    "Carrier pay 950.00 USD for version 2, open 950.00",
  );

  // N6-04: the order's margin, derived by the server.
  await page.getByRole("button", { name: `Money for FAKE-SO-${p}` }).click();
  const margin = page.getByRole("region", { name: `Margin for FAKE-SO-${p}` });
  await expect(margin).toContainText("Revenue1500.00 USD");
  await expect(margin).toContainText("Carrier cost950.00 USD");
  await expect(margin).toContainText("Margin550.00 USD");
  await check(page, testInfo, "margin");
});
