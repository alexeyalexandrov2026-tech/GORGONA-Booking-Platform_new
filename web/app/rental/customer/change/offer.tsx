"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { businessDateTime } from "../../../../lib/business-time";
import {
  currencyPlaces,
  formatMinor,
} from "../../../../lib/construction-rules";
import { ManagementApiError } from "../../../../lib/management-api";
import {
  acceptRentalChange,
  fetchRentalChange,
  rentalChangeHref,
} from "../../../../lib/rental-api";
import {
  rentalChangeLinkSchema,
  type RentalChangeDocument,
  type RentalChangeLink,
} from "../../../../lib/rental-contracts";
import {
  CustomerAccessFeedback,
  customerFailure,
  type CustomerProblem,
} from "../../../construction/customer/access";

export function RentalChangePage() {
  const params = useSearchParams();
  const revision = params.get("revision") ?? "";
  const result = rentalChangeLinkSchema.safeParse({
    business: params.get("business")?.toLowerCase(),
    booking: params.get("booking")?.toLowerCase(),
    grant: params.get("grant")?.toLowerCase(),
    revision: /^[1-9][0-9]{0,9}$/.test(revision) ? Number(revision) : null,
  });
  if (!result.success)
    return (
      <p role="alert">This rental change link is incomplete or invalid.</p>
    );
  const href = rentalChangeHref(result.data);
  return <OfferView key={href} link={result.data} returnPath={href} />;
}

function when(value: string, timezone: string) {
  try {
    const { date, time } = businessDateTime(value, timezone);
    return `${date} ${time}`;
  } catch {
    return value;
  }
}

function rentalChangeFailure(
  failure: unknown,
  submitting: boolean,
): CustomerProblem {
  if (failure instanceof ManagementApiError) {
    if (failure.code === "RENTAL_PROPOSAL_STALE")
      return {
        message:
          "This offer is out of date. Ask the rental company for the latest link.",
        hideDocument: true,
      };
    if (["RENTAL_UNIT_BUSY", "RENTAL_UNAVAILABLE"].includes(failure.code))
      return {
        message:
          "The proposed period is no longer available. Ask the rental company for a new offer.",
        hideDocument: true,
      };
  }
  return customerFailure(failure, submitting, "rental change");
}

function OfferView({
  link: { business, booking, grant, revision },
  returnPath,
}: {
  link: RentalChangeLink;
  returnPath: string;
}) {
  const [document, setDocument] = useState<RentalChangeDocument | null>(null);
  const [problem, setProblem] = useState<CustomerProblem | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [signatory, setSignatory] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);
  const receipt = useRef<HTMLParagraphElement>(null);
  const focusReceipt = useRef(false);

  useEffect(() => {
    const request = new AbortController();
    fetchRentalChange(
      { business, booking, grant, revision },
      request.signal,
    ).then(
      (loaded) => {
        if (!request.signal.aborted) setDocument(loaded);
      },
      (failure: unknown) => {
        if (!request.signal.aborted)
          setProblem(rentalChangeFailure(failure, false));
      },
    );
    return () => request.abort();
  }, [business, booking, grant, revision, attempt]);

  useEffect(() => {
    if (document?.status === "accepted" && focusReceipt.current) {
      receipt.current?.focus();
      focusReceipt.current = false;
    }
  }, [document]);

  function reload() {
    setProblem(null);
    setAttempt((value) => value + 1);
  }

  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = pending ?? signatory.trim();
    if (submitting.current || document?.status !== "pending" || !name) return;
    submitting.current = true;
    setSaving(true);
    setPending(name);
    setProblem(null);
    try {
      const accepted = await acceptRentalChange(
        { business, booking, grant, revision },
        document,
        name,
      );
      focusReceipt.current = true;
      setDocument(accepted);
    } catch (failure) {
      if (failure instanceof ManagementApiError && failure.status === 422) {
        setPending(null);
        setProblem({ message: "Check the signatory name and try again." });
      } else {
        const next = rentalChangeFailure(failure, true);
        if (next.hideDocument) {
          setPending(null);
          setDocument(null);
        }
        setProblem(next);
      }
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  }

  if (document?.status === "accepted")
    return (
      <>
        <p role="status" tabIndex={-1} ref={receipt}>
          Agreement change accepted.
        </p>
        <p>Agreement version {document.agreement_version}</p>
      </>
    );

  const offer = document?.status === "pending" ? document : null;
  const total = (value: number, currency: string) => {
    const places = currencyPlaces(currency);
    return places === null
      ? `${value} minor units`
      : formatMinor(value, places);
  };
  return (
    <>
      {!offer && !problem && <p role="status">Loading rental change…</p>}
      {problem && (
        <CustomerAccessFeedback
          problem={problem}
          returnPath={returnPath}
          onReload={reload}
        />
      )}
      {offer && (
        <>
          <p>{offer.reason}</p>
          <dl>
            <dt>Pickup</dt>
            <dd>
              <time dateTime={offer.quote.starts_at}>
                {when(offer.quote.starts_at, offer.pickup_timezone)}
              </time>
            </dd>
            <dt>Return</dt>
            <dd>
              <time dateTime={offer.quote.ends_at}>
                {when(offer.quote.ends_at, offer.pickup_timezone)}
              </time>
            </dd>
            <dt>Time zone</dt>
            <dd>{offer.pickup_timezone}</dd>
            <dt>New total</dt>
            <dd>
              <strong>
                {offer.quote.currency}{" "}
                {total(offer.quote.total, offer.quote.currency)}
              </strong>
            </dd>
          </dl>
          {offer.quote.extras.length > 0 && (
            <>
              <h2>Extras</h2>
              <ul>
                {offer.quote.extras.map((line) => (
                  <li key={line.code}>
                    {offer.extra_names[line.code] ?? line.code} ×{" "}
                    {line.quantity}
                    {" · "}
                    {offer.quote.currency}{" "}
                    {total(line.amount, offer.quote.currency)}
                  </li>
                ))}
              </ul>
            </>
          )}
          <form
            className="customer-proposal-form"
            onSubmit={(event) => void accept(event)}
          >
            <label>
              Signatory name
              <input
                autoComplete="name"
                maxLength={200}
                required
                value={signatory}
                disabled={saving || pending !== null}
                onChange={(event) => setSignatory(event.target.value)}
              />
            </label>
            <button type="submit" disabled={saving || !signatory.trim()}>
              {saving
                ? "Accepting change…"
                : pending
                  ? "Retry acceptance"
                  : "Accept change"}
            </button>
          </form>
        </>
      )}
    </>
  );
}
