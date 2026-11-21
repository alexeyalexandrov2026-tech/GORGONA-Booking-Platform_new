import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
test.describe.configure({ mode: "serial" });

const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const OWNER_NAME = "FAKE user sup-ui-owner";

async function signIn(page: Page) {
  const switched = await page.request.post(`${issuer}/fixture/user/owner`);
  expect(switched.ok()).toBe(true);
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(OWNER_NAME, { exact: true }),
  ).toBeVisible();
}

async function openSupply(page: Page) {
  await page.getByRole("link", { name: "Supply Chain", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Supply Chain, 3PL WMS & Manufacturing",
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

test("end-to-end 3PL WMS goods-owner isolation, manufacturing output/return lot & cost conservation, and trade shipment/return", async ({
  page,
}, testInfo) => {
  const tag = testInfo.project.name.toUpperCase();
  const coCode = `OWN_CO_${tag}`;
  const tplCode = `OWN_3PL_${tag}`;
  const binCoCode = `BIN_CO_${tag}`;
  const binTplCode = `BIN_3PL_${tag}`;
  const lotCoCode = `LOT-CO-${tag}`;
  const lotTplCode = `LOT-3PL-${tag}`;
  const lotFgCode = `LOT-FG-${tag}`;
  const bomCode = `BOM_${tag}`;
  const woCode = `WO_${tag}`;
  const plCode = `PL_${tag}`;
  const ordCode = `ORD_${tag}`;

  await signIn(page);
  await openSupply(page);
  await checkA11yAndViewport(page, testInfo);

  // 1. Create Company Goods Owner & 3PL Bailor Goods Owner
  await page.getByLabel(/^Owner code/).fill(coCode);
  await page.getByLabel(/^Owner display name/).fill(`Company Owner ${tag}`);
  await page.getByLabel(/^Owner kind/).selectOption("company_entity");
  await page.getByLabel(/^Legal entity/).selectOption({
    label: `SUP_UI_LE_${tag} — Gorgona Industrial Supply ${tag}`,
  });
  await page
    .getByRole("button", { name: "Save goods owner", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved goods owner ${coCode}`,
  );

  await page.getByLabel(/^Owner code/).fill(tplCode);
  await page.getByLabel(/^Owner display name/).fill(`3PL Bailor ${tag}`);
  await page.getByLabel(/^Owner kind/).selectOption("counterparty_3pl");
  await page
    .getByLabel(/^3PL Counterparty/)
    .selectOption({ label: `Bailor Partner ${tag}` });
  await page
    .getByRole("button", { name: "Save goods owner", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved goods owner ${tplCode}`,
  );

  // 2. Create Dedicated Bins for Company and 3PL Bailor
  await page.getByLabel(/^Bin code/).fill(binCoCode);
  await page
    .getByLabel(/^Dedicated goods owner/)
    .selectOption({ label: `${coCode} (company_entity)` });
  await page
    .getByRole("button", { name: "Save warehouse bin", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved warehouse bin ${binCoCode}`,
  );

  await page.getByLabel(/^Bin code/).fill(binTplCode);
  await page
    .getByLabel(/^Dedicated goods owner/)
    .selectOption({ label: `${tplCode} (counterparty_3pl)` });
  await page
    .getByRole("button", { name: "Save warehouse bin", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved warehouse bin ${binTplCode}`,
  );

  // 3. Create Company Component Lot & 3PL Bailor Lot
  await page
    .getByLabel(/^Lot goods owner/)
    .selectOption({ label: `${coCode} (company_entity)` });
  await page
    .getByLabel(/^Lot stock item/)
    .selectOption({ label: "COMP_VALVE — Valve Body Component" });
  await page.getByLabel(/^Lot code/).fill(lotCoCode);
  await page.getByLabel(/^Lot unit cost minor/).fill("5000");
  await page.getByRole("button", { name: "Save lot", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Saved lot ${lotCoCode}`,
  );

  await page
    .getByLabel(/^Lot goods owner/)
    .selectOption({ label: `${tplCode} (counterparty_3pl)` });
  await page
    .getByLabel(/^Lot stock item/)
    .selectOption({ label: "COMP_VALVE — Valve Body Component" });
  await page.getByLabel(/^Lot code/).fill(lotTplCode);
  await page.getByLabel(/^Lot unit cost minor/).fill("0");
  await page.getByRole("button", { name: "Save lot", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    `Saved lot ${lotTplCode}`,
  );

  // 4. Switch to Lots, Balances & Movements via keyboard ArrowRight
  const wmsTab = page.getByRole("tab", { name: "WMS Owners & Bins" });
  await wmsTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Lots, Balances & Movements" }),
  ).toHaveAttribute("aria-selected", "true");
  await checkA11yAndViewport(page, testInfo);

  // Negative proof: Company owner cannot put away into 3PL dedicated bin
  await page
    .getByLabel(/^Inbound goods owner/)
    .selectOption({ label: `${coCode} (company_entity)` });
  await page
    .getByLabel(/^Inbound bin/)
    .selectOption({ label: `${binTplCode} (ZONE_A)` });
  await page
    .getByLabel(/^Inbound item/)
    .selectOption({ label: "COMP_VALVE — Valve Body Component" });
  await page.getByLabel(/^Inbound lot/).selectOption({ label: lotCoCode });
  await page.getByLabel(/^Inbound quantity/).fill("10");
  await page.getByLabel(/^Auto stock receipt amount/).fill("500.00");
  await page
    .getByRole("button", { name: "Post inbound putaway", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "SUPPLY_OWNER_MISMATCH",
  );

  // Valid company inbound putaway (10 units @ $500.00)
  await page
    .getByLabel(/^Inbound bin/)
    .selectOption({ label: `${binCoCode} (ZONE_A)` });
  await page
    .getByRole("button", { name: "Post inbound putaway", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Recorded inbound putaway (10 units)",
  );

  // Valid 3PL bailor inbound putaway (4 units)
  await page
    .getByLabel(/^Inbound goods owner/)
    .selectOption({ label: `${tplCode} (counterparty_3pl)` });
  await page
    .getByLabel(/^Inbound bin/)
    .selectOption({ label: `${binTplCode} (ZONE_A)` });
  await page.getByLabel(/^Inbound lot/).selectOption({ label: lotTplCode });
  await page.getByLabel(/^Inbound quantity/).fill("4");
  await page
    .getByRole("button", { name: "Post inbound putaway", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Recorded inbound putaway (4 units)",
  );

  // 5. Manufacturing & Costing tab
  await page.getByRole("tab", { name: "Manufacturing & Costing" }).click();
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel(/^BOM code/).fill(bomCode);
  await page.getByLabel(/^BOM title/).fill(`Valve Assembly BOM ${tag}`);
  await page
    .getByLabel(/^Output item/)
    .selectOption({ label: "ASSY_VALVE — Assembled Industrial Valve" });
  await page
    .getByLabel(/^Component item/)
    .selectOption({ label: "COMP_VALVE — Valve Body Component" });
  await page.getByLabel(/^Component qty per batch/).fill("2");
  await page.getByLabel(/^Standard labor minor/).fill("3000");
  await page.getByLabel(/^Standard overhead minor/).fill("1000");
  await page.getByRole("button", { name: "Save BOM", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(`Saved BOM ${bomCode}`);

  await page.getByLabel(/^Work order code/).fill(woCode);
  await page
    .getByLabel(/^Work order goods owner/)
    .selectOption({ label: `${coCode} (company_entity)` });
  await page
    .getByLabel(/^Work order BOM/)
    .selectOption({ label: `${bomCode} — Valve Assembly BOM ${tag}` });
  await page.getByLabel(/^Planned quantity/).fill("2");
  await page
    .getByRole("button", { name: "Create work order", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Created work order ${woCode}`,
  );

  // Negative proof: cannot issue 3PL bailor lot to company work order
  await page.getByLabel(/^Issue bin/).selectOption({ label: binTplCode });
  await page
    .getByLabel(/^Issue component item/)
    .selectOption({ label: "COMP_VALVE" });
  await page.getByLabel(/^Issue lot/).selectOption({ label: lotTplCode });
  await page.getByLabel(/^Issue quantity/).fill("2");
  await page
    .getByRole("button", { name: "Post component issue", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "SUPPLY_OWNER_MISMATCH",
  );

  // Issue 5 company component units ($250.00) -> Return 1 unused unit ($50.00) -> QC 2 -> Output 2 ($240.00)
  await page.getByLabel(/^Issue bin/).selectOption({ label: binCoCode });
  await page.getByLabel(/^Issue lot/).selectOption({ label: lotCoCode });
  await page.getByLabel(/^Issue quantity/).fill("5");
  await page
    .getByRole("button", { name: "Post component issue", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Issued 5 component units (STOCK-01 cost 250.00 USD)",
  );

  await page.getByLabel(/^Return bin/).selectOption({ label: binCoCode });
  await page.getByLabel(/^Return quantity/).fill("1");
  await page
    .getByRole("button", { name: "Post material return", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Returned 1 unused component units (cost restored 50.00 USD)",
  );

  await page.getByLabel(/^QC passed quantity/).fill("2");
  await page.getByLabel(/^QC scrap quantity/).fill("0");
  await page
    .getByRole("button", { name: "Record QC inspection", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Recorded QC inspection (2 passed)",
  );

  await page.getByLabel(/^Output bin/).selectOption({ label: binCoCode });
  await page.getByLabel(/^Output lot code/).fill(lotFgCode);
  await page
    .getByRole("button", { name: "Post finished output", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Posted finished output lot (2 units, total cost 240.00 USD)",
  );

  // 6. Trade & 3PL Orders tab
  await page.getByRole("tab", { name: "Trade & 3PL Orders" }).click();
  await checkA11yAndViewport(page, testInfo);

  await page.getByLabel(/^Price list code/).fill(plCode);
  await page.getByLabel(/^Price list title/).fill(`Wholesale List ${tag}`);
  await page
    .getByLabel(/^Price list item/)
    .selectOption({ label: "ASSY_VALVE" });
  await page.getByLabel(/^Tier min quantity/).fill("1");
  await page.getByLabel(/^Tier unit price minor/).fill("25000");
  await page
    .getByRole("button", { name: "Save price list", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Saved price list ${plCode}`,
  );

  await page.getByLabel(/^Order code/).fill(ordCode);
  await page.getByLabel(/^Order kind/).selectOption("wholesale_sale");
  await page
    .getByLabel(/^Order goods owner/)
    .selectOption({ label: `${coCode} (company_entity)` });
  await page
    .getByLabel(/^Order ledger book/)
    .selectOption({ label: `SUP_UI_LE_${tag} — USD` });
  await page.getByLabel(/^Order price list/).selectOption({ label: plCode });
  await page.getByLabel(/^Order item/).selectOption({ label: "ASSY_VALVE" });
  await page.getByLabel(/^Ordered quantity/).fill("2");
  await page
    .getByRole("button", { name: "Create trade order", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    `Created trade order ${ordCode}`,
  );

  // Negative proof: cannot ship company trade order from 3PL bin/lot
  await page.getByLabel(/^Shipment bin/).selectOption({ label: binTplCode });
  await page.getByLabel(/^Shipment lot/).selectOption({ label: lotTplCode });
  await page.getByLabel(/^Shipment quantity/).fill("1");
  await page
    .getByRole("button", { name: "Post order shipment", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "SUPPLY_OWNER_MISMATCH",
  );

  // Ship 2 finished-goods units from LOT-FG-${tag} -> Revenue $500.00, COGS $240.00
  await page.getByLabel(/^Shipment bin/).selectOption({ label: binCoCode });
  await page.getByLabel(/^Shipment lot/).selectOption({ label: lotFgCode });
  await page.getByLabel(/^Shipment quantity/).fill("2");
  await page
    .getByRole("button", { name: "Post order shipment", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Shipped 2 units (revenue 500.00 USD, COGS 240.00 USD)",
  );

  // Customer returns 1 unit -> Refund $250.00, COGS restored $120.00
  await page
    .getByLabel(/^Customer return bin/)
    .selectOption({ label: binCoCode });
  await page.getByLabel(/^Customer return quantity/).fill("1");
  await page
    .getByLabel(/^Customer return reason/)
    .fill(`Customer partial return ${tag}`);
  await page
    .getByRole("button", { name: "Post customer return", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Processed customer return (1 units, refund 250.00 USD, COGS restored 120.00 USD)",
  );
});
