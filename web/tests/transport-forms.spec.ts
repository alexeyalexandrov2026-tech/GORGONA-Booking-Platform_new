import { test, expect, type Page, type TestInfo } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

// M6b (package M): an owner registers the fleet, enters an order and plans a trip, offers a carrier
// transport actions; the carrier accepts for its dispatcher, who sees only the granted forms. FAKE data only.
const issuer = process.env.GBA_TEST_OIDC_ISSUER!;
const owner = process.env.GBA_M6B_OWNER_BUSINESS!;
const carrier = process.env.GBA_M6B_CARRIER_BUSINESS!;
const location = process.env.GBA_M6B_LOCATION_NAME!;

const screen = (page: Page) => page.locator(".transport-screen");
const statusOf = (page: Page) =>
  screen(page).locator(".transport-status[role=status]");
const alertOf = (page: Page) => screen(page).getByRole("alert");

async function signIn(page: Page, who: string) {
  const switched = await page.request.post(`${issuer}/fixture/user/${who}`);
  expect(switched.ok()).toBe(true);
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(`FAKE user ${who}`, {
      exact: true,
    }),
  ).toBeVisible();
}
async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "You’re signed out." }),
  ).toBeVisible();
}
async function openTransport(page: Page) {
  await page.getByRole("link", { name: "Transport", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Transport", level: 1 }),
  ).toBeVisible();
  await expect(page.getByText("Loading the trips…")).toBeHidden();
}
async function check(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".transport-screen")
    .analyze();
  expect(axe.violations).toEqual([]);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
}

test("an owner plans with the forms and a carrier's dispatcher works through the grant", async ({
  page,
}, testInfo) => {
  const p = testInfo.project.name as "desktop" | "mobile";
  const dispatcher = `m6b-dispatcher-${p}`;

  // Fleet: a driver and a truck (owner only).
  await signIn(page, "m6b-owner");
  await openTransport(page);
  const driverForm = page.getByRole("form", { name: "Driver" });
  await driverForm.getByLabel("Name").fill(`FAKE Driver ${p}`);
  await driverForm.getByLabel("Location").selectOption({ label: location });
  await driverForm.getByRole("button", { name: "Save driver" }).click();
  await expect(statusOf(page)).toHaveText("Driver saved.");
  await expect(page.getByRole("table", { name: "Drivers" })).toContainText(
    `FAKE Driver ${p}`,
  );
  const vehicleForm = page.getByRole("form", { name: "Vehicle" });
  await vehicleForm.getByLabel("Kind").selectOption({ label: "Truck" });
  await vehicleForm.getByLabel("Unit number").fill(`FAKE-T-${p}-1`);
  await vehicleForm.getByLabel("Location").selectOption({ label: location });
  await vehicleForm.getByRole("button", { name: "Save vehicle" }).click();
  await expect(statusOf(page)).toHaveText("Vehicle saved.");

  // An order with two loads, then a correction with its revision.
  const orderForm = page.getByRole("form", { name: "Order" });
  await orderForm
    .getByLabel("Customer")
    .selectOption({ label: "FAKE Shipper" });
  await orderForm.getByLabel("Reference").fill(`FAKE-SO-${p}`);
  const first = orderForm.getByRole("group", { name: "Load 1" });
  await first.getByLabel("Description").fill("FAKE pallets");
  await first.getByLabel("Quantity").fill("10");
  await first.getByLabel("Unit").fill("pallet");
  await orderForm.getByRole("button", { name: "Add a load" }).click();
  const second = orderForm.getByRole("group", { name: "Load 2" });
  await second.getByLabel("Description").fill("FAKE crates");
  await second.getByLabel("Quantity").fill("6");
  await second.getByLabel("Unit").fill("crate");
  await orderForm.getByRole("button", { name: "Save order" }).click();
  await expect(statusOf(page)).toHaveText("Order saved.");
  await page
    .getByRole("table", { name: "Orders" })
    .getByRole("row")
    .filter({ hasText: `FAKE-SO-${p}` })
    .getByRole("button", { name: "Edit" })
    .click();
  await orderForm
    .getByRole("group", { name: "Load 2" })
    .getByLabel("Quantity")
    .fill("8");
  await orderForm.getByRole("button", { name: "Save order" }).click();
  await expect(statusOf(page)).toHaveText("Order saved.");

  // A trip with stops in their own zones; an overplanned leg is refused and corrected.
  const tripForm = page.getByRole("form", { name: "Trip" });
  await tripForm.getByLabel("Location").selectOption({ label: location });
  await tripForm.getByLabel("Reference").fill(`FAKE-TR-${p}`);
  const stops = [
    ["Pickup", "FAKE dock, Chicago", "America/Chicago", "08:00", "10:00"],
    [
      "Delivery",
      "FAKE yard, Indianapolis",
      "America/Indiana/Indianapolis",
      "14:00",
      "16:00",
    ],
    ["Delivery", "FAKE store, New York", "America/New_York", "20:00", "23:00"],
  ];
  for (const [index, [kind, place, zone, from, to]] of stops.entries()) {
    if (index > 1)
      await tripForm.getByRole("button", { name: "Add a stop" }).click();
    const stop = tripForm.getByRole("group", { name: `Stop ${index + 1}` });
    await stop.getByLabel("Kind").selectOption({ label: kind! });
    await stop.getByLabel("Place").fill(place!);
    await stop.getByLabel("Time zone").fill(zone!);
    await stop.getByLabel("Date").fill("2031-06-02");
    await stop.getByLabel("From").fill(from!);
    await stop.getByLabel("To").fill(to!);
  }
  const legs = [
    ["FAKE pallets", "10", "1", "2"],
    ["FAKE crates", "9", "1", "3"],
  ];
  for (const [index, [cargo, quantity, from, to]] of legs.entries()) {
    if (index > 0)
      await tripForm.getByRole("button", { name: "Add a leg" }).click();
    const leg = tripForm.getByRole("group", { name: `Leg ${index + 1}` });
    await leg
      .getByLabel("Load")
      .selectOption({ label: `FAKE-SO-${p} · ${cargo}` });
    await leg.getByLabel("Quantity").fill(quantity!);
    await leg.getByLabel("Pickup stop").selectOption(from!);
    await leg.getByLabel("Delivery stop").selectOption(to!);
  }
  await tripForm.getByRole("button", { name: "Save trip" }).click();
  await expect(alertOf(page)).toContainText("The trip was not saved");
  await tripForm
    .getByRole("group", { name: "Leg 2" })
    .getByLabel("Quantity")
    .fill("8");
  await tripForm.getByRole("button", { name: "Save trip" }).click();
  await expect(statusOf(page)).toHaveText("Trip saved.");
  await expect(alertOf(page)).toHaveCount(0);
  const board = page.getByRole("table", { name: "Trips" });
  await board.getByRole("button", { name: `FAKE-TR-${p}` }).click();
  await expect(
    page.getByRole("heading", { name: `Trip FAKE-TR-${p}` }),
  ).toBeVisible();
  await expect(page.getByRole("table", { name: "Stops" })).toContainText(
    "2031-06-02 14:00–16:00 (America/Indiana/Indianapolis)",
  );
  // A planned, unassigned trip can still be corrected.
  await page.getByRole("button", { name: "Edit trip" }).click();
  await tripForm
    .getByRole("group", { name: "Stop 3" })
    .getByLabel("Place")
    .fill("FAKE store 2, New York");
  await tripForm.getByRole("button", { name: "Save trip" }).click();
  await expect(statusOf(page)).toHaveText("Trip saved.");
  await expect(page.getByRole("table", { name: "Stops" })).toContainText(
    "FAKE store 2, New York",
  );
  await check(page, testInfo, "owner-forms");

  // Offer the carrier transport actions without booking access.
  await page
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  const access = page.getByRole("region", { name: "Delegated access" });
  await access.getByLabel("Serving business ID").fill(carrier);
  await access.getByLabel("Access", { exact: true }).selectOption("none");
  await access.getByRole("checkbox", { name: "Assign crews" }).check();
  await access.getByRole("checkbox", { name: "Record stop events" }).check();
  const lastDay = new Date(Date.now() + 7 * 86_400_000)
    .toISOString()
    .slice(0, 10);
  await access.getByLabel("Last day of access").fill(lastDay);
  if (p === "mobile") {
    // One open delegation per pair of businesses: the offer is refused in words (D-02), the message
    // survives the reload that follows, and the desktop run's grant is revoked before offering again.
    await access.getByRole("button", { name: "Offer access" }).click();
    const refused = access.getByRole("alert");
    await expect(refused).toContainText("already has an open delegation");
    await expect(access.getByText("Loading access…")).toBeHidden();
    await expect(refused).toContainText("already has an open delegation");
    await access
      .getByRole("listitem")
      .filter({ hasText: "Active" })
      .getByRole("button", { name: /^Revoke access for / })
      .click();
    await expect(access.getByRole("status")).toHaveText(
      "Access revoked. It stops at the next action.",
    );
    await expect(refused).toHaveCount(0);
  }
  await access.getByRole("button", { name: "Offer access" }).click();
  await expect(access.getByRole("status")).toHaveText(
    "Access offered. It starts after the other business accepts.",
  );
  await expect(
    access.getByRole("listitem").filter({ hasText: "Waiting for acceptance" }),
  ).toContainText("Transport: view, assign crews, record stop events");
  await signOut(page);

  // The carrier accepts for its dispatcher.
  await signIn(page, "m6b-carrier");
  await page
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  const offers = page.getByRole("region", { name: "Delegated access" });
  const offer = offers
    .getByRole("listitem")
    .filter({ hasText: "Waiting for acceptance" });
  await expect(offer).toHaveCount(1);
  await offer
    .getByRole("checkbox", {
      name: new RegExp(`${dispatcher} \\(manager\\)$`),
    })
    .check();
  await offer.getByRole("button", { name: /^Accept access from / }).click();
  await expect(offers.getByRole("status")).toHaveText("Access accepted.");
  await signOut(page);

  // The dispatcher works in the owner's business through the grant.
  await signIn(page, dispatcher);
  await page.getByLabel("Active Salon").selectOption(owner);
  await expect(
    page.getByText("You are serving", { exact: false }),
  ).toBeVisible();
  for (const name of ["Calendar", "Bookings", "Business profile", "Staff"])
    await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0);
  await openTransport(page);
  for (const name of ["Driver", "Vehicle", "Order", "Trip"])
    await expect(page.getByRole("form", { name, exact: true })).toHaveCount(0);
  // M7b-04: money is a finance task; a delegate never sees its panels.
  await expect(page.getByRole("button", { name: /^Money for / })).toHaveCount(
    0,
  );
  // N6-05: brokerage is a company-wide broker task; a delegate never sees its panels.
  for (const name of ["Broker authority", "Carriers", "Loads to cover"])
    await expect(page.getByRole("heading", { name, exact: true })).toHaveCount(
      0,
    );
  await board.getByRole("button", { name: `FAKE-TR-${p}` }).click();
  await expect(page.getByRole("button", { name: "Edit trip" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Trip pay" })).toHaveCount(0);
  const assign = page.getByRole("form", { name: "Assign or replace" });
  for (const [role, assignee] of [
    ["Driver", `FAKE Driver ${p}`],
    ["Truck", `FAKE-T-${p}-1`],
  ]) {
    await assign.getByLabel("Role").selectOption({ label: role! });
    await assign.getByLabel("Assignee").selectOption({ label: assignee! });
    await assign.getByRole("button", { name: "Assign" }).click();
    await expect(assign.getByLabel("Assignee")).toHaveValue("");
    await expect(alertOf(page)).toHaveCount(0);
  }
  const event = page.getByRole("form", { name: "Record a stop event" });
  await event
    .getByLabel("Stop")
    .selectOption({ label: "1 · Pickup · FAKE dock, Chicago" });
  await event.getByLabel("Event").selectOption({ label: "Arrived" });
  await event.getByLabel("Date").fill("2031-06-02");
  await event.getByLabel("Time").fill("08:30");
  await event.getByRole("button", { name: "Record" }).click();
  await expect(page.getByText("Status: In transit")).toBeVisible();
  await check(page, testInfo, "dispatcher");
});
