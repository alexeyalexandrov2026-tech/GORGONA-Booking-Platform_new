import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

type Fixture = {
  project: string;
  project_number: string;
  reported: string;
  link: string;
};

test("records, repairs, reopens and closes a claim with one actual cost assignment", async ({
  page,
}, testInfo) => {
  const fixtures = JSON.parse(
    process.env.GBA_WARRANTY_FIXTURES ?? "{}",
  ) as Record<string, Fixture>;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_o7c4_construction_warranty_browser.py.");
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator(".mgmt-header-actions")).toContainText(
    "FAKE user o7c4-owner",
  );
  await page.getByRole("link", { name: "Construction", exact: true }).click();
  await page
    .getByRole("table", { name: "Projects" })
    .getByRole("button", { name: fixture.project_number })
    .click();
  const warranty = page.getByRole("region", {
    name: "Warranty claims",
    exact: true,
  });
  await warranty
    .getByRole("button", { name: "New warranty claim" })
    .press("Enter");
  const newClaim = warranty.getByRole("form", { name: "New warranty claim" });
  const title = newClaim.getByRole("textbox", { name: "Claim title" });
  await title.focus();
  await page.keyboard.type("FAKE cracked tile");
  await page.keyboard.press("Tab");
  await expect(
    newClaim.getByRole("textbox", { name: "Reported by" }),
  ).toBeFocused();
  await page.keyboard.type("FAKE homeowner");
  await newClaim.getByLabel("Reported on").fill(fixture.reported);
  await newClaim
    .getByRole("combobox", { name: "Claim phase" })
    .selectOption("Finishes");
  await newClaim
    .getByRole("button", { name: "Record warranty claim" })
    .press("Enter");

  const detail = warranty.getByRole("region", {
    name: "Warranty claim 1",
    exact: true,
  });
  await expect(detail).toContainText("Status open");
  const keys: string[] = [];
  await page.route(
    `**/construction/projects/${fixture.project}/warranty-claims/1/repairs`,
    async (route) => {
      keys.push(route.request().headers()["idempotency-key"] ?? "");
      if (keys.length === 1) {
        expect((await route.fetch()).ok()).toBe(true);
        await route.abort();
        return;
      }
      await route.continue();
    },
  );
  await detail.getByRole("button", { name: "Assign repair cost" }).click();
  const repair = detail.getByRole("form", { name: "Assign repair cost" });
  await repair
    .getByRole("combobox", { name: "Project cost link" })
    .selectOption(fixture.link);
  const saveRepair = repair.getByRole("button", { name: "Save repair cost" });
  await saveRepair.click();
  await expect(detail.getByRole("alert")).toBeVisible();
  await saveRepair.click();
  await expect(detail).toContainText("Active repair costs 25.00 USD");
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);

  async function move(state: string, note?: string) {
    await detail.getByRole("button", { name: "Update claim status" }).click();
    const form = detail.getByRole("form", {
      name: "Update warranty claim status",
    });
    await form
      .getByRole("combobox", { name: "Claim transition" })
      .selectOption(state);
    if (note) {
      const reason = form.getByRole("textbox", { name: "Status note" });
      await expect(reason).toHaveAttribute("required", "");
      await reason.fill(note);
    }
    await form.getByRole("button", { name: "Save claim status" }).click();
    await expect(detail).toContainText(`Status ${state}`);
  }
  await move("repaired");
  await move("open", "FAKE resubmitted evidence");
  await move("repaired");
  await move("closed");
  await expect(
    detail.getByRole("button", { name: "Assign repair cost" }),
  ).toHaveCount(0);
  await expect(
    detail.getByRole("list", { name: "Claim history" }).getByRole("listitem"),
  ).toHaveCount(4);

  const costs = page.getByRole("region", { name: "Actual costs", exact: true });
  await costs
    .getByRole("button", { name: `Reverse cost ${fixture.link}` })
    .click();
  await costs
    .getByRole("textbox", { name: "Reversal reason" })
    .fill("FAKE corrected ledger fact");
  await costs.getByRole("button", { name: "Confirm reversal" }).click();
  await expect(detail).toContainText("Active repair costs 0.00 USD");
  await expect(
    detail.getByRole("list", { name: "Assigned repair costs" }),
  ).toContainText("25.00 USD · Reversed");
  const recon = page.getByRole("region", {
    name: "Project reconciliation",
    exact: true,
  });
  await expect(
    recon.getByRole("row", {
      name: "Warranty repairs included in actual 0.00",
    }),
  ).toBeVisible();

  const audit = await new AxeBuilder({ page })
    .include(".construction-screen")
    .analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
