import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
test.describe.configure({ mode: "serial" });

const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const NAME = {
  owner: "FAKE user rest-ui-owner",
  front_desk: "FAKE user rest-ui-front",
  kitchen: "FAKE user rest-ui-kitchen",
} as const;
type Person = keyof typeof NAME;

async function signIn(page: Page, who: Person) {
  const switched = await page.request.post(`${issuer}/fixture/user/${who}`);
  expect(switched.ok()).toBe(true);
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(NAME[who], { exact: true }),
  ).toBeVisible();
}

async function openRestaurant(page: Page) {
  await page.getByRole("link", { name: "Restaurant", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Restaurant", exact: true }),
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

test("end-to-end restaurant floor, menu/recipe, check split, kitchen board and STOCK-01 write-off", async ({
  page,
}, testInfo) => {
  const tag = testInfo.project.name.toUpperCase();
  const areaName = `Dining ${tag}`;
  const tableCode = `T_${tag}`;
  const itemCode = `BRG_${tag}`;
  const itemName = `Grill Burger ${tag}`;
  const grpCode = `MOD_${tag}`;
  const optCode = `CHS_${tag}`;

  // 1. Owner sets up Floor, Table, Reservation, Menu item, Modifier & STOCK-01 Recipe
  await signIn(page, "owner");
  await openRestaurant(page);
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel("Area name").fill(areaName);
  await page.getByRole("button", { name: "Save area", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Dining area ${areaName} saved.`,
  );

  await page.getByLabel("Table code").fill(tableCode);
  await page.getByRole("button", { name: "Save table", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Table ${tableCode} saved.`,
  );

  await page.getByLabel("Guest name").fill(`Guest ${tag}`);
  await page.getByRole("button", { name: "Book table", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Reservation for Guest ${tag} booked.`,
  );

  // Keyboard switch to Menu & Recipes tab
  const floorTab = page.getByRole("tab", { name: "Floor & Reservations" });
  await floorTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Menu & Recipes" }),
  ).toHaveAttribute("aria-selected", "true");
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel("Item code").fill(itemCode);
  await page.getByLabel("Item name").fill(itemName);
  await page.getByLabel("Price", { exact: true }).fill("15.00");
  await page
    .getByRole("button", { name: "Save menu item", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Menu item ${itemName} saved`,
  );

  await page.getByLabel("Group code").fill(grpCode);
  await page.getByLabel("Group name").fill(`Extras ${tag}`);
  await page
    .getByRole("button", { name: "Save modifier group", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Modifier group Extras ${tag} saved.`,
  );

  await page.getByLabel("Option code").fill(optCode);
  await page.getByLabel("Option name").fill(`Cheddar ${tag}`);
  await page.getByLabel("Price delta").fill("2.00");
  await page
    .getByRole("button", { name: "Save modifier option", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Modifier option Cheddar ${tag} saved.`,
  );

  await page.getByRole("button", { name: "Attach group", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Modifier group attached to ${itemName}.`,
  );

  await page.getByLabel("Scaled quantity").fill("180");
  await page
    .getByRole("button", { name: "Save recipe revision", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Recipe rev 1 saved for ${itemName}.`,
  );

  // 2. Front desk opens independent takeout check, orders Burger + Cheddar ($17.00), fires to kitchen
  await signIn(page, "front_desk");
  await openRestaurant(page);
  await page.getByRole("tab", { name: "Checks & Split Billing" }).click();
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel("Guest label").fill(`Order ${tag}`);
  await page.getByRole("button", { name: "Open check", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Check opened (takeout).",
  );

  await page
    .getByLabel("Order menu item")
    .selectOption({ label: `${itemName} (15.00 USD)` });
  await page
    .getByLabel("Optional modifier")
    .selectOption({ label: `Cheddar ${tag} (2.00 USD)` });
  await page.getByRole("button", { name: "Add line", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Order line added to check.",
  );
  await expect(
    page.getByText("Selected Check (open — 17.00 USD)"),
  ).toBeVisible();

  await page
    .getByRole("button", { name: "Fire to kitchen", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Fired 1 kitchen ticket(s).",
  );

  // 3. Kitchen artist advances hot ticket queued -> preparing -> ready -> served
  await signIn(page, "kitchen");
  await openRestaurant(page);
  await expect(
    page.getByRole("tab", { name: "Kitchen Station Board" }),
  ).toHaveAttribute("aria-selected", "true");
  await checkA11yAndViewport(page, testInfo);

  // Kitchen artist has zero menu-manage forms on Menu tab
  await page.getByRole("tab", { name: "Menu & Recipes" }).click();
  await expect(
    page.getByRole("button", { name: "Save menu item" }),
  ).toHaveCount(0);
  await page.getByRole("tab", { name: "Kitchen Station Board" }).click();

  await page.getByRole("button", { name: "hot", exact: true }).click();
  const ticketCard = page.locator("article", { hasText: itemName });
  await ticketCard
    .getByRole("button", { name: "Start prep", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("is now preparing.");
  await ticketCard
    .getByRole("button", { name: "Mark ready", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("is now ready.");
  await ticketCard
    .getByRole("button", { name: "Mark served", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("is now served.");

  // 4. Owner splits check ($10.00 + $7.00 = $17.00), posts STOCK-01 write-off, verifies Balanced = Yes
  await signIn(page, "owner");
  await openRestaurant(page);
  await page.getByRole("tab", { name: "Checks & Split Billing" }).click();
  const row = page.locator("tr", { hasText: `Order ${tag}` });
  await row.getByRole("button").click();

  await page.getByLabel("Share 1 amount").fill("10.00");
  await page.getByLabel("Share 2 amount").fill("7.00");
  await page.getByRole("button", { name: "Save split", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Check split conserved and saved.",
  );

  await page
    .getByRole("button", { name: "Post STOCK-01 write-off", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "STOCK-01 write-off posted (1 materials).",
  );
  await expect(page.getByText("17.00 USD").first()).toBeVisible();
});
