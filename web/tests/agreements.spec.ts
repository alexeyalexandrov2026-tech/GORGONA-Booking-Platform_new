import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

test("contracts: drafts, attested agreement, amendment, termination and retained versions", async ({
  page,
}, testInfo) => {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Counterparties", exact: true }).click();
  await page
    .getByRole("region", { name: "Counterparty list", exact: true })
    .getByRole("button", { name: "FAKE Contract Partner", exact: true })
    .click();
  const contracts = page.getByRole("region", {
    name: "Contracts",
    exact: true,
  });
  const status = contracts.getByRole("status");
  const inForce = contracts.getByRole("region", {
    name: "Agreed version in force",
  });
  const today = await page.evaluate(() =>
    new Date().toLocaleDateString("en-CA"),
  );
  // Fixed per day so the desktop and mobile projects see the same recorded date.
  const later = await page.evaluate(() => {
    const day = new Date();
    day.setDate(day.getDate() + 30);
    return day.toLocaleDateString("en-CA");
  });
  if (testInfo.project.name === "desktop") {
    await contracts
      .getByLabel("Contract title", { exact: true })
      .fill("FAKE Service contract");
    await contracts
      .getByLabel("Contract number", { exact: true })
      .fill("FAKE-77");

    // A save whose response is lost is retried with the same key.
    const keys: string[] = [];
    let first = 0;
    let lose = true;
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    let arrived!: () => void;
    const reached = new Promise<void>((resolve) => (arrived = resolve));
    const pattern = "**/v1/businesses/*/agreements/*";
    await page.route(pattern, async (route) => {
      if (route.request().method() !== "PUT") return route.continue();
      keys.push(route.request().headers()["idempotency-key"]!);
      if (lose) {
        lose = false;
        arrived();
        await held;
        first = (await route.fetch()).status();
        await route.abort("failed");
      } else await route.continue();
    });
    await contracts
      .getByRole("button", { name: "Save contract draft" })
      .click();
    // While the request is still in flight its result is not yet uncertain.
    await reached;
    await expect(
      contracts.getByText(/result of the last contract command is uncertain/),
    ).toHaveCount(0, { timeout: 1500 });
    release();
    await contracts
      .getByRole("button", { name: "Retry same contract command" })
      .click();
    await expect(status).toHaveText("Contract draft saved.");
    expect(first).toBe(200);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await page.unroute(pattern);
    await expect(contracts).toContainText("version 1 · draft");

    // Agreement is shown only after the server answers.
    await contracts.getByLabel("Signed on", { exact: true }).fill(today);
    await expect(
      contracts.getByRole("button", { name: "Record as agreed" }),
    ).toBeDisabled();
    await contracts
      .getByLabel(/Signed outside the platform; no electronic signature/)
      .check();
    await contracts.getByRole("button", { name: "Record as agreed" }).click();
    await expect(status).toHaveText("Recorded as agreed.");
    await expect(contracts).toContainText("version 2 · agreed");
    await expect(inForce).toContainText(
      `signed outside the platform on ${today}`,
    );
    await expect(contracts).toContainText("Status: in force");

    await contracts
      .getByLabel("Contract title", { exact: true })
      .fill("FAKE Service contract v2");
    await contracts
      .getByRole("button", { name: "Save contract draft" })
      .click();
    await expect(status).toHaveText("Contract draft saved.");
    await expect(contracts).toContainText("version 3 · draft");
    await contracts
      .getByRole("button", { name: "Read contract version 2", exact: true })
      .click();
    const saved = contracts.getByRole("region", {
      name: "Saved contract version",
    });
    await expect(saved).toContainText("Saved version 2 · agreed");
    await expect(saved).toContainText("FAKE Service contract · FAKE-77");

    await contracts.getByLabel("Signed on", { exact: true }).fill(today);
    await contracts
      .getByLabel(/Signed outside the platform; no electronic signature/)
      .check();
    await contracts.getByRole("button", { name: "Record as agreed" }).click();
    await expect(contracts).toContainText("version 4 · agreed");

    // An unsigned amendment does not replace the agreed version in force.
    await contracts
      .getByLabel("Contract title", { exact: true })
      .fill("FAKE Service contract v3");
    await contracts
      .getByRole("button", { name: "Save contract draft" })
      .click();
    await expect(status).toHaveText("Contract draft saved.");
    await expect(contracts).toContainText("version 5 · draft");
    await expect(inForce).toContainText(
      "Agreed version 4: FAKE Service contract v2",
    );
    await expect(inForce).toContainText(
      "Version 5 is an unsigned amendment draft.",
    );
    await expect(contracts).toContainText(
      "Status: in force · unsigned amendment drafted",
    );

    // Termination ends agreed version 4 from a future date; the draft is abandoned.
    await expect(contracts).toContainText("closed as abandoned");
    await contracts
      .getByLabel("Termination takes effect on", { exact: true })
      .fill(later);
    await contracts.getByRole("button", { name: "Record termination" }).click();
    await expect(status).toHaveText("Termination recorded.");
    await expect(contracts).toContainText("version 6 · terminated");
    await expect(
      contracts.getByLabel("Contract title", { exact: true }),
    ).toBeDisabled();
  } else {
    await contracts
      .getByRole("button", { name: "FAKE Service contract v2", exact: true })
      .click();
    await expect(contracts).toContainText("version 6 · terminated");
    await contracts
      .getByRole("button", { name: "Read contract version 2", exact: true })
      .click();
    await expect(
      contracts.getByRole("region", { name: "Saved contract version" }),
    ).toContainText("FAKE Service contract · FAKE-77");
  }
  // The agreed version stays in force until the termination takes effect.
  await expect(inForce).toContainText(
    "Agreed version 4: FAKE Service contract v2",
  );
  await expect(inForce).toContainText(
    `stays in force until it takes effect on ${later}`,
  );
  await expect(contracts).toContainText(
    "Status: in force until the termination takes effect",
  );
  await expect(contracts).toContainText(
    "draft · abandoned, closed by the termination",
  );
  const reload = contracts.getByRole("button", {
    name: "Reload contract",
    exact: true,
  });
  await expect(reload).toBeEnabled();
  await reload.focus();
  await expect(reload).toBeFocused();
  const audit = await new AxeBuilder({ page }).analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
