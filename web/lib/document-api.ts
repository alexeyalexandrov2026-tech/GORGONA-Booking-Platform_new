import { z } from "zod";
import {
  authorizedResponse,
  managementFetch,
  ManagementApiError,
} from "./management-api";
import {
  MAX_FILE_BYTES,
  counterpartyDocumentsSchema,
  detectMediaType,
  documentFileSchema,
  documentHistorySchema,
  documentLinkResultSchema,
  documentLinksSchema,
  documentListSchema,
  documentSchema,
  type DocumentCommand,
  type DocumentFile,
  type FileUpload,
} from "./document-contracts";

const base = (business: string) => `/v1/businesses/${business}`;
const unsafe = (message: string) =>
  new ManagementApiError("INVALID_RESPONSE", message);

async function read<T extends { business_id: string; document_id?: string }>(
  business: string,
  schema: z.ZodType<T>,
  path: string,
  subject?: string,
  init?: RequestInit,
): Promise<T> {
  const result = schema.parse(await managementFetch(path, init));
  if (
    result.business_id !== business ||
    (subject && result.document_id !== subject)
  )
    throw unsafe("Unable to load this document safely.");
  return result;
}

export function fetchDocuments(
  business: string,
  q: string,
  archived: boolean,
  after?: string,
) {
  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (archived) query.set("archived", "true");
  if (after) query.set("after", after);
  return read(
    business,
    documentListSchema,
    `${base(business)}/documents?${query}`,
  );
}
export async function fetchDocument(
  business: string,
  subject: string,
  revision?: number,
) {
  const result = await read(
    business,
    documentSchema,
    `${base(business)}/documents/${subject}${revision ? `?revision=${revision}` : ""}`,
    subject,
  );
  if (revision && result.revision !== revision)
    throw unsafe("Unable to load this saved version safely.");
  return result;
}
export function fetchDocumentHistory(
  business: string,
  subject: string,
  before?: number,
) {
  return read(
    business,
    documentHistorySchema,
    `${base(business)}/documents/${subject}/versions${before ? `?before=${before}` : ""}`,
    subject,
  );
}
export function fetchDocumentLinks(business: string, subject: string) {
  return read(
    business,
    documentLinksSchema,
    `${base(business)}/documents/${subject}/counterparty-links`,
    subject,
  );
}
export async function fetchCounterpartyDocuments(
  business: string,
  counterparty: string,
  after?: string,
) {
  const result = await read(
    business,
    counterpartyDocumentsSchema,
    `${base(business)}/counterparties/${counterparty}/documents${after ? `?after=${after}` : ""}`,
  );
  if (result.counterparty_id !== counterparty)
    throw unsafe("Unable to load linked documents safely.");
  return result;
}
export function executeDocumentCommand(
  business: string,
  command: DocumentCommand,
) {
  const init = {
    body: JSON.stringify(command.body),
    headers: { "Idempotency-Key": command.key },
  };
  const path = `${base(business)}/documents/${command.id}`;
  return command.type === "save"
    ? read(business, documentSchema, path, command.id, {
        ...init,
        method: "PUT",
      })
    : read(
        business,
        documentLinkResultSchema,
        `${path}/counterparty-links`,
        command.id,
        { ...init, method: "POST" },
      );
}

async function sha256(data: ArrayBuffer): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", data));
  return Array.from(digest, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Check a chosen file locally; the server repeats every check. */
export async function prepareUpload(file: File): Promise<FileUpload> {
  if (file.size < 1 || file.size > MAX_FILE_BYTES)
    throw new ManagementApiError(
      "FILE_TOO_LARGE",
      "Choose a PDF, PNG or JPEG file of at most 10 MiB.",
    );
  const bytes = await file.arrayBuffer();
  const media = detectMediaType(
    new Uint8Array(bytes, 0, Math.min(8, bytes.byteLength)),
  );
  if (!media)
    throw new ManagementApiError(
      "UNSUPPORTED_MEDIA_TYPE",
      "Choose a PDF, PNG or JPEG file. Other types are not accepted.",
    );
  return {
    fileId: crypto.randomUUID(),
    key: crypto.randomUUID(),
    name: file.name,
    bytes,
    mediaType: media,
    sha256: await sha256(bytes),
  };
}

/** Send raw bytes once per key; a retry with the same key replays the stored result. */
export async function uploadDocumentFile(
  business: string,
  upload: FileUpload,
): Promise<DocumentFile> {
  const response = await authorizedResponse(
    `${base(business)}/document-files/${upload.fileId}`,
    {
      method: "PUT",
      body: upload.bytes,
      headers: {
        "Content-Type": upload.mediaType,
        "X-File-Name": encodeURIComponent(upload.name),
        "Idempotency-Key": upload.key,
      },
    },
    60000,
  );
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ManagementApiError(
      "NETWORK_ERROR",
      "The upload result was not received. Retry the same upload to check it.",
    );
  }
  const parsed = documentFileSchema.safeParse(data);
  if (
    !parsed.success ||
    parsed.data.business_id !== business ||
    parsed.data.file_id !== upload.fileId ||
    parsed.data.media_type !== upload.mediaType ||
    parsed.data.size_bytes !== upload.bytes.byteLength ||
    parsed.data.sha256 !== upload.sha256
  )
    throw unsafe("The stored file does not match the chosen file.");
  return parsed.data;
}

/**
 * Download one saved version's file and verify type, size and SHA-256 before it
 * reaches the device. Nothing is previewed or opened.
 */
export async function downloadDocumentFile(
  business: string,
  subject: string,
  revision: number,
  expected: { media_type: string; size_bytes: number; sha256: string },
): Promise<Blob> {
  const response = await authorizedResponse(
    `${base(business)}/documents/${subject}/versions/${revision}/file`,
    { method: "GET" },
    60000,
  );
  let bytes: ArrayBuffer;
  try {
    bytes = await response.arrayBuffer();
  } catch {
    throw new ManagementApiError(
      "NETWORK_ERROR",
      "The download was interrupted. Try again.",
    );
  }
  const type = (response.headers.get("content-type") ?? "")
    .split(";")[0]!
    .trim()
    .toLowerCase();
  if (
    type !== expected.media_type ||
    response.headers.get("x-file-sha256") !== expected.sha256 ||
    bytes.byteLength !== expected.size_bytes ||
    (await sha256(bytes)) !== expected.sha256
  )
    throw new ManagementApiError(
      "FILE_INTEGRITY_FAILED",
      "The downloaded file did not match its saved record and was not saved.",
    );
  return new Blob([bytes], { type: "application/octet-stream" });
}
