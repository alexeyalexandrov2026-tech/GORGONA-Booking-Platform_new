import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
test.describe.configure({ mode: "serial" });

const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const OWNER_NAME = "FAKE user mkt-ui-owner";

async function signIn(page: Page) {
  const switched = await page.request.post(`${issuer}/fixture/user/owner`);
  expect(switched.ok()).toBe(true);
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(OWNER_NAME, { exact: true }),
  ).toBeVisible();
}

async function openMarketplace(page: Page) {
  await page.getByRole("link", { name: "Marketplace", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Storefronts & Client-Operated Marketplaces",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole("tabpanel")).toBeVisible();
}

async function checkA11yAndViewport(page: Page, testInfo: TestInfo) {
  const axe = await new AxeBuilder({ page }).include("main").analyze();
  expect(axe.violations).toEqual([]);
  if (testInfo.project.name === "mobile") {
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    );
    expect(overflow).toBe(false);
  }
}

test("end-to-end strict storefront projection, zero-commission marketplace revocation, and isolated multi-seller basket split", async ({
  page,
}, testInfo) => {
  const tag = testInfo.project.name.toUpperCase();
  const low = testInfo.project.name.toLowerCase();
  const sfAlpha = `alpha-${low}`;
  const sfBeta = `beta-${low}`;
  const skuAlpha = `ALPHA-${tag}`;
  const skuDraft = `DRAFT-${tag}`;
  const skuBeta = `BETA-${tag}`;
  const mpSlug = `hub-${low}`;
  const sellerSlug = `studio-${low}`;

  await signIn(page);
  await openMarketplace(page);
  await checkA11yAndViewport(page, testInfo);

  // 1. Create Seller Alpha & Seller Beta Storefronts
  await page
    .getByLabel(/^Seller legal entity/)
    .selectOption({ label: "MKT_SELLER_A — Seller Alpha LLC" });
  await page.getByLabel(/^Storefront slug/).fill(sfAlpha);
  await page.getByLabel(/^Storefront display name/).fill(`Alpha Shop ${tag}`);
  await page
    .getByRole("button", { name: "Save storefront", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved storefront ${sfAlpha}`,
  );

  await page
    .getByLabel(/^Seller legal entity/)
    .selectOption({ label: "MKT_SELLER_B — Seller Beta LLC" });
  await page.getByLabel(/^Storefront slug/).fill(sfBeta);
  await page.getByLabel(/^Storefront display name/).fill(`Beta Shop ${tag}`);
  await page
    .getByRole("button", { name: "Save storefront", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved storefront ${sfBeta}`,
  );

  // 2. Create published & draft listings for Alpha, plus published listing for Beta
  await page
    .getByLabel(/^Listing storefront/)
    .selectOption({ label: `${sfAlpha} — Alpha Shop ${tag}` });
  await page.getByLabel(/^Listing SKU/).fill(skuAlpha);
  await page.getByLabel(/^Listing title/).fill(`Alpha Motor ${tag}`);
  await page.getByLabel(/^Price minor/).fill("20000");
  await page.getByLabel(/^Available quantity/).fill("10");
  await page.getByLabel(/^Moderation status/).selectOption("published");
  await page.getByRole("button", { name: "Save listing", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Saved listing ${skuAlpha} (published)`,
  );

  await page
    .getByLabel(/^Listing storefront/)
    .selectOption({ label: `${sfAlpha} — Alpha Shop ${tag}` });
  await page.getByLabel(/^Listing SKU/).fill(skuDraft);
  await page.getByLabel(/^Listing title/).fill(`Secret Draft ${tag}`);
  await page.getByLabel(/^Moderation status/).selectOption("draft");
  await page.getByRole("button", { name: "Save listing", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Saved listing ${skuDraft} (draft)`,
  );

  await page
    .getByLabel(/^Listing storefront/)
    .selectOption({ label: `${sfBeta} — Beta Shop ${tag}` });
  await page.getByLabel(/^Listing SKU/).fill(skuBeta);
  await page.getByLabel(/^Listing title/).fill(`Beta Sensor ${tag}`);
  await page.getByLabel(/^Price minor/).fill("15000");
  await page.getByLabel(/^Available quantity/).fill("10");
  await page.getByLabel(/^Moderation status/).selectOption("published");
  await page.getByRole("button", { name: "Save listing", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Saved listing ${skuBeta} (published)`,
  );

  // 3. Verify strict Public Catalog Projection: ONLY intersection [title, price, currency], NO private data/drafts
  await page.getByLabel(/^Preview storefront/).selectOption({ label: sfAlpha });
  await page
    .getByRole("button", { name: "Load public catalog", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Loaded public catalog for ${sfAlpha} (1 published listing(s))`,
  );
  const catalogText = await page.getByTestId("public-catalog-json").innerText();
  expect(catalogText).toContain(`Alpha Motor ${tag}`);
  expect(catalogText).not.toContain("SECRET MARGIN");
  expect(catalogText).not.toContain("8500");
  expect(catalogText).not.toContain(skuAlpha);
  expect(catalogText).not.toContain(`Secret Draft ${tag}`);
  expect(catalogText).not.toContain("Unselected internal description");

  // 4. Switch to Client-Operated Marketplaces via keyboard ArrowRight
  const sfTab = page.getByRole("tab", { name: "Storefronts & Publishing" });
  await sfTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Client-Operated Marketplaces" }),
  ).toHaveAttribute("aria-selected", "true");
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel(/^Marketplace slug/).fill(mpSlug);
  await page.getByLabel(/^Marketplace title/).fill(`Industrial Hub ${tag}`);
  await page.getByLabel(/^Operator commercial fee \(bps\)/).fill("300");
  await page
    .getByRole("button", { name: "Save marketplace", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved marketplace ${mpSlug} (AMARKAL commission 0 bps)`,
  );

  // Connect seller, revoke, then prove reactivation is rejected (MARKET_STATE_INVALID)
  await page.getByLabel(/^Seller storefront slug/).fill(sellerSlug);
  await page
    .getByRole("button", { name: "Connect seller", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Connected seller ${sellerSlug}`,
  );

  await page
    .getByRole("button", { name: `Revoke ${sellerSlug}`, exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Updated seller ${sellerSlug} status to revoked`,
  );

  await page
    .getByRole("button", {
      name: `Attempt reactivate ${sellerSlug}`,
      exact: true,
    })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "MARKET_STATE_INVALID",
  );

  // 5. Multi-Seller Checkout & Settlement tab
  await page
    .getByRole("tab", { name: "Multi-Seller Checkout & Settlement" })
    .click();
  await checkA11yAndViewport(page, testInfo);

  await page
    .getByLabel(/^Buyer counterparty/)
    .selectOption({ label: "Marketplace Buyer Corp" });
  await page
    .getByLabel(/^Checkout marketplace/)
    .selectOption({ label: mpSlug });
  await page
    .getByLabel(/^Seller fee counterparty/)
    .selectOption({ label: "Independent Seller Studio" });
  await page
    .getByLabel(/^Basket line 1 listing/)
    .selectOption({ label: `${skuAlpha} — Alpha Motor ${tag}` });
  await page.getByLabel(/^Basket line 1 quantity/).fill("2");
  await page
    .getByLabel(/^Line 1 seller book/)
    .selectOption({ label: "MKT_SELLER_A — USD" });
  await page
    .getByLabel(/^Basket line 2 listing/)
    .selectOption({ label: `${skuBeta} — Beta Sensor ${tag}` });
  await page.getByLabel(/^Basket line 2 quantity/).fill("1");

  // Negative proof: cannot commingle Beta's storefront into Alpha's book!
  await page
    .getByLabel(/^Line 2 seller book/)
    .selectOption({ label: "MKT_SELLER_A — USD" });
  await page
    .getByRole("button", { name: "Checkout multi-seller basket", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "INVALID_REFERENCE",
  );

  // Valid isolated multi-seller basket split -> 2 independent orders & FIN-03 invoices
  await page
    .getByLabel(/^Line 2 seller book/)
    .selectOption({ label: "MKT_SELLER_B — USD" });
  await page
    .getByRole("button", { name: "Checkout multi-seller basket", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Split multi-seller basket into 2 isolated single-seller order(s)",
  );

  // Partial refund ($100.00) on the newly created order -> FIN-03 credit note draft
  await page.getByLabel(/^Refund amount minor/).fill("10000");
  await page.getByLabel(/^Refund reason/).fill(`Partial refund ${tag}`);
  await page
    .getByRole("button", { name: "Post order refund", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "status partially_refunded",
  );
});
