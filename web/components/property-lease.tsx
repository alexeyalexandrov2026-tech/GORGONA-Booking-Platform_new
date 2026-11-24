"use client";

// PROPERTY-01: the signed contract, term history and move-in of one unit. Only a company-wide
// owner or manager reaches this section. A write keeps its idempotency key until it succeeds,
// and a stale term revision is never submitted again with a newer expected revision.
import React, { useEffect, useRef, useState } from "react";
import { fetchAgreement, fetchAgreements } from "../lib/agreement-api";
import type { Agreement } from "../lib/agreement-contracts";
import { businessDateTime } from "../lib/business-time";
import {
  downloadDocumentFile,
  fetchDocument,
  fetchDocumentHistory,
  fetchDocuments,
} from "../lib/document-api";
import type { Document } from "../lib/document-contracts";
import {
  fetchLeases,
  fetchMoveIn,
  fetchMoveOut,
  fetchTermHistory,
  recordMoveIn,
  recordMoveOut,
  recordTerm,
  registerLease,
  refusal,
  termConflict,
} from "../lib/property-api";
import {
  MOVE_OUT_CONDITIONS,
  type LeaseTerm,
  type LeaseView,
  type MoveInView,
  type MoveOutCondition,
  type MoveOutView,
} from "../lib/property-contracts";

type Named = { id: string; name: string };
type Summary = Awaited<ReturnType<typeof fetchDocuments>>["items"][number];
type ContractSummary = Awaited<
  ReturnType<typeof fetchAgreements>
>["items"][number];
type VersionChoice = { documentId: string; revision: number };
type LoadedLease = {
  lease: LeaseView;
  history: LeaseTerm[];
  moveIn: MoveInView | null;
  moveOut: MoveOutView | null;
  latest: Agreement;
  source: Agreement;
};

function recorded(instant: string, zone: string | undefined): string {
  if (!zone) return instant;
  try {
    const local = businessDateTime(instant, zone);
    return local.date + " " + local.time;
  } catch {
    return instant;
  }
}

function actionLabel(action: LeaseTerm["action"]): string {
  switch (action) {
    case "register":
      return "Registered";
    case "extend":
      return "Extended";
    case "release":
      return "Released";
    default: {
      const unexpected: never = action;
      return unexpected;
    }
  }
}

function occupied(value: string | null): string {
  return value ?? "No occupied days";
}

async function everyDocument(business: string): Promise<Summary[]> {
  const all: Summary[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await fetchDocuments(business, "", false, after);
    all.push(...page.items);
    if (!page.next_cursor) return all;
    after = page.next_cursor;
  }
}

async function everyContract(
  business: string,
  counterparty: string,
): Promise<ContractSummary[]> {
  const all: ContractSummary[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await fetchAgreements(business, counterparty, after);
    all.push(...page.items);
    if (!page.next_cursor) return all;
    after = page.next_cursor;
  }
}

async function storedVersions(
  business: string,
  documentId: string,
): Promise<Document[]> {
  const items: Awaited<ReturnType<typeof fetchDocumentHistory>>["items"] = [];
  let before: number | undefined;
  for (;;) {
    const page = await fetchDocumentHistory(business, documentId, before);
    items.push(...page.items);
    if (page.next_cursor === null) break;
    before = page.next_cursor;
  }
  const versions = await Promise.all(
    items
      .filter((item) => item.file_id && !item.archived)
      .map((item) => fetchDocument(business, documentId, item.revision)),
  );
  return versions.filter((item) => item.file && !item.archived);
}

async function downloadVersion(
  business: string,
  documentId: string,
  revision: number,
) {
  const stored = await fetchDocument(business, documentId, revision);
  if (!stored.file) throw new Error("This version has no stored file.");
  const blob = await downloadDocumentFile(business, documentId, revision, {
    media_type: stored.file.media_type,
    size_bytes: stored.file.size_bytes,
    sha256: stored.file.sha256,
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = stored.file.file_name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function DownloadButton({
  businessId,
  documentId,
  revision,
  label,
}: {
  businessId: string;
  documentId: string;
  revision: number;
  label: string;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <>
      <button
        type="button"
        className="secondary"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError("");
          void downloadVersion(businessId, documentId, revision)
            .catch((failure: unknown) => setError(refusal(failure)))
            .finally(() => setBusy(false));
        }}
      >
        {busy ? "Downloading…" : label}
      </button>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
    </>
  );
}

function DocumentChoice({
  businessId,
  label,
  documents,
  accept,
  onChange,
}: {
  businessId: string;
  label: string;
  documents: Summary[];
  accept: (item: Document) => boolean;
  onChange: (choice: VersionChoice | null) => void;
}) {
  const [documentId, setDocumentId] = useState("");
  const [versions, setVersions] = useState<Document[]>([]);
  const [revision, setRevision] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function emit(
    nextId: string,
    nextVersions: Document[],
    nextRevision: string,
  ) {
    const picked = nextVersions.find(
      (item) => String(item.revision) === nextRevision,
    );
    onChange(
      picked?.file && nextId
        ? { documentId: nextId, revision: picked.revision }
        : null,
    );
  }

  async function chooseDocument(nextId: string) {
    setDocumentId(nextId);
    setVersions([]);
    setRevision("");
    setError("");
    emit(nextId, [], "");
    if (!nextId) return;
    setLoading(true);
    try {
      const stored = (await storedVersions(businessId, nextId))
        .filter(accept)
        .sort((left, right) => right.revision - left.revision);
      const nextRevision = stored[0] ? String(stored[0].revision) : "";
      setVersions(stored);
      setRevision(nextRevision);
      emit(nextId, stored, nextRevision);
    } catch (failure) {
      setError(refusal(failure));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <label>
        {label}
        <select
          value={documentId}
          required
          onChange={(event) => void chooseDocument(event.target.value)}
        >
          <option value="">Choose a document</option>
          {documents.map((item) => (
            <option key={item.document_id} value={item.document_id}>
              {item.title}
            </option>
          ))}
        </select>
      </label>
      <label>
        {label + " version"}
        <select
          value={revision}
          required
          disabled={!versions.length}
          onChange={(event) => {
            setRevision(event.target.value);
            emit(documentId, versions, event.target.value);
          }}
        >
          <option value="">
            {loading ? "Loading versions…" : "Choose a version"}
          </option>
          {versions.map((item) => (
            <option key={item.revision} value={String(item.revision)}>
              {"Version " + item.revision}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
    </>
  );
}

function termChange(current: LeaseTerm, latest: Agreement) {
  if (
    current.action === "release" ||
    latest.revision <= current.agreement_revision
  )
    return null;
  if (
    latest.state === "agreed" &&
    latest.document &&
    latest.effective_from === current.starts_on &&
    latest.effective_until &&
    latest.effective_until > (current.ends_on ?? "")
  )
    return {
      action: "extend" as const,
      agreementRevision: latest.revision,
      until: latest.effective_until,
    };
  if (latest.state === "terminated" && latest.terminated_on)
    return {
      action: "release" as const,
      agreementRevision: latest.revision,
      until: latest.terminated_on,
    };
  return null;
}

export function PropertyLease({
  businessId,
  objectId,
  parties,
  timezone,
}: {
  businessId: string;
  objectId: string;
  parties: Named[];
  timezone: string | undefined;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [rows, setRows] = useState<LoadedLease[]>([]);
  const [documents, setDocuments] = useState<Summary[]>([]);

  useEffect(() => {
    let live = true;
    fetchLeases(businessId, objectId)
      .then(async (leases) => {
        const loaded = await Promise.all(
          leases.map(async (lease) => {
            const [history, moveIn, latest] = await Promise.all([
              fetchTermHistory(businessId, lease.lease_id),
              fetchMoveIn(businessId, lease.lease_id),
              fetchAgreement(businessId, lease.agreement_id),
            ]);
            const moveOut = moveIn
              ? await fetchMoveOut(businessId, lease.lease_id)
              : null;
            const source =
              latest.revision === lease.agreement_revision
                ? latest
                : await fetchAgreement(
                    businessId,
                    lease.agreement_id,
                    lease.agreement_revision,
                  );
            return {
              lease,
              history: [...history].sort(
                (left, right) => right.revision - left.revision,
              ),
              moveIn,
              moveOut,
              latest,
              source,
            };
          }),
        );
        const files = leases.length ? await everyDocument(businessId) : [];
        return { loaded, files };
      })
      .then(({ loaded, files }) => {
        if (!live) return;
        setRows(loaded);
        setDocuments(files);
        setError("");
        setReady(true);
      })
      .catch((failure: unknown) => {
        if (live) setError("The lease could not be read: " + refusal(failure));
      });
    return () => {
      live = false;
    };
  }, [businessId, objectId, attempt]);

  function reload() {
    setError("");
    setReady(false);
    setAttempt((value) => value + 1);
  }

  function announce(message: string) {
    setNotice(message);
    requestAnimationFrame(() => heading.current?.focus());
    reload();
  }

  return (
    <section aria-label="Unit lease">
      <h3 ref={heading} tabIndex={-1}>
        Lease
      </h3>
      <p role="status">{notice}</p>
      {!ready && !error ? (
        <p className="muted" role="status">
          Loading the lease…
        </p>
      ) : null}
      {error ? (
        <div className="property-error">
          <p className="error" role="alert">
            {error}
          </p>
          <button type="button" onClick={reload}>
            Reload lease
          </button>
        </div>
      ) : null}
      {ready
        ? rows.map((row) => (
            <LeaseCard
              key={row.lease.lease_id}
              businessId={businessId}
              row={row}
              documents={documents}
              timezone={timezone}
              onChanged={announce}
              reload={reload}
            />
          ))
        : null}
      {ready && rows.length === 0 ? (
        <p className="muted">No lease for this unit.</p>
      ) : null}
      {ready ? (
        <RegisterForm
          businessId={businessId}
          objectId={objectId}
          parties={parties}
          onRegistered={() => announce("Lease registered.")}
        />
      ) : null}
    </section>
  );
}

function LeaseCard({
  businessId,
  row,
  documents,
  timezone,
  onChanged,
  reload,
}: {
  businessId: string;
  row: LoadedLease;
  documents: Summary[];
  timezone: string | undefined;
  onChanged: (message: string) => void;
  reload: () => void;
}) {
  const current = row.history[0];
  const original =
    row.history.find((item) => item.action === "register") ??
    row.history.at(-1);
  if (!current || !original)
    return (
      <p className="error" role="alert">
        The lease term could not be read.
      </p>
    );
  const change = termChange(current, row.latest);
  const reports = documents.filter(
    (item) => item.category === "report" && item.media_type && !item.archived,
  );
  const images = documents.filter(
    (item) =>
      (item.media_type === "image/png" || item.media_type === "image/jpeg") &&
      !item.archived,
  );
  return (
    <>
      <h4>Original contract</h4>
      <dl className="property-facts">
        <div>
          <dt>Contract</dt>
          <dd>{row.source.title}</dd>
        </div>
        <div>
          <dt>Signed</dt>
          <dd>{row.lease.signed_on}</dd>
        </div>
        <div>
          <dt>Agreement version</dt>
          <dd>{row.lease.agreement_revision}</dd>
        </div>
        <div>
          <dt>From</dt>
          <dd>{row.lease.starts_on}</dd>
        </div>
        <div>
          <dt>Until</dt>
          <dd>{row.lease.ends_on}</dd>
        </div>
      </dl>
      <DownloadButton
        businessId={businessId}
        documentId={row.lease.document_id}
        revision={row.lease.document_revision}
        label="Download original contract"
      />
      <h4>Current term</h4>
      <dl className="property-facts">
        <div>
          <dt>Term revision</dt>
          <dd>{current.revision}</dd>
        </div>
        <div>
          <dt>Action</dt>
          <dd>{actionLabel(current.action)}</dd>
        </div>
        <div>
          <dt>From</dt>
          <dd>{current.starts_on}</dd>
        </div>
        <div>
          <dt>Through</dt>
          <dd>{occupied(current.ends_on)}</dd>
        </div>
        <div>
          <dt>Agreement version</dt>
          <dd>{current.agreement_revision}</dd>
        </div>
      </dl>
      {current.document_id !== null && current.document_revision !== null ? (
        <DownloadButton
          businessId={businessId}
          documentId={current.document_id}
          revision={current.document_revision}
          label="Download current contract"
        />
      ) : null}
      {change ? (
        <TermForm
          businessId={businessId}
          leaseId={row.lease.lease_id}
          expectedRevision={current.revision}
          agreementRevision={change.agreementRevision}
          action={change.action}
          until={change.until}
          onSaved={(revision) =>
            onChanged("Term saved as revision " + revision + ".")
          }
          onReload={reload}
        />
      ) : null}
      {row.latest.state === "draft" ? (
        <p className="muted">
          An unsigned amendment is open. Sign it before changing the term.
        </p>
      ) : null}
      <h4>Term history</h4>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Term history table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Term history">
          <thead>
            <tr>
              <th scope="col">Revision</th>
              <th scope="col">Action</th>
              <th scope="col">Agreement version</th>
              <th scope="col">From</th>
              <th scope="col">Through</th>
              <th scope="col">Recorded</th>
              <th scope="col">File</th>
            </tr>
          </thead>
          <tbody>
            {row.history.map((item) => (
              <tr key={item.revision}>
                <th scope="row">{item.revision}</th>
                <td>{actionLabel(item.action)}</td>
                <td>{item.agreement_revision}</td>
                <td>{item.starts_on}</td>
                <td>{occupied(item.ends_on)}</td>
                <td>{recorded(item.recorded_at, timezone)}</td>
                <td>
                  {item.document_id !== null &&
                  item.document_revision !== null ? (
                    <DownloadButton
                      businessId={businessId}
                      documentId={item.document_id}
                      revision={item.document_revision}
                      label={"Download revision " + item.revision}
                    />
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>Move-in</h4>
      {row.moveIn ? (
        <MoveInRecord businessId={businessId} moveIn={row.moveIn} />
      ) : current.ends_on ? (
        <MoveInForm
          key={current.revision}
          businessId={businessId}
          leaseId={row.lease.lease_id}
          termRevision={current.revision}
          reports={reports}
          images={images}
          timezone={timezone}
          onSaved={() => onChanged("Move-in recorded.")}
          onReload={reload}
        />
      ) : (
        <p className="muted">This lease has no occupied days to record.</p>
      )}
      {row.moveIn ? (
        <>
          <h4>Move-out</h4>
          {row.moveOut ? (
            <MoveOutRecord businessId={businessId} moveOut={row.moveOut} />
          ) : (
            <MoveOutForm
              key={current.revision + ":" + row.moveIn.moved_in_on}
              businessId={businessId}
              leaseId={row.lease.lease_id}
              termRevision={current.revision}
              moveIn={row.moveIn}
              reports={reports}
              images={images}
              timezone={timezone}
              onSaved={() => onChanged("Move-out recorded.")}
              onReload={reload}
            />
          )}
        </>
      ) : null}
    </>
  );
}

function TermForm({
  businessId,
  leaseId,
  expectedRevision,
  agreementRevision,
  action,
  until,
  onSaved,
  onReload,
}: {
  businessId: string;
  leaseId: string;
  expectedRevision: number;
  agreementRevision: number;
  action: "extend" | "release";
  until: string;
  onSaved: (revision: number) => void;
  onReload: () => void;
}) {
  const running = useRef(false);
  const [saving, setSaving] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState("");
  const label = action === "extend" ? "Extend term" : "Release term";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (running.current || blocked) return;
    running.current = true;
    setSaving(true);
    setError("");
    try {
      const saved = await recordTerm(businessId, leaseId, {
        schema_version: 1,
        action,
        expected_revision: expectedRevision,
        agreement_revision: agreementRevision,
      });
      onSaved(saved.revision);
    } catch (failure) {
      if (termConflict(failure)) {
        setBlocked(true);
        setError("The lease term changed. Reload it before saving.");
      } else setError(refusal(failure));
    } finally {
      running.current = false;
      setSaving(false);
    }
  }

  const detail =
    "Expected term revision " +
    expectedRevision +
    ". Version " +
    agreementRevision +
    ", " +
    (action === "extend" ? "through" : "ending") +
    " " +
    until +
    ".";
  return (
    <form
      aria-label={label}
      className="mgmt-form"
      onSubmit={(event) => void submit(event)}
    >
      <p className="muted">{detail}</p>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mgmt-form-actions">
        <button type="submit" disabled={saving || blocked}>
          {saving ? "Saving…" : label}
        </button>
        {blocked ? (
          <button type="button" className="secondary" onClick={onReload}>
            Reload lease
          </button>
        ) : null}
      </div>
    </form>
  );
}

function MoveInRecord({
  businessId,
  moveIn,
}: {
  businessId: string;
  moveIn: MoveInView;
}) {
  return (
    <>
      <dl className="property-facts">
        <div>
          <dt>Moved in</dt>
          <dd>{moveIn.moved_in_on}</dd>
        </div>
        <div>
          <dt>Term revision</dt>
          <dd>{moveIn.term_revision}</dd>
        </div>
      </dl>
      <DownloadButton
        businessId={businessId}
        documentId={moveIn.report.document_id}
        revision={moveIn.report.revision}
        label="Download condition report"
      />
      {moveIn.photos.map((photo, index) => (
        <DownloadButton
          key={photo.document_id + ":" + photo.revision}
          businessId={businessId}
          documentId={photo.document_id}
          revision={photo.revision}
          label={"Download photo " + (index + 1)}
        />
      ))}
    </>
  );
}

function MoveInForm({
  businessId,
  leaseId,
  termRevision,
  reports,
  images,
  timezone,
  onSaved,
  onReload,
}: {
  businessId: string;
  leaseId: string;
  termRevision: number;
  reports: Summary[];
  images: Summary[];
  timezone: string | undefined;
  onSaved: () => void;
  onReload: () => void;
}) {
  const running = useRef(false);
  const [day, setDay] = useState("");
  const [report, setReport] = useState<VersionChoice | null>(null);
  const [photos, setPhotos] = useState<
    { id: string; choice: VersionChoice | null }[]
  >(() => [{ id: crypto.randomUUID(), choice: null }]);
  const [saving, setSaving] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState("");
  const chosen = photos.map((row) => row.choice);
  const keys = chosen.map((item) =>
    item ? item.documentId + ":" + item.revision : "",
  );
  const duplicate = keys.some(
    (key, index) => key !== "" && keys.indexOf(key) !== index,
  );
  const complete = Boolean(
    day && report && chosen.every((item) => item) && !duplicate,
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (running.current || blocked || !report || !complete) return;
    const selected = chosen.filter(
      (item): item is VersionChoice => item !== null,
    );
    running.current = true;
    setSaving(true);
    setError("");
    try {
      await recordMoveIn(businessId, leaseId, {
        schema_version: 1,
        term_revision: termRevision,
        moved_in_on: day,
        report: { document_id: report.documentId, revision: report.revision },
        photos: selected.map((item) => ({
          document_id: item.documentId,
          revision: item.revision,
        })),
      });
      onSaved();
    } catch (failure) {
      if (termConflict(failure)) {
        setBlocked(true);
        setError("The lease term changed. Reload it before saving.");
      } else setError(refusal(failure));
    } finally {
      running.current = false;
      setSaving(false);
    }
  }

  return (
    <form
      aria-label="Record move-in"
      className="mgmt-form"
      onSubmit={(event) => void submit(event)}
    >
      <div className="property-operation-fields">
        <label>
          Move-in date
          <input
            type="date"
            required
            value={day}
            onChange={(event) => setDay(event.target.value)}
          />
        </label>
        <DocumentChoice
          businessId={businessId}
          label="Report"
          documents={reports}
          accept={(item) => item.category === "report" && item.file !== null}
          onChange={setReport}
        />
        {photos.map((row, index) => (
          <DocumentChoice
            key={row.id}
            businessId={businessId}
            label={"Photo " + (index + 1)}
            documents={images}
            accept={(item) =>
              item.file?.media_type === "image/png" ||
              item.file?.media_type === "image/jpeg"
            }
            onChange={(choice) =>
              setPhotos((current) =>
                current.map((item) =>
                  item.id === row.id ? { ...item, choice } : item,
                ),
              )
            }
          />
        ))}
      </div>
      <p className="muted">
        {"Uses term revision " +
          termRevision +
          ". The date is the branch local day" +
          (timezone ? " (" + timezone + ")" : "") +
          "."}
      </p>
      {!reports.length ? (
        <p className="muted">
          Store a condition report before recording move-in.
        </p>
      ) : null}
      {!images.length ? (
        <p className="muted">
          Store a PNG or JPEG photo before recording move-in.
        </p>
      ) : null}
      {duplicate ? (
        <p className="error" role="alert">
          Select each photo version once.
        </p>
      ) : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mgmt-form-actions">
        <button
          type="button"
          className="secondary"
          disabled={photos.length >= 50}
          onClick={() =>
            setPhotos((current) => [
              ...current,
              { id: crypto.randomUUID(), choice: null },
            ])
          }
        >
          Add photo
        </button>
        {photos.length > 1 ? (
          <button
            type="button"
            className="secondary"
            onClick={() => setPhotos((current) => current.slice(0, -1))}
          >
            Remove photo
          </button>
        ) : null}
        <button type="submit" disabled={saving || blocked || !complete}>
          {saving ? "Saving…" : "Record move-in"}
        </button>
        {blocked ? (
          <button type="button" className="secondary" onClick={onReload}>
            Reload lease
          </button>
        ) : null}
      </div>
    </form>
  );
}

function enforceable(item: ContractSummary): boolean {
  return Boolean(
    item.in_force?.effective_from && item.in_force.effective_until,
  );
}

function RegisterForm({
  businessId,
  objectId,
  parties,
  onRegistered,
}: {
  businessId: string;
  objectId: string;
  parties: Named[];
  onRegistered: () => void;
}) {
  const running = useRef(false);
  const request = useRef(0);
  const [leaseId, setLeaseId] = useState(() => crypto.randomUUID());
  const [counterparty, setCounterparty] = useState("");
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [agreementId, setAgreementId] = useState("");
  const [version, setVersion] = useState<Agreement | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const signedFile = version?.state === "agreed" ? version.document : null;
  const usable = Boolean(
    signedFile && version?.effective_from && version.effective_until,
  );

  async function chooseParty(id: string) {
    const token = ++request.current;
    setCounterparty(id);
    setAgreementId("");
    setVersion(null);
    setContracts([]);
    setError("");
    if (!id) return;
    setLoading(true);
    try {
      const found = (await everyContract(businessId, id)).filter(enforceable);
      if (token !== request.current) return;
      setContracts(found);
    } catch (failure) {
      if (token === request.current) setError(refusal(failure));
    } finally {
      if (token === request.current) setLoading(false);
    }
  }

  async function chooseContract(id: string) {
    const token = ++request.current;
    setAgreementId(id);
    setVersion(null);
    setError("");
    const summary = contracts.find((item) => item.agreement_id === id);
    const revision = summary?.in_force?.revision;
    if (!id || !revision) return;
    setLoading(true);
    try {
      const loaded = await fetchAgreement(businessId, id, revision);
      if (token !== request.current) return;
      setVersion(loaded);
      if (!loaded.document) setError("This signed version has no stored file.");
    } catch (failure) {
      if (token === request.current) setError(refusal(failure));
    } finally {
      if (token === request.current) setLoading(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (running.current || !usable || !version?.document) return;
    running.current = true;
    setSaving(true);
    setError("");
    try {
      await registerLease(businessId, leaseId, {
        schema_version: 1,
        object_id: objectId,
        agreement_id: version.agreement_id,
        agreement_revision: version.revision,
      });
      setLeaseId(crypto.randomUUID());
      setAgreementId("");
      setVersion(null);
      onRegistered();
    } catch (failure) {
      setError(refusal(failure));
    } finally {
      running.current = false;
      setSaving(false);
    }
  }

  return (
    <form
      aria-label="Register lease"
      className="mgmt-form"
      onSubmit={(event) => void submit(event)}
    >
      <div className="property-operation-fields">
        <label>
          Counterparty
          <select
            value={counterparty}
            required
            onChange={(event) => void chooseParty(event.target.value)}
          >
            <option value="">Choose a counterparty</option>
            {parties.map((party) => (
              <option key={party.id} value={party.id}>
                {party.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Contract
          <select
            value={agreementId}
            required
            disabled={!counterparty}
            onChange={(event) => void chooseContract(event.target.value)}
          >
            <option value="">
              {loading ? "Loading contracts…" : "Choose a contract"}
            </option>
            {contracts.map((item) => (
              <option key={item.agreement_id} value={item.agreement_id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      {version ? (
        <p className="muted">
          {"Version " +
            version.revision +
            ", signed " +
            (version.signed_on ?? "undated") +
            ", " +
            (version.effective_from ?? "no start") +
            " to " +
            (version.effective_until ?? "no end") +
            "."}
        </p>
      ) : null}
      {!parties.length ? (
        <p className="muted">Add a counterparty before registering a lease.</p>
      ) : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mgmt-form-actions">
        {version?.document ? (
          <DownloadButton
            businessId={businessId}
            documentId={version.document.document_id}
            revision={version.document.revision}
            label="Download selected contract"
          />
        ) : null}
        <button type="submit" disabled={saving || !usable}>
          {saving ? "Saving…" : "Register lease"}
        </button>
      </div>
    </form>
  );
}

const CONDITION_LABELS: Record<MoveOutCondition, string> = {
  normal_wear: "Normal wear",
  damage_noted: "Damage noted",
};

function MoveOutRecord({
  businessId,
  moveOut,
}: {
  businessId: string;
  moveOut: MoveOutView;
}) {
  return (
    <>
      <dl className="property-facts">
        <div>
          <dt>Moved out</dt>
          <dd>{moveOut.moved_out_on}</dd>
        </div>
        <div>
          <dt>Condition</dt>
          <dd>{CONDITION_LABELS[moveOut.condition_summary]}</dd>
        </div>
        <div>
          <dt>Move-out term revision</dt>
          <dd>{moveOut.term_revision}</dd>
        </div>
        {moveOut.note ? (
          <div>
            <dt>Move-out note</dt>
            <dd>{moveOut.note}</dd>
          </div>
        ) : null}
      </dl>
      <DownloadButton
        businessId={businessId}
        documentId={moveOut.report.document_id}
        revision={moveOut.report.revision}
        label="Download move-out report"
      />
      {moveOut.photos.map((photo, index) => (
        <DownloadButton
          key={photo.document_id + ":" + photo.revision}
          businessId={businessId}
          documentId={photo.document_id}
          revision={photo.revision}
          label={"Download move-out photo " + (index + 1)}
        />
      ))}
    </>
  );
}

function MoveOutForm({
  businessId,
  leaseId,
  termRevision,
  moveIn,
  reports,
  images,
  timezone,
  onSaved,
  onReload,
}: {
  businessId: string;
  leaseId: string;
  termRevision: number;
  moveIn: MoveInView;
  reports: Summary[];
  images: Summary[];
  timezone: string | undefined;
  onSaved: () => void;
  onReload: () => void;
}) {
  const running = useRef(false);
  const [day, setDay] = useState("");
  const [condition, setCondition] = useState<MoveOutCondition>("normal_wear");
  const [note, setNote] = useState("");
  const [report, setReport] = useState<VersionChoice | null>(null);
  const [photos, setPhotos] = useState<
    { id: string; choice: VersionChoice | null }[]
  >(() => [{ id: crypto.randomUUID(), choice: null }]);
  const [saving, setSaving] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState("");
  const chosen = photos.map((row) => row.choice);
  const keys = chosen.map((item) =>
    item ? item.documentId + ":" + item.revision : "",
  );
  const duplicate = keys.some(
    (key, index) => key !== "" && keys.indexOf(key) !== index,
  );
  const sameReport = Boolean(
    report &&
    report.documentId === moveIn.report.document_id &&
    report.revision === moveIn.report.revision,
  );
  const complete = Boolean(
    day && report && !sameReport && chosen.every((item) => item) && !duplicate,
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (running.current || blocked || !report || !complete) return;
    const selected = chosen.filter(
      (item): item is VersionChoice => item !== null,
    );
    running.current = true;
    setSaving(true);
    setError("");
    try {
      const cleanedNote = note.trim();
      await recordMoveOut(businessId, leaseId, {
        schema_version: 1,
        term_revision: termRevision,
        moved_out_on: day,
        condition_summary: condition,
        note: cleanedNote || null,
        report: { document_id: report.documentId, revision: report.revision },
        photos: selected.map((item) => ({
          document_id: item.documentId,
          revision: item.revision,
        })),
      });
      onSaved();
    } catch (failure) {
      if (termConflict(failure)) {
        setBlocked(true);
        setError("The lease term changed. Reload it before saving.");
      } else setError(refusal(failure));
    } finally {
      running.current = false;
      setSaving(false);
    }
  }

  return (
    <form
      aria-label="Record move-out"
      className="mgmt-form"
      onSubmit={(event) => void submit(event)}
    >
      <div className="property-operation-fields">
        <label>
          Move-out date
          <input
            type="date"
            required
            min={moveIn.moved_in_on}
            value={day}
            onChange={(event) => setDay(event.target.value)}
          />
        </label>
        <label>
          Condition summary
          <select
            value={condition}
            onChange={(event) => {
              const next = MOVE_OUT_CONDITIONS.find(
                (item) => item === event.target.value,
              );
              if (next) setCondition(next);
            }}
          >
            {MOVE_OUT_CONDITIONS.map((item) => (
              <option key={item} value={item}>
                {CONDITION_LABELS[item]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Move-out note (optional)
          <textarea
            value={note}
            maxLength={2000}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <DocumentChoice
          businessId={businessId}
          label="Move-out report"
          documents={reports}
          accept={(item) => item.category === "report" && item.file !== null}
          onChange={setReport}
        />
        {photos.map((row, index) => (
          <DocumentChoice
            key={row.id}
            businessId={businessId}
            label={"Move-out photo " + (index + 1)}
            documents={images}
            accept={(item) =>
              item.file?.media_type === "image/png" ||
              item.file?.media_type === "image/jpeg"
            }
            onChange={(choice) =>
              setPhotos((current) =>
                current.map((item) =>
                  item.id === row.id ? { ...item, choice } : item,
                ),
              )
            }
          />
        ))}
      </div>
      <p className="muted">
        {"Uses term revision " +
          termRevision +
          ". Must be on or after " +
          moveIn.moved_in_on +
          (timezone ? " (" + timezone + ")" : "") +
          "."}
      </p>
      {sameReport ? (
        <p className="error" role="alert">
          Choose a different condition report version than move-in.
        </p>
      ) : null}
      {duplicate ? (
        <p className="error" role="alert">
          Select each move-out photo version once.
        </p>
      ) : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mgmt-form-actions">
        <button
          type="button"
          className="secondary"
          disabled={photos.length >= 50}
          onClick={() =>
            setPhotos((current) => [
              ...current,
              { id: crypto.randomUUID(), choice: null },
            ])
          }
        >
          Add move-out photo
        </button>
        {photos.length > 1 ? (
          <button
            type="button"
            className="secondary"
            onClick={() => setPhotos((current) => current.slice(0, -1))}
          >
            Remove move-out photo
          </button>
        ) : null}
        <button type="submit" aria-disabled={saving || blocked || !complete}>
          {saving ? "Saving…" : "Record move-out"}
        </button>
        {blocked ? (
          <button type="button" className="secondary" onClick={onReload}>
            Reload lease
          </button>
        ) : null}
      </div>
    </form>
  );
}
