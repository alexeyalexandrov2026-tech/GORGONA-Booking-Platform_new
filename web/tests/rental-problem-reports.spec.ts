import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  business: string;
  booking: string;
  number: number;
  grant: string;
  revoked: string;
  companyName: string;
};

async function ringed(page: Page) {
  const focused = page.locator(":focus");
  await expect(focused).toHaveCount(1);
  await expect(focused).toBeVisible();
  const ring = await focused.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      what: element.outerHTML.slice(0, 90),
      shown: element.matches(":focus-visible"),
      style: style.outlineStyle,
      width: Number.parseFloat(style.outlineWidth),
    };
  });
  expect(ring.shown, `${ring.what} matches :focus-visible`).toBe(true);
  expect(ring.style, `${ring.what} has an outline`).not.toBe("none");
  expect(ring.width, `${ring.what} outline width`).toBeGreaterThan(0);
}

/** Press Tab until target is focused, checking the focus ring on every light-DOM stop. */
async function tabTo(page: Page, target: Locator, limit = 30) {
  for (let presses = 0; presses <= limit; presses += 1) {
    if (
      await target.evaluate((element) => element === document.activeElement)
    ) {
      await ringed(page);
      return;
    }
    await page.keyboard.press("Tab");
    const onShadowPicker = await page.evaluate(
      () =>
        document.activeElement instanceof HTMLInputElement &&
        (document.activeElement.type === "date" ||
          document.activeElement.type === "time") &&
        document.querySelectorAll(":focus").length === 0,
    );
    if (!onShadowPicker) await ringed(page);
  }
  throw new Error(`Tab did not reach ${String(target)} in ${limit} presses`);
}

async function atTheTop(page: Page) {
  await page.evaluate(() => {
    document.body.tabIndex = -1;
    document.body.focus();
    document.body.removeAttribute("tabindex");
    window.scrollTo(0, 0);
  });
}

test("staff record a phoned-in problem and the renter reports one through a live grant", async ({
  page,
  context,
}, testInfo) => {
  const entries = JSON.parse(process.env.GBA_RENTAL_PROBLEMS ?? "{}") as Record<
    string,
    Fixture
  >;
  const fixture = entries[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_r09_rental_problem_reports_browser.py.");
  const provider = process.env.GBA_TEST_OIDC_ISSUER;
  const link = (grant: string) =>
    `/rental/customer/problems/?${new URLSearchParams({
      business: fixture.business,
      booking: fixture.booking,
      grant,
    })}`;

  expect((await page.request.post(`${provider}/browser/user/owner`)).ok()).toBe(
    true,
  );
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Rental", exact: true }).click();
  await page
    .getByRole("table", { name: "Bookings", exact: true })
    .getByRole("button", { name: `Booking ${fixture.number}`, exact: true })
    .click();
  const reports = page.getByRole("region", {
    name: "Problem reports",
    exact: true,
  });
  await expect(reports.getByText("No problem reports yet.")).toBeVisible();
  const form = reports.getByRole("form", { name: "Record a problem report" });
  await form.getByLabel("Kind").selectOption("breakdown");
  await form.getByLabel("What happened").fill("FAKE flat tyre on the motorway");
  await form.getByLabel("Date").fill("2026-01-15");
  await form.getByLabel("Time").fill("09:30");
  await form.getByLabel("How it was reported").selectOption("phone");
  await form.getByLabel("Reporter name").fill("FAKE Renter Ivan");
  await form.getByRole("button", { name: "Record problem report" }).click();
  await expect(form.getByRole("status")).toHaveText(
    "Problem report 1 recorded.",
  );
  const table = reports.getByRole("table", {
    name: "Problem reports",
    exact: true,
  });
  await expect(table).toContainText("FAKE flat tyre on the motorway");
  await expect(table).toContainText("FAKE Renter Ivan by phone");
  await expect(table).toContainText("Breakdown");

  const access = page.getByRole("region", { name: "Customer proposal access" });
  await access.getByRole("button", { name: "Manage customer access" }).click();
  await access.getByLabel("Active rental grant").selectOption(fixture.grant);
  await access.getByRole("button", { name: "Prepare proposal link" }).click();
  await expect(
    access.getByRole("link", { name: "Problem report link", exact: true }),
  ).toHaveAttribute("href", link(fixture.grant));

  const customer = await context.newPage();
  expect(
    (await customer.request.post(`${provider}/browser/user/customer`)).ok(),
  ).toBe(true);
  const signIn = customer.getByRole("button", { name: "Sign in", exact: true });
  const main = customer.getByRole("main");
  await customer.goto(link(fixture.grant));
  await expect(signIn).toBeVisible();
  await atTheTop(customer);
  await tabTo(customer, signIn);
  await customer.keyboard.press("Enter");
  await expect(main.getByText("No problem reports yet.")).toBeVisible();
  await expect(main.getByText("FAKE flat tyre on the motorway")).toHaveCount(0);
  expect(
    await customer.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const audit = await new AxeBuilder({ page: customer })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(audit.violations).toEqual([]);

  const attempts: { key: string; body: unknown }[] = [];
  await customer.route(
    `**/customer-problems/${fixture.grant}`,
    async (route) => {
      const request = route.request();
      if (request.method() !== "POST") return route.continue();
      attempts.push({
        key: request.headers()["idempotency-key"] ?? "",
        body: request.postDataJSON() as unknown,
      });
      if (attempts.length === 1) {
        expect((await route.fetch()).ok()).toBe(true);
        return route.abort();
      }
      return route.continue();
    },
  );
  const report = main.getByRole("form", { name: "Report a problem" });
  const kind = report.getByLabel("Kind");
  const description = report.getByLabel("What happened");
  const date = report.getByLabel("Date");
  const time = report.getByLabel("Time");
  const send = report.getByRole("button", { name: "Send problem report" });
  await atTheTop(customer);
  await tabTo(customer, kind);
  await customer.keyboard.type("Damage");
  await expect(kind.locator("option:checked")).toHaveText("Damage");
  await tabTo(customer, description);
  await customer.keyboard.type("FAKE cracked side mirror");
  await tabTo(customer, date);
  await date.fill("2026-01-16");
  await tabTo(customer, time);
  await time.fill("10:00");
  await tabTo(customer, send);
  await customer.keyboard.press("Enter");
  await expect(main.getByRole("alert")).toContainText(
    "could not confirm your report",
  );
  await expect(description).toBeDisabled();
  const retry = report.getByRole("button", { name: "Retry problem report" });
  await atTheTop(customer);
  await tabTo(customer, retry);
  await customer.keyboard.press("Enter");
  const sent = main
    .getByRole("status")
    .filter({ hasText: "Problem report 2 sent." });
  await expect(sent).toBeFocused();
  expect(attempts).toHaveLength(2);
  expect(attempts[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
  expect(attempts[1]).toEqual(attempts[0]);
  const mine = main.getByRole("list", { name: "Your problem reports" });
  await expect(mine).toContainText("FAKE cracked side mirror");
  await expect(mine).toContainText("Report 2: Damage");

  // Staff reloads problem reports and sees the customer company name for the platform report.
  await reports.getByRole("button", { name: "Reload problem reports" }).click();
  await expect(table).toContainText("FAKE cracked side mirror");
  await expect(table).toContainText(`${fixture.companyName} on the platform`);

  await customer.reload();
  await signIn.click();
  await expect(mine).toContainText("FAKE cracked side mirror");
  await expect(main.getByText("FAKE flat tyre on the motorway")).toHaveCount(0);

  await customer.goto(link(fixture.revoked));
  await signIn.click();
  await expect(main.getByRole("alert")).toHaveText(
    "Problem reports are unavailable for your account.",
  );
  await expect(report).toHaveCount(0);
});
