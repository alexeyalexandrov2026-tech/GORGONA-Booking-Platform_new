import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

// The signed-in person owns the servicing business. The owner business issued a
// location-limited offer before the run; both companies keep their own records.
test("servicing business accepts limited access, books for the owner and ends access", async ({
  page,
}, testInfo) => {
  const partner = process.env.GBA_DELEGATION_PARTNER!;
  const own = process.env.GBA_DELEGATION_SERVICER!;
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  const section = page.getByRole("region", { name: "Delegated access" });
  await expect(
    section.getByRole("heading", { name: "Access you serve" }),
  ).toBeVisible();
  if (testInfo.project.name === "desktop") {
    const offer = section
      .getByRole("listitem")
      .filter({ hasText: "Waiting for acceptance" });
    await expect(offer).toHaveCount(1);
    await offer.getByRole("checkbox", { name: /\(owner\)$/ }).check();
    const keys: string[] = [];
    let loseResponse = true;
    await page.route(
      "**/v1/businesses/*/delegations/*/accept",
      async (route) => {
        keys.push(route.request().headers()["idempotency-key"]!);
        if (loseResponse) {
          loseResponse = false;
          await route.fetch(); // Real acceptance; the client loses only the response.
          await route.abort("failed");
        } else await route.continue();
      },
    );
    await offer.getByRole("button", { name: /^Accept access from / }).click();
    await section
      .getByRole("button", { name: "Retry same access action" })
      .click();
    await expect(section.getByRole("status")).toHaveText("Access accepted.");
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await page.unroute("**/v1/businesses/*/delegations/*/accept");

    // This business may also offer its own work to the partner, then withdraw it.
    const lastDay = new Date(Date.now() + 7 * 86_400_000)
      .toISOString()
      .slice(0, 10);
    await section.getByLabel("Serving business ID").fill(partner);
    await section.getByLabel("Access", { exact: true }).selectOption("view");
    await section.getByLabel("Last day of access").fill(lastDay);
    await section.getByRole("button", { name: "Offer access" }).click();
    await expect(section.getByRole("status")).toHaveText(
      "Access offered. It starts after the other business accepts.",
    );
    await section
      .getByRole("listitem")
      .filter({ hasText: `Business ${partner}` })
      .getByRole("button", { name: /^Revoke access for / })
      .click();
    await expect(section.getByRole("status")).toHaveText(
      "Access revoked. It stops at the next action.",
    );

    // Work in the owner business as a named delegate: bookings only, one location.
    // In-app navigation keeps the session and reloads the account's businesses.
    await page.getByRole("link", { name: "Overview", exact: true }).click();
    await page.getByLabel("Active Salon").selectOption(partner);
    await expect(
      page.getByText("You are serving", { exact: false }),
    ).toBeVisible();
    for (const name of [
      "Business profile",
      "Settings",
      "Services",
      "Staff",
      "Clients",
    ])
      await expect(page.getByRole("link", { name, exact: true })).toHaveCount(
        0,
      );
    await page.getByRole("link", { name: "Calendar", exact: true }).click();
    await expect(page.getByLabel("Location:").locator("option")).toHaveCount(1);
    const day = process.env.GBA_MGMT_BROWSER_DAY!;
    await page.getByLabel("Selected Calendar Date").fill(day);
    await page.getByRole("button", { name: "+ Book Appointment" }).click();
    await page
      .getByRole("combobox", { name: "Service:", exact: true })
      .selectOption({ label: "FAKE FAKE_BASE (60m) • $50.00" });
    await page.getByLabel("Date:", { exact: true }).fill(day);
    await page.getByLabel("Start Time:", { exact: true }).fill("12:00");
    await page.getByLabel("Client Name:").fill("FAKE Delegated Browser Guest");
    await page
      .getByLabel("Email:", { exact: true })
      .fill("delegated-browser@example.test");
    await page.getByLabel("Phone:", { exact: true }).fill("+15551234571");
    await page
      .getByRole("button", { name: "Create Appointment", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("link", { name: "Bookings", exact: true }).click();
    const row = page
      .getByRole("row")
      .filter({ hasText: "FAKE Delegated Browser Guest" })
      .filter({ hasText: "CONFIRMED" });
    await row.getByRole("button", { name: "Cancel", exact: true }).click();
    await page
      .getByRole("button", { name: "Confirm Cancellation", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    // End the relationship from the servicing side; the owner's business disappears.
    await page.getByLabel("Active Salon").selectOption(own);
    await page
      .getByRole("link", { name: "Business profile", exact: true })
      .click();
    await section
      .getByRole("listitem")
      .filter({ hasText: "Active" })
      .getByRole("button", { name: /^End access for / })
      .click();
    await expect(section.getByRole("status")).toHaveText(
      "Access revoked. It stops at the next action.",
    );
    await page.getByRole("link", { name: "Overview", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: /Today’s Overview/ }),
    ).toBeVisible();
    await expect(page.getByLabel("Active Salon")).toHaveCount(0);
    await page
      .getByRole("link", { name: "Business profile", exact: true })
      .click();
  }
  await expect(
    section.getByText("Ended by the serving business"),
  ).toBeVisible();
  await expect(
    section.getByText("Revoked by the business owner"),
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
  await page.screenshot({
    path: `test-results/delegation-${page.viewportSize()?.width}.png`,
    fullPage: true,
  });
});
