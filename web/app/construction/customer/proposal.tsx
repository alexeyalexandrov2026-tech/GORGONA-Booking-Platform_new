"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { signIn } from "../../../lib/auth";
import {
  acceptCustomerProposal,
  fetchCustomerProposal,
} from "../../../lib/construction-api";
import {
  customerProposalLinkSchema,
  type CustomerProposal,
  type CustomerProposalLink,
} from "../../../lib/construction-contracts";
import {
  currencyPlaces,
  formatMinor,
  quantityText,
} from "../../../lib/construction-rules";
import { ManagementApiError } from "../../../lib/management-api";

export function CustomerProposalPage() {
  const params = useSearchParams();
  const parsed = customerProposalLinkSchema.safeParse({
    business: params.get("business"),
    project: params.get("project"),
    grant: params.get("grant"),
  });
  if (!parsed.success)
    return <p role="alert">This proposal link is incomplete or invalid.</p>;
  const query = new URLSearchParams(parsed.data).toString();
  return (
    <Proposal
      key={query}
      reference={parsed.data}
      returnPath={`/construction/customer/?${query}`}
    />
  );
}

type Problem = {
  message: string;
  needsSignIn?: boolean;
  needsReload?: boolean;
  hideProposal?: boolean;
};

function failure(error: unknown, submitting: boolean): Problem {
  if (error instanceof ManagementApiError) {
    if (error.status === 401 || error.code === "AUTHENTICATION_REQUIRED")
      return {
        message: "Sign in to view and accept this proposal.",
        needsSignIn: true,
        hideProposal: true,
      };
    if (error.status === 403 || error.status === 404)
      return {
        message: "This proposal is unavailable for your account.",
        hideProposal: true,
      };
    if (error.status === 409)
      return {
        message:
          "The proposal could not be accepted. Reload it before trying again.",
        needsReload: true,
        hideProposal: true,
      };
  }
  return submitting
    ? {
        message:
          "We could not confirm your acceptance. Try again to check whether it was received.",
      }
    : {
        message: "We could not load the proposal.",
        needsReload: true,
        hideProposal: true,
      };
}

function Proposal({
  reference: { business, project, grant },
  returnPath,
}: {
  reference: CustomerProposalLink;
  returnPath: string;
}) {
  const [proposal, setProposal] = useState<CustomerProposal | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [signatory, setSignatory] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const result = useRef<HTMLParagraphElement>(null);
  const focusResult = useRef(false);

  useEffect(() => {
    const request = new AbortController();
    fetchCustomerProposal({ business, project, grant }, request.signal).then(
      (data) => {
        if (!request.signal.aborted) setProposal(data);
      },
      (error: unknown) => {
        if (!request.signal.aborted) setProblem(failure(error, false));
      },
    );
    return () => request.abort();
  }, [business, project, grant, attempt]);

  useEffect(() => {
    if (proposal?.accepted && focusResult.current) {
      result.current?.focus();
      focusResult.current = false;
    }
  }, [proposal]);

  async function authenticate() {
    setSigningIn(true);
    try {
      await signIn(returnPath);
    } catch {
      setProblem({
        message: "Sign-in could not start. Try again.",
        needsSignIn: true,
      });
    } finally {
      setSigningIn(false);
    }
  }

  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !proposal || proposal.accepted || !signatory.trim()) return;
    setSaving(true);
    setProblem(null);
    try {
      const accepted = await acceptCustomerProposal(
        { business, project, grant },
        proposal,
        signatory.trim(),
        note.trim(),
      );
      focusResult.current = true;
      setProposal(accepted);
    } catch (error) {
      const refusal = failure(error, true);
      if (refusal.hideProposal) setProposal(null);
      setProblem(refusal);
    } finally {
      setSaving(false);
    }
  }

  const places = proposal && currencyPlaces(proposal.currency);
  const amount = (value: number) =>
    places === null ? `${value} minor units` : formatMinor(value, places ?? 0);

  return (
    <>
      {!proposal && !problem && <p role="status">Loading proposal…</p>}
      {problem && (
        <div>
          <p role={problem.needsSignIn ? "status" : "alert"}>
            {problem.message}
          </p>
          {problem.needsSignIn && (
            <button
              type="button"
              disabled={signingIn}
              onClick={() => void authenticate()}
            >
              {signingIn ? "Starting sign-in…" : "Sign in"}
            </button>
          )}
          {problem.needsReload && (
            <button
              type="button"
              onClick={() => {
                setProblem(null);
                setAttempt(attempt + 1);
              }}
            >
              Reload proposal
            </button>
          )}
        </div>
      )}
      {proposal && (
        <>
          <p>
            Version {proposal.version} · Total{" "}
            <strong>
              {proposal.currency} {amount(proposal.price_total_minor)}
            </strong>
          </p>
          {proposal.accepted && (
            <p role="status" tabIndex={-1} ref={result}>
              Proposal accepted.
            </p>
          )}
          <h2>Scope of work</h2>
          <ol className="customer-proposal-lines">
            {proposal.lines.map((line) => (
              <li key={line.position}>
                <h3>{line.description}</h3>
                <p>{line.phase}</p>
                <p>
                  {quantityText(line.quantity)} {line.unit} ×{" "}
                  {proposal.currency} {amount(line.unit_price_minor)}
                  {" · "}
                  <strong>
                    {proposal.currency} {amount(line.price_minor)}
                  </strong>
                </p>
              </li>
            ))}
          </ol>
          {!proposal.accepted && (
            <form
              className="customer-proposal-form"
              onSubmit={(event) => void accept(event)}
            >
              <h2>Accept proposal</h2>
              <label>
                Signatory name
                <input
                  autoComplete="name"
                  required
                  maxLength={200}
                  value={signatory}
                  onChange={(event) => setSignatory(event.target.value)}
                  disabled={saving}
                />
              </label>
              <label>
                Note (optional)
                <textarea
                  maxLength={1000}
                  rows={3}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  disabled={saving}
                />
              </label>
              <button type="submit" disabled={saving || !signatory.trim()}>
                {saving ? "Accepting proposal…" : "Accept proposal"}
              </button>
            </form>
          )}
        </>
      )}
    </>
  );
}
