import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  business: string;
  company: string;
  booking: string;
  number: number;
  grant: string;
  revoked: string;
};

test("prepares the rental link, replays a lost reply and shows the stored receipt", async ({
  context,
  page,
}, testInfo) => {
  const fixtures = JSON.parse(
    process.env.GBA_RENTAL_PROPOSALS ?? "{}",
  ) as Record<string, Fixture>;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_r09_rental_proposal_browser.py.");
  const provider = process.env.GBA_TEST_OIDC_ISSUER;
  const link = (grant: string) =>
    `/rental/customer/?${new URLSearchParams({ business: fixture.business, booking: fixture.booking, grant })}`;

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
    .getByRole("textbox", { name: "Customer business ID" })
    .fill(fixture.company);
  await access.getByRole("button", { name: "Save customer company" }).click();
  await expect(access.getByRole("status")).toHaveText(
    "Customer company saved.",
  );
  await access.getByLabel("Active rental grant").selectOption(fixture.grant);
  await access.getByRole("button", { name: "Prepare proposal link" }).click();
  const prepared = access.getByRole("link", { name: "Rental proposal link" });
  await expect(prepared).toHaveAttribute("href", link(fixture.grant));

  const customer = await context.newPage();
  expect(
    (await customer.request.post(`${provider}/browser/user/customer`)).ok(),
  ).toBe(true);
  await customer.goto(link(fixture.grant));
  const signIn = customer.getByRole("button", { name: "Sign in", exact: true });
  await expect(signIn).toBeVisible();
  await customer.keyboard.press("Tab");
  await expect(signIn).toBeFocused();
  await customer.keyboard.press("Enter");
  const main = customer.getByRole("main");
  await expect(main).toContainText("EUR 100.00");
  await expect(main.getByText("Pickup", { exact: true })).toBeVisible();
  await expect(main.getByText("Return", { exact: true })).toBeVisible();
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
    `**/customer-proposal/${fixture.grant}`,
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

  const signatory = main.getByRole("textbox", { name: "Signatory name" });
  await signatory.fill("FAKE rental delegate");
  await customer.keyboard.press("Tab");
  const accept = main.getByRole("button", {
    name: "Accept proposal",
    exact: true,
  });
  await expect(accept).toBeFocused();
  await customer.keyboard.press("Enter");
  await expect(main.getByRole("alert")).toContainText(
    "could not confirm your acceptance",
  );
  await expect(signatory).toBeDisabled();
  await main.getByRole("button", { name: "Retry acceptance" }).press("Enter");
  const accepted = main
    .getByRole("status")
    .filter({ hasText: "Proposal accepted." });
  await expect(accepted).toBeFocused();
  expect(attempts).toHaveLength(2);
  expect(attempts[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
  expect(attempts[1]).toEqual(attempts[0]);

  await customer.reload();
  await signIn.click();
  await expect(accepted).toBeVisible();

  await customer.goto(link(fixture.revoked));
  await signIn.click();
  await expect(main.getByRole("alert")).toHaveText(
    "This proposal is unavailable for your account.",
  );
  await expect(main.getByText("EUR 100.00")).toHaveCount(0);
  await expect(accept).toHaveCount(0);
});
