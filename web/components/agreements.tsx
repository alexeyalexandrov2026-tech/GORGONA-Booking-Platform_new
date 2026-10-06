"use client";
import { useEffect, useState } from "react";
import {
  executeAgreementCommand,
  fetchAgreement,
  fetchAgreementHistory,
  fetchAgreements,
} from "../lib/agreement-api";
import { ManagementApiError } from "../lib/management-api";
import {
  canDraftOrAgree,
  contractStatus,
  draftDocument,
  type Agreement,
  type AgreementCommand,
  type AgreementHistory,
  type AgreementPage,
  type ContractStatus,
} from "../lib/agreement-contracts";

type Form = {
  title: string;
  number: string;
  summary: string;
  effective_from: string;
  effective_until: string;
};
const emptyForm = (): Form => ({
  title: "",
  number: "",
  summary: "",
  effective_from: "",
  effective_until: "",
});
const failure = (error: unknown) =>
  error instanceof Error ? error.message : "Unable to complete this action.";
const uncertain = (error: unknown) =>
  !(error instanceof ManagementApiError) ||
  error.status === undefined ||
  error.status >= 500;
const done = {
  draft: "Contract draft saved.",
  agree: "Recorded as agreed.",
  terminate: "Termination recorded.",
};

function term(item: {
  effective_from: string | null;
  effective_until: string | null;
}) {
  if (!item.effective_from && !item.effective_until) return "no term set";
  return `${item.effective_from ?? "open"} to ${item.effective_until ?? "open"}`;
}
const statusText: Record<ContractStatus, string> = {
  draft: "draft, never agreed",
  in_force: "in force",
  in_force_amendment_draft: "in force · unsigned amendment drafted",
  expired: "term ended",
  termination_scheduled: "in force until the termination takes effect",
  terminated: "terminated",
};

/** Contracts of one counterparty: drafts, attested agreement, amendment, termination. */
export function CounterpartyAgreements({
  businessId,
  counterpartyId,
  cardActive,
  enabled,
}: {
  businessId: string;
  counterpartyId: string;
  cardActive: boolean;
  enabled: boolean;
}) {
  const [page, setPage] = useState<AgreementPage | null>(null);
  const [selected, setSelected] = useState<Agreement | null>(null);
  // The agreed version in force for the selected contract, if any.
  const [inForce, setInForce] = useState<Agreement | null>(null);
  const [history, setHistory] = useState<AgreementHistory | null>(null);
  const [historical, setHistorical] = useState<Agreement | null>(null);
  const [form, setForm] = useState<Form>(emptyForm);
  const [signedOn, setSignedOn] = useState("");
  const [attested, setAttested] = useState(false);
  const [terminatedOn, setTerminatedOn] = useState("");
  const [pending, setPending] = useState<AgreementCommand | null>(null);
  const [conflict, setConflict] = useState(false);
  // The panel stays mounted across card edits, so an uncertain command survives;
  // the module state follows the parent unless the server refused a command.
  const [refusedByModule, setRefusedByModule] = useState(false);
  const moduleOn = enabled && !refusedByModule;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const today = new Date().toLocaleDateString("en-CA");

  useEffect(() => {
    let active = true;
    fetchAgreements(businessId, counterpartyId)
      .then((result) => {
        if (active) setPage(result);
      })
      .catch((e: unknown) => {
        if (active) setError(failure(e));
      });
    return () => {
      active = false;
    };
  }, [businessId, counterpartyId]);

  function show(agreement: Agreement | null, current: Agreement | null = null) {
    setSelected(agreement);
    setInForce(current);
    setForm(
      agreement
        ? {
            title: agreement.title,
            number: agreement.number ?? "",
            summary: agreement.summary ?? "",
            effective_from: agreement.effective_from ?? "",
            effective_until: agreement.effective_until ?? "",
          }
        : emptyForm(),
    );
    setHistorical(null);
    setHistory(null);
    setSignedOn("");
    setAttested(false);
    setTerminatedOn("");
    setConflict(false);
  }

  async function load(id: string) {
    const agreement = await fetchAgreement(businessId, id);
    // An unsigned amendment draft does not replace the agreed version in force,
    // and a termination names the agreed version it ends: show that version.
    const revision = agreement.in_force_revision;
    const current =
      revision === null
        ? null
        : revision === agreement.revision
          ? agreement
          : await fetchAgreement(businessId, id, revision);
    show(agreement, current);
    setHistory(await fetchAgreementHistory(businessId, id));
  }

  async function read(action: () => Promise<void>) {
    if (busy || pending) return;
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

  async function run(command: AgreementCommand) {
    if (busy) return;
    setPending(command);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await executeAgreementCommand(businessId, command);
      setPending(null);
      // Only the server's answer shows a contract as agreed or terminated.
      setMessage(done[command.type]);
      await load(command.id);
      setPage(await fetchAgreements(businessId, counterpartyId));
    } catch (e: unknown) {
      setError(failure(e));
      if (!uncertain(e) && e instanceof ManagementApiError) {
        setPending(null);
        if (e.code === "MODULE_DISABLED") setRefusedByModule(true);
        else setConflict(e.status === 409);
      }
    } finally {
      setBusy(false);
    }
  }

  function saveDraft(event: React.FormEvent) {
    event.preventDefault();
    if (locked || !editable) return;
    void run({
      type: "draft",
      id: selected?.agreement_id ?? crypto.randomUUID(),
      key: crypto.randomUUID(),
      body: {
        schema_version: 1,
        expected_revision: selected?.revision ?? 0,
        counterparty_id: selected?.counterparty_id ?? counterpartyId,
        legal_entity_id: selected?.legal_entity_id ?? null,
        title: form.title,
        number: form.number.trim() || null,
        summary: form.summary.trim() || null,
        effective_from: form.effective_from || null,
        effective_until: form.effective_until || null,
        // A new amendment starts without the signed copy of the agreed version.
        document: draftDocument(selected),
      },
    });
  }

  const locked = busy || !moduleOn || Boolean(pending) || conflict;
  // Contracts listed through a merged duplicate can be read and terminated here,
  // but drafted or agreed only from their own card.
  const editable = canDraftOrAgree(selected, counterpartyId, cardActive);
  // Agreeing records the saved draft: unsaved edits must be saved first.
  const dirty =
    selected !== null &&
    (form.title !== selected.title ||
      form.number !== (selected.number ?? "") ||
      form.summary !== (selected.summary ?? "") ||
      form.effective_from !== (selected.effective_from ?? "") ||
      form.effective_until !== (selected.effective_until ?? ""));
  return (
    <section aria-label="Contracts" className="mgmt-card">
      <h2>Contracts</h2>
      <p>
        Contracts are signed outside the platform. Recording one as agreed only
        notes that it was signed; agreed versions are never changed, amendments
        and terminations add new versions.
      </p>
      {!moduleOn && (
        <p className="warning">
          Contract changes are paused while this module is off. Saved contracts
          remain readable.
        </p>
      )}
      {!cardActive && (
        <p>
          New contracts and drafts need an active card. Agreed contracts can
          still be terminated.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {pending && !busy && (
        <div className="warning">
          <p>
            The result of the last contract command is uncertain. Retry the same
            command to check it.
          </p>
          <button disabled={busy} onClick={() => void run(pending)}>
            Retry same contract command
          </button>
        </div>
      )}
      {conflict && (
        <p className="warning">
          The contract or card changed. Reload the contract before continuing.
        </p>
      )}
      {page && page.items.length === 0 && <p>No contracts yet.</p>}
      <ul className="cp-list">
        {page?.items.map((item) => (
          <li key={item.agreement_id}>
            <button
              className="secondary"
              disabled={busy || Boolean(pending)}
              onClick={() => void read(() => load(item.agreement_id))}
            >
              {item.title}
            </button>{" "}
            <span>
              {item.number ? `${item.number} · ` : ""}
              {statusText[contractStatus(item, item.in_force, today)]}
              {item.terminated_on && ` · ends ${item.terminated_on}`} · version{" "}
              {item.revision} ·{" "}
              {item.in_force && item.state === "draft"
                ? `agreed version ${item.in_force.revision}: ${item.in_force.title}${item.in_force.number ? ` · ${item.in_force.number}` : ""} · ${term(item.in_force)}`
                : term(item)}
              {item.counterparty_id !== counterpartyId && " · via merged card"}
            </span>
          </li>
        ))}
      </ul>
      {page?.next_cursor && (
        <button
          disabled={busy}
          onClick={() =>
            void read(async () => {
              const next = await fetchAgreements(
                businessId,
                counterpartyId,
                page.next_cursor ?? undefined,
              );
              setPage({ ...next, items: [...page.items, ...next.items] });
            })
          }
        >
          Load more contracts
        </button>
      )}
      <button
        className="secondary"
        disabled={busy || Boolean(pending) || !cardActive || !moduleOn}
        onClick={() => {
          show(null);
          setMessage(null);
          setError(null);
        }}
      >
        New contract
      </button>
      {selected && (
        <>
          <h3>
            {selected.title}: version {selected.revision} · {selected.state}
          </h3>
          <p>Status: {statusText[contractStatus(selected, inForce, today)]}</p>
          {inForce && (
            <div role="region" aria-label="Agreed version in force">
              <p>
                Agreed version {inForce.revision}: {inForce.title}
                {inForce.number && ` · ${inForce.number}`} · {term(inForce)} ·
                signed outside the platform on {inForce.signed_on}
              </p>
              {selected.state === "draft" && (
                <p>
                  Version {selected.revision} is an unsigned amendment draft.
                  Agreed version {inForce.revision} stays in force until an
                  amendment is recorded as agreed or the contract is terminated.
                </p>
              )}
              {selected.terminated_on &&
                (selected.terminated_on > today ? (
                  <p>
                    Termination recorded: agreed version {inForce.revision}{" "}
                    stays in force until it takes effect on{" "}
                    {selected.terminated_on}.
                  </p>
                ) : (
                  <p>Terminated with effect from {selected.terminated_on}.</p>
                ))}
            </div>
          )}
          <button
            className="secondary"
            disabled={busy || Boolean(pending)}
            onClick={() => void read(() => load(selected.agreement_id))}
          >
            Reload contract
          </button>
        </>
      )}
      <form onSubmit={saveDraft}>
        <fieldset disabled={locked || !editable}>
          <legend>
            {selected?.state === "agreed" ||
            (selected?.state === "draft" && selected.in_force_revision !== null)
              ? "Amendment (a new draft; the agreed version stays in force)"
              : selected
                ? "Contract draft"
                : "New contract draft"}
          </legend>
          <div className="cp-fields">
            <label>
              Contract title
              <input
                required
                maxLength={200}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <label>
              Contract number
              <input
                maxLength={64}
                value={form.number}
                onChange={(e) => setForm({ ...form, number: e.target.value })}
              />
            </label>
            <label>
              Effective from
              <input
                type="date"
                value={form.effective_from}
                onChange={(e) =>
                  setForm({ ...form, effective_from: e.target.value })
                }
              />
            </label>
            <label>
              Effective until
              <input
                type="date"
                min={form.effective_from || undefined}
                value={form.effective_until}
                onChange={(e) =>
                  setForm({ ...form, effective_until: e.target.value })
                }
              />
            </label>
          </div>
          <label>
            Summary
            <textarea
              maxLength={2000}
              rows={3}
              value={form.summary}
              onChange={(e) => setForm({ ...form, summary: e.target.value })}
            />
          </label>
          <button type="submit">Save contract draft</button>
        </fieldset>
      </form>
      {selected?.state === "draft" && (
        <fieldset disabled={locked || !editable}>
          <legend>Record as agreed</legend>
          {dirty && (
            <p className="warning">
              Save the draft first: only the saved draft can be recorded as
              agreed.
            </p>
          )}
          <label>
            Signed on
            <input
              type="date"
              max={today}
              value={signedOn}
              onChange={(e) => setSignedOn(e.target.value)}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={attested}
              onChange={(e) => setAttested(e.target.checked)}
            />{" "}
            Signed outside the platform; no electronic signature is made here
          </label>
          <button
            disabled={!signedOn || !attested || dirty}
            onClick={() =>
              void run({
                type: "agree",
                id: selected.agreement_id,
                key: crypto.randomUUID(),
                body: {
                  schema_version: 1,
                  expected_revision: selected.revision,
                  signed_on: signedOn,
                  attestation: "signed_outside_platform",
                },
              })
            }
          >
            Record as agreed
          </button>
        </fieldset>
      )}
      {selected && inForce && selected.state !== "terminated" && (
        <fieldset disabled={locked}>
          <legend>Terminate</legend>
          <p>
            Ends agreed version {inForce.revision}. The date can be in the
            future; the agreed version stays in force until then.
          </p>
          {selected.state === "draft" && (
            <p className="warning">
              The unsigned amendment draft (version {selected.revision}) is not
              agreed by this. It stays in the history, closed as abandoned.
            </p>
          )}
          <label>
            Termination takes effect on
            <input
              type="date"
              min={inForce.signed_on ?? undefined}
              value={terminatedOn}
              onChange={(e) => setTerminatedOn(e.target.value)}
            />
          </label>
          <button
            disabled={!terminatedOn}
            onClick={() =>
              void run({
                type: "terminate",
                id: selected.agreement_id,
                key: crypto.randomUUID(),
                body: {
                  schema_version: 1,
                  expected_revision: selected.revision,
                  terminated_on: terminatedOn,
                },
              })
            }
          >
            Record termination
          </button>
        </fieldset>
      )}
      {history && (
        <>
          <h3>Contract versions</h3>
          <ul className="cp-list">
            {history.items.map((item) => (
              <li key={item.revision}>
                <button
                  className="secondary"
                  disabled={busy || Boolean(pending)}
                  onClick={() =>
                    void read(async () =>
                      setHistorical(
                        await fetchAgreement(
                          businessId,
                          selected!.agreement_id,
                          item.revision,
                        ),
                      ),
                    )
                  }
                >
                  Read contract version {item.revision}
                </button>{" "}
                <span>
                  {item.state}
                  {item.abandoned &&
                    " · abandoned, closed by the termination"}{" "}
                  · {item.title}
                </span>
              </li>
            ))}
          </ul>
          {history.next_cursor && (
            <button
              disabled={busy || Boolean(pending)}
              onClick={() =>
                void read(async () => {
                  const older = await fetchAgreementHistory(
                    businessId,
                    history.agreement_id,
                    history.next_cursor ?? undefined,
                  );
                  setHistory({
                    ...older,
                    items: [...history.items, ...older.items],
                  });
                })
              }
            >
              Load older contract versions
            </button>
          )}
        </>
      )}
      {historical && (
        <div role="region" aria-label="Saved contract version">
          <h3>
            Saved version {historical.revision} · {historical.state}
          </h3>
          <p>
            {historical.title}
            {historical.number && ` · ${historical.number}`} ·{" "}
            {term(historical)}
          </p>
          {historical.summary && <p>{historical.summary}</p>}
          {historical.signed_on && (
            <p>Signed outside the platform on {historical.signed_on}</p>
          )}
        </div>
      )}
    </section>
  );
}
