import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  business: string;
  project: string;
  grant: string;
  revoked: string;
};

test("signs in from a proposal link, retries acceptance safely, and rejects a revoked grant", async ({
  page,
}, testInfo) => {
  const fixtures = JSON.parse(
    process.env.GBA_CUSTOMER_PROPOSALS ?? "{}",
  ) as Record<string, Fixture>;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_o9_customer_proposal_browser.py.");
  const link = (grant: string) =>
    `/construction/customer/?${new URLSearchParams({ business: fixture.business, project: fixture.project, grant })}`;

  await page.goto(link(fixture.grant));
  const proposalPage = page.getByRole("main");
  const signIn = page.getByRole("button", { name: "Sign in", exact: true });
  await expect(signIn).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(signIn).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "FAKE customer scope" }),
  ).toBeVisible();
  expect(new URL(page.url()).searchParams.get("grant")).toBe(fixture.grant);
  await expect(proposalPage).toContainText("USD 250.00");
  await expect(proposalPage).not.toContainText("150.00");
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(audit.violations).toEqual([]);

  const keys: string[] = [];
  await page.route(`**/customer-proposal/${fixture.grant}`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    keys.push(route.request().headers()["idempotency-key"] ?? "");
    if (keys.length === 1) {
      expect((await route.fetch()).ok()).toBe(true);
      return route.abort();
    }
    return route.continue();
  });

  const signatory = page.getByRole("textbox", { name: "Signatory name" });
  await signatory.focus();
  await page.keyboard.type("FAKE signing delegate");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("textbox", { name: "Note (optional)" }),
  ).toBeFocused();
  await page.keyboard.type("FAKE scope reviewed");
  await page.keyboard.press("Tab");
  const accept = page.getByRole("button", { name: "Accept proposal" });
  await expect(accept).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(proposalPage.getByRole("alert")).toContainText(
    "could not confirm your acceptance",
  );
  await accept.press("Enter");
  const accepted = page
    .getByRole("status")
    .filter({ hasText: "Proposal accepted." });
  await expect(accepted).toBeFocused();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
  expect(keys[1]).toBe(keys[0]);

  await page.goto(link(fixture.revoked));
  await signIn.click();
  await expect(proposalPage.getByRole("alert")).toContainText(
    "This proposal is unavailable for your account",
  );
  await expect(page.getByText("FAKE customer scope")).toHaveCount(0);
  await expect(accept).toHaveCount(0);
});
