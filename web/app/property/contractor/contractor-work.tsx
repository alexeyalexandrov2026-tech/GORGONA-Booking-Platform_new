"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  CATEGORY_LABELS,
  PRIORITY_LABELS,
  STATE_LABELS,
  UPDATE_KIND_LABELS,
} from "../../../components/property-maintenance";
import { businessDateTime } from "../../../lib/business-time";
import { ManagementApiError } from "../../../lib/management-api";
import {
  fetchContractorWork,
  postContractorUpdate,
} from "../../../lib/property-api";
import {
  CONTRACTOR_UPDATE_KINDS,
  contractorWorkLinkSchema,
  type ContractorUpdateBody,
  type ContractorUpdateKind,
  type ContractorWorkLink,
  type ContractorWorkOrderView,
} from "../../../lib/property-contracts";
import {
  CustomerAccessFeedback,
  type CustomerProblem,
} from "../../construction/customer/access";

// PROPERTY-01 (5b/5c): a delegate of the bound contractor company views ONLY the single assigned
// maintenance work order and records progress updates through their live delegation grant.
export function ContractorWorkPage() {
  const params = useSearchParams();
  const reference = contractorWorkLinkSchema.safeParse({
    business: params.get("business")?.toLowerCase(),
    request: params.get("request")?.toLowerCase(),
    grant: params.get("grant")?.toLowerCase(),
  });
  if (!reference.success)
    return (
      <p role="alert">
        This contractor work order link is incomplete or invalid.
      </p>
    );
  const query = new URLSearchParams(reference.data).toString();
  return (
    <WorkOrder
      key={query}
      link={reference.data}
      returnPath={`/property/contractor/?${query}`}
    />
  );
}

function unavailable(error: unknown): CustomerProblem | null {
  if (!(error instanceof ManagementApiError)) return null;
  if (error.status === 401 || error.code === "AUTHENTICATION_REQUIRED")
    return {
      message: "Sign in to view this work order and post updates.",
      needsSignIn: true,
      hideDocument: true,
    };
  if (error.status === 403 || error.status === 404)
    return {
      message: "This contractor work order is unavailable for your account.",
      hideDocument: true,
    };
  return null;
}

function loadFailure(error: unknown): CustomerProblem {
  return (
    unavailable(error) ?? {
      message: "We could not load the contractor work order.",
      needsReload: true,
      hideDocument: true,
    }
  );
}

function sendFailure(error: unknown): {
  problem: CustomerProblem;
  retry: boolean;
} {
  const access = unavailable(error);
  if (access) return { problem: access, retry: false };
  if (
    error instanceof ManagementApiError &&
    error.status !== undefined &&
    error.status >= 400 &&
    error.status < 500
  ) {
    if (error.code === "PROPERTY_MAINTENANCE_STATE_INVALID")
      return {
        problem: {
          message:
            "This work order is no longer assigned and cannot accept updates.",
          needsReload: true,
        },
        retry: false,
      };
    return {
      problem: {
        message: "Check your update details and try again.",
      },
      retry: false,
    };
  }
  return {
    problem: {
      message:
        "We could not confirm your update. Try again to check whether it was received.",
    },
    retry: true,
  };
}

function when(instant: string, zone: string): string {
  try {
    const { date, time } = businessDateTime(instant, zone);
    return `${date} ${time} (${zone})`;
  } catch {
    return instant;
  }
}

function WorkOrder({
  link,
  returnPath,
}: {
  link: ContractorWorkLink;
  returnPath: string;
}) {
  const [zone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [order, setOrder] = useState<ContractorWorkOrderView | null>(null);
  const [problem, setProblem] = useState<CustomerProblem | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [kind, setKind] = useState<ContractorUpdateKind | "">("");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<ContractorUpdateBody | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const inFlight = useRef(false);
  const result = useRef<HTMLParagraphElement>(null);
  const locked = saving || pending !== null;

  useEffect(() => {
    const request = new AbortController();
    fetchContractorWork(link, request.signal).then(
      (data) => {
        if (!request.signal.aborted) setOrder(data);
      },
      (failure: unknown) => {
        if (!request.signal.aborted) setProblem(loadFailure(failure));
      },
    );
    return () => request.abort();
  }, [link, attempt]);

  useEffect(() => {
    if (notice) result.current?.focus();
  }, [notice]);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || !order) return;
    setNotice("");
    let body = pending;
    if (!body) {
      if (!kind) {
        setProblem({ message: "Choose the update status." });
        return;
      }
      const cleaned = note.trim();
      if (!cleaned) {
        setProblem({ message: "Enter a note describing the work update." });
        return;
      }
      body = {
        schema_version: 1,
        kind,
        note: cleaned,
      };
    }
    inFlight.current = true;
    setPending(body);
    setSaving(true);
    setProblem(null);
    try {
      const saved = await postContractorUpdate(link, body);
      setOrder(
        (current) =>
          current && {
            ...current,
            updates: [
              ...current.updates.filter((item) => item.number !== saved.number),
              saved,
            ].sort((left, right) => left.number - right.number),
          },
      );
      setPending(null);
      setKind("");
      setNote("");
      setNotice(`Work update ${saved.number} sent.`);
    } catch (failure) {
      const next = sendFailure(failure);
      if (!next.retry) setPending(null);
      if (next.problem.hideDocument) setOrder(null);
      setProblem(next.problem);
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  return (
    <>
      {!order && !problem ? <p role="status">Loading work order…</p> : null}
      {problem ? (
        <CustomerAccessFeedback
          problem={problem}
          returnPath={returnPath}
          onReload={() => {
            setProblem(null);
            setOrder(null);
            setPending(null);
            setAttempt((value) => value + 1);
          }}
        />
      ) : null}
      {notice ? (
        <p role="status" tabIndex={-1} ref={result}>
          {notice}
        </p>
      ) : null}
      {order ? (
        <>
          <h2>{order.title}</h2>
          <dl>
            <div>
              <dt>Property</dt>
              <dd>{`${order.object_name} (${order.object_kind})`}</dd>
            </div>
            <div>
              <dt>Category</dt>
              <dd>{CATEGORY_LABELS[order.category]}</dd>
            </div>
            <div>
              <dt>Priority</dt>
              <dd>{PRIORITY_LABELS[order.priority]}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{STATE_LABELS[order.state]}</dd>
            </div>
          </dl>
          <p>{order.description}</p>
          <h2>Work updates</h2>
          {order.updates.length === 0 ? (
            <p>No updates posted yet.</p>
          ) : (
            <ol className="customer-proposal-lines" aria-label="Work updates">
              {order.updates.map((item) => (
                <li key={item.number}>
                  <h3>{`Update ${item.number}: ${UPDATE_KIND_LABELS[item.kind]}`}</h3>
                  <p>{`${item.company_name} · ${when(item.created_at, zone)}`}</p>
                  <p>{item.note}</p>
                </li>
              ))}
            </ol>
          )}
          {order.state === "assigned" ? (
            <>
              <h2>Post an update</h2>
              <form
                className="customer-proposal-form"
                aria-label="Post contractor update"
                onSubmit={(event) => void send(event)}
              >
                <label>
                  Update status
                  <select
                    value={kind}
                    required
                    disabled={locked}
                    onChange={(event) =>
                      setKind(
                        CONTRACTOR_UPDATE_KINDS.find(
                          (item) => item === event.target.value,
                        ) ?? "",
                      )
                    }
                  >
                    <option value="">Choose a status</option>
                    {CONTRACTOR_UPDATE_KINDS.map((item) => (
                      <option key={item} value={item}>
                        {UPDATE_KIND_LABELS[item]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Update note
                  <textarea
                    value={note}
                    required
                    maxLength={2000}
                    disabled={locked}
                    onChange={(event) => setNote(event.target.value)}
                  />
                </label>
                <button
                  type="submit"
                  aria-disabled={saving || (!pending && !note.trim())}
                >
                  {saving
                    ? "Sending update…"
                    : pending
                      ? "Retry update"
                      : "Send update"}
                </button>
              </form>
            </>
          ) : (
            <p>This work order is closed and can no longer accept updates.</p>
          )}
        </>
      ) : null}
    </>
  );
}
