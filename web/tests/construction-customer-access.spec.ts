import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL, actionTimeout: 15000 });

test("an operator links the customer, offers access and shares working document links", async ({
  page,
  context,
}, testInfo) => {
  const fixtures = JSON.parse(
    process.env.GBA_CUSTOMER_ACCESS ?? "{}",
  ) as Record<
    string,
    {
      business: string;
      company: string;
      project: string;
      number: string;
      location: string;
      expires: string;
    }
  >;
  const fixture = fixtures[testInfo.project.name];
  if (!fixture)
    throw new Error("Seed with test_o9_customer_access_browser.py.");
  const provider = process.env.GBA_TEST_OIDC_ISSUER;
  expect((await page.request.post(`${provider}/browser/user/owner`)).ok()).toBe(
    true,
  );
  await page.goto("/overview/");
  await page
    .getByRole("button", { name: "Sign in", exact: true })
    .press("Enter");
  await page.getByRole("link", { name: "Construction", exact: true }).click();
  await page
    .getByRole("table", { name: "Projects", exact: true })
    .getByRole("button", { name: fixture.number })
    .click();
  const access = page.getByRole("region", {
    name: "Customer access",
    exact: true,
  });
  await expect(
    access.getByRole("textbox", { name: "Customer business ID" }),
  ).toBeVisible();
  const keys: string[] = [];
  await page.route(
    `**/projects/${fixture.project}/customer-company`,
    async (route) => {
      if (route.request().method() !== "PUT") return route.continue();
      keys.push(route.request().headers()["idempotency-key"] ?? "");
      if (keys.length === 1) {
        expect((await route.fetch()).ok()).toBe(true);
        return route.abort();
      }
      return route.continue();
    },
  );
  const company = access.getByRole("textbox", { name: "Customer business ID" });
  await company.fill(fixture.company);
  await access
    .getByRole("button", { name: "Save customer company" })
    .press("Enter");
  await expect(access.getByRole("alert")).toBeVisible();
  await expect(company).toBeDisabled();
  await access
    .getByRole("button", { name: "Retry customer company" })
    .press("Enter");
  await expect(access.getByRole("status")).toHaveText(
    "Customer company saved.",
  );
  expect(keys).toHaveLength(2);
  expect(keys[1]).toBe(keys[0]);

  await access.getByRole("link", { name: "Manage delegated access" }).click();
  const delegations = page.getByRole("region", {
    name: "Delegated access",
    exact: true,
  });
  await delegations.getByLabel("Serving business ID").fill(fixture.company);
  await delegations
    .getByLabel("Access", { exact: true })
    .selectOption("manage");
  for (const name of [
    "Plan trips (API only)",
    "Assign crews",
    "Record stop events",
    "Answer construction documents",
  ])
    await delegations.getByRole("checkbox", { name, exact: true }).check();
  await delegations
    .getByLabel("Location", { exact: true })
    .selectOption(fixture.location);
  await delegations.getByLabel("Last day of access").fill(fixture.expires);
  await delegations
    .getByRole("button", { name: "Offer access", exact: true })
    .press("Enter");
  await expect(delegations.getByRole("status")).toHaveText(
    "Access offered. It starts after the other business accepts.",
  );

  const customer = await context.newPage();
  expect(
    (await customer.request.post(`${provider}/browser/user/customer`)).ok(),
  ).toBe(true);
  await customer.goto("/overview/");
  await customer.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    customer.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  const businessChoice = customer.getByLabel("Active Business");
  if (await businessChoice.count())
    await businessChoice.selectOption(fixture.company);
  await customer
    .getByRole("link", { name: "Business profile", exact: true })
    .click();
  const offered = customer
    .getByRole("region", { name: "Delegated access", exact: true })
    .getByRole("listitem")
    .filter({ hasText: "Waiting for acceptance" });
  await expect(offered).toHaveCount(1);
  await offered.getByRole("checkbox", { name: /\(owner\)$/ }).check();
  await offered.getByRole("button", { name: /^Accept access from / }).click();
  await expect(
    customer
      .getByRole("region", { name: "Delegated access", exact: true })
      .getByRole("status"),
  ).toHaveText("Access accepted.");

  await page.getByRole("link", { name: "Construction", exact: true }).click();
  await page
    .getByRole("table", { name: "Projects", exact: true })
    .getByRole("button", { name: fixture.number })
    .click();
  await access
    .getByRole("combobox", { name: "Customer access grant" })
    .selectOption({ index: 1 });
  await access
    .getByRole("button", { name: "Prepare customer links" })
    .press("Enter");
  const proposal = access.getByRole("link", {
    name: "Customer proposal",
    exact: true,
  });
  await expect(proposal).toBeVisible();
  const audit = await new AxeBuilder({ page })
    .include(".construction-project")
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const proposalUrl = await proposal.getAttribute("href");
  expect(proposalUrl).toBeTruthy();
  await customer.goto(proposalUrl!);
  await customer.getByRole("button", { name: "Sign in", exact: true }).click();
  await customer
    .getByRole("textbox", { name: "Signatory name" })
    .fill("FAKE access customer");
  await customer
    .getByRole("button", { name: "Accept proposal", exact: true })
    .press("Enter");
  await expect(customer.getByRole("main").getByRole("status")).toHaveText(
    "Proposal accepted.",
  );

  await page
    .getByRole("button", { name: "Reload project", exact: true })
    .click();
  const change = page.getByRole("form", {
    name: "Propose a change order",
    exact: true,
  });
  await expect(change).toBeVisible();
  await change.getByLabel("Title", { exact: true }).fill("FAKE smaller scope");
  await change.getByLabel("Change line 1 action").selectOption("remove");
  await change.getByLabel("Change line 1 contract line").selectOption("1");
  await change.getByLabel("Change line 1 quantity").fill("1");
  await change.getByRole("button", { name: "Propose", exact: true }).click();
  await expect(
    page.getByRole("table", { name: "Change orders", exact: true }),
  ).toContainText("FAKE smaller scope");
  await access
    .getByRole("combobox", { name: "Customer access grant" })
    .selectOption({ index: 1 });
  await access.getByRole("button", { name: "Prepare customer links" }).click();
  const changeUrl = await access
    .getByRole("link", { name: "Customer change order 1", exact: true })
    .getAttribute("href");
  const acceptanceUrl = await access
    .getByRole("link", { name: "Customer work acceptance", exact: true })
    .getAttribute("href");
  expect(changeUrl).toBeTruthy();
  expect(acceptanceUrl).toBeTruthy();
  await customer.goto(changeUrl!);
  await customer.getByRole("button", { name: "Sign in", exact: true }).click();
  await customer.getByRole("radio", { name: "Reject change order" }).check();
  await customer
    .getByRole("button", { name: "Send answer", exact: true })
    .click();
  await expect(customer.getByRole("main").getByRole("status")).toHaveText(
    "Change order rejected.",
  );
  await customer.goto(acceptanceUrl!);
  await customer.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    customer.getByRole("heading", { name: "Work to review", exact: true }),
  ).toBeVisible();
  await expect(customer.getByRole("main")).toContainText("Work remaining");
  await expect(customer.getByRole("main")).not.toContainText("USD 150.00");

  expect(
    (
      await page.request.post(`${provider}/browser/revoke/${fixture.company}`)
    ).ok(),
  ).toBe(true);
  await access
    .getByRole("button", { name: "Prepare customer links" })
    .press("Enter");
  await expect(access.getByRole("alert")).toContainText(
    "This access is no longer available",
  );
  await expect(proposal).toHaveCount(0);
  await expect(
    access.getByRole("link", { name: "Customer work acceptance", exact: true }),
  ).toHaveCount(0);
  await customer.close();
});
