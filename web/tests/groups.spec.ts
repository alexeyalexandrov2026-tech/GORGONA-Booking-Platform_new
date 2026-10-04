import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

// The signed-in person owns a business invited to the partner's group before the run.
test("a business joins and leaves a group and runs its own, without gaining access", async ({
  page,
}, testInfo) => {
  const partner = process.env.GBA_GROUP_PARTNER!;
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  const section = page.getByRole("region", { name: "Company groups" });
  const partnerGroup = section
    .getByRole("listitem")
    .filter({ hasText: "FAKE Partner Holding" });
  if (testInfo.project.name === "desktop") {
    await expect(partnerGroup).toContainText("Invited");
    const keys: string[] = [];
    let authorization = "";
    let loseResponse = true;
    await page.route("**/v1/businesses/*/groups/*/accept", async (route) => {
      keys.push(route.request().headers()["idempotency-key"]!);
      authorization = route.request().headers()["authorization"]!;
      if (loseResponse) {
        loseResponse = false;
        await route.fetch(); // Real decision; the client loses only the response.
        await route.abort("failed");
      } else await route.continue();
    });
    await partnerGroup
      .getByRole("button", { name: "Join FAKE Partner Holding" })
      .click();
    await section
      .getByRole("button", { name: "Retry same group action" })
      .click();
    await expect(section.getByRole("status")).toHaveText(
      "You joined the group.",
    );
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await page.unroute("**/v1/businesses/*/groups/*/accept");
    // Belonging to the group gives no access to the partner's records.
    const partnerBookings = await page.request.get(
      `/v1/salons/${partner}/bookings`,
      { headers: { authorization } },
    );
    expect(partnerBookings.status()).toBe(403);

    await section.getByLabel("Internal reference").fill("FAKE_NETWORK");
    await section.getByLabel("Group name").fill("FAKE Own Network");
    await section.getByRole("button", { name: "Create group" }).click();
    await expect(section.getByRole("status")).toHaveText("Group created.");
    const ownGroup = section
      .getByRole("listitem")
      .filter({ hasText: "FAKE Own Network" });
    await ownGroup
      .getByLabel("Invite business by ID to FAKE Own Network")
      .fill(partner);
    await ownGroup.getByRole("button", { name: "Send invitation" }).click();
    await expect(section.getByRole("status")).toHaveText("Invitation sent.");
    await ownGroup.getByRole("button", { name: /^End membership of / }).click();
    await expect(section.getByRole("status")).toHaveText("Membership ended.");
    await partnerGroup
      .getByRole("button", { name: "Leave FAKE Partner Holding" })
      .click();
    await expect(section.getByRole("status")).toHaveText("You left the group.");
  }
  await expect(partnerGroup).toContainText("Left the group");
  await expect(
    section.getByRole("listitem").filter({ hasText: "FAKE Own Network" }),
  ).toContainText("Removed");
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
    path: `test-results/groups-${page.viewportSize()?.width}.png`,
    fullPage: true,
  });
});
