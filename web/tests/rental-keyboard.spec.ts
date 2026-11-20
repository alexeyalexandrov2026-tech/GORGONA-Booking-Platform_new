import {
  test,
  expect,
  type Locator,
  type Page,
  type TestInfo,
} from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// R-10 (package R): the rental screens used with the keyboard alone. Once signed in nothing is
// clicked: Tab moves, Enter and Space act, text is typed, and every stop must be on screen and
// wear the shared focus ring. Runs on the R8a seed (owner r8a-owner, customer FAKE Renter, a
// branch); what it creates has its own codes and days, so it can follow rental.spec.ts. Date and
// time fields are filled, not typed: their segmented editing depends on the locale.
test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const OWNER = "FAKE user r8a-owner";

async function signIn(page: Page) {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(OWNER, { exact: true }),
  ).toBeVisible();
}

async function accessible(page: Page, testInfo: TestInfo, name: string) {
  const axe = await new AxeBuilder({ page })
    .include(".rental-screen")
    .analyze();
  expect(axe.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
}

/** The focused control is on screen and wears the focus ring (the shared :focus-visible outline). */
async function ringed(page: Page) {
  const focused = page.locator(":focus");
  await expect(focused).toHaveCount(1);
  await expect(focused).toBeVisible();
  const ring = await focused.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      what: element.outerHTML.slice(0, 90),
      shown: element.matches(":focus-visible"),
      style: style.outlineStyle,
      width: Number.parseFloat(style.outlineWidth),
    };
  });
  expect(ring.shown, `${ring.what} matches :focus-visible`).toBe(true);
  expect(ring.style, `${ring.what} has an outline`).not.toBe("none");
  expect(ring.width, `${ring.what} outline width`).toBeGreaterThan(0);
}

/** A place to start from: the only use of focus(). The key presses do the rest. */
async function startAt(target: Locator) {
  await target.focus();
  await expect(target).toBeFocused();
}

/** Press Tab until the control has focus; every stop on the way must be on screen with its ring. */
async function tabTo(page: Page, target: Locator, limit = 40) {
  for (let presses = 0; presses <= limit; presses += 1) {
    if (await target.evaluate((element) => element === document.activeElement))
      return;
    await page.keyboard.press("Tab");
    await ringed(page);
  }
  throw new Error(`Tab did not reach ${String(target)} in ${limit} presses`);
}

/** Put the keyboard back at the top of the document, as after a page load. */
async function atTheTop(page: Page) {
  await page.evaluate(() => {
    document.body.tabIndex = -1;
    document.body.focus();
    document.body.removeAttribute("tabindex");
    window.scrollTo(0, 0);
  });
}

/** The period fields are started with focus() and filled: Tab inside a date or time input only walks its segments. */
async function period(form: Locator, from: string, to: string) {
  const fields = [
    ["From date", from],
    ["From time", "10:00"],
    ["To date", to],
    ["To time", "10:00"],
  ] as const;
  for (const [label, value] of fields) {
    const field = form.getByLabel(label);
    await startAt(field);
    await field.fill(value);
  }
}

/** What a disclosure button controls: it exists whether the button is open or closed. */
async function controlled(page: Page, button: Locator) {
  const id = await button.getAttribute("aria-controls");
  expect(id, "the button names what it opens").toBeTruthy();
  return page.locator(`[id="${id}"]`);
}

test("an owner runs the rental screens with the keyboard alone", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);
  const project = testInfo.project.name as "desktop" | "mobile";
  const code = `FAKE-KB-${project.toUpperCase()}`;
  const unitId = `FAKE-KU-${project}`;
  // Each project books its own days, apart from the days rental.spec.ts books.
  const [from, to] =
    project === "desktop"
      ? ["2032-06-01", "2032-06-03"]
      : ["2032-07-01", "2032-07-03"];
  const cancellations: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      /\/bookings\/[^/]+\/cancellation$/.test(new URL(request.url()).pathname)
    )
      cancellations.push(request.url());
  });

  // The rental screen, reached from its navigation link.
  await signIn(page);
  await startAt(page.getByRole("link", { name: "Rental", exact: true }));
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Rental", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Loading the rental catalogue…")).toBeHidden({
    timeout: 15000,
  });
  await accessible(page, testInfo, `${project}-keyboard-empty`);

  // From the top of the page the first Tab reaches the skip link, which leads into the main part.
  await atTheTop(page);
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content", exact: true }),
  ).toBeFocused();
  await ringed(page);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);
  await page.keyboard.press("Tab");
  await expect(page.locator("main#main-content :focus")).toHaveCount(1);
  await ringed(page);

  // A class, typed and saved with the keyboard.
  const classForm = page.getByRole("form", { name: "Class", exact: true });
  await tabTo(page, classForm.getByLabel("Code"));
  await page.keyboard.type(code);
  await tabTo(page, classForm.getByLabel("Name"));
  await page.keyboard.type(`FAKE keyboard van ${project}`);
  await tabTo(page, classForm.getByRole("button", { name: "Save class" }));
  await page.keyboard.press("Enter");
  await expect(page.getByText(`Class ${code} saved.`)).toBeVisible();

  // Activating the class code opens it for editing and moves focus to the form's heading.
  const classes = page.getByRole("table", { name: "Classes", exact: true });
  await startAt(classes.getByRole("button", { name: code, exact: true }));
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: `Edit class ${code}`, exact: true }),
  ).toBeFocused();
  await ringed(page);

  // A unit of that class at the first branch: a select answers to typing and the arrow keys.
  const unitForm = page.getByRole("form", { name: "Unit", exact: true });
  const unitClass = unitForm.getByLabel("Class");
  await startAt(unitClass);
  await page.keyboard.type(code);
  await expect(unitClass.locator("option:checked")).toContainText(code);
  await tabTo(page, unitForm.getByLabel("Identifier"));
  await page.keyboard.type(unitId);
  const unitBranch = unitForm.getByLabel("Branch");
  await tabTo(page, unitBranch);
  await page.keyboard.press("ArrowDown");
  await expect(unitBranch.locator("option:checked")).not.toHaveText("Choose");
  await tabTo(page, unitForm.getByRole("button", { name: "Save unit" }));
  await page.keyboard.press("Space");
  await expect(page.getByText(`Unit ${unitId} saved.`)).toBeVisible();

  // A booking of that class for the customer, from that branch back to it.
  const book = page.getByRole("form", { name: "Booking", exact: true });
  const bookClass = book.getByLabel("Class");
  await startAt(bookClass);
  await page.keyboard.type(code);
  await expect(bookClass.locator("option:checked")).toContainText(code);
  const customer = book.getByLabel("Customer");
  await tabTo(page, customer);
  await page.keyboard.type("FAKE");
  await expect(customer.locator("option:checked")).toHaveText("FAKE Renter");
  await tabTo(page, book.getByLabel("Pickup branch"));
  await page.keyboard.press("ArrowDown");
  await tabTo(page, book.getByLabel("Return branch"));
  await page.keyboard.press("ArrowDown");
  await period(book, from, to);
  await startAt(book.getByLabel("Note"));
  await tabTo(page, book.getByRole("button", { name: "Save booking" }));
  await page.keyboard.press("Enter");
  const saved = page.getByText(/^Booking \d+ saved\.$/);
  await expect(saved).toBeVisible();
  const number = ((await saved.textContent()) ?? "").match(/\d+/)?.[0] ?? "";
  expect(number).not.toBe("");

  // Activating "Booking N" opens the booking and moves focus to its heading.
  const bookings = page.getByRole("table", { name: "Bookings", exact: true });
  await startAt(
    bookings.getByRole("button", { name: `Booking ${number}`, exact: true }),
  );
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: `Booking ${number}`, exact: true }),
  ).toBeFocused();
  await ringed(page);

  // The customer access disclosure names its panel, closed or open, and opens with Enter.
  const access = page.getByRole("region", { name: "Customer proposal access" });
  const toggle = access.getByRole("button", {
    name: /^(Manage|Close) customer access$/,
  });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  const panel = await controlled(page, toggle);
  await expect(panel).toHaveCount(1);
  await expect(panel).toBeEmpty();
  await startAt(toggle);
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(
    panel.getByRole("form", { name: "Rental customer company" }),
  ).toBeVisible();
  await accessible(page, testInfo, `${project}-keyboard-booking`);
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(panel).toBeEmpty();

  // Damage marks: after a mark is removed focus is never left on the button that went away.
  const inspect = page.getByRole("form", { name: "Inspection", exact: true });
  const add = inspect.getByRole("button", { name: "Add mark" });
  for (const area of ["FAKE scratch", "FAKE dent", "FAKE chip"]) {
    await startAt(inspect.getByLabel("Mark area"));
    await page.keyboard.type(area);
    await tabTo(page, add);
    await page.keyboard.press("Enter");
    await expect(
      inspect.getByRole("listitem").filter({ hasText: area }),
    ).toHaveCount(1);
  }
  const marks = inspect.getByRole("list", { name: "Marks to record" });
  const remove = (position: number) =>
    marks.getByRole("button", { name: `Remove mark ${position}`, exact: true });
  // From the middle: focus goes to the mark that took its place.
  await startAt(remove(2));
  await page.keyboard.press("Enter");
  await expect(marks.getByRole("listitem")).toHaveCount(2);
  await expect(remove(2)).toBeFocused();
  await expect(marks.getByRole("listitem").nth(1)).toContainText("FAKE chip");
  await ringed(page);
  // The last one: focus goes to the one before it.
  await page.keyboard.press("Enter");
  await expect(marks.getByRole("listitem")).toHaveCount(1);
  await expect(remove(1)).toBeFocused();
  // The only one: focus goes to Add mark.
  await page.keyboard.press("Enter");
  await expect(marks).toHaveCount(0);
  await expect(add).toBeFocused();
  await ringed(page);

  // Cancelling takes a reason and a confirmation: Enter without the confirmation is refused.
  const cancel = page.getByRole("form", {
    name: "Cancel booking",
    exact: true,
  });
  const confirm = cancel.getByLabel("I confirm this booking will be cancelled");
  await startAt(cancel.getByLabel("Reason"));
  await page.keyboard.type(`FAKE keyboard plans changed ${project}`);
  await page.keyboard.press("Enter");
  await expect(confirm).toBeFocused();
  await ringed(page);
  expect(cancellations).toHaveLength(0);
  await expect(page.getByText(`Booking ${number} cancelled.`)).toHaveCount(0);
  const row = bookings.getByRole("row").filter({
    has: page.getByRole("button", { name: `Booking ${number}`, exact: true }),
  });
  await expect(row).toContainText("Booked");
  // Space ticks the box; the submit button is the next stop, and Enter cancels.
  await page.keyboard.press("Space");
  await expect(confirm).toBeChecked();
  await tabTo(page, cancel.getByRole("button", { name: "Cancel booking" }));
  await page.keyboard.press("Enter");
  await expect(page.getByText(`Booking ${number} cancelled.`)).toBeVisible();
  expect(cancellations).toHaveLength(1);
  await expect(row).toContainText("Cancelled");
  await accessible(page, testInfo, `${project}-keyboard-cancelled`);
});
