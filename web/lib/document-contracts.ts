import { z } from "zod";

export const MAX_FILE_BYTES = 10 * 1024 * 1024;
const id = z.uuid();
const revision = z.number().int().positive();
const instant = z.iso.datetime({ offset: true });
const day = z.iso.date();
export const mediaType = z.enum(["application/pdf", "image/png", "image/jpeg"]);
export const category = z.enum([
  "agreement",
  "certificate",
  "invoice",
  "report",
  "other",
]);
const envelope = { schema_version: z.literal(1), business_id: id };
// The server limits text in Unicode code points, not UTF-16 units.
export const text = (min: number, max: number) =>
  z.string().refine((v) => {
    const length = Array.from(v).length;
    return length >= min && length <= max;
  });
const ordered = (v: {
  valid_from: string | null;
  valid_until: string | null;
}) =>
  v.valid_from === null ||
  v.valid_until === null ||
  v.valid_from <= v.valid_until;

const fileFields = {
  file_id: id,
  media_type: mediaType,
  size_bytes: z.number().int().min(1).max(MAX_FILE_BYTES),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  file_name: text(5, 120),
  validator_version: z.string().min(1).max(64),
  // There is no scanner: the server never claims a file is safe.
  scan_status: z.literal("not_scanned"),
  uploaded_at: instant,
};
const fileMetadata = z.strictObject(fileFields);
export const documentFileSchema = z.strictObject({
  ...envelope,
  ...fileFields,
});
export const documentSchema = z
  .strictObject({
    ...envelope,
    document_id: id,
    revision,
    title: text(1, 200),
    category,
    valid_from: day.nullable(),
    valid_until: day.nullable(),
    archived: z.boolean(),
    file: fileMetadata.nullable(),
    created_at: instant,
  })
  .refine(ordered);
const summary = z
  .strictObject({
    document_id: id,
    revision,
    title: text(1, 200),
    category,
    valid_from: day.nullable(),
    valid_until: day.nullable(),
    archived: z.boolean(),
    media_type: mediaType.nullable(),
    updated_at: instant,
  })
  .refine(ordered);
export const documentListSchema = z
  .strictObject({
    ...envelope,
    file_uploads: z.enum(["enabled", "scanner_not_configured"]),
    items: z.array(summary).max(100),
    next_cursor: id.nullable(),
  })
  .refine(
    (v) => new Set(v.items.map((d) => d.document_id)).size === v.items.length,
  );
export const documentHistorySchema = z.strictObject({
  ...envelope,
  document_id: id,
  items: z
    .array(
      z.strictObject({
        revision,
        title: z.string(),
        archived: z.boolean(),
        file_id: id.nullable(),
        created_at: instant,
      }),
    )
    .max(100),
  next_cursor: revision.nullable(),
});
const link = z.strictObject({
  link_id: id,
  document_id: id,
  counterparty_id: id,
  sequence: revision,
  action: z.enum(["linked", "unlinked"]),
  decided_at: instant,
});
export const documentLinkResultSchema = z
  .strictObject({ ...envelope, document_id: id, link })
  .refine((v) => v.link.document_id === v.document_id);
export const documentLinksSchema = z
  .strictObject({
    ...envelope,
    document_id: id,
    current: z
      .array(
        z.strictObject({
          counterparty_id: id,
          display_name: z.string(),
          state: z.enum(["active", "archived", "merged"]),
          sequence: revision,
          decided_at: instant,
        }),
      )
      .max(200),
    history: z.array(link).max(200),
  })
  .refine((v) => v.history.every((l) => l.document_id === v.document_id));
export const counterpartyDocumentsSchema = z.strictObject({
  ...envelope,
  counterparty_id: id,
  items: z
    .array(
      z.strictObject({
        document: summary,
        counterparty_id: id,
        sequence: revision,
        decided_at: instant,
      }),
    )
    .max(100),
  next_cursor: id.nullable(),
});

/**
 * JSON contracts of document routes. File bytes (upload and download) are not JSON:
 * they use their own checked requests, so a JSON request to them is refused here.
 */
export function documentResponseSchema(
  path: string,
  method: string,
): z.ZodType | null {
  if (path === "/documents" && method === "GET") return documentListSchema;
  if (/^\/document-files\/[0-9a-f-]{36}$/i.test(path) && method === "GET")
    return documentFileSchema;
  if (/^\/counterparties\/[0-9a-f-]{36}\/documents$/i.test(path))
    return method === "GET" ? counterpartyDocumentsSchema : null;
  const route =
    /^\/documents\/[0-9a-f-]{36}(?:\/(versions|counterparty-links))?$/i.exec(
      path,
    );
  if (!route) return null;
  const suffix = route[1];
  if (!suffix && ["GET", "PUT"].includes(method)) return documentSchema;
  if (suffix === "versions" && method === "GET") return documentHistorySchema;
  if (suffix === "counterparty-links")
    return method === "GET"
      ? documentLinksSchema
      : method === "POST"
        ? documentLinkResultSchema
        : null;
  return null;
}

/** The type proven by the leading bytes; the declared browser type is not trusted. */
export function detectMediaType(
  head: Uint8Array,
): z.infer<typeof mediaType> | null {
  const starts = (bytes: number[]) => bytes.every((b, i) => head[i] === b);
  if (starts([0x25, 0x50, 0x44, 0x46, 0x2d])) return "application/pdf";
  if (starts([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
    return "image/png";
  if (starts([0xff, 0xd8])) return "image/jpeg";
  return null;
}

export function validityState(
  document: { valid_from: string | null; valid_until: string | null },
  today: string,
): "not_yet_valid" | "valid" | "expired" | "no_dates" {
  if (document.valid_until !== null && document.valid_until < today)
    return "expired";
  if (document.valid_from !== null && document.valid_from > today)
    return "not_yet_valid";
  return document.valid_from === null && document.valid_until === null
    ? "no_dates"
    : "valid";
}

export type MediaType = z.infer<typeof mediaType>;
export type DocumentCategory = z.infer<typeof category>;
export type DocumentFile = z.infer<typeof documentFileSchema>;
export type Document = z.infer<typeof documentSchema>;
export type DocumentPage = z.infer<typeof documentListSchema>;
export type DocumentHistory = z.infer<typeof documentHistorySchema>;
export type DocumentLinks = z.infer<typeof documentLinksSchema>;
export type CounterpartyDocuments = z.infer<typeof counterpartyDocumentsSchema>;
export interface DocumentInput {
  schema_version: 1;
  expected_revision: number;
  title: string;
  category: DocumentCategory;
  valid_from: string | null;
  valid_until: string | null;
  archived: boolean;
  file_id: string | null;
}
export type DocumentLinkInput =
  | { schema_version: 1; action: "link"; counterparty_id: string }
  | {
      schema_version: 1;
      action: "unlink";
      counterparty_id: string;
      expected_sequence: number;
    };
export type DocumentCommand =
  | { type: "save"; id: string; key: string; body: DocumentInput }
  | { type: "link"; id: string; key: string; body: DocumentLinkInput };
/** A checked upload: exactly these bytes are hashed, sent and retried. */
export interface FileUpload {
  fileId: string;
  key: string;
  name: string;
  bytes: ArrayBuffer;
  sha256: string;
  mediaType: MediaType;
}
