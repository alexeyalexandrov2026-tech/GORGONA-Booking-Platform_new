"use client";
import type {
  Document,
  DocumentFile,
  DocumentInput,
} from "../lib/document-contracts";

export const categories = [
  ["agreement", "Agreement"],
  ["certificate", "Certificate"],
  ["invoice", "Invoice"],
  ["report", "Report"],
  ["other", "Other"],
] as const;

export function fileSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileSummary({
  file,
}: {
  file: DocumentFile | Document["file"];
}) {
  if (!file) return <p>No file attached.</p>;
  return (
    <p>
      {file.file_name} · {file.media_type} · {fileSize(file.size_bytes)} ·{" "}
      <strong>Not scanned for malware</strong>
    </p>
  );
}

export function DocumentEditor({
  selected,
  form,
  setForm,
  attached,
  locked,
  uploadLocked,
  reloadDisabled,
  onReload,
  onChooseFile,
  onDownload,
  onSubmit,
}: {
  selected: Document | null;
  form: DocumentInput;
  setForm: (form: DocumentInput) => void;
  attached: DocumentFile | Document["file"];
  locked: boolean;
  uploadLocked: boolean;
  reloadDisabled: boolean;
  onReload: () => void;
  onChooseFile: (file: File) => void;
  onDownload: (() => void) | null;
  onSubmit: (event: React.FormEvent) => void;
}) {
  return (
    <section aria-label="Document card" className="mgmt-card">
      <h2>{selected ? selected.title : "New document"}</h2>
      {selected && (
        <>
          <p>
            Version {selected.revision} ·{" "}
            {selected.archived ? "archived" : "current"}
          </p>
          <button
            disabled={reloadDisabled}
            className="secondary"
            onClick={onReload}
          >
            Reload document
          </button>
          <h3>Saved file</h3>
          <FileSummary file={selected.file} />
          {onDownload && (
            <button
              className="secondary"
              disabled={reloadDisabled}
              onClick={onDownload}
            >
              Download file
            </button>
          )}
        </>
      )}
      <form onSubmit={(e) => void onSubmit(e)}>
        <fieldset disabled={locked}>
          <legend>Document details</legend>
          <div className="cp-fields">
            <label>
              Title
              <input
                required
                maxLength={200}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <label>
              Category
              <select
                value={form.category}
                onChange={(e) =>
                  setForm({
                    ...form,
                    category: e.target.value as DocumentInput["category"],
                  })
                }
              >
                {categories.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Valid from
              <input
                type="date"
                value={form.valid_from ?? ""}
                onChange={(e) =>
                  setForm({ ...form, valid_from: e.target.value || null })
                }
              />
            </label>
            <label>
              Valid until
              <input
                type="date"
                min={form.valid_from ?? undefined}
                value={form.valid_until ?? ""}
                onChange={(e) =>
                  setForm({ ...form, valid_until: e.target.value || null })
                }
              />
            </label>
          </div>
          <label>
            <input
              type="checkbox"
              checked={form.archived}
              onChange={(e) => setForm({ ...form, archived: e.target.checked })}
            />{" "}
            Archived
          </label>
          <h3>File for the next saved version</h3>
          <FileSummary file={attached} />
          {attached && (
            <button
              type="button"
              className="secondary"
              onClick={() => setForm({ ...form, file_id: null })}
            >
              Save the next version without a file
            </button>
          )}
          <label>
            Attach a PDF, PNG or JPEG file (up to 10 MiB)
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              disabled={uploadLocked}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) onChooseFile(file);
              }}
            />
          </label>
          <button type="submit">Save document</button>
        </fieldset>
      </form>
    </section>
  );
}
