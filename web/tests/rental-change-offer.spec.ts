import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  business: string;
  booking: string;
  number: number;
  grant: string;
  revoked: string;
};

test("manager offers an extension and the renter accepts through a live grant", async ({
  page,
  context,
}, testInfo) => {
  const entries = JSON.parse(
    process.env.GBA_RENTAL_CHANGE_OFFERS ?? "{}",
  ) as Record<string, Fixture>;
  const fixture = entries[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_r09_rental_change_offer_browser.py.");
  const provider = process.env.GBA_TEST_OIDC_ISSUER;
  const link = (revision: number, grant = fixture.grant) =>
    `/rental/customer/change/?${new URLSearchParams({
      business: fixture.business,
      booking: fixture.booking,
      revision: String(revision),
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
  const access = page.getByRole("region", { name: "Customer proposal access" });
  await access.getByRole("button", { name: "Manage customer access" }).click();
  await access
    .getByRole("button", { name: "Manage agreement changes" })
    .click();
  const panel = access.getByRole("region", { name: "Agreement change offer" });
  const form = panel.getByRole("form", { name: "Prepare agreement change" });
  await form.getByRole("spinbutton", { name: "FAKE seat" }).fill("1");
  await form
    .getByLabel("Reason shown to customer")
    .fill("FAKE add a child seat");
  const save = form.getByRole("button", { name: "Save change offer" });
  await save.click();
  await expect(panel.getByRole("status")).toHaveText("Change offer saved.");

  await form.getByRole("checkbox", { name: "Change rental period" }).check();
  await form.getByLabel("Return date").fill("2031-06-05");
  await form
    .getByLabel("Reason shown to customer")
    .fill("FAKE proposed extra day");
  await save.click();
  await expect(panel).toContainText("EUR 228.00");
  const select = panel.getByLabel("Grant for change offer");
  await select.selectOption(fixture.grant);
  const prepare = panel.getByRole("button", { name: "Prepare change link" });
  await prepare.click();
  const prepared = panel.getByRole("link", {
    name: "Rental change link",
    exact: true,
  });
  await expect(prepared).toHaveAttribute("href", link(2));

  const customer = await context.newPage();
  expect(
    (await customer.request.post(`${provider}/browser/user/customer`)).ok(),
  ).toBe(true);
  const signIn = customer.getByRole("button", { name: "Sign in", exact: true });
  const main = customer.getByRole("main");
  const accept = main.getByRole("button", {
    name: "Accept change",
    exact: true,
  });
  const signatory = main.getByRole("textbox", { name: "Signatory name" });
  await customer.goto(link(1));
  await signIn.click();
  await expect(main.getByRole("alert")).toContainText(
    "This offer is out of date.",
  );
  await expect(accept).toHaveCount(0);

  await customer.goto(link(2));
  await signIn.click();
  await expect(main).toContainText("EUR 228.00");
  await signatory.fill("FAKE change delegate");
  await accept.click();
  await expect(main.getByRole("alert")).toContainText(
    "The proposed period is no longer available.",
  );
  await expect(accept).toHaveCount(0);

  await form.getByLabel("Return date").fill("2031-06-04");
  await form
    .getByLabel("Reason shown to customer")
    .fill("FAKE corrected extension");
  await save.click();
  await expect(panel).toContainText("EUR 171.00");
  await select.selectOption(fixture.grant);
  await prepare.click();
  await expect(prepared).toHaveAttribute("href", link(3));

  await customer.goto(link(3));
  await expect(signIn).toBeVisible();
  await customer.keyboard.press("Tab");
  await expect(signIn).toBeFocused();
  await customer.keyboard.press("Enter");
  await expect(main).toContainText("EUR 171.00");
  await expect(main).toContainText("FAKE seat × 1");
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
    `**/customer-changes/3/${fixture.grant}`,
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
  await signatory.fill("FAKE change delegate");
  await customer.keyboard.press("Tab");
  await expect(accept).toBeFocused();
  await customer.keyboard.press("Enter");
  await expect(main.getByRole("alert")).toContainText(
    "could not confirm your answer",
  );
  await expect(signatory).toBeDisabled();
  await main.getByRole("button", { name: "Retry acceptance" }).press("Enter");
  const receipt = main
    .getByRole("status")
    .filter({ hasText: "Agreement change accepted." });
  await expect(receipt).toBeFocused();
  await expect(main).toContainText("Agreement version 2");
  expect(attempts).toHaveLength(2);
  expect(attempts[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
  expect(attempts[1]).toEqual(attempts[0]);

  await customer.reload();
  await signIn.click();
  await expect(receipt).toBeVisible();
  await customer.goto(link(3, fixture.revoked));
  await signIn.click();
  await expect(main.getByRole("alert")).toHaveText(
    "This rental change is unavailable for your account.",
  );
  await expect(receipt).toHaveCount(0);
});
