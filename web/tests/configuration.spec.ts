import { expect, test, type Locator, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

async function openBusiness(page: Page): Promise<Locator> {
  await page
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  const section = page.getByRole("region", {
    name: "Configuration",
    exact: true,
  });
  await expect(section.getByRole("heading", { name: "History" })).toBeVisible();
  return section;
}

async function validateAndPublish(section: Locator, version: number) {
  await section
    .getByRole("button", { name: `Validate version ${version}` })
    .click();
  await expect(section.getByRole("status")).toHaveText(
    "Draft validated. It can now be published.",
  );
  await section
    .getByRole("button", { name: `Publish version ${version}` })
    .click();
}

// The signed-in owner's business has a saved profile and one appointment before the run.
test("the owner turns booking off and on through published configuration versions", async ({
  page,
}, testInfo) => {
  const business = process.env.GBA_CONFIG_BUSINESS!;
  const booking = process.env.GBA_CONFIG_BOOKING!;
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  let section = await openBusiness(page);
  const bookingModule = section.getByRole("checkbox", {
    name: /Booking and resources/,
  });
  if (testInfo.project.name === "desktop") {
    await expect(section).toContainText("No published version yet");
    // Planned modules are listed with their readiness and cannot be chosen.
    await expect(
      section
        .getByRole("checkbox", {
          name: / · (Planned|Implemented, not yet verified)/,
        })
        .first(),
    ).toBeDisabled();
    await expect(
      section.getByRole("checkbox", { name: /Organization and structure/ }),
    ).toBeDisabled();
    await expect(bookingModule).toBeChecked();
    await bookingModule.uncheck();
    await section
      .getByRole("button", { name: "Save configuration draft" })
      .click();
    await expect(section.getByRole("status")).toHaveText(
      "Draft saved. Check the preview, then validate it.",
    );
    const preview = section.getByRole("region", {
      name: "Configuration preview",
    });
    await expect(preview).toContainText(
      "Turns off Booking and resources. Stops: New bookings and reschedules",
    );
    await validateAndPublish(section, 1);

    const keys: string[] = [];
    let authorization = "";
    let loseResponse = true;
    const publish = "**/v1/businesses/*/configuration/versions/*/publish";
    await page.route(publish, async (route) => {
      keys.push(route.request().headers()["idempotency-key"]!);
      authorization = route.request().headers()["authorization"]!;
      if (loseResponse) {
        loseResponse = false;
        await route.fetch(); // Real publication; the client loses only the response.
        await route.abort("failed");
      } else await route.continue();
    });
    await section.getByRole("button", { name: "Confirm publication" }).click();
    await section
      .getByRole("button", { name: "Retry same configuration action" })
      .click();
    await expect(section.getByRole("status")).toHaveText(
      "Configuration published.",
    );
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await page.unroute(publish);
    await expect(section).toContainText("Published version 1.");

    // The server refuses new bookings; the screen explains and keeps history.
    const refused = await page.request.post(`/v1/salons/${business}/bookings`, {
      headers: { authorization },
      data: JSON.parse(booking),
    });
    expect(refused.status()).toBe(409);
    expect((await refused.json()).error.code).toBe("MODULE_DISABLED");
    await page.getByRole("link", { name: "Bookings", exact: true }).click();
    await expect(
      page.getByText("Booking is turned off in this business"),
    ).toBeVisible();
    await expect(page.getByText("FAKE Configuration Guest")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "+ New Appointment" }),
    ).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Reschedule" })).toHaveCount(
      0,
    );
    await expect(
      page.getByRole("button", { name: "Cancel", exact: true }).first(),
    ).toBeVisible();

    // Turning booking on again is a new version; the first one is replaced.
    section = await openBusiness(page);
    await section
      .getByRole("checkbox", { name: /Booking and resources/ })
      .check();
    await section
      .getByRole("button", { name: "Save configuration draft" })
      .click();
    await expect(section.getByRole("status")).toHaveText(
      "Draft saved. Check the preview, then validate it.",
    );
    await validateAndPublish(section, 2);
    await section.getByRole("button", { name: "Confirm publication" }).click();
    await expect(section.getByRole("status")).toHaveText(
      "Configuration published.",
    );
  }
  await expect(section).toContainText("Published version 2.");
  const history = section.getByRole("list", { name: "Configuration history" });
  await expect(history.getByRole("listitem")).toHaveText([
    /Version 2 · Published · Booking and resources/,
    /Version 1 · Replaced · core modules only · replaced by version 2/,
  ]);
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
    path: `test-results/configuration-${page.viewportSize()?.width}.png`,
    fullPage: true,
  });
});
