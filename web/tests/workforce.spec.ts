import { test, expect, type Locator, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });
const issuer = process.env.GBA_TEST_OIDC_ISSUER;
const phase = process.env.GBA_I4_PHASE;
const business = process.env.GBA_I4_BUSINESS ?? "";
const otherBusiness = process.env.GBA_I4_OTHER_BUSINESS ?? "";
const homeLocation = process.env.GBA_I4_LOCATION ?? "";
const firstDay = process.env.GBA_I4_DAY ?? "";
const pastDay = process.env.GBA_I4_PAST ?? "";
const NAME = {
  owner: "FAKE user i4-owner",
  manager: "FAKE user i4-manager",
  ada: "FAKE user i4-ada",
  ben: "FAKE user i4-ben",
  cy: "FAKE user i4-cy",
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

async function signIn(page: Page, who: Person, choose = true) {
  if (choose) {
    const switched = await page.request.post(`${issuer}/fixture/user/${who}`);
    expect(switched.ok()).toBe(true);
  }
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".mgmt-header-actions").getByText(NAME[who], { exact: true }),
  ).toBeVisible();
  // The owner belongs to two businesses; the scenario runs in the first one.
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
async function option(select: Locator, text: string | RegExp) {
  const value = await select
    .locator("option")
    .filter({ hasText: text })
    .first()
    .getAttribute("value");
  expect(value).toBeTruthy();
  await select.selectOption(value!);
}
/** Let the server record the next matching command, then lose its answer. */
async function loseAnswer(page: Page, url: string, method: string) {
  let lost = false;
  await page.route(url, async (route) => {
    if (!lost && route.request().method() === method) {
      lost = true;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
}
/** Drop the next matching command before it reaches the server. */
async function dropRequest(page: Page, url: string, method: string) {
  let dropped = false;
  await page.route(url, async (route) => {
    if (!dropped && route.request().method() === method) {
      dropped = true;
      await route.abort("failed");
    } else await route.continue();
  });
}
async function savedReferences(page: Page) {
  return page.evaluate(() =>
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith("gorgona.workforce.recovery."))
      .map((key) => sessionStorage.getItem(key) ?? ""),
  );
}
async function fillShift(
  form: Locator,
  shift: {
    position?: string;
    date?: string;
    from?: string;
    to?: string;
    skill?: string;
    status?: "Draft" | "Published" | "Cancelled";
    assignee?: string;
  },
) {
  if (shift.position)
    await form.getByLabel("Position", { exact: true }).fill(shift.position);
  if (shift.date) {
    await form.getByLabel("Start date", { exact: true }).fill(shift.date);
    await form.getByLabel("End date", { exact: true }).fill(shift.date);
  }
  if (shift.from)
    await form.getByLabel("Start time", { exact: true }).fill(shift.from);
  if (shift.to)
    await form.getByLabel("End time", { exact: true }).fill(shift.to);
  if (shift.skill) await form.getByLabel(shift.skill, { exact: true }).check();
  if (shift.status)
    await form
      .getByRole("combobox", { name: "Status", exact: true })
      .selectOption({ label: shift.status });
  if (shift.assignee)
    await form
      .getByRole("combobox", { name: "Assigned to", exact: true })
      .selectOption({ label: shift.assignee });
  await form.getByRole("button", { name: "Save shift", exact: true }).click();
}
const SHOWN = "Staff see the published shifts of colleagues in this location";
const OWN_ONLY = "Staff see only their own shifts and open shifts";
const hiddenNote = (page: Page) =>
  page
    .getByRole("note")
    .filter({ hasText: "does not show colleagues’ shifts" });
async function openPrivacy(page: Page) {
  await page.getByRole("button", { name: "Privacy", exact: true }).click();
  return within(page, "Privacy");
}
async function showWeek(page: Page, day: string, company: boolean) {
  if (company)
    await page
      .getByLabel("Location:", { exact: true })
      .selectOption(homeLocation);
  await page.getByLabel("Week from", { exact: true }).fill(day);
}

test("workforce stays closed until it is accepted", async ({ page }) => {
  test.skip(phase !== "closed", "runs against the registry as it is");
  await signIn(page, "owner");
  await open(page, "Schedule");
  await expect(
    page.getByText("Scheduling is not available for this business yet.", {
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
  // The privacy setting is readable and closed to change like everything else.
  const untouched = await openPrivacy(page);
  await expect(
    untouched.getByText(
      "Never changed: colleagues’ shifts are visible by default.",
    ),
  ).toBeVisible();
  await expect(
    untouched.getByRole("radio", { name: SHOWN, exact: true }),
  ).toBeChecked();
  await expect(
    untouched.getByRole("radio", { name: OWN_ONLY, exact: true }),
  ).toBeDisabled();
  await accessible(page);
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

test("schedule, own shifts and timesheets with real gates, recovery and roles", async ({
  page,
}, testInfo) => {
  test.skip(phase !== "enabled", "needs the fixture's opened readiness");
  test.setTimeout(600000);
  const project = testInfo.project.name;
  const tag = `FAKE ${project}`;
  const actor: Person = project === "desktop" ? "ada" : "ben";
  const colleague: Person = project === "desktop" ? "ben" : "ada";
  const day = plus(firstDay, project === "desktop" ? 0 : 3);
  const skill = `${tag} barista`;
  const root = `/v1/businesses/${business}/workforce`;
  const window = `starts=${day}T00:00:00Z&ends=${plus(day, 7)}T00:00:00Z`;

  // --- The owner plans: staff, a skill, shifts, a stale edit, own time. ---
  await signIn(page, "owner");
  await open(page, "Schedule");
  // The week starts today in the location's own time, not on the UTC date.
  const places = page.getByLabel("Location:", { exact: true });
  const zone = ((await places.locator("option:checked").textContent()) ?? "")
    .split(" · ")
    .pop()!;
  await expect(page.getByLabel("Week from", { exact: true })).toHaveValue(
    new Intl.DateTimeFormat("en-CA", { timeZone: zone }).format(new Date()),
  );
  // An unsaved privacy choice of one location is never shown for another.
  const drafted = await openPrivacy(page);
  await places.selectOption(homeLocation);
  await drafted.getByRole("radio", { name: OWN_ONLY, exact: true }).check();
  await page.getByRole("button", { name: "Shifts", exact: true }).click();
  const elsewhere = await places
    .locator("option")
    .evaluateAll(
      (options, home) =>
        options
          .map((option) => (option as HTMLOptionElement).value)
          .find((value) => value !== home) ?? "",
      homeLocation,
    );
  expect(elsewhere).not.toBe("");
  await places.selectOption(elsewhere);
  const other = await openPrivacy(page);
  await expect(
    other.getByRole("radio", { name: SHOWN, exact: true }),
  ).toBeChecked();
  await expect(
    other.getByRole("button", { name: "Save privacy", exact: true }),
  ).toBeDisabled();
  await places.selectOption(homeLocation);
  await expect(
    other.getByRole("radio", { name: SHOWN, exact: true }),
  ).toBeChecked();
  await page
    .getByRole("button", { name: "Staff and skills", exact: true })
    .click();
  const staff = within(page, "Staff");
  // Staff names the location a company-wide person would be added to.
  await expect(places).toHaveValue(homeLocation);
  // Company-wide access shows the other branch too.
  await expect(
    staff.getByRole("heading", { name: NAME.cy, exact: true }),
  ).toBeVisible();
  const added = `FAKE user i4-new-${project}`;
  await page
    .getByRole("button", {
      name: new RegExp(`^Add ${added} to the schedule of `),
    })
    .click();
  await expect(statusOf(page)).toContainText(`${added} is now on the schedule`);
  await page.getByRole("button", { name: "New skill", exact: true }).click();
  const skillForm = within(page, "New skill");
  await expect(
    skillForm.getByRole("heading", { name: "New skill", exact: true }),
  ).toBeFocused();
  await skillForm
    .getByLabel("Code (capital letters, digits and underscores)", {
      exact: true,
    })
    .fill(`FAKE_${project.toUpperCase()}`);
  await skillForm.getByLabel("Name", { exact: true }).fill(skill);
  await skillForm
    .getByRole("button", { name: "Save skill", exact: true })
    .click();
  await expect(statusOf(page)).toHaveText("Skill saved.");
  await page
    .getByRole("button", { name: `Skills of ${NAME[actor]}`, exact: true })
    .click();
  const actorSkills = within(page, `Skills of ${NAME[actor]}`);
  await actorSkills
    .getByRole("button", { name: `Grant ${skill}`, exact: true })
    .click();
  await expect(statusOf(page)).toHaveText(
    `${skill} granted to ${NAME[actor]}.`,
  );
  await expect(
    actorSkills
      .getByRole("listitem")
      .filter({ hasText: skill })
      .getByText("Step 1: granted from", { exact: false }),
  ).toBeVisible();
  await accessible(page);
  await actorSkills.getByRole("button", { name: "Close", exact: true }).click();

  await page.getByRole("button", { name: "Shifts", exact: true }).click();
  await showWeek(page, day, true);
  // Keyboard: the form takes focus, Escape closes it and focus returns.
  const newShift = page.getByRole("button", { name: "New shift", exact: true });
  await newShift.focus();
  await page.keyboard.press("Enter");
  const shiftForm = within(page, "New shift");
  await expect(
    shiftForm.getByRole("heading", { name: "New shift", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(shiftForm).toHaveCount(0);
  await expect(newShift).toBeFocused();

  // A person without the required skill is refused; the form keeps its values.
  await newShift.click();
  await fillShift(shiftForm, {
    position: `${tag} morning`,
    date: day,
    from: "09:00",
    to: "13:00",
    skill,
    status: "Published",
    assignee: NAME[colleague],
  });
  await expect(alertOf(page, "does not hold a required skill")).toBeVisible();
  await accessible(page);
  await fillShift(shiftForm, { assignee: NAME[actor] });
  await expect(statusOf(page)).toHaveText(
    `Published and assigned to ${NAME[actor]}.`,
  );
  await newShift.click();
  await fillShift(shiftForm, {
    position: `${tag} evening`,
    date: day,
    from: "14:00",
    to: "18:00",
    status: "Published",
    assignee: NAME[colleague],
  });
  await expect(statusOf(page)).toHaveText(
    `Published and assigned to ${NAME[colleague]}.`,
  );
  await newShift.click();
  await fillShift(shiftForm, {
    position: `${tag} open`,
    date: day,
    from: "19:00",
    to: "22:00",
    status: "Published",
  });
  await expect(statusOf(page)).toHaveText("Published as an open shift.");
  await newShift.click();
  await fillShift(shiftForm, {
    position: `${tag} draft`,
    date: day,
    from: "06:00",
    to: "07:00",
    status: "Draft",
  });
  await expect(statusOf(page)).toHaveText("Draft saved.");
  await page
    .getByRole("button", { name: new RegExp(`^Edit ${tag} draft `) })
    .click();
  await fillShift(within(page, new RegExp(`^Edit ${tag} draft `)), {
    status: "Cancelled",
  });
  await expect(statusOf(page)).toHaveText(
    "Shift cancelled. Its history is kept.",
  );
  await page
    .getByRole("button", { name: new RegExp(`^Versions of ${tag} draft `) })
    .click();
  const versions = within(page, new RegExp(`^Versions of ${tag} draft `));
  await expect(versions.getByRole("listitem")).toHaveCount(2);
  await expect(versions.getByRole("listitem").first()).toContainText(
    "Version 2: Cancelled",
  );
  await expect(versions.getByRole("listitem").last()).toContainText(
    "Version 1: Draft",
  );
  await versions.getByRole("button", { name: "Close", exact: true }).click();
  // A published shift cannot go back to a draft, so its form does not offer it.
  await page
    .getByRole("button", { name: new RegExp(`^Edit ${tag} open `) })
    .click();
  await expect(
    within(page, new RegExp(`^Edit ${tag} open `))
      .getByRole("combobox", { name: "Status", exact: true })
      .locator("option"),
  ).toHaveText(["Published", "Cancelled"]);
  await page.keyboard.press("Escape");

  // The same shift changes in another tab; this tab's stale edit is refused.
  const second = await page.context().newPage();
  await signIn(second, "owner", false);
  await open(second, "Schedule");
  await showWeek(second, day, true);
  await second
    .getByRole("button", { name: new RegExp(`^Edit ${tag} evening `) })
    .click();
  await fillShift(within(second, new RegExp(`^Edit ${tag} evening `)), {
    position: `${tag} evening late`,
  });
  await expect(statusOf(second)).toHaveText(
    `Published and assigned to ${NAME[colleague]}.`,
  );
  await second.close();
  await page
    .getByRole("button", { name: new RegExp(`^Edit ${tag} evening `) })
    .click();
  const stale = within(page, new RegExp(`^Edit ${tag} evening `));
  await fillShift(stale, { to: "18:30" });
  await expect(alertOf(page, "This record changed or overlaps")).toBeVisible();
  await stale.getByRole("button", { name: "Close", exact: true }).click();
  const shifts = within(page, "Shifts");
  await expect(
    shifts.getByRole("heading", {
      name: new RegExp(`^${tag} evening late .* 14:00–18:00$`),
    }),
  ).toBeVisible();
  await fits(page);

  // The colleague gets the skill before any handover names them.
  await page
    .getByRole("button", { name: "Staff and skills", exact: true })
    .click();
  await page
    .getByRole("button", { name: `Skills of ${NAME[colleague]}`, exact: true })
    .click();
  await within(page, `Skills of ${NAME[colleague]}`)
    .getByRole("button", { name: `Grant ${skill}`, exact: true })
    .click();
  await expect(statusOf(page)).toHaveText(
    `${skill} granted to ${NAME[colleague]}.`,
  );

  // The owner's own time: approving it is allowed and visibly marked. The
  // answer is lost, and the saved reference follows neither business nor person.
  await open(page, "Timesheets");
  await page.getByRole("button", { name: "Clock in", exact: true }).click();
  await expect(statusOf(page)).toHaveText("You are clocked in.");
  await page.getByRole("button", { name: "Clock out", exact: true }).click();
  await expect(statusOf(page)).toContainText("You are clocked out.");
  await loseAnswer(page, "**/workforce/time-entries/*/events", "POST");
  await page
    .getByRole("button", {
      name: new RegExp(`^Approve my own time ${NAME.owner} `),
    })
    .click();
  await expect(recoveryOf(page)).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
  const ownerSaved = await savedReferences(page);
  expect(ownerSaved).toHaveLength(1);
  expect(Object.keys(JSON.parse(ownerSaved[0]!) as object).sort()).toEqual([
    "actor_id",
    "business_id",
    "key",
    "reference",
    "saved_at",
    "schema_version",
  ]);
  expect(ownerSaved[0]).not.toContain("i4-");
  expect(ownerSaved[0]).not.toContain("reason");
  await expect(
    page.getByRole("button", { name: "Clock in", exact: true }),
  ).toBeDisabled();
  await accessible(page);
  await page
    .getByRole("combobox", { name: "Active Salon" })
    .selectOption(otherBusiness);
  await expect(
    page.getByText("Scheduling is turned off for this business.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(recoveryOf(page)).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "Active Salon" })
    .selectOption(business);
  await expect(statusOf(page)).toHaveText("Your earlier action was recorded.");
  await expect(recoveryOf(page)).toHaveCount(0);
  expect(await savedReferences(page)).toHaveLength(0);
  await expect(
    within(page, "My time records")
      .getByText("Approved by the owner for their own time")
      .first(),
  ).toBeVisible();

  // --- The employee: no management area, in the screen or on the server. ---
  await signOut(page);
  const authorized = page.waitForRequest(
    (request) =>
      request.url().includes("/workforce/desk") &&
      request.headers()["authorization"] != null,
  );
  await signIn(page, actor);
  await expect(
    page.getByRole("link", { name: "Schedule", exact: true }),
  ).toHaveCount(0);
  // The address opened by hand, without a reload that would end the session.
  await page.evaluate(() =>
    (
      window as unknown as { next: { router: { push(path: string): void } } }
    ).next.router.push("/schedule/"),
  );
  await expect(
    page.getByText("This area requires owner or manager access."),
  ).toBeVisible();
  await open(page, "My shifts");
  const employee = {
    authorization: (await authorized).headers()["authorization"]!,
  };
  for (const path of [
    "/directory",
    "/staff",
    "/skills",
    `/shifts?${window}`,
    "/changes",
    "/time-entries",
  ])
    expect(
      (await page.request.get(root + path, { headers: employee })).status(),
      path,
    ).toBe(403);
  await page.getByLabel("Show four weeks from", { exact: true }).fill(day);
  const assigned = within(page, "Assigned to me");
  await expect(
    assigned.getByRole("heading", { name: new RegExp(`^${tag} morning `) }),
  ).toBeVisible();

  // A handover is recorded, its answer is lost, and another person signs in.
  await loseAnswer(page, "**/workforce/changes/*", "PUT");
  const handOver = page.getByRole("button", {
    name: new RegExp(`^Hand over ${tag} morning `),
  });
  await handOver.focus();
  await page.keyboard.press("Enter");
  const handover = within(page, new RegExp(`^Hand over ${tag} morning `));
  await expect(handover.getByRole("heading")).toBeFocused();
  await handover
    .getByRole("combobox", { name: "Colleague", exact: true })
    .selectOption({ label: NAME[colleague] });
  await handover
    .getByRole("button", { name: "Send request", exact: true })
    .click();
  await expect(recoveryOf(page)).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
  const saved = await savedReferences(page);
  expect(saved).toHaveLength(1);
  for (const leaked of ["morning", "i4-", "position", "body"])
    expect(saved[0]).not.toContain(leaked);
  await accessible(page);
  await signOut(page);
  await signIn(page, colleague);
  await open(page, "My shifts");
  await expect(recoveryOf(page)).toHaveCount(0);
  const incoming = within(page, "My requests")
    .getByRole("listitem")
    .filter({ hasText: `${tag} morning` });
  // The recorded request arrived exactly once.
  await expect(incoming).toHaveCount(1);
  await incoming
    .getByRole("button", { name: new RegExp("^Accept Handover: ") })
    .click();
  await expect(statusOf(page)).toHaveText("Accepted. A manager decides next.");

  // Back as the employee, after a full reload: settled by the original key.
  await signOut(page);
  await signIn(page, actor);
  await open(page, "My shifts");
  await expect(statusOf(page)).toHaveText("Your earlier action was recorded.");
  await expect(recoveryOf(page)).toHaveCount(0);
  expect(await savedReferences(page)).toHaveLength(0);
  await page.getByLabel("Show four weeks from", { exact: true }).fill(day);
  const requests = within(page, "My requests");
  const sent = requests
    .getByRole("listitem")
    .filter({ hasText: `${tag} morning` });
  await expect(sent).toHaveCount(1);
  await expect(sent).toContainText("Accepted, waiting for a manager");

  // A swap needs the colleague's own shift; an open shift needs a confirmation.
  await page
    .getByRole("button", { name: new RegExp(`^Swap ${tag} swap `) })
    .click();
  const swap = within(page, new RegExp(`^Swap ${tag} swap `));
  await swap
    .getByRole("combobox", { name: "Colleague", exact: true })
    .selectOption({ label: NAME[colleague] });
  await option(
    swap.getByRole("combobox", { name: "Their shift", exact: true }),
    `${tag} evening late`,
  );
  await swap.getByRole("button", { name: "Send request", exact: true }).click();
  await expect(statusOf(page)).toContainText(
    `Request sent to ${NAME[colleague]}.`,
  );
  await within(page, "Open shifts")
    .getByRole("button", { name: new RegExp(`^Ask for ${tag} open `) })
    .click();
  await expect(statusOf(page)).toContainText("Request saved.");
  await requests
    .getByRole("button", {
      name: new RegExp(`^Confirm Open shift request: ${tag} open `),
    })
    .click();
  await expect(statusOf(page)).toHaveText("Accepted. A manager decides next.");
  for (const position of ["extra", "spare"]) {
    await page
      .getByRole("button", {
        name: new RegExp(`^Hand over ${tag} ${position} `),
      })
      .click();
    const form = within(page, new RegExp(`^Hand over ${tag} ${position} `));
    await form
      .getByRole("combobox", { name: "Colleague", exact: true })
      .selectOption({ label: NAME[colleague] });
    await form
      .getByRole("button", { name: "Send request", exact: true })
      .click();
    await expect(statusOf(page)).toContainText(
      `Request sent to ${NAME[colleague]}.`,
    );
  }
  await requests
    .getByRole("button", {
      name: new RegExp(`^Withdraw Handover: ${tag} spare `),
    })
    .click();
  await expect(statusOf(page)).toHaveText(
    "Request withdrawn. Nothing changed.",
  );
  await requests
    .getByRole("button", {
      name: new RegExp(`^History of Handover: ${tag} spare `),
    })
    .click();
  const steps = within(page, new RegExp(`^History of Handover: ${tag} spare `));
  await expect(steps.getByRole("listitem")).toHaveCount(2);
  await expect(steps.getByRole("listitem").last()).toContainText(
    "Step 2: Withdrawn by you",
  );
  await accessible(page);
  await fits(page);
  await page.keyboard.press("Escape");
  await expect(steps).toHaveCount(0);

  // Own time. A command that never arrived is sent again under the same key;
  // another one is discarded, and only then started afresh.
  await open(page, "Timesheets");
  const records = within(page, "My time records");
  await expect(
    records.getByText("You have no time records yet."),
  ).toBeVisible();
  await dropRequest(page, "**/workforce/time-entries/*", "PUT");
  await page.getByRole("button", { name: "Clock in", exact: true }).click();
  await expect(recoveryOf(page)).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
  await recoveryOf(page)
    .getByRole("button", { name: "Check the result", exact: true })
    .click();
  await expect(recoveryOf(page)).toContainText(
    "The server has no record of your last action",
  );
  await recoveryOf(page)
    .getByRole("button", { name: "Send the same action again", exact: true })
    .click();
  await expect(statusOf(page)).toHaveText("You are clocked in.");
  await expect(recoveryOf(page)).toHaveCount(0);
  await dropRequest(page, "**/workforce/time-entries/*/events", "POST");
  await page.getByRole("button", { name: "Start break", exact: true }).click();
  await expect(recoveryOf(page)).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
  await recoveryOf(page)
    .getByRole("button", { name: "Check the result", exact: true })
    .click();
  await recoveryOf(page)
    .getByRole("button", { name: "Discard this action", exact: true })
    .click();
  await expect(statusOf(page)).toHaveText(
    "The earlier action was discarded. Nothing was recorded.",
  );
  await page.getByRole("button", { name: "Start break", exact: true }).click();
  await expect(statusOf(page)).toHaveText("Break started.");
  await page.getByRole("button", { name: "End break", exact: true }).click();
  await expect(statusOf(page)).toHaveText("Break ended.");
  await page.getByRole("button", { name: "Clock out", exact: true }).click();
  await expect(statusOf(page)).toContainText("You are clocked out.");
  const record = records.getByRole("listitem");
  await expect(record).toHaveCount(1);
  await expect(record).toContainText("Waiting for a decision");
  await expect(record).toContainText("Outside the schedule");
  await expect(record).toContainText("1 break");
  await expect(record).toContainText("Nothing is in effect yet");
  await accessible(page);
  await fits(page);

  // --- The colleague accepts the swap and declines one handover. ---
  await signOut(page);
  await signIn(page, colleague);
  await open(page, "My shifts");
  const asked = within(page, "My requests");
  await asked
    .getByRole("button", { name: new RegExp(`^Accept Swap: ${tag} swap `) })
    .click();
  await expect(statusOf(page)).toHaveText("Accepted. A manager decides next.");
  await asked
    .getByRole("button", {
      name: new RegExp(`^Decline Handover: ${tag} extra `),
    })
    .click();
  await expect(statusOf(page)).toHaveText("Request declined.");

  // --- The branch manager: one branch, decisions with a visible result. ---
  await signOut(page);
  const managed = page.waitForRequest(
    (request) =>
      request.url().includes("/workforce/desk") &&
      request.headers()["authorization"] != null,
  );
  await signIn(page, "manager");
  await open(page, "Schedule");
  const manager = {
    authorization: (await managed).headers()["authorization"]!,
  };
  // Company skills need company-wide access, on the server too.
  const refused = await page.request.put(
    `${root}/skills/00000000-0000-4000-8000-000000000001`,
    {
      headers: { ...manager, "Idempotency-Key": `FAKE-${project}-skill` },
      data: {
        schema_version: 1,
        expected_revision: 0,
        code: "FAKE_REFUSED",
        name: "FAKE refused",
      },
    },
  );
  expect(refused.status()).toBe(403);
  await expect(page.getByLabel("Location:", { exact: true })).toHaveCount(0);
  await page
    .getByRole("button", { name: "Staff and skills", exact: true })
    .click();
  await expect(
    within(page, "Staff").getByRole("heading", {
      name: NAME[actor],
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    within(page, "Staff").getByRole("heading", { name: NAME.cy, exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Changing them requires company-wide access.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "New skill", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Change requests", exact: true })
    .click();
  const waiting = within(page, "Change requests");
  for (const [kind, position] of [
    ["Handover", "morning"],
    ["Swap", "swap"],
    ["Open shift request", "open"],
  ]) {
    await waiting
      .getByRole("button", {
        name: new RegExp(`^Approve ${kind}: ${tag} ${position} `),
      })
      .click();
    await expect(statusOf(page)).toContainText("Approved and applied.");
  }
  await expect(
    waiting.getByText("No requests are waiting for a manager."),
  ).toBeVisible();
  await waiting
    .getByLabel("Only requests waiting for a manager", { exact: true })
    .uncheck();
  await expect(
    waiting
      .getByRole("listitem")
      .filter({ hasText: `Handover: ${tag} morning` }),
  ).toContainText("is now version 2");
  await accessible(page);
  await page.getByRole("button", { name: "Shifts", exact: true }).click();
  await showWeek(page, day, false);
  const planned = within(page, "Shifts");
  await expect(
    planned.getByRole("listitem").filter({ hasText: `${tag} morning` }),
  ).toContainText(`Assigned to ${NAME[colleague]}`);
  await expect(
    planned.getByRole("listitem").filter({ hasText: `${tag} evening late` }),
  ).toContainText(`Assigned to ${NAME[actor]}`);
  await expect(
    planned.getByRole("listitem").filter({ hasText: `${tag} open` }),
  ).toContainText(`Assigned to ${NAME[actor]}`);
  await page
    .getByRole("button", { name: new RegExp(`^Versions of ${tag} morning `) })
    .click();
  const assignment = within(page, new RegExp(`^Versions of ${tag} morning `));
  await expect(assignment.getByRole("listitem").first()).toContainText(
    `assigned to ${NAME[colleague]}`,
  );
  await expect(assignment.getByRole("listitem").last()).toContainText(
    `assigned to ${NAME[actor]}`,
  );
  // The branch manager hides colleagues' shifts in their own location, by keyboard.
  const privacy = await openPrivacy(page);
  await expect(page.getByLabel("Location:", { exact: true })).toHaveCount(0);
  const showChoice = privacy.getByRole("radio", { name: SHOWN, exact: true });
  const hideChoice = privacy.getByRole("radio", {
    name: OWN_ONLY,
    exact: true,
  });
  const savePrivacy = privacy.getByRole("button", {
    name: "Save privacy",
    exact: true,
  });
  await expect(showChoice).toBeChecked();
  await expect(savePrivacy).toBeDisabled();
  await showChoice.focus();
  await page.keyboard.press("ArrowDown");
  await expect(hideChoice).toBeChecked();
  await accessible(page);
  await fits(page);
  await savePrivacy.click();
  await expect(statusOf(page)).toHaveText(
    "Saved. Staff of this location now see only their own shifts and open shifts.",
  );
  await expect(
    privacy.getByText(/^Version \d+: last changed by you on /),
  ).toBeVisible();
  await expect(hideChoice).toBeChecked();
  await expect(savePrivacy).toBeDisabled();
  await open(page, "Timesheets");
  const team = within(page, "Team time records");
  await team
    .getByRole("button", { name: new RegExp(`^Approve ${NAME[actor]} `) })
    .click();
  await expect(statusOf(page)).toHaveText(
    "Approved. This version is now in effect.",
  );
  await expect(
    team.getByText("No records are waiting for a decision."),
  ).toBeVisible();

  // --- Hidden shifts: no browsing and no swap; the rest still works. ---
  await signOut(page);
  const restricted = page.waitForRequest(
    (request) =>
      request.url().includes("/workforce/desk") &&
      request.headers()["authorization"] != null,
  );
  await signIn(page, actor);
  await open(page, "My shifts");
  await page.getByLabel("Show four weeks from", { exact: true }).fill(day);
  await expect(hiddenNote(page)).toBeVisible();
  const lane = within(page, "Assigned to me");
  await expect(
    lane.getByRole("button", { name: /^Swap / }).first(),
  ).toBeDisabled();
  await expect(
    lane.getByRole("button", { name: /^Hand over / }).first(),
  ).toBeEnabled();
  // A request still names both of its shifts to the people who take part in it.
  await expect(
    within(page, "My requests")
      .getByRole("listitem")
      .filter({ hasText: `Swap: ${tag} swap` }),
  ).toContainText(`${tag} evening late`);
  const browse = await page.request.get(
    `${root}/colleagues/00000000-0000-4000-8000-000000000002/shifts?${window}`,
    {
      headers: {
        authorization: (await restricted).headers()["authorization"]!,
      },
    },
  );
  expect(browse.status()).toBe(403);
  expect((await browse.json()).error.code).toBe("COLLEAGUE_SHIFTS_HIDDEN");
  await accessible(page);
  await fits(page);

  // --- A correction waits; the approved version stays in effect. ---
  await open(page, "Timesheets");
  const own = within(page, "My time records").getByRole("listitem");
  await expect(own).toContainText("Approved");
  await page.getByRole("button", { name: /^Correct My record / }).click();
  const correction = within(page, /^Correct My record /);
  const hours = project === "desktop" ? ["08:00", "10:00"] : ["12:00", "14:00"];
  await correction.getByLabel("Start date", { exact: true }).fill(pastDay);
  await correction.getByLabel("Start time", { exact: true }).fill(hours[0]!);
  await correction.getByLabel("End date", { exact: true }).fill(pastDay);
  await correction.getByLabel("End time", { exact: true }).fill(hours[1]!);
  await correction
    .getByRole("button", { name: "Remove break 1", exact: true })
    .click();
  await accessible(page);
  await correction
    .getByLabel("Reason for the correction", { exact: true })
    .fill(`${tag} worked on another day`);
  await correction
    .getByRole("button", { name: "Send correction", exact: true })
    .click();
  await expect(statusOf(page)).toContainText("Correction sent.");
  await expect(own).toContainText("Waiting for a decision");
  await expect(own).toContainText("In effect: approved version 5");
  await expect(own).toContainText(
    "Version 6 is a pending correction and does not count",
  );
  await expect(own).toContainText(`${tag} worked on another day`);
  await fits(page);

  // --- The manager declines it with a reason. ---
  await signOut(page);
  await signIn(page, "manager");
  await open(page, "Timesheets");
  const decided = within(page, "Team time records");
  await expect(decided.getByRole("listitem")).toContainText(
    "In effect: approved version 5",
  );
  await decided
    .getByRole("button", { name: new RegExp(`^Decline ${NAME[actor]} `) })
    .click();
  const decline = within(page, new RegExp(`^Decline ${NAME[actor]} `));
  await decline
    .getByLabel("Reason for declining", { exact: true })
    .fill(`${tag} no proof of that day`);
  await decline
    .getByRole("button", { name: "Decline this version", exact: true })
    .click();
  await expect(statusOf(page)).toContainText("Declined.");
  // The manager shows colleagues' shifts again.
  await open(page, "Schedule");
  const reopened = await openPrivacy(page);
  await expect(
    reopened.getByRole("radio", { name: OWN_ONLY, exact: true }),
  ).toBeChecked();
  await reopened.getByRole("radio", { name: SHOWN, exact: true }).check();
  await reopened
    .getByRole("button", { name: "Save privacy", exact: true })
    .click();
  await expect(statusOf(page)).toHaveText(
    "Saved. Staff of this location now see colleagues’ published shifts.",
  );

  // --- The employee sees the decision, the whole history and the new shifts. ---
  await signOut(page);
  await signIn(page, actor);
  await open(page, "Timesheets");
  const final = within(page, "My time records").getByRole("listitem");
  await expect(final).toContainText("Declined");
  await expect(final).toContainText(
    "Version 7 was declined and does not count",
  );
  await expect(final).toContainText(`${tag} no proof of that day`);
  await page.getByRole("button", { name: /^History of My record / }).click();
  const history = within(page, /^History of My record /);
  await expect(history.getByRole("listitem")).toHaveCount(7);
  await expect(history.getByRole("listitem").nth(4)).toContainText(
    "Version 5: Approved",
  );
  await expect(history.getByRole("listitem").nth(4)).toContainText(
    "in effect from this version",
  );
  await expect(history.getByRole("listitem").nth(5)).toContainText(
    "Version 6: Correction proposed by you",
  );
  await accessible(page);
  await history.getByRole("button", { name: "Close", exact: true }).click();
  await open(page, "My shifts");
  await page.getByLabel("Show four weeks from", { exact: true }).fill(day);
  const mine = within(page, "Assigned to me");
  await expect(
    mine.getByRole("heading", { name: new RegExp(`^${tag} evening late `) }),
  ).toBeVisible();
  await expect(
    mine.getByRole("heading", { name: new RegExp(`^${tag} open `) }),
  ).toBeVisible();
  await expect(
    mine.getByRole("heading", { name: new RegExp(`^${tag} morning `) }),
  ).toHaveCount(0);
  // Shown again: the note is gone and a swap can be chosen.
  await expect(hiddenNote(page)).toHaveCount(0);
  await expect(
    mine.getByRole("button", { name: /^Swap / }).first(),
  ).toBeEnabled();
  const outcome = within(page, "My requests")
    .getByRole("listitem")
    .filter({ hasText: tag });
  await expect(outcome.filter({ hasText: "Approved and applied" })).toHaveCount(
    3,
  );
  await expect(outcome.filter({ hasText: "Declined" })).toHaveCount(1);
  await expect(outcome.filter({ hasText: "Withdrawn" })).toHaveCount(1);
  await accessible(page);
  // An open record is left for the switched-off phase.
  await open(page, "Timesheets");
  await page.getByRole("button", { name: "Clock in", exact: true }).click();
  await expect(statusOf(page)).toHaveText("You are clocked in.");
});

test("a switched-off module keeps history and lets an open record close", async ({
  page,
}, testInfo) => {
  test.skip(phase !== "off", "needs the records of the enabled phase");
  test.setTimeout(180000);
  const project = testInfo.project.name;
  const tag = `FAKE ${project}`;
  const actor: Person = project === "desktop" ? "ada" : "ben";
  const day = plus(firstDay, project === "desktop" ? 0 : 3);
  const closed = page.getByText("Scheduling is turned off for this business.", {
    exact: false,
  });
  await signIn(page, actor);
  await open(page, "Timesheets");
  await expect(closed).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start break", exact: true }),
  ).toBeDisabled();
  const records = within(page, "My time records");
  await expect(records.getByRole("listitem")).toHaveCount(2);
  await expect(
    records.getByRole("button", { name: /^Correct My record / }),
  ).toBeDisabled();
  await records
    .getByRole("button", { name: /^History of My record / })
    .last()
    .click();
  await expect(
    within(page, /^History of My record /).getByRole("listitem"),
  ).toHaveCount(7);
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Clock out", exact: true }).click();
  await expect(statusOf(page)).toContainText("You are clocked out.");
  await expect(
    page.getByRole("button", { name: "Clock in", exact: true }),
  ).toBeDisabled();
  await accessible(page);
  await fits(page);
  await open(page, "My shifts");
  await expect(closed).toBeVisible();
  await page.getByLabel("Show four weeks from", { exact: true }).fill(day);
  await expect(
    within(page, "Assigned to me")
      .getByRole("button", { name: /^Hand over / })
      .first(),
  ).toBeDisabled();
  await within(page, "My requests")
    .getByRole("button", {
      name: new RegExp(`^History of Handover: ${tag} morning `),
    })
    .click();
  await expect(
    within(page, new RegExp(`^History of Handover: ${tag} morning `)).getByRole(
      "listitem",
    ),
  ).toHaveCount(3);
  await accessible(page);
  await signOut(page);
  await signIn(page, "owner");
  await open(page, "Schedule");
  await expect(closed).toBeVisible();
  await showWeek(page, day, true);
  await expect(
    page.getByRole("button", { name: "New shift", exact: true }),
  ).toBeDisabled();
  const planned = within(page, "Shifts");
  await expect(
    planned.getByRole("listitem").filter({ hasText: `${tag} morning` }),
  ).toBeVisible();
  await expect(
    planned.getByRole("button", { name: new RegExp(`^Edit ${tag} morning `) }),
  ).toBeDisabled();
  await accessible(page);
  // The privacy setting keeps its last version and cannot be changed while off.
  const kept = await openPrivacy(page);
  await expect(
    kept.getByText(
      new RegExp(`^Version \\d+: last changed by ${NAME.manager} on `),
    ),
  ).toBeVisible();
  await expect(
    kept.getByRole("radio", { name: SHOWN, exact: true }),
  ).toBeChecked();
  await expect(
    kept.getByRole("radio", { name: OWN_ONLY, exact: true }),
  ).toBeDisabled();
  await expect(
    kept.getByRole("button", { name: "Save privacy", exact: true }),
  ).toBeDisabled();
  await accessible(page);
});
