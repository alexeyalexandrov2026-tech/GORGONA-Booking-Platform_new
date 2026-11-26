import { z } from "zod";
import { api } from "./api";
import { authorizedResponse, ManagementApiError } from "./management-api";

/** Brand media backed by Cloudflare R2 (PNG, JPEG, WEBP only; 5 MiB per file). */
export const MEDIA_MAX_BYTES = 5 * 1024 * 1024;
export const MEDIA_CONTENT_TYPES = ["image/png", "image/jpeg", "image/webp"];
export const MEDIA_ACCEPT = MEDIA_CONTENT_TYPES.join(",");
export type MediaKind = "logo" | "cover" | "service_photo" | "gallery";

export const mediaAssetSchema = z.object({
  id: z.string(),
  kind: z.string(),
  filename: z.string(),
  content_type: z.string(),
  size_bytes: z.number().int(),
  sha256: z.string(),
  storage_backend: z.string(),
  public_url: z.string(),
  created_at: z.string(),
});
export type MediaAsset = z.infer<typeof mediaAssetSchema>;

/** Client-side check mirroring the backend: allowed type, magic bytes and size. */
export async function validateImageFile(file: File): Promise<string | null> {
  if (!MEDIA_CONTENT_TYPES.includes(file.type))
    return "Choose a PNG, JPEG, or WEBP image.";
  if (file.size === 0) return "The selected file is empty.";
  if (file.size > MEDIA_MAX_BYTES)
    return `The image is ${formatBytes(file.size)}. The limit is 5 MB.`;
  const head = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const png = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every(
    (b, i) => head[i] === b,
  );
  const jpeg = head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff;
  const webp =
    String.fromCharCode(...head.slice(0, 4)) === "RIFF" &&
    String.fromCharCode(...head.slice(8, 12)) === "WEBP";
  if (!png && !jpeg && !webp)
    return "The file content is not a valid PNG, JPEG, or WEBP image.";
  return null;
}

export function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () =>
      typeof reader.result === "string"
        ? resolve(reader.result)
        : reject(new Error("The image could not be read."));
    reader.onerror = () => reject(new Error("The image could not be read."));
    reader.readAsDataURL(file);
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function mediaPath(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/media`;
}

async function parse<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "The media service returned incomplete information. Please retry.",
      response.status,
    );
  return parsed.data;
}

export async function fetchBusinessMedia(
  businessId: string,
  kind?: MediaKind,
): Promise<MediaAsset[]> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  const response = await authorizedResponse(
    `${mediaPath(businessId)}${query}`,
    {
      headers: { Accept: "application/json" },
    },
  );
  return parse(response, z.array(mediaAssetSchema));
}

export async function uploadBusinessMedia(
  businessId: string,
  kind: MediaKind,
  file: File,
): Promise<MediaAsset> {
  const dataUrl = await readAsDataUrl(file);
  const comma = dataUrl.indexOf(",");
  const data_base64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
  const response = await authorizedResponse(
    mediaPath(businessId),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        kind,
        filename: file.name.slice(0, 180) || `${kind}.img`,
        data_base64,
      }),
    },
    60000,
  );
  return parse(response, mediaAssetSchema);
}

export async function deleteBusinessMedia(
  businessId: string,
  assetId: string,
): Promise<void> {
  await authorizedResponse(
    `${mediaPath(businessId)}/${encodeURIComponent(assetId)}`,
    { method: "DELETE" },
  );
}

/** Public storefront media for the business resolved by the request host. */
export async function fetchCustomerMedia(
  signal?: AbortSignal,
): Promise<MediaAsset[]> {
  return api("media", z.array(mediaAssetSchema), undefined, undefined, signal);
}

/** The newest asset of a kind (the list is newest first). */
export function latestOfKind(
  assets: readonly MediaAsset[],
  kind: MediaKind,
): MediaAsset | undefined {
  return assets
    .filter((a) => a.kind === kind)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
}

/** Only same-origin media URLs issued by the API are rendered. */
export function safeMediaUrl(asset: MediaAsset | undefined): string | null {
  if (!asset) return null;
  return /^\/v1\/customer\/media\/[0-9a-f-]{36}$/i.test(asset.public_url)
    ? asset.public_url
    : null;
}
