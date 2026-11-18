"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { businessDateTime } from "../../../lib/business-time";
import { currencyPlaces, formatMinor } from "../../../lib/construction-rules";
import { ManagementApiError } from "../../../lib/management-api";
import {
  acceptRentalProposal,
  fetchRentalProposal,
} from "../../../lib/rental-api";
import {
  rentalProposalLinkSchema,
  type RentalCustomerDocument,
  type RentalProposalLink,
} from "../../../lib/rental-contracts";
import {
  CustomerAccessFeedback,
  customerFailure,
  type CustomerProblem,
} from "../../construction/customer/access";

export function RentalProposalPage() {
  const params = useSearchParams();
  const reference = rentalProposalLinkSchema.safeParse({
    business: params.get("business")?.toLowerCase(),
    booking: params.get("booking")?.toLowerCase(),
    grant: params.get("grant")?.toLowerCase(),
  });
  if (!reference.success)
    return <p role="alert">This proposal link is incomplete or invalid.</p>;
  const query = new URLSearchParams(reference.data).toString();
  return (
    <Proposal
      key={query}
      link={reference.data}
      returnPath={`/rental/customer/?${query}`}
    />
  );
}

function when(instant: string, timezone: string) {
  try {
    const { date, time } = businessDateTime(instant, timezone);
    return `${date} ${time} (${timezone})`;
  } catch {
    return instant;
  }
}

function Proposal({
  link: { business, booking, grant },
  returnPath,
}: {
  link: RentalProposalLink;
  returnPath: string;
}) {
  const [document, setDocument] = useState<RentalCustomerDocument | null>(null);
  const [problem, setProblem] = useState<CustomerProblem | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [signatory, setSignatory] = useState("");
  const [submittedName, setSubmittedName] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);
  const result = useRef<HTMLParagraphElement>(null);
  const focusResult = useRef(false);

  useEffect(() => {
    const request = new AbortController();
    fetchRentalProposal({ business, booking, grant }, request.signal).then(
      (data) => {
        if (!request.signal.aborted) setDocument(data);
      },
      (failure: unknown) => {
        if (!request.signal.aborted)
          setProblem(customerFailure(failure, false, "proposal"));
      },
    );
    return () => request.abort();
  }, [business, booking, grant, attempt]);

  useEffect(() => {
    if (document?.status === "accepted" && focusResult.current) {
      result.current?.focus();
      focusResult.current = false;
    }
  }, [document]);

  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = submittedName ?? signatory.trim();
    if (inFlight.current || document?.status !== "pending" || !name) return;
    inFlight.current = true;
    setSaving(true);
    setSubmittedName(name);
    setProblem(null);
    try {
      const receipt = await acceptRentalProposal(
        { business, booking, grant },
        document,
        name,
      );
      focusResult.current = true;
      setDocument(receipt);
    } catch (failure) {
      if (failure instanceof ManagementApiError && failure.status === 422) {
        setSubmittedName(null);
        setProblem({ message: "Check the signatory name and try again." });
      } else {
        const next = customerFailure(failure, true, "proposal");
        if (next.hideDocument) {
          setDocument(null);
          setSubmittedName(null);
        }
        setProblem(next);
      }
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  if (document?.status === "accepted")
    return (
      <>
        <p role="status" tabIndex={-1} ref={result}>
          Proposal accepted.
        </p>
        <p>Agreement reference: {document.agreement_id}</p>
      </>
    );
  const offer = document?.status === "pending" ? document : null;
  const places = offer && currencyPlaces(offer.quote.currency);

  return (
    <>
      {!offer && !problem && <p role="status">Loading proposal…</p>}
      {problem && (
        <CustomerAccessFeedback
          problem={problem}
          returnPath={returnPath}
          onReload={() => {
            setProblem(null);
            setAttempt((value) => value + 1);
          }}
        />
      )}
      {offer && (
        <>
          <h2>{offer.class_name}</h2>
          <dl>
            <dt>Pickup</dt>
            <dd>
              {offer.pickup.name} ·{" "}
              {when(offer.quote.starts_at, offer.pickup.timezone)}
            </dd>
            <dt>Return</dt>
            <dd>
              {offer.return_location?.name ??
                `Location reference ${offer.return_location_id}`}
              {" · "}
              {when(
                offer.quote.ends_at,
                offer.return_location?.timezone ?? offer.pickup.timezone,
              )}
            </dd>
            <dt>Total</dt>
            <dd>
              <strong>
                {offer.quote.currency}{" "}
                {places === null
                  ? `${offer.quote.total} minor units`
                  : formatMinor(offer.quote.total, places ?? 0)}
              </strong>
            </dd>
          </dl>
          <form
            className="customer-proposal-form"
            onSubmit={(event) => void accept(event)}
          >
            <label>
              Signatory name
              <input
                autoComplete="name"
                required
                maxLength={200}
                value={signatory}
                onChange={(event) => setSignatory(event.target.value)}
                disabled={saving || submittedName !== null}
              />
            </label>
            <button type="submit" disabled={saving || !signatory.trim()}>
              {saving
                ? "Accepting proposal…"
                : submittedName
                  ? "Retry acceptance"
                  : "Accept proposal"}
            </button>
          </form>
        </>
      )}
    </>
  );
}
