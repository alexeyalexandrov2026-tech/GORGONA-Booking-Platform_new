import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, timezoneId: "UTC" });
test("owner invites an independent company; its consent gates a live report", async ({
  page,
}) => {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  const selector = page.getByLabel("Active Salon");
  await selector.selectOption({ label: "FAKE salon B (owner)" });
  await page
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  const groups = page.getByRole("region", {
    name: "Company groups",
    exact: true,
  });
  const code = `FAKE_${test.info().project.name.toUpperCase()}`;
  const original = `FAKE group for browser acceptance ${code}`;
  const renamed = `FAKE renamed group ${code}`;
  await groups.getByLabel("Group internal reference").fill(code);
  await groups.getByLabel("Group name", { exact: true }).fill(original);
  const attempts: string[] = [];
  let lose = true;
  await page.route("**/v1/businesses/*/groups/*", async (route) => {
    if (
      route.request().method() !== "PUT" ||
      route.request().url().includes("invitations")
    )
      return route.continue();
    attempts.push(route.request().headers()["idempotency-key"]!);
    if (lose) {
      lose = false;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await groups
    .getByRole("button", { name: "Save company group", exact: true })
    .click();
  await expect(
    groups.getByRole("button", { name: "Retry same group change" }),
  ).toBeVisible();
  await groups.getByRole("button", { name: "Retry same group change" }).click();
  await expect(groups.getByRole("status")).toHaveText(
    "Company group change saved.",
  );
  expect(attempts).toHaveLength(2);
  expect(attempts[0]).toBe(attempts[1]);
  await page.unroute("**/v1/businesses/*/groups/*");
  await groups.getByLabel("Group name", { exact: true }).fill(renamed);
  await groups
    .getByRole("button", { name: "Save company group", exact: true })
    .click();
  await expect(
    groups.getByRole("button", {
      name: new RegExp(`^${code} · ${renamed} · version 2`),
    }),
  ).toBeVisible();
  await groups.getByRole("button", { name: "Previous group version" }).click();
  await expect(groups.getByRole("note")).toContainText(
    "FAKE group for browser acceptance",
  );
  await groups
    .getByLabel("Participant business ID")
    .fill(process.env.GBA_OWNER_BUSINESS!.toUpperCase());
  await groups.getByRole("button", { name: "Send group invitation" }).click();
  await expect(
    groups.getByText(/invitation active · consent pending/),
  ).toBeVisible();
  const day = process.env.GBA_MGMT_BROWSER_DAY!;
  await groups.getByLabel("Report starts").fill(`${day}T00:00`);
  await groups.getByLabel("Report ends").fill(`${day}T23:59`);
  await groups.getByRole("button", { name: "Read booking counts" }).click();
  await expect(groups.getByLabel("Group booking report")).toContainText(
    "0 companies permitted",
  );
  await selector.selectOption({ label: "FAKE salon A (owner)" });
  const invite = groups
    .getByRole("listitem")
    .filter({ hasText: new RegExp(`${renamed} · operator`) });
  await invite.getByRole("button", { name: "Accept group membership" }).click();
  await expect(invite).toContainText("consent accepted");
  await selector.selectOption({ label: "FAKE salon B (owner)" });
  await groups
    .getByRole("button", { name: new RegExp(`^${code} · ${renamed}`) })
    .click();
  await groups.getByLabel("Report starts").fill(`${day}T00:00`);
  await groups.getByLabel("Report ends").fill(`${day}T23:59`);
  await groups.getByRole("button", { name: "Read booking counts" }).click();
  await expect(groups.getByLabel("Group booking report")).toContainText(
    "1 companies permitted",
  );
  await expect(groups.getByLabel("Group booking report")).toContainText(
    "CONFIRMED: 1",
  );
  await expect(groups.getByLabel("Group booking report")).toContainText(
    "legal entity unassigned",
  );
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await selector.selectOption({ label: "FAKE salon A (owner)" });
  await invite.getByRole("button", { name: "Withdraw group consent" }).click();
  await expect(invite).toContainText("consent withdrawn");
  await selector.selectOption({ label: "FAKE salon B (owner)" });
  await groups
    .getByRole("button", { name: new RegExp(`^${code} · ${renamed}`) })
    .click();
  await groups.getByLabel("Report starts").fill(`${day}T00:00`);
  await groups.getByLabel("Report ends").fill(`${day}T23:59`);
  await groups.getByRole("button", { name: "Read booking counts" }).click();
  await expect(groups.getByLabel("Group booking report")).toContainText(
    "0 companies permitted",
  );
});
