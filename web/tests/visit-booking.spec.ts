import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { availabilitySchema } from "../lib/contracts";

// L7c (package L): a guest books a visit of several services and sees its stages.
// Run by api/tests/integration/test_l7c_customer_visit_browser.py against a real API and
// PostgreSQL; the database is read back there. Keyboard only: buttons are focused and pressed.

async function press(page: Page, name: string) {
  const button = page.getByRole("button", { name, exact: true });
  await button.focus();
  await page.keyboard.press("Enter");
}

async function noViolations(page: Page) {
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
}

async function noSideScroll(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}

async function chooseVisit(page: Page, second: string) {
  await page.goto("/book/");
  await expect(
    page.getByRole("heading", {
      name: "Your appointment, thoughtfully arranged.",
    }),
  ).toBeVisible({ timeout: 15000 });
  await page
    .getByLabel("Service and variant")
    .selectOption({ label: "FAKE FAKE_GEL · 110 min" });
  await press(page, "Add another service");
  await page.getByLabel("Service 2").selectOption({ label: second });
  await noViolations(page);
  await noSideScroll(page);
  await press(page, "Continue to times");
  const response = page.waitForResponse(
    (r) =>
      r.url().includes("/availability") &&
      r.request().postDataJSON().day === process.env.GBA_BROWSER_DAY,
  );
  await page.getByLabel("Date").fill(process.env.GBA_BROWSER_DAY ?? "");
  return await response;
}

test("a guest books a staged service and a second service, sees the stages and confirms", async ({
  page,
}) => {
  const answer = await chooseVisit(page, "FAKE style · 30 min");
  const sent = answer.request().postDataJSON() as {
    extra_lines: { variant_id: string; add_on_ids: string[] }[];
  };
  expect(sent.extra_lines).toHaveLength(1);
  const available = availabilitySchema.parse(await answer.json());
  expect(available.quote.version).toBe(2);
  await expect(page.getByRole("button", { name: /^\d/ }).first()).toBeVisible({
    timeout: 15000,
  });

  const summary = page.getByRole("complementary", { name: "Price summary" });
  await expect(summary).toContainText("FAKE FAKE_GEL");
  await expect(summary).toContainText("$65.00");
  await expect(summary).toContainText("FAKE style");
  await expect(summary).toContainText("$30.00");
  await expect(summary).toContainText("$95.00");
  await expect(summary).toContainText("140 minutes");
  await expect(
    summary.getByRole("list", { name: "Stages" }).getByRole("listitem"),
  ).toHaveText([
    "With your specialist · 30 min",
    "Processing — your specialist is free meanwhile · 60 min",
    "Finish · 20 min",
    "With your specialist · 30 min",
  ]);
  // Only the specialist who serves both services is offered (decision 50).
  await expect(
    page.getByRole("combobox", { name: /^Artist/ }).getByRole("option"),
  ).toHaveText(["Any available artist", "FAKE artist A1"]);
  await noViolations(page);
  await noSideScroll(page);

  await page.getByRole("button", { name: /^\d/ }).first().focus();
  await page.keyboard.press("Enter");
  await press(page, "Continue to details");
  await expect(
    page.getByRole("heading", { name: "A few personal details." }),
  ).toBeVisible({ timeout: 15000 });
  await page.getByLabel("Full name").fill("FAKE Visit Guest");
  await page.getByLabel("Email").fill("fake-visit@example.test");
  await page.getByLabel("Phone").fill("+1 555 010 4321");
  await page.getByLabel("I agree to the cancellation policy").focus();
  await page.keyboard.press("Space");
  await press(page, "Review appointment");
  await expect(
    page.getByRole("heading", { name: "One last look." }),
  ).toBeVisible();
  await expect(page.getByTestId("visit-services")).toHaveText(
    "FAKE FAKE_GEL, FAKE style",
  );
  await noViolations(page);
  await press(page, "Confirm booking");
  await expect(
    page.getByRole("heading", { name: "You’re booked." }),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId("visit-services")).toHaveText(
    "FAKE FAKE_GEL, FAKE style",
  );
  await expect(page.getByTestId("booking-reference")).toContainText(
    /[0-9a-f-]{36}/,
  );
  await noViolations(page);
  await noSideScroll(page);
  await page.screenshot({
    path: `test-results/visit-${page.viewportSize()?.width}.png`,
    fullPage: true,
  });
});

test("a visit the server refuses shows its plain reason and no retry", async ({
  page,
}) => {
  const answer = await chooseVisit(page, "FAKE FAKE_BASE · 60 min");
  expect(answer.status()).toBe(422);
  await expect(
    page.getByRole("alert").filter({
      hasText: "FAKE FAKE_BASE duplicates something already in this visit",
    }),
  ).toBeVisible({ timeout: 15000 });
  await expect(
    page.getByRole("button", { name: "Retry availability" }),
  ).toHaveCount(0);
  await noViolations(page);
});
