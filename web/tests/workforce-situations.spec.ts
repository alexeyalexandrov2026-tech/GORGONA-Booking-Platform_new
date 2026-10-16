import {
  test,
  expect as immediate,
  type Locator,
  type Page,
  type Request,
} from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { shiftListSchema } from "../lib/workforce-contracts";

// Situations the acceptance record listed as untested. The fixture is
// api/tests/integration/test_i4_situations_browser.py.
// Several of them make a screen read ten small pages one after another, so every
// expectation may wait longer than the default five seconds on a slow machine.
const expect = immediate.configure({ timeout: 30000 });
const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const business = process.env.GBA_I4S_BUSINESS ?? "";
const otherBusiness = process.env.GBA_I4S_OTHER_BUSINESS ?? "";
const homeLocation = process.env.GBA_I4S_LOCATION ?? "";
const zone = process.env.GBA_I4S_ZONE ?? "UTC";
const firstDay = process.env.GBA_I4S_FIRST ?? "";
const faultDay = process.env.GBA_I4S_FAULT_DAY ?? "";
const clockDay = process.env.GBA_I4S_CLOCK_DAY ?? "";
const clockKind = process.env.GBA_I4S_CLOCK_KIND ?? "";
const clockBadTime = process.env.GBA_I4S_CLOCK_BAD_TIME ?? "";
const pagedCount = Number(process.env.GBA_I4S_PAGED_COUNT ?? "0");
const versionedDay = process.env.GBA_I4S_VERSIONED_DAY ?? "";
const dateIn = (timeZone: string) =>
  new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date());
const hourIn = (timeZone: string) =>
  Number(
    new Intl.DateTimeFormat("en-US", {
      timeZone,
      hour: "2-digit",
      hourCycle: "h23",
    }).format(new Date()),
  );
// A browser clock whose calendar date differs from the location's right now.
const farZone = hourIn(zone) >= 6 ? "Pacific/Kiritimati" : "Pacific/Pago_Pago";
test.use({
  baseURL: process.env.GBA_MGMT_BROWSER_URL,
  actionTimeout: 15000,
  timezoneId: farZone,
});
test.beforeEach(() => {
  test.skip(!business, "needs the fixture of test_i4_situations_browser.py");
  test.setTimeout(240000);
});

const NAME = {
  owner: "FAKE user i4s-owner",
  ada: "FAKE user i4s-ada",
  ben: "FAKE user i4s-ben",
} as const;
type Person = keyof typeof NAME;
const plus = (date: string, days: number) => {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
};
const recoveryOf = (page: Page) =>
  page.getByRole("region", { name: "Workforce command recovery", exact: true });
const statusOf = (page: Page) => page.getByRole("status");
const alertOf = (page: Page, text: string | RegExp) =>
  page.getByRole("alert").filter({ hasText: text });
const within = (page: Page, name: string | RegExp) =>
  page.getByRole("region", { name, exact: typeof name === "string" });
const cutNote = (page: Page) =>
  page.getByRole("note").filter({ hasText: "Only the first 1000 records" });
const SHIFT_LIST = /\/workforce\/shifts\?/;
const OPEN_LIST = /\/workforce\/open-shifts\?/;
const SHIFT_SAVE = /\/workforce\/shifts\/[0-9a-f-]{36}$/;
const PRIVACY_SAVE = /\/workforce\/locations\/[0-9a-f-]{36}\/settings$/;
const SHOWN = "Staff see the published shifts of colleagues in this location";
const OWN_ONLY = "Staff see only their own shifts and open shifts";
// Named in full: the page also carries the route announcer of Next.js, another alert.
const READ_FAILED =
  "The studio service is temporarily unavailable. Please try again.";

async function signIn(page: Page, who: Person) {
  const switched = await page.request.post(`${issuer}/fixture/user/${who}`);
  expect(switched.ok()).toBe(true);
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(NAME[who], { exact: true }),
  ).toBeVisible();
  // The owner belongs to two businesses; the scenarios start in the first one.
  if (who === "owner")
    await page
      .getByRole("combobox", { name: "Active Salon" })
      .selectOption(business);
}
async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "You’re signed out." }),
  ).toBeVisible();
}
async function open(
  page: Page,
  screen: "Schedule" | "My shifts" | "Timesheets",
) {
  await page.getByRole("link", { name: screen, exact: true }).click();
  await expect(
    page.getByRole("heading", { name: screen, exact: true, level: 1 }),
  ).toBeVisible();
}
async function accessible(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
}
/** The page never scrolls sideways, on a phone as on a desktop. */
async function fits(page: Page) {
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
}
async function showWeek(page: Page, day: string) {
  await page
    .getByLabel("Location:", { exact: true })
    .selectOption(homeLocation);
  await page.getByLabel("Week from", { exact: true }).fill(day);
}
/** Ask the server for small pages, so a short list already needs several. */
async function pagesOf(page: Page, url: RegExp, size: number) {
  await page.route(url, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const target = new URL(route.request().url());
    target.searchParams.set("limit", String(size));
    await route.continue({ url: target.toString() });
  });
}
/** Answer the next matching command with `reply`; `record` lets the server save it first. */
async function faultOnce(
  page: Page,
  url: RegExp,
  method: string,
  record: boolean,
  reply: { status: number; contentType: string; body: string } | null,
) {
  let done = false;
  await page.route(url, async (route) => {
    if (done || route.request().method() !== method) return route.continue();
    done = true;
    if (record) await route.fetch();
    if (reply) await route.fulfill(reply);
    else await route.abort("failed");
  });
}
async function saveShift(
  page: Page,
  shift: {
    position: string;
    start: string;
    end?: string;
    from: string;
    to: string;
  },
) {
  const form = within(page, "New shift");
  if ((await form.count()) === 0)
    await page.getByRole("button", { name: "New shift", exact: true }).click();
  await form.getByLabel("Position", { exact: true }).fill(shift.position);
  await form.getByLabel("Start date", { exact: true }).fill(shift.start);
  await form
    .getByLabel("End date", { exact: true })
    .fill(shift.end ?? shift.start);
  await form.getByLabel("Start time", { exact: true }).fill(shift.from);
  await form.getByLabel("End time", { exact: true }).fill(shift.to);
  await form
    .getByRole("combobox", { name: "Status", exact: true })
    .selectOption({ label: "Published" });
  await form.getByRole("button", { name: "Save shift", exact: true }).click();
  return form;
}
const listed = (scope: Page | Locator, start: string) =>
  scope.getByRole("heading", { level: 3 }).filter({ hasText: start });
async function settle(page: Page) {
  await page.unrouteAll({ behavior: "wait" });
  await recoveryOf(page)
    .getByRole("button", { name: "Check the result", exact: true })
    .click();
}

test("my shifts keep to four weeks of the location's dates under a far browser clock", async ({
  page,
}, testInfo) => {
  const tag = `FAKE ${testInfo.project.name}`;
  const actor: Person = testInfo.project.name === "desktop" ? "ada" : "ben";
  await signIn(page, actor);
  await open(page, "My shifts");
  // The browser's own calendar date is not the location's date.
  const today = dateIn(zone);
  expect(dateIn(farZone)).not.toBe(today);
  expect(
    await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
  ).toBe(farZone);
  const from = page.getByLabel("Show four weeks from", { exact: true });
  await expect(from).toHaveValue(today);
  await from.fill(firstDay);
  const lane = within(page, "Assigned to me");
  // Times are the location's wall clock, and only its 28 dates are listed.
  await expect(
    listed(lane, `${tag} first · ${firstDay} 08:00–10:00`),
  ).toBeVisible();
  await expect(
    listed(lane, `${tag} last · ${plus(firstDay, 27)} 20:00–22:00`),
  ).toBeVisible();
  await expect(listed(lane, `${tag} before`)).toHaveCount(0);
  await expect(listed(lane, `${tag} after`)).toHaveCount(0);
  await accessible(page);
  await fits(page);
});

test("lists longer than one page are read to the end, and a cut list says so", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name;
  const tag = `FAKE ${project} page`;
  const actor: Person = project === "desktop" ? "ada" : "ben";
  const week =
    (project === "desktop"
      ? process.env.GBA_I4S_PAGED_DESKTOP
      : process.env.GBA_I4S_PAGED_MOBILE) ?? "";
  // The manager's schedule follows the cursors of small pages to the end.
  await signIn(page, "owner");
  await open(page, "Schedule");
  await pagesOf(page, SHIFT_LIST, 5);
  await showWeek(page, week);
  await expect(listed(page, tag)).toHaveCount(pagedCount);
  await expect(cutNote(page)).toHaveCount(0);
  // Ten pages are the limit; a longer list is cut and the screen says so.
  await page.unrouteAll({ behavior: "wait" });
  await pagesOf(page, SHIFT_LIST, 1);
  await page.getByLabel("Week from", { exact: true }).fill(plus(week, 1));
  await expect(cutNote(page)).toBeVisible();
  await expect(listed(page, tag)).toHaveCount(10);
  await accessible(page);
  await fits(page);
  await page.unrouteAll({ behavior: "wait" });
  await signOut(page);

  // The employee's own screen does the same for open shifts.
  await signIn(page, actor);
  await open(page, "My shifts");
  await pagesOf(page, OPEN_LIST, 5);
  const from = page.getByLabel("Show four weeks from", { exact: true });
  await from.fill(week);
  const vacant = within(page, "Open shifts");
  await expect(listed(vacant, tag)).toHaveCount(pagedCount);
  await expect(cutNote(page)).toHaveCount(0);
  await page.unrouteAll({ behavior: "wait" });
  await pagesOf(page, OPEN_LIST, 1);
  await from.fill(plus(week, 1));
  await expect(cutNote(page)).toBeVisible();
  await expect(listed(vacant, tag)).toHaveCount(10);
  await accessible(page);
  await fits(page);
});

test("a slower previous date never replaces the selected open shifts", async ({
  page,
}, testInfo) => {
  const project = testInfo.project.name;
  const actor: Person = project === "desktop" ? "ada" : "ben";
  const week =
    (project === "desktop"
      ? process.env.GBA_I4S_PAGED_DESKTOP
      : process.env.GBA_I4S_PAGED_MOBILE) ?? "";
  const tag = "FAKE " + project + " page";
  const pending = new Set<Request>();
  let released = false;
  let oldDetails = 0;
  const tracked = (request: Request) =>
    request.method() === "GET" &&
    new URL(request.url()).pathname.includes("/workforce/");
  const started = (request: Request) => {
    if (tracked(request)) pending.add(request);
  };
  const finished = (request: Request) => {
    pending.delete(request);
    if (
      released &&
      /\/my-changes\/[0-9a-f-]+\/shifts$/.test(new URL(request.url()).pathname)
    )
      oldDetails++;
  };
  const failed = (request: Request) => {
    pending.delete(request);
  };
  let releaseOld!: () => void;
  let oldReady = false;
  let oldTagCount = -1;
  const release = new Promise<void>((resolve) => {
    releaseOld = resolve;
  });
  let held = false;
  await signIn(page, actor);
  page.on("request", started);
  page.on("requestfinished", finished);
  page.on("requestfailed", failed);
  await open(page, "My shifts");
  const from = page.getByLabel("Show four weeks from", { exact: true });
  await expect(from).toBeVisible();
  // Track only finite workforce reads; authentication can keep other traffic open.
  await expect.poll(() => pending.size).toBe(0);
  await page.route(OPEN_LIST, async (route) => {
    if (held || route.request().method() !== "GET") return route.continue();
    held = true;
    const response = await route.fetch();
    // Earlier scenarios may leave unrelated shifts in the old date window.
    oldTagCount = shiftListSchema
      .parse(await response.json())
      .items.filter((shift) => shift.position.startsWith(tag)).length;
    oldReady = true;
    await release;
    await route.fulfill({ response });
  });
  try {
    await from.fill(firstDay);
    await expect.poll(() => oldReady).toBe(true);
    expect(oldTagCount).toBe(0);
    await from.fill(week);
    const vacant = within(page, "Open shifts");
    await expect(listed(vacant, tag)).toHaveCount(pagedCount);
    // Only the held old response remains; all lookups for the new date finished.
    await expect.poll(() => pending.size).toBe(1);
    released = true;
    releaseOld();
    // The old load reads the latest twenty request details after its held list.
    await expect.poll(() => oldDetails).toBe(20);
    await expect.poll(() => pending.size).toBe(0);
    // Let that completed load publish its state and paint, without a timed sleep.
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    await expect(from).toHaveValue(week);
    await expect(listed(vacant, tag)).toHaveCount(pagedCount);
  } finally {
    releaseOld();
    await page.unrouteAll({ behavior: "ignoreErrors" });
    page.off("request", started);
    page.off("requestfinished", finished);
    page.off("requestfailed", failed);
  }
});

test("a server fault or an unreadable answer to a command is settled by its key", async ({
  page,
}, testInfo) => {
  const tag = `FAKE ${testInfo.project.name} fault`;
  await signIn(page, "owner");
  await open(page, "Schedule");
  await showWeek(page, faultDay);
  const newShift = page.getByRole("button", { name: "New shift", exact: true });

  // The server recorded the shift, then the browser was told of a server fault.
  await faultOnce(page, SHIFT_SAVE, "PUT", true, {
    status: 500,
    contentType: "application/json",
    body: "{}",
  });
  await saveShift(page, {
    position: `${tag} 500`,
    start: faultDay,
    from: "09:00",
    to: "10:00",
  });
  await expect(recoveryOf(page)).toContainText(
    "We could not confirm whether your last action was recorded.",
  );
  await expect(newShift).toBeDisabled();
  await accessible(page);
  await fits(page);
  await settle(page);
  await expect(statusOf(page)).toHaveText("Your earlier action was recorded.");
  await expect(recoveryOf(page)).toHaveCount(0);
  await expect(listed(page, `${tag} 500 · `)).toHaveCount(1);

  // The server recorded the shift, then the answer arrived unreadable.
  await faultOnce(page, SHIFT_SAVE, "PUT", true, {
    status: 200,
    contentType: "text/html",
    body: "<html><body>Bad gateway</body></html>",
  });
  await saveShift(page, {
    position: `${tag} unreadable`,
    start: faultDay,
    from: "11:00",
    to: "12:00",
  });
  await expect(recoveryOf(page)).toBeVisible();
  await settle(page);
  await expect(statusOf(page)).toHaveText("Your earlier action was recorded.");
  await expect(listed(page, `${tag} unreadable · `)).toHaveCount(1);

  // The command never reached the server: nothing is recorded, and it can be discarded.
  await faultOnce(page, SHIFT_SAVE, "PUT", false, {
    status: 503,
    contentType: "text/plain",
    body: "",
  });
  await saveShift(page, {
    position: `${tag} 503`,
    start: faultDay,
    from: "13:00",
    to: "14:00",
  });
  await expect(recoveryOf(page)).toBeVisible();
  await settle(page);
  await expect(recoveryOf(page)).toContainText(
    "The server has no record of your last action",
  );
  await recoveryOf(page)
    .getByRole("button", { name: "Discard this action", exact: true })
    .click();
  await expect(statusOf(page)).toHaveText(
    "The earlier action was discarded. Nothing was recorded.",
  );
  await expect(listed(page, `${tag} 503 · `)).toHaveCount(0);

  // A reading that fails is reported, and the next reading recovers.
  await page.route(SHIFT_LIST, (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
  );
  const week = page.getByLabel("Week from", { exact: true });
  await week.fill(plus(faultDay, -1));
  await expect(alertOf(page, READ_FAILED)).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
  await week.fill(faultDay);
  await expect(alertOf(page, READ_FAILED)).toHaveCount(0);
  await expect(listed(page, `${tag} 500 · `)).toHaveCount(1);
});

test("a lost answer to the privacy setting is settled, not repeated", async ({
  page,
}) => {
  await signIn(page, "owner");
  await open(page, "Schedule");
  await page
    .getByLabel("Location:", { exact: true })
    .selectOption(homeLocation);
  await page.getByRole("button", { name: "Privacy", exact: true }).click();
  const privacy = within(page, "Privacy");
  const shown = privacy.getByRole("radio", { name: SHOWN, exact: true });
  const ownOnly = privacy.getByRole("radio", { name: OWN_ONLY, exact: true });
  const save = privacy.getByRole("button", {
    name: "Save privacy",
    exact: true,
  });
  await expect(shown).toBeChecked();
  await ownOnly.check();
  await faultOnce(page, PRIVACY_SAVE, "PUT", true, null);
  await save.click();
  await expect(recoveryOf(page)).toBeVisible();
  await expect(save).toBeDisabled();
  await accessible(page);
  await settle(page);
  await expect(statusOf(page)).toHaveText("Your earlier action was recorded.");
  await expect(ownOnly).toBeChecked();
  await expect(
    privacy.getByText(/^Version \d+: last changed by you on /),
  ).toBeVisible();
  await expect(save).toBeDisabled();
  await shown.check();
  await save.click();
  await expect(statusOf(page)).toHaveText(
    "Saved. Staff of this location now see colleagues’ published shifts.",
  );
  await expect(shown).toBeChecked();
});

test("a shift across the night the clocks change keeps its real length", async ({
  page,
}, testInfo) => {
  const tag = `FAKE ${testInfo.project.name}`;
  const eve = plus(clockDay, -1);
  await signIn(page, "owner");
  await open(page, "Schedule");
  await showWeek(page, eve);
  await saveShift(page, {
    position: `${tag} clocks`,
    start: eve,
    end: clockDay,
    from: "22:00",
    to: "06:00",
  });
  await expect(statusOf(page)).toHaveText("Published as an open shift.");
  await expect(
    listed(page, `${tag} clocks · ${eve} 22:00–${clockDay} 06:00`),
  ).toHaveCount(1);
  // A wall-clock time that the change makes ambiguous or impossible is refused.
  const form = await saveShift(page, {
    position: `${tag} impossible`,
    start: clockDay,
    from: clockBadTime,
    to: "08:00",
  });
  await expect(
    alertOf(
      page,
      clockKind === "fold"
        ? "occurs twice because the clocks change"
        : "does not exist because the clocks change",
    ),
  ).toBeVisible();
  await accessible(page);
  await form.getByRole("button", { name: "Close", exact: true }).click();
  await expect(listed(page, `${tag} impossible`)).toHaveCount(0);
});

test("a company that never enabled the module shows closed screens", async ({
  page,
}) => {
  await signIn(page, "owner");
  await page
    .getByRole("combobox", { name: "Active Salon" })
    .selectOption(otherBusiness);
  await open(page, "Schedule");
  await expect(
    page.getByText("Scheduling is turned off for this business.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "New shift", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("No shifts in this location for these seven days."),
  ).toBeVisible();
  await accessible(page);
  await fits(page);
  await page.getByRole("button", { name: "Privacy", exact: true }).click();
  await expect(
    within(page, "Privacy").getByRole("radio", { name: OWN_ONLY, exact: true }),
  ).toBeDisabled();
  await open(page, "Timesheets");
  await expect(
    page.getByText("You are not on the staff schedule yet", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("You have no time records yet.")).toBeVisible();
  await accessible(page);
  await open(page, "My shifts");
  await expect(
    page.getByText("You are not on the staff schedule yet.", { exact: false }),
  ).toBeVisible();
  await accessible(page);
});

test("a shift with more than twenty versions lists the latest twenty and says so", async ({
  page,
}, testInfo) => {
  const tag = `FAKE ${testInfo.project.name} versioned`;
  await signIn(page, "owner");
  await open(page, "Schedule");
  await showWeek(page, versionedDay);
  await page
    .getByRole("button", { name: new RegExp(`^Versions of ${tag} `) })
    .click();
  const versions = within(page, new RegExp(`^Versions of ${tag} `));
  await expect(versions.getByRole("listitem")).toHaveCount(20);
  await expect(versions.getByRole("listitem").first()).toContainText(
    "Version 21: Draft",
  );
  await expect(versions.getByRole("listitem").last()).toContainText(
    "Version 2: Draft",
  );
  await expect(
    versions.getByText("Only the latest 20 versions are listed."),
  ).toBeVisible();
  await accessible(page);
  await fits(page);
});

test("more than twenty requests stay listed; the oldest names no shift", async ({
  page,
}, testInfo) => {
  const tag = `FAKE ${testInfo.project.name} wanted`;
  const actor: Person = testInfo.project.name === "desktop" ? "ada" : "ben";
  await signIn(page, actor);
  await open(page, "My shifts");
  await page.getByLabel("Show four weeks from", { exact: true }).fill(firstDay);
  const requests = within(page, "My requests");
  const asked = requests
    .getByRole("heading", { level: 3 })
    .filter({ hasText: "Open shift request: " });
  // Every request is listed; shift details are read for the latest twenty only.
  await expect(asked).toHaveCount(21);
  await expect(asked.filter({ hasText: tag })).toHaveCount(20);
  await expect(
    asked.filter({ hasText: "a shift outside the dates shown" }),
  ).toHaveCount(1);
  await accessible(page);
  await fits(page);
});
