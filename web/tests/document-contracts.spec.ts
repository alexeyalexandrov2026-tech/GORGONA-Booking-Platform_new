import { expect, test } from "@playwright/test";
import {
  detectMediaType,
  documentLinkResultSchema,
  documentListSchema,
  documentSchema,
  validityState,
} from "../lib/document-contracts";
import { managementResponseSchema } from "../lib/management-contracts";

const business = "00000000-0000-4000-8000-000000000001";
const subject = "00000000-0000-4000-8000-000000000002";
const other = "00000000-0000-4000-8000-000000000003";
const envelope = { schema_version: 1, business_id: business };
const file = {
  file_id: other,
  media_type: "application/pdf",
  size_bytes: 1024,
  sha256: "a".repeat(64),
  file_name: "FAKE Agreement.pdf",
  validator_version: "gorgona-file-profile-v1",
  scan_status: "not_scanned",
  uploaded_at: "2026-10-05T12:00:00Z",
};
const document = {
  ...envelope,
  document_id: subject,
  revision: 1,
  title: "FAKE Agreement",
  category: "agreement",
  valid_from: "2026-01-01",
  valid_until: "2026-12-31",
  archived: false,
  file,
  created_at: "2026-10-05T12:00:00Z",
};
const summary = {
  document_id: subject,
  revision: 1,
  title: "FAKE Agreement",
  category: "agreement",
  valid_from: null,
  valid_until: null,
  archived: false,
  media_type: null,
  updated_at: "2026-10-05T12:00:00Z",
};

test("documents reject extra fields, scan verdicts and inverted validity", () => {
  expect(documentSchema.safeParse(document).success).toBe(true);
  expect(documentSchema.safeParse({ ...document, file: null }).success).toBe(
    true,
  );
  for (const change of [
    { content: "AAAA" },
    { category: "contract" },
    { revision: 0 },
    { valid_from: "2027-01-01" },
    { valid_until: "2026-13-01" },
    { file: { ...file, scan_status: "clean" } },
    { file: { ...file, media_type: "text/html" } },
    { file: { ...file, sha256: "A".repeat(64) } },
    { file: { ...file, size_bytes: 10 * 1024 * 1024 + 1 } },
    { file: { ...file, preview_url: "https://example.test/x" } },
  ])
    expect(documentSchema.safeParse({ ...document, ...change }).success).toBe(
      false,
    );
});

test("lists name the upload state and refuse duplicate documents", () => {
  const page = {
    ...envelope,
    file_uploads: "scanner_not_configured",
    items: [summary],
    next_cursor: null,
  };
  expect(documentListSchema.safeParse(page).success).toBe(true);
  expect(
    documentListSchema.safeParse({ ...page, items: [summary, summary] })
      .success,
  ).toBe(false);
  expect(
    documentListSchema.safeParse({ ...page, file_uploads: "scanned" }).success,
  ).toBe(false);
});

test("link results must name the document they changed", () => {
  const result = {
    ...envelope,
    document_id: subject,
    link: {
      link_id: other,
      document_id: subject,
      counterparty_id: other,
      sequence: 1,
      action: "linked",
      decided_at: "2026-10-05T12:00:00Z",
    },
  };
  expect(documentLinkResultSchema.safeParse(result).success).toBe(true);
  expect(
    documentLinkResultSchema.safeParse({
      ...result,
      link: { ...result.link, document_id: other },
    }).success,
  ).toBe(false);
});

test("JSON contracts cover document routes but never file bytes", () => {
  const root = `/v1/businesses/${business}`;
  expect(
    managementResponseSchema(`${root}/documents`, "GET").safeParse({
      ...envelope,
      file_uploads: "enabled",
      items: [],
      next_cursor: null,
    }).success,
  ).toBe(true);
  expect(
    managementResponseSchema(`${root}/documents/${subject}`, "PUT").safeParse(
      document,
    ).success,
  ).toBe(true);
  expect(
    managementResponseSchema(
      `${root}/document-files/${other}`,
      "GET",
    ).safeParse({ ...envelope, ...file }).success,
  ).toBe(true);
  for (const [path, method] of [
    [`${root}/documents/${subject}/versions/1/file`, "GET"],
    [`${root}/document-files/${other}`, "PUT"],
    [`${root}/documents/${subject}/counterparty-links`, "DELETE"],
  ] as const)
    expect(() => managementResponseSchema(path, method)).toThrow(
      "Unrecognized business response contract",
    );
});

test("only PDF, PNG and JPEG signatures are recognized", () => {
  const bytes = (text: string) => new TextEncoder().encode(text);
  expect(detectMediaType(bytes("%PDF-1.7\n"))).toBe("application/pdf");
  expect(
    detectMediaType(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10])),
  ).toBe("image/png");
  expect(detectMediaType(new Uint8Array([0xff, 0xd8, 0xff]))).toBe(
    "image/jpeg",
  );
  for (const head of [
    bytes("GIF89a"),
    bytes("<html>"),
    bytes("%PDF"),
    new Uint8Array([0x89, 0x50, 0x4e, 0x47]),
    new Uint8Array([]),
  ])
    expect(detectMediaType(head)).toBeNull();
});

test("validity is computed from dates, never stored", () => {
  const dates = (valid_from: string | null, valid_until: string | null) => ({
    valid_from,
    valid_until,
  });
  expect(validityState(dates(null, null), "2026-10-05")).toBe("no_dates");
  expect(validityState(dates(null, "2026-10-04"), "2026-10-05")).toBe(
    "expired",
  );
  expect(validityState(dates(null, "2026-10-05"), "2026-10-05")).toBe("valid");
  expect(validityState(dates("2026-10-06", null), "2026-10-05")).toBe(
    "not_yet_valid",
  );
});

test("names and titles are limited in code points like the server", () => {
  const emoji = "\u{1F600}";
  const astral = {
    ...document,
    title: emoji.repeat(200),
    file: { ...file, file_name: emoji.repeat(116) + ".pdf" },
  };
  expect(documentSchema.safeParse(astral).success).toBe(true);
  expect(
    documentSchema.safeParse({ ...astral, title: emoji.repeat(201) }).success,
  ).toBe(false);
  expect(
    documentSchema.safeParse({
      ...astral,
      file: { ...file, file_name: emoji.repeat(117) + ".pdf" },
    }).success,
  ).toBe(false);
});
