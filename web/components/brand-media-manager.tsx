"use client";

import Image from "next/image";
import { useEffect, useId, useRef, useState } from "react";
import { formatDate } from "../lib/management-api";
import {
  deleteBusinessMedia,
  fetchBusinessMedia,
  formatBytes,
  MEDIA_ACCEPT,
  safeMediaUrl,
  uploadBusinessMedia,
  validateImageFile,
  type MediaAsset,
  type MediaKind,
} from "../lib/media-api";
import "../app/us-release-v2.css";

const KINDS: { kind: MediaKind; title: string; hint: string }[] = [
  {
    kind: "logo",
    title: "Logo",
    hint: "Shown in the header of your public booking page. Square images work best.",
  },
  {
    kind: "cover",
    title: "Cover image",
    hint: "A wide banner on your public booking page. 1600 × 600 px or larger works best.",
  },
  {
    kind: "gallery",
    title: "Photos",
    hint: "Photos of your work, team, or space for your storefront gallery.",
  },
];

function backendLabel(backend: string): string {
  if (backend === "r2") return "Stored on Cloudflare R2";
  if (backend === "inline") return "Stored in the database (R2 unavailable)";
  return `Stored: ${backend}`;
}

/** Brand media for the public storefront: logo, cover and photos. */
export function BrandMediaManager({ businessId }: { businessId: string }) {
  const [assets, setAssets] = useState<MediaAsset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let active = true;
    fetchBusinessMedia(businessId)
      .then((list) => {
        if (!active) return;
        setAssets(list);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active)
          setError(
            err instanceof Error ? err.message : "Unable to load brand media.",
          );
      });
    return () => {
      active = false;
    };
  }, [businessId, tick]);

  return (
    <section
      className="usr-card"
      aria-labelledby="brand-media-heading"
      style={{ marginBottom: 0 }}
    >
      <h3 id="brand-media-heading" style={{ fontSize: "1.1rem" }}>
        Brand media
      </h3>
      <p className="usr-muted">
        Upload PNG, JPEG, or WEBP images up to 5 MB each. The newest logo and
        cover appear on your public booking page.
      </p>
      {error && (
        <div className="mgmt-error-banner" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="secondary mgmt-btn-small"
            onClick={() => setTick((t) => t + 1)}
          >
            Retry
          </button>
        </div>
      )}
      {!assets && !error && (
        <p className="mgmt-loading" aria-live="polite">
          Loading brand media…
        </p>
      )}
      {assets && (
        <div className="usr-media-kinds">
          {KINDS.map((k) => (
            <MediaKindPanel
              key={k.kind}
              businessId={businessId}
              kind={k.kind}
              title={k.title}
              hint={k.hint}
              assets={assets.filter((a) => a.kind === k.kind)}
              onChanged={() => setTick((t) => t + 1)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function MediaKindPanel({
  businessId,
  kind,
  title,
  hint,
  assets,
  onChanged,
}: {
  businessId: string;
  kind: MediaKind;
  title: string;
  hint: string;
  assets: MediaAsset[];
  onChanged: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [broken, setBroken] = useState<Set<string>>(() => new Set());
  const previewRef = useRef<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const hintId = useId();
  const headingId = useId();

  useEffect(
    () => () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    },
    [],
  );

  function clearSelection() {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = null;
    setPreview(null);
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function choose(next: File | null) {
    setInvalid(null);
    setNotice(null);
    setError(null);
    clearSelection();
    if (!next) return;
    const problem = await validateImageFile(next);
    if (problem) {
      setInvalid(problem);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    const url = URL.createObjectURL(next);
    previewRef.current = url;
    setPreview(url);
    setFile(next);
  }

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await uploadBusinessMedia(businessId, kind, file);
      clearSelection();
      setNotice(`${title} uploaded: ${saved.filename}.`);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(asset: MediaAsset) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await deleteBusinessMedia(businessId, asset.id);
      setConfirmDelete(null);
      setNotice(`${asset.filename} deleted.`);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setBusy(false);
    }
  }

  const newestId = assets[0]?.id;

  return (
    <div
      className="usr-connector"
      role="group"
      aria-labelledby={headingId}
      aria-busy={busy}
    >
      <h4 id={headingId}>{title}</h4>
      <p id={hintId} className="usr-muted">
        {hint}
      </p>
      <label htmlFor={inputId} style={{ marginBottom: 4 }}>
        Choose a {title.toLowerCase()} file
      </label>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={MEDIA_ACCEPT}
        aria-describedby={hintId}
        disabled={busy}
        onChange={(e) => void choose(e.target.files?.[0] ?? null)}
      />
      {invalid && (
        <p className="usr-field-error" role="alert">
          {invalid}
        </p>
      )}
      {preview && file && (
        <div className="usr-stack" style={{ gap: 8 }}>
          <Image
            src={preview}
            alt={`Preview of ${file.name}`}
            width={320}
            height={200}
            unoptimized
            className="usr-preview"
            style={{ width: "auto", height: "auto" }}
          />
          <span className="usr-muted">
            {file.name} · {formatBytes(file.size)}
          </span>
          <div className="usr-inline">
            <button
              type="button"
              className="usr-small-btn"
              disabled={busy}
              onClick={() => void upload()}
            >
              {busy ? "Uploading…" : `Upload ${title.toLowerCase()}`}
            </button>
            <button
              type="button"
              className="secondary usr-small-btn"
              disabled={busy}
              onClick={clearSelection}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && (
        <p className="usr-field-error" role="alert">
          {error}
        </p>
      )}
      <p role="status" className="usr-muted" style={{ margin: 0 }}>
        {notice ?? ""}
      </p>
      {assets.length === 0 ? (
        <p className="usr-muted" style={{ margin: 0 }}>
          No {title.toLowerCase()} uploaded yet.
        </p>
      ) : (
        <ul className="usr-media-list" aria-label={`Uploaded ${title}`}>
          {assets.map((a) => {
            const src = safeMediaUrl(a);
            return (
              <li key={a.id} className="usr-media-item">
                {src && !broken.has(a.id) ? (
                  <Image
                    src={src}
                    alt={`${title}: ${a.filename}`}
                    width={96}
                    height={96}
                    unoptimized
                    className="usr-thumb"
                    onError={() => setBroken((b) => new Set(b).add(a.id))}
                  />
                ) : (
                  <span className="usr-thumb usr-thumb-fallback">
                    Preview unavailable on this host
                  </span>
                )}
                <div style={{ minWidth: 0 }}>
                  <strong style={{ overflowWrap: "anywhere" }}>
                    {a.filename}
                  </strong>
                  {kind !== "gallery" && a.id === newestId && (
                    <>
                      {" "}
                      <span className="usr-badge usr-badge-ai">
                        Live on storefront
                      </span>
                    </>
                  )}
                  <div className="usr-muted">
                    {formatBytes(a.size_bytes)} ·{" "}
                    {backendLabel(a.storage_backend)} ·{" "}
                    {formatDate(a.created_at)}
                  </div>
                  {confirmDelete === a.id ? (
                    <div
                      className="usr-inline"
                      role="group"
                      aria-label={`Delete ${a.filename}?`}
                    >
                      <span>Delete {a.filename}?</span>
                      <button
                        type="button"
                        className="usr-danger usr-small-btn"
                        disabled={busy}
                        onClick={() => void remove(a)}
                      >
                        {busy ? "Deleting…" : "Delete image"}
                      </button>
                      <button
                        type="button"
                        className="secondary usr-small-btn"
                        disabled={busy}
                        onClick={() => setConfirmDelete(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="usr-danger usr-small-btn"
                      style={{ marginTop: 8 }}
                      aria-label={`Delete ${a.filename}`}
                      onClick={() => setConfirmDelete(a.id)}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
