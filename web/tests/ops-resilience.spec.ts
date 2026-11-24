import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

async function checkAccessibilityAndLayout(page: Page) {
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(axe.violations).toEqual([]);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth + 1,
  );
  expect(overflow).toBe(true);
}

test("OPS-03: mobile/desktop layout, keyboard traversal, 503 outage, 409 offline conflict and recovery", async ({
  page,
}, testInfo) => {
  test.setTimeout(180000);
  const pageErrors: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await checkAccessibilityAndLayout(page);

  // 1. Keyboard traversal: Tab moves focus across interactive controls without trapping
  const focusedTags: string[] = [];
  for (let i = 0; i < 6; i += 1) {
    await page.keyboard.press("Tab");
    const tag = await page.evaluate(
      () => document.activeElement?.tagName.toLowerCase() ?? "none",
    );
    focusedTags.push(tag);
  }
  expect(focusedTags.some((t) => t === "a" || t === "button")).toBe(true);

  // 2. Navigate client-side (preserving in-memory OIDC session) to Counterparties
  await page.getByRole("link", { name: "Counterparties", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Counterparties", exact: true }),
  ).toBeVisible();
  await checkAccessibilityAndLayout(page);

  // 3. Simulate provider/backend 503 outage -> visible accessible alert -> retry -> saved
  const card = page.getByRole("region", {
    name: "Counterparty card",
    exact: true,
  });
  const suffix = testInfo.project.name === "mobile" ? "Mobile" : "Desktop";
  const clientName = `FAKE OPS03 ${suffix} Client`;
  await card.getByLabel("Display name", { exact: true }).fill(clientName);
  await card.getByLabel("customer", { exact: true }).check();
  await card
    .getByRole("button", { name: "Review and save card", exact: true })
    .click();

  const pattern = "**/v1/businesses/*/counterparties/*";
  let mode: "outage503" | "conflict409" | "pass" = "outage503";
  await page.route(pattern, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    if (mode === "outage503") {
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "PROVIDER_UNAVAILABLE",
            message: "Upstream provider temporarily unavailable.",
          },
        }),
      });
    }
    if (mode === "conflict409") {
      return route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "REVISION_CONFLICT",
            message: "This record changed offline. Reload before saving.",
          },
        }),
      });
    }
    return route.continue();
  });

  // 3a. Trigger 503 outage -> accessible alert rendered, no silent success
  await page
    .getByRole("button", { name: "Confirm counterparty action", exact: true })
    .click();
  const alert = page.locator("main").getByRole("alert").first();
  await expect(alert).toBeVisible();
  await checkAccessibilityAndLayout(page);

  // 3b. Clear outage and retry -> succeeds cleanly against real PG18 API
  mode = "pass";
  const retryBtn = page.getByRole("button", {
    name: "Retry same counterparty command",
    exact: true,
  });
  if (await retryBtn.isVisible()) {
    await retryBtn.click();
  } else {
    const reviewBtn = card.getByRole("button", {
      name: "Review and save card",
      exact: true,
    });
    if (await reviewBtn.isVisible()) {
      await reviewBtn.click();
    }
    await page
      .getByRole("button", { name: "Confirm counterparty action", exact: true })
      .click();
  }
  await expect(page.getByRole("status")).toHaveText("Counterparty saved.");
  await expect(card).toContainText("Version 1 · active");
  await checkAccessibilityAndLayout(page);

  // 4. Simulate 409 offline revision conflict on subsequent edit -> honest alert, no false save
  mode = "conflict409";
  await card
    .getByLabel("Display name", { exact: true })
    .fill(`${clientName} Conflict`);
  await card
    .getByRole("button", { name: "Review and save card", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm counterparty action", exact: true })
    .click();
  await expect(alert).toBeVisible();
  await expect(alert).toContainText(/changed offline|Reload/i);
  await checkAccessibilityAndLayout(page);
  await page.unroute(pattern);

  // 5. Client-side audit of stage 6-8 routes on both desktop and 390px mobile with active session
  for (const href of [
    "/supply/",
    "/marketplace/",
    "/enterprise/",
    "/specialized/",
  ]) {
    const link = page.locator(`a[href="${href}"]`).first();
    if (await link.isVisible()) {
      await link.click();
      await expect(page).toHaveURL(
        new RegExp(`${href.replace(/\//g, "\\/")}$`),
      );
      await expect(page).toHaveTitle(/.+/);
      await expect(page.locator("main")).toBeVisible();
      await checkAccessibilityAndLayout(page);
    }
  }

  expect(pageErrors).toEqual([]);
});
