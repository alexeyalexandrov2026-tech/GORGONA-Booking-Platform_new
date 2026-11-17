import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

test("answers change orders from a sign-in link and refuses a grant revoked after loading", async ({
  page,
}, testInfo) => {
  const fixtures = JSON.parse(
    process.env.GBA_CUSTOMER_CHANGES ?? "{}",
  ) as Record<
    string,
    {
      business: string;
      project: string;
      grant: string;
    }
  >;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_o9_customer_change_browser.py.");
  const link = (number: number) =>
    `/construction/customer/change/?${new URLSearchParams({
      ...fixture,
      number: String(number),
    })}`;
  const main = page.getByRole("main");
  await page.goto(link(1));
  const signIn = page.getByRole("button", { name: "Sign in", exact: true });
  await expect(signIn).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(signIn).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    main.getByRole("heading", { name: "FAKE change", exact: true }),
  ).toBeVisible();
  expect(new URL(page.url()).searchParams.get("number")).toBe("1");
  await expect(main).toContainText("Price change USD 25.00");
  await expect(main).toContainText("Schedule change -2 days");
  await expect(main).toContainText("USD -50.00");
  await expect(main).not.toContainText("USD 15.00");
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);

  const keys: string[] = [];
  const bodies: string[] = [];
  await page.route(
    `**/change-orders/1/customer-answer/${fixture.grant}`,
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      keys.push(route.request().headers()["idempotency-key"] ?? "");
      bodies.push(route.request().postData() ?? "");
      if (keys.length === 1) {
        expect((await route.fetch()).ok()).toBe(true);
        return route.abort();
      }
      return route.continue();
    },
  );
  const approve = page.getByRole("radio", { name: "Approve change order" });
  await approve.focus();
  await page.keyboard.press("Space");
  await page.keyboard.press("Tab");
  const note = page.getByRole("textbox", { name: "Note (optional)" });
  await expect(note).toBeFocused();
  await page.keyboard.type("FAKE reviewed scope");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Send answer" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(main.getByRole("alert")).toContainText(
    "could not confirm your answer",
  );
  await expect(approve).toBeDisabled();
  await expect(note).toBeDisabled();
  await page.getByRole("button", { name: "Retry answer" }).press("Enter");
  await expect(main.getByRole("status")).toHaveText("Change order approved.");
  await expect(main.getByRole("status")).toBeFocused();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
  expect(keys[1]).toBe(keys[0]);
  expect(bodies[1]).toBe(bodies[0]);

  // Client navigation keeps the verified session while changing the document.
  await page.evaluate((href) => {
    window.history.pushState(null, "", href);
  }, link(2));
  await expect(main).toContainText("Change order 2");
  await page.getByRole("radio", { name: "Reject change order" }).check();
  await note.fill("FAKE out of scope");
  await page.getByRole("button", { name: "Send answer" }).press("Enter");
  await expect(main.getByRole("status")).toHaveText("Change order rejected.");

  await page.evaluate((href) => {
    window.history.pushState(null, "", href);
  }, link(3));
  await expect(main).toContainText("Change order 3");
  const revoked = await page.request.post(
    `${process.env.GBA_TEST_OIDC_ISSUER}/browser/revoke/${fixture.grant}`,
  );
  expect(revoked.ok()).toBe(true);
  await approve.check();
  await page.getByRole("button", { name: "Send answer" }).press("Enter");
  await expect(main.getByRole("alert")).toHaveText(
    "This change order is unavailable for your account.",
  );
  await expect(
    main.getByRole("heading", { name: "FAKE change", exact: true }),
  ).toHaveCount(0);
  await expect(approve).toHaveCount(0);
});
