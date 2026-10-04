import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Times are entered in the device time zone; the harness supplies UTC values.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, timezoneId: "UTC" });

test("owner grants access, the serving business designates and the owner revokes", async ({
  page,
}) => {
  const purpose = `FAKE browser call centre ${test.info().project.name}`;
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  const selector = page.getByLabel("Active Salon");
  await selector.selectOption({ label: "FAKE salon A (owner)" });
  await page
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  const outgoing = page.getByRole("region", {
    name: "Delegations to other businesses",
  });
  await expect(outgoing.getByRole("heading", { level: 2 })).toHaveText(
    "Access for other businesses",
  );
  await outgoing.getByRole("button", { name: "New delegation" }).click();
  await outgoing
    .getByLabel("Serving business ID")
    .fill(process.env.GBA_SERVING_BUSINESS!);
  await outgoing.getByLabel("Purpose").fill(purpose);
  await outgoing
    .getByRole("checkbox", { name: "Create, move and cancel bookings" })
    .check();
  for (const name of [
    "View bookings and clients",
    "View services",
    "View staff and schedules",
  ]) {
    const dependency = outgoing.getByRole("checkbox", { name });
    await expect(dependency).toBeChecked();
    await expect(dependency).toBeDisabled();
  }
  await outgoing.getByLabel("Starts").fill(process.env.GBA_DELEGATION_FROM!);
  await outgoing.getByLabel("Ends").fill(process.env.GBA_DELEGATION_UNTIL!);
  await outgoing.getByRole("button", { name: "Save delegation" }).click();
  await expect(
    outgoing.getByText("Delegation saved. Version 1."),
  ).toBeVisible();
  await expect(
    outgoing.getByText("Designated by the serving business: nobody yet"),
  ).toBeVisible();

  await selector.selectOption({ label: "FAKE salon B (owner)" });
  const received = page.getByRole("region", { name: "Delegations received" });
  const item = received.getByRole("listitem").filter({ hasText: purpose });
  await expect(item).toContainText("Active");
  await expect(item).toContainText(process.env.GBA_OWNER_BUSINESS!);
  await item
    .getByLabel("Employee")
    .selectOption({ label: process.env.GBA_DELEGATE_OPTION! });
  await item.getByRole("button", { name: "Designate employee" }).click();
  await expect(
    received.getByText(
      "Employee designated. They can now work for this business.",
    ),
  ).toBeVisible();
  await expect(
    item.getByRole("button", {
      name: `Remove ${process.env.GBA_DELEGATE_NAME}`,
    }),
  ).toBeVisible();

  await selector.selectOption({ label: "FAKE salon A (owner)" });
  await outgoing
    .getByRole("button", { name: new RegExp(`^${purpose} · Active`) })
    .click();
  await expect(
    outgoing.getByText(
      `Designated by the serving business: user ${process.env.GBA_DELEGATE_USER}`,
    ),
  ).toBeVisible();
  await outgoing.getByRole("button", { name: "Revoke access" }).click();
  await outgoing.getByRole("button", { name: "Confirm revocation" }).click();
  await expect(
    outgoing.getByText(
      "Access revoked. The serving business can no longer use this delegation.",
    ),
  ).toBeVisible();
  await expect(
    outgoing.getByRole("button", { name: new RegExp(`^${purpose} · Revoked`) }),
  ).toBeVisible();
  await expect(
    outgoing.getByRole("button", { name: "Save delegation" }),
  ).toHaveCount(0);
  await outgoing
    .getByRole("button", { name: "View previous delegation version" })
    .click();
  await expect(
    outgoing.getByText(
      /Previous delegation version 1: FAKE browser call centre/,
    ),
  ).toBeVisible();

  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(await page.evaluate(() => window.innerWidth)).toBeLessThanOrEqual(
    page.viewportSize()!.width,
  );
  await page.screenshot({
    path: `test-results/delegation-management-${page.viewportSize()?.width}.png`,
    fullPage: true,
  });
});
