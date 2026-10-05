"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { DocumentEditor, categories } from "./document-editor";
import { DocumentRelations } from "./document-relations";
import {
  downloadDocumentFile,
  executeDocumentCommand,
  fetchDocument,
  fetchDocumentHistory,
  fetchDocumentLinks,
  fetchDocuments,
  prepareUpload,
  uploadDocumentFile,
} from "../lib/document-api";
import { fetchConfiguration, ManagementApiError } from "../lib/management-api";
import {
  validityState,
  type Document,
  type DocumentCommand,
  type DocumentFile,
  type DocumentHistory,
  type DocumentInput,
  type DocumentLinks,
  type DocumentPage,
  type FileUpload,
} from "../lib/document-contracts";

const empty = (): DocumentInput => ({
  schema_version: 1,
  expected_revision: 0,
  title: "",
  category: "agreement",
  valid_from: null,
  valid_until: null,
  archived: false,
  file_id: null,
});
const failure = (error: unknown) =>
  error instanceof Error ? error.message : "Unable to complete this action.";
const uncertain = (error: unknown) =>
  !(error instanceof ManagementApiError) ||
  error.status === undefined ||
  error.status >= 500;
const validityText = {
  expired: "expired",
  not_yet_valid: "not yet valid",
  valid: "valid",
  no_dates: "no validity dates",
};

function saveToDevice(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.rel = "noopener";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function Documents({ businessId }: { businessId: string }) {
  const [items, setItems] = useState<DocumentPage["items"]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [uploads, setUploads] =
    useState<DocumentPage["file_uploads"]>("enabled");
  const [query, setQuery] = useState("");
  const [archived, setArchived] = useState(false);
  const [selected, setSelected] = useState<Document | null>(null);
  const [form, setForm] = useState<DocumentInput>(empty);
  const [uploaded, setUploaded] = useState<DocumentFile | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [linksEnabled, setLinksEnabled] = useState(false);
  const [history, setHistory] = useState<DocumentHistory | null>(null);
  const [historical, setHistorical] = useState<Document | null>(null);
  const [links, setLinks] = useState<DocumentLinks | null>(null);
  const [pending, setPending] = useState<DocumentCommand | null>(null);
  const [pendingUpload, setPendingUpload] = useState<FileUpload | null>(null);
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const today = new Date().toLocaleDateString("en-CA");

  function applyConfiguration(modules: string[]) {
    setEnabled(modules.includes("documents"));
    setLinksEnabled(
      modules.includes("documents") && modules.includes("counterparties"),
    );
  }

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchDocuments(businessId, "", false),
      fetchConfiguration(businessId),
    ])
      .then(([page, configuration]) => {
        if (!active) return;
        setItems(page.items);
        setCursor(page.next_cursor);
        setUploads(page.file_uploads);
        applyConfiguration(configuration.effective_module_ids);
      })
      .catch((e: unknown) => {
        if (active) setError(failure(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId]);

  function choose(doc: Document | null) {
    setSelected(doc);
    setForm(
      doc
        ? {
            schema_version: 1,
            expected_revision: doc.revision,
            title: doc.title,
            category: doc.category,
            valid_from: doc.valid_from,
            valid_until: doc.valid_until,
            archived: doc.archived,
            file_id: doc.file?.file_id ?? null,
          }
        : empty(),
    );
    setUploaded(null);
    setHistorical(null);
    setHistory(null);
    setLinks(null);
    setConflict(false);
  }

  async function load(id: string) {
    const doc = await fetchDocument(businessId, id);
    choose(doc);
    const [versions, linked, configuration] = await Promise.all([
      fetchDocumentHistory(businessId, id),
      fetchDocumentLinks(businessId, id),
      fetchConfiguration(businessId),
    ]);
    setHistory(versions);
    setLinks(linked);
    applyConfiguration(configuration.effective_module_ids);
  }

  async function inspect(id: string) {
    if (busy || pending || pendingUpload) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await load(id);
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  async function search(after?: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const page = await fetchDocuments(
        businessId,
        query.trim(),
        archived,
        after,
      );
      setItems((previous) =>
        after
          ? [
              ...previous,
              ...page.items.filter(
                (row) =>
                  !previous.some((p) => p.document_id === row.document_id),
              ),
            ]
          : page.items,
      );
      setCursor(page.next_cursor);
      setUploads(page.file_uploads);
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  async function run(command: DocumentCommand) {
    if (busy) return;
    setPending(command);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await executeDocumentCommand(businessId, command);
      setPending(null);
      setMessage(
        command.type === "save" ? "Document saved." : "Link change recorded.",
      );
      // The command succeeded. Any following read failure is separate from its receipt.
      await load(command.id);
      const page = await fetchDocuments(businessId, query.trim(), archived);
      setItems(page.items);
      setCursor(page.next_cursor);
    } catch (e: unknown) {
      setError(failure(e));
      if (!uncertain(e) && e instanceof ManagementApiError) {
        setPending(null);
        // A disabled module is explained by its own notice; nothing needs reloading.
        setConflict(e.status === 409 && e.code !== "MODULE_DISABLED");
        if (e.code === "MODULE_DISABLED") {
          if (command.type === "save") setEnabled(false);
          setLinksEnabled(false);
        }
      }
    } finally {
      setBusy(false);
    }
  }

  async function sendUpload(upload: FileUpload) {
    setPendingUpload(upload);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const stored = await uploadDocumentFile(businessId, upload);
      setPendingUpload(null);
      setUploaded(stored);
      setForm((current) => ({ ...current, file_id: stored.file_id }));
      setMessage(
        "File uploaded. It was checked against the supported formats but not scanned for malware. Save the document to attach it.",
      );
    } catch (e: unknown) {
      setError(failure(e));
      if (
        e instanceof ManagementApiError &&
        (!uncertain(e) || e.code === "FILE_SCANNING_NOT_CONFIGURED")
      ) {
        setPendingUpload(null);
        if (e.code === "MODULE_DISABLED") setEnabled(false);
        if (e.code === "FILE_SCANNING_NOT_CONFIGURED")
          setUploads("scanner_not_configured");
      }
    } finally {
      setBusy(false);
    }
  }

  async function chooseFile(file: File) {
    if (busy || pending || pendingUpload) return;
    try {
      await sendUpload(await prepareUpload(file));
    } catch (e: unknown) {
      setError(failure(e));
    }
  }

  async function download(doc: Document) {
    const file = doc.file;
    if (busy || !file) return;
    setBusy(true);
    setError(null);
    try {
      saveToDevice(
        await downloadDocumentFile(
          businessId,
          doc.document_id,
          doc.revision,
          file,
        ),
        file.file_name,
      );
      setMessage(
        `Downloaded ${file.file_name}. It was not scanned for malware.`,
      );
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  async function readDetails(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!enabled || busy || pending || pendingUpload || conflict) return;
    void run({
      type: "save",
      id: selected?.document_id ?? crypto.randomUUID(),
      key: crypto.randomUUID(),
      body: form,
    });
  }

  const interrupted = Boolean(pending) || Boolean(pendingUpload);
  const locked = busy || !enabled || interrupted || conflict;
  const attached =
    uploaded && uploaded.file_id === form.file_id
      ? uploaded
      : selected?.file && selected.file.file_id === form.file_id
        ? selected.file
        : null;
  if (loading) return <p role="status">Loading documents…</p>;
  return (
    <div className="mgmt-page documents">
      <h1>Documents</h1>
      <p>
        Company documents with validity dates and one PDF, PNG or JPEG file per
        version. Files are checked against the supported formats but are not
        scanned for malware, and they are never opened in the browser.
      </p>
      {!enabled && (
        <p className="warning">
          Documents is turned off. Saved documents, versions and files remain
          readable. Enable it through a validated{" "}
          <Link href="/business/">business configuration</Link> before making
          changes.
        </p>
      )}
      {uploads === "scanner_not_configured" && (
        <p className="warning">
          File uploads are unavailable here until a malware scanner is
          configured. Documents without files can still be saved.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {pending && (
        <div className="warning">
          <p>
            The result of the last command is uncertain. Editing is paused until
            the same command is retried.
          </p>
          <button disabled={busy} onClick={() => void run(pending)}>
            Retry same document command
          </button>
        </div>
      )}
      {pendingUpload && (
        <div className="warning">
          <p>
            The upload result is uncertain. Retry the same upload to check
            whether the file arrived.
          </p>
          <button
            disabled={busy}
            onClick={() => void sendUpload(pendingUpload)}
          >
            Retry same upload
          </button>
        </div>
      )}
      {conflict && (
        <p className="warning">
          The data or configuration changed. Reload the document before
          continuing.
        </p>
      )}
      <section aria-label="Document list" className="mgmt-card">
        <form
          className="mgmt-filter-bar"
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
        >
          <label>
            Search documents
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={200}
            />
          </label>
          <label>
            Show
            <select
              value={archived ? "archived" : "current"}
              onChange={(e) => setArchived(e.target.value === "archived")}
            >
              <option value="current">Current documents</option>
              <option value="archived">Archived documents</option>
            </select>
          </label>
          <button disabled={busy}>Search</button>
          <button
            type="button"
            className="secondary"
            disabled={busy || interrupted}
            onClick={() => {
              choose(null);
              setError(null);
              setMessage(null);
            }}
          >
            New document
          </button>
        </form>
        {items.length === 0 && <p>No documents match this search.</p>}
        <ul className="cp-list">
          {items.map((item) => (
            <li key={item.document_id}>
              <button
                className="secondary"
                disabled={busy || interrupted}
                onClick={() => void inspect(item.document_id)}
              >
                {item.title}
              </button>{" "}
              <span>
                {categories.find(([key]) => key === item.category)?.[1]} ·
                version {item.revision} ·{" "}
                {validityText[validityState(item, today)]} ·{" "}
                {item.media_type ?? "no file"}
              </span>
            </li>
          ))}
        </ul>
        {cursor && (
          <button disabled={busy} onClick={() => void search(cursor)}>
            Load more documents
          </button>
        )}
      </section>
      <DocumentEditor
        selected={selected}
        form={form}
        setForm={setForm}
        attached={attached}
        locked={locked}
        uploadLocked={uploads !== "enabled"}
        reloadDisabled={busy || interrupted}
        onReload={() => void inspect(selected!.document_id)}
        onChooseFile={(file) => void chooseFile(file)}
        onDownload={selected?.file ? () => void download(selected) : null}
        onSubmit={submit}
      />
      {selected && (
        <DocumentRelations
          businessId={businessId}
          selected={selected}
          history={history}
          setHistory={setHistory}
          historical={historical}
          setHistorical={setHistorical}
          links={links}
          linksEnabled={linksEnabled}
          locked={locked}
          readLocked={busy || interrupted}
          onRead={(action) => void readDetails(action)}
          onCommand={(command) => void run(command)}
          onDownload={(doc) => void download(doc)}
        />
      )}
    </div>
  );
}
