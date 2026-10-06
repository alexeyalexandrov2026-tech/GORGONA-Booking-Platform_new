import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ baseURL: process.env.GBA_MGMT_BROWSER_URL });

const business = process.env.GBA_DOC_BUSINESS;
const samplePath = process.env.GBA_DOC_SAMPLE_PDF!;
const sampleSha = process.env.GBA_DOC_SAMPLE_SHA256!;

async function status(page: Page, text: string | RegExp) {
  await expect(page.getByRole("status")).toHaveText(text);
}

test("documents, verified files, counterparty links, uncertain retries and retained versions", async ({
  page,
}, testInfo) => {
  await page.goto("/overview/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Today’s Overview/ }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Documents", exact: true }),
  ).toBeVisible();
  const card = page.getByRole("region", { name: "Document card", exact: true });
  const list = page.getByRole("region", { name: "Document list", exact: true });
  const links = page.getByRole("region", {
    name: "Linked counterparties",
    exact: true,
  });
  if (testInfo.project.name === "desktop") {
    await card
      .getByLabel("Title", { exact: true })
      .fill("FAKE Supply agreement");
    await card.getByLabel("Valid from", { exact: true }).fill("2026-01-01");
    await card.getByLabel("Valid until", { exact: true }).fill("2026-12-31");

    // An upload whose response is lost is retried with the same key and bytes.
    const keys: string[] = [];
    let authorization = "";
    let lose = true;
    let firstUpload = 0;
    const pattern = "**/v1/businesses/*/document-files/*";
    await page.route(pattern, async (route) => {
      if (route.request().method() !== "PUT") return route.continue();
      keys.push(route.request().headers()["idempotency-key"]!);
      authorization = route.request().headers()["authorization"]!;
      if (lose) {
        lose = false;
        firstUpload = (await route.fetch()).status();
        await route.abort("failed");
      } else await route.continue();
    });
    await card
      .getByLabel("Attach a PDF, PNG or JPEG file (up to 10 MiB)")
      .setInputFiles({
        name: "FAKE Agreement.pdf",
        mimeType: "application/pdf",
        buffer: await readFile(samplePath),
      });
    await expect(card.getByLabel("Title", { exact: true })).toBeDisabled();
    await page
      .getByRole("button", { name: "Retry same upload", exact: true })
      .click();
    await status(page, /^File uploaded\./);
    // The lost attempt was stored; the retry replayed its result.
    expect(firstUpload).toBe(200);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await page.unroute(pattern);
    await expect(card).toContainText("Not scanned for malware");

    // A save whose response is lost is retried with the same key.
    const saves: string[] = [];
    let loseSave = true;
    let firstSave = 0;
    const documents = "**/v1/businesses/*/documents/*";
    await page.route(documents, async (route) => {
      if (route.request().method() !== "PUT") return route.continue();
      saves.push(route.request().headers()["idempotency-key"]!);
      if (loseSave) {
        loseSave = false;
        firstSave = (await route.fetch()).status();
        await route.abort("failed");
      } else await route.continue();
    });
    await card.getByRole("button", { name: "Save document" }).click();
    await page
      .getByRole("button", { name: "Retry same document command" })
      .click();
    await status(page, "Document saved.");
    expect(firstSave).toBe(200);
    expect(saves).toHaveLength(2);
    expect(saves[0]).toBe(saves[1]);
    await page.unroute(documents);
    await expect(card).toContainText("Version 1 · current");
    await expect(card).toContainText("FAKE Agreement.pdf");

    // Downloads are verified attachments, never previews.
    const download = page.waitForEvent("download");
    await card
      .getByRole("button", { name: "Download file", exact: true })
      .click();
    const saved = await download;
    expect(saved.suggestedFilename()).toBe("FAKE Agreement.pdf");
    const bytes = await readFile((await saved.path())!);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(sampleSha);

    await links
      .getByLabel("Find a counterparty to link", { exact: true })
      .fill("FAKE Document Partner");
    await links.getByRole("button", { name: "Search counterparties" }).click();
    await links
      .getByRole("button", { name: "Link FAKE Document Partner", exact: true })
      .click();
    await status(page, "Link change recorded.");
    await expect(links).toContainText("FAKE Document Partner · active");

    await card
      .getByLabel("Title", { exact: true })
      .fill("FAKE Supply agreement v2");
    await card
      .getByRole("button", { name: "Save the next version without a file" })
      .click();
    await card.getByRole("button", { name: "Save document" }).click();
    await status(page, "Document saved.");
    await expect(card).toContainText("Version 2 · current");
    await expect(card).toContainText("No file attached.");
    await page
      .getByRole("button", { name: "Read version 1", exact: true })
      .click();
    const version = page.getByRole("region", {
      name: "Saved document version",
    });
    await expect(version).toContainText("FAKE Supply agreement");
    await expect(version).toContainText("FAKE Agreement.pdf");

    // A changed revision returns a conflict; the editor freezes until reloaded.
    await expect(list.getByRole("listitem")).toHaveCount(1);
    const listed = await page.request.get(
      `/v1/businesses/${business}/documents`,
      { headers: { authorization } },
    );
    const id = (await listed.json()).items[0].document_id as string;
    const changed = await page.request.put(
      `/v1/businesses/${business}/documents/${id}`,
      {
        headers: { authorization, "Idempotency-Key": crypto.randomUUID() },
        data: {
          expected_revision: 2,
          title: "FAKE Supply agreement v3",
          category: "agreement",
        },
      },
    );
    expect(changed.status()).toBe(200);
    await card.getByRole("button", { name: "Save document" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(card.getByLabel("Title", { exact: true })).toBeDisabled();
    await card
      .getByRole("button", { name: "Reload document", exact: true })
      .click();
    await expect(card).toContainText("Version 3 · current");

    await links
      .getByRole("button", { name: "Unlink FAKE Document Partner" })
      .click();
    await status(page, "Link change recorded.");
    await expect(links).toContainText("No linked counterparties.");

    // Disable through real configuration commands; reads and downloads continue.
    const base = `/v1/businesses/${business}/configuration`;
    for (const [method, path, body] of [
      [
        "PUT",
        `${base}/draft`,
        {
          expected_version: 1,
          profile_revision: 1,
          module_ids: ["booking_resources", "counterparties"],
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
      .getByRole("button", { name: "Reload document", exact: true })
      .click();
    await expect(
      page.getByText("Documents is turned off.", { exact: false }),
    ).toBeVisible();
    await expect(
      card.getByRole("button", { name: "Save document" }),
    ).toBeDisabled();
    await list.getByRole("button", { name: "Search", exact: true }).click();
    await expect(list).toContainText("FAKE Supply agreement v3");
  } else {
    await expect(
      page.getByText("Documents is turned off.", { exact: false }),
    ).toBeVisible();
    await list
      .getByRole("button", { name: "FAKE Supply agreement v3", exact: true })
      .click();
    await expect(card.getByLabel("Title", { exact: true })).toHaveValue(
      "FAKE Supply agreement v3",
    );
    await page
      .getByRole("button", { name: "Read version 1", exact: true })
      .click();
    const version = page.getByRole("region", {
      name: "Saved document version",
    });
    await expect(version).toContainText("FAKE Agreement.pdf");
    const download = page.waitForEvent("download");
    await version
      .getByRole("button", { name: "Download file of version 1" })
      .click();
    const bytes = await readFile((await (await download).path())!);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(sampleSha);
  }
  // Desktop and mobile: labeled form, keyboard focus, no horizontal overflow and axe.
  const reload = card.getByRole("button", {
    name: "Reload document",
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
