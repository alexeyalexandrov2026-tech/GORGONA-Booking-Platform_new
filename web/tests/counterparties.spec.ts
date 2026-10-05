import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

async function confirm(page: Page) {
  await page
    .getByRole("button", { name: "Confirm counterparty action", exact: true })
    .click();
}

test("counterparty cards, manual decisions, links, uncertain retries and retained history", async ({
  page,
}, testInfo) => {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Counterparties", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Counterparties", exact: true }),
  ).toBeVisible();
  const card = page.getByRole("region", {
    name: "Counterparty card",
    exact: true,
  });
  const list = page.getByRole("region", {
    name: "Counterparty list",
    exact: true,
  });
  if (testInfo.project.name === "desktop") {
    await card.getByLabel("Display name", { exact: true }).fill("FAKE Alpha");
    await card
      .getByLabel("Email", { exact: true })
      .fill("fake.counterparty@example.test");
    await card.getByLabel("Phone", { exact: true }).fill("+1 555 010 1234");
    await card.getByLabel("customer", { exact: true }).check();
    await card
      .getByRole("button", { name: "Add contact", exact: true })
      .click();
    await card
      .getByLabel("Contact name", { exact: true })
      .fill("FAKE Office Contact");
    await card
      .getByLabel("Contact email", { exact: true })
      .fill("office@example.test");
    await card
      .getByRole("button", { name: "Review and save card", exact: true })
      .click();

    const keys: string[] = [];
    let authorization = "";
    let firstId = "";
    let lose = true;
    const pattern = "**/v1/businesses/*/counterparties/*";
    await page.route(pattern, async (route) => {
      if (route.request().method() !== "PUT") return route.continue();
      keys.push(route.request().headers()["idempotency-key"]!);
      authorization = route.request().headers()["authorization"]!;
      firstId = route.request().url().split("/").at(-1)!;
      if (lose) {
        lose = false;
        await route.fetch();
        await route.abort("failed");
      } else await route.continue();
    });
    await confirm(page);
    await expect(
      card.getByLabel("Display name", { exact: true }),
    ).toBeDisabled();
    await page
      .getByRole("button", {
        name: "Retry same counterparty command",
        exact: true,
      })
      .click();
    await expect(page.getByRole("status")).toHaveText("Counterparty saved.");
    await expect(card).toContainText("Version 1 · active");
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await page.unroute(pattern);

    const candidates = page.getByRole("region", {
      name: "Booking candidates",
      exact: true,
    });
    await candidates.getByRole("checkbox").check();
    await candidates
      .getByRole("button", { name: "Review selected booking links" })
      .click();
    await confirm(page);
    await expect(page.getByRole("status")).toHaveText("Decision recorded.");
    await expect(
      page.getByRole("region", { name: "Linked bookings", exact: true }),
    ).toContainText("FAKE Counterparty Browser Guest");

    await card
      .getByLabel("Display name", { exact: true })
      .fill("FAKE Alpha Updated");
    await card.getByRole("button", { name: "Review and save card" }).click();
    await confirm(page);
    await expect(card).toContainText("Version 2 · active");
    await page
      .getByRole("button", { name: "Read version 1", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Saved card version" }),
    ).toContainText("FAKE Alpha");
    await expect(
      page.getByRole("region", { name: "Saved card version" }),
    ).toContainText("FAKE Office Contact");
    // A changed revision returns a conflict; the editor freezes until explicitly reloaded.
    const second = await page.request.get(
      `/v1/businesses/${process.env.GBA_CP_BUSINESS}/counterparties/${firstId}`,
      { headers: { authorization } },
    );
    expect(second.status()).toBe(200);
    const changed = await page.request.put(
      `/v1/businesses/${process.env.GBA_CP_BUSINESS}/counterparties/${firstId}`,
      {
        headers: { authorization, "Idempotency-Key": crypto.randomUUID() },
        data: {
          expected_revision: 2,
          kind: "person",
          display_name: "FAKE Alpha Updated",
          email: "fake.counterparty@example.test",
          phone: "+15550101234",
          roles: ["customer"],
          contacts: [
            { name: "FAKE Office Contact", email: "office@example.test" },
          ],
        },
      },
    );
    expect(changed.status()).toBe(200);
    await card.getByRole("button", { name: "Review and save card" }).click();
    await confirm(page);
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(
      card.getByLabel("Display name", { exact: true }),
    ).toBeDisabled();
    await card
      .getByRole("button", { name: "Reload card", exact: true })
      .click();
    await expect(card).toContainText("Version 3 · active");

    await list
      .getByRole("button", { name: "New counterparty", exact: true })
      .click();
    await card.getByLabel("Display name", { exact: true }).fill("FAKE Beta");
    await card
      .getByLabel("Email", { exact: true })
      .fill("fake.counterparty@example.test");
    await card
      .getByRole("button", { name: "Review and save card", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Possible matches" }),
    ).toContainText("FAKE Alpha Updated");
    await confirm(page);
    await expect(card).toContainText("Version 1 · active");
    await page
      .getByRole("button", {
        name: "Review merge into FAKE Alpha Updated",
        exact: true,
      })
      .click();
    await confirm(page);
    await expect(card).toContainText("Version 2 · merged");
    await list
      .getByRole("button", { name: "FAKE Alpha Updated", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Merged cards" }),
    ).toContainText("FAKE Beta");
    await page
      .getByRole("button", { name: "Read merged card: FAKE Beta", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Review separation", exact: true })
      .click();
    await confirm(page);
    await expect(card).toContainText("Version 3 · active");
    await list
      .getByRole("button", { name: "FAKE Alpha Updated", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Review unlink", exact: true })
      .click();
    await confirm(page);
    await expect(
      page.getByRole("region", { name: "Linked bookings" }),
    ).not.toContainText("FAKE Counterparty Browser Guest");

    // Disable through real configuration commands; a stale screen is stopped by the server.
    const base = `/v1/businesses/${process.env.GBA_CP_BUSINESS}/configuration`;
    for (const [method, path, body] of [
      [
        "PUT",
        `${base}/draft`,
        {
          expected_version: 1,
          profile_revision: 1,
          module_ids: ["booking_resources"],
        },
      ],
      ["POST", `${base}/versions/2/validate`, { expected_revision: 1 }],
      ["POST", `${base}/versions/2/publish`, { expected_revision: 2 }],
    ] as const) {
      const result = await page.request.fetch(path, {
        method,
        headers: { authorization, "Idempotency-Key": crypto.randomUUID() },
        data: body,
      });
      expect(result.status()).toBe(200);
    }
    await card
      .getByRole("button", { name: "Reload card", exact: true })
      .click();
    await expect(
      page.getByText("Counterparties is turned off.", { exact: false }),
    ).toBeVisible();
    await expect(
      card.getByRole("button", { name: "Review and save card" }),
    ).toBeDisabled();
  } else {
    await expect(
      page.getByText("Counterparties is turned off.", { exact: false }),
    ).toBeVisible();
    await list
      .getByRole("button", { name: "FAKE Alpha Updated", exact: true })
      .click();
    await expect(card.getByLabel("Contact name", { exact: true })).toHaveValue(
      "FAKE Office Contact",
    );
    await page
      .getByRole("button", { name: "Read version 1", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Saved card version" }),
    ).toContainText("FAKE Alpha");
  }
  // Desktop and mobile: labeled form, keyboard focus, no horizontal overflow and axe.
  await card.getByRole("button", { name: "Reload card", exact: true }).focus();
  await expect(
    card.getByRole("button", { name: "Reload card", exact: true }),
  ).toBeFocused();
  const audit = await new AxeBuilder({ page }).analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
