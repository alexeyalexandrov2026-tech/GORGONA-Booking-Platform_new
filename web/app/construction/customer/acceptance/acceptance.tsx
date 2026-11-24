"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  acceptCustomerWork,
  fetchCustomerWorkReview,
} from "../../../../lib/construction-api";
import {
  customerProposalLinkSchema,
  type CustomerProposalLink,
} from "../../../../lib/construction-contracts";
import type {
  CustomerWorkAnswer,
  CustomerWorkReceipt,
  CustomerWorkReview,
} from "../../../../lib/construction-customer-acceptance-contracts";
import {
  currencyPlaces,
  formatMinor,
  quantityText,
} from "../../../../lib/construction-rules";
import {
  CustomerAccessFeedback,
  customerFailure,
  type CustomerProblem,
} from "../access";
import { ManagementApiError } from "../../../../lib/management-api";

export function CustomerWorkPage() {
  const params = useSearchParams();
  const parsed = customerProposalLinkSchema.safeParse({
    business: params.get("business"),
    project: params.get("project"),
    grant: params.get("grant"),
  });
  if (!parsed.success)
    return <p role="alert">This acceptance link is incomplete or invalid.</p>;
  const query = new URLSearchParams(parsed.data).toString();
  return (
    <Work
      key={query}
      reference={parsed.data}
      returnPath={`/construction/customer/acceptance/?${query}`}
    />
  );
}

function Work({
  reference: { business, project, grant },
  returnPath,
}: {
  reference: CustomerProposalLink;
  returnPath: string;
}) {
  const [review, setReview] = useState<CustomerWorkReview | null>(null);
  const [receipt, setReceipt] = useState<CustomerWorkReceipt | null>(null);
  const [problem, setProblem] = useState<CustomerProblem | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [selection, setSelection] = useState("");
  const [date, setDate] = useState("");
  const [warranty, setWarranty] = useState("");
  const [signatory, setSignatory] = useState("");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<CustomerWorkAnswer | null>(null);
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);
  const result = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const request = new AbortController();
    fetchCustomerWorkReview({ business, project, grant }, request.signal).then(
      (value) => {
        if (!request.signal.aborted) {
          setReview(value);
          setDate(value.site_today);
        }
      },
      (error: unknown) => {
        if (!request.signal.aborted)
          setProblem(customerFailure(error, false, "work acceptance"));
      },
    );
    return () => request.abort();
  }, [business, project, grant, attempt]);

  useEffect(() => {
    if (receipt) result.current?.focus();
  }, [receipt]);

  function reload() {
    setReview(null);
    setReceipt(null);
    setProblem(null);
    setSelection("");
    setDate("");
    setWarranty("");
    setPending(null);
    setAttempt(attempt + 1);
  }

  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || !review || !selection || !signatory.trim()) return;
    const body: CustomerWorkAnswer = pending ?? {
      schema_version: 1,
      expected_customer_generation: review.customer_generation,
      expected_review_hash: review.review_hash,
      accepted_on: date,
      signatory: signatory.trim(),
      note: note.trim() || null,
      ...(selection === "final"
        ? ({ scope: "final", phase: null, warranty_ends_on: warranty } as const)
        : ({
            scope: "phase",
            phase: selection.slice(6),
            warranty_ends_on: null,
          } as const)),
    };
    inFlight.current = true;
    setSaving(true);
    setPending(body);
    setProblem(null);
    try {
      setReceipt(await acceptCustomerWork({ business, project, grant }, body));
      setPending(null);
    } catch (error) {
      if (error instanceof ManagementApiError && error.status === 422) {
        setPending(null);
        setProblem({ message: error.message });
        return;
      }
      const refused = customerFailure(error, true, "work acceptance");
      if (refused.hideDocument) setReview(null);
      setProblem(refused);
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  const finalAccepted = review?.accepted.some((item) => item.scope === "final");
  const finalReady =
    review?.fully_billed &&
    review.open_items === 0 &&
    review.phases.every((phase) => phase.finished);
  const places = review && currencyPlaces(review.currency);
  const amount = (minor: number) =>
    places === null ? `${minor} minor units` : formatMinor(minor, places ?? 0);

  return (
    <>
      {!review && !problem && <p role="status">Loading work…</p>}
      {problem && (
        <CustomerAccessFeedback
          problem={problem}
          returnPath={returnPath}
          onReload={reload}
        />
      )}
      {review && (
        <>
          {receipt ? (
            <section aria-label="Acceptance receipt">
              <p role="status" tabIndex={-1} ref={result}>
                {receipt.scope === "final"
                  ? "Final acceptance recorded."
                  : `Phase ${receipt.phase} accepted.`}
              </p>
              <p>
                Accepted on {receipt.accepted_on} by {receipt.signatory}.
              </p>
              {receipt.warranty_ends_on && (
                <p>Warranty ends {receipt.warranty_ends_on}.</p>
              )}
              {receipt.scope === "phase" && (
                <button type="button" onClick={reload}>
                  Review remaining work
                </button>
              )}
            </section>
          ) : (
            <>
              {finalAccepted && (
                <p role="status">The project has final acceptance.</p>
              )}
              <h2>Work to review</h2>
              <ol className="customer-proposal-lines">
                {review.lines.map((line) => (
                  <li
                    key={`${line.change_order ?? "original"}:${line.position}`}
                  >
                    <h3>{line.description}</h3>
                    <p>
                      {line.phase} · {quantityText(line.quantity)} {line.unit} ·{" "}
                      {review.currency} {amount(line.price_minor)}
                    </p>
                    <p>
                      Completed {quantityText(line.completed_quantity)}{" "}
                      {line.unit}
                      {line.measured_on && ` as of ${line.measured_on}`}.
                    </p>
                  </li>
                ))}
              </ol>
              <h2>Readiness</h2>
              <ul>
                {review.phases.map((phase) => (
                  <li key={phase.phase}>
                    {phase.phase} ·{" "}
                    {phase.finished ? "Work completed" : "Work remaining"} ·{" "}
                    {phase.open_items} open items
                  </li>
                ))}
              </ul>
              <p>{review.open_items} open items across the project.</p>
              <p>
                {review.fully_billed
                  ? "The full contract has been billed."
                  : "Final acceptance requires the full contract to be billed."}
              </p>
              {review.accepted.length > 0 && (
                <section aria-label="Recorded acceptances">
                  <h2>Recorded acceptances</h2>
                  <ul>
                    {review.accepted.map((item) => (
                      <li key={item.number}>
                        {item.scope === "final"
                          ? "Final acceptance"
                          : item.phase}{" "}
                        · {item.accepted_on} · {item.signatory}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {!finalAccepted && (
                <form
                  className="customer-proposal-form"
                  aria-label="Accept work"
                  onSubmit={(event) => void accept(event)}
                >
                  <label>
                    Work to accept
                    <select
                      value={selection}
                      required
                      disabled={saving || pending !== null}
                      onChange={(event) => setSelection(event.target.value)}
                    >
                      <option value="">Choose work</option>
                      {review.phases.map((phase) => (
                        <option
                          key={phase.phase}
                          value={`phase:${phase.phase}`}
                          disabled={
                            !phase.finished ||
                            phase.open_items > 0 ||
                            review.accepted.some(
                              (item) => item.phase === phase.phase,
                            )
                          }
                        >
                          {phase.phase}
                        </option>
                      ))}
                      <option value="final" disabled={!finalReady}>
                        Final acceptance
                      </option>
                    </select>
                  </label>
                  <label>
                    Acceptance date
                    <input
                      type="date"
                      required
                      min="2000-01-01"
                      max={review.site_today}
                      value={date}
                      disabled={saving || pending !== null}
                      onChange={(event) => setDate(event.target.value)}
                    />
                  </label>
                  <label>
                    Signatory name
                    <input
                      required
                      maxLength={200}
                      autoComplete="name"
                      value={signatory}
                      disabled={saving || pending !== null}
                      onChange={(event) => setSignatory(event.target.value)}
                    />
                  </label>
                  {selection === "final" && (
                    <label>
                      Warranty end date
                      <input
                        type="date"
                        required
                        max="2100-12-31"
                        aria-describedby="warranty-guidance"
                        min={date}
                        value={warranty}
                        disabled={saving || pending !== null}
                        onChange={(event) => setWarranty(event.target.value)}
                      />
                    </label>
                  )}
                  {selection === "final" && (
                    <p id="warranty-guidance">
                      Warranty must end after the acceptance date and within 10
                      years.
                    </p>
                  )}
                  <label>
                    Note (optional)
                    <textarea
                      rows={3}
                      maxLength={1000}
                      value={note}
                      disabled={saving || pending !== null}
                      onChange={(event) => setNote(event.target.value)}
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={
                      saving ||
                      !selection ||
                      !date ||
                      !signatory.trim() ||
                      (selection === "final" && (!warranty || warranty <= date))
                    }
                  >
                    {saving
                      ? "Recording acceptance…"
                      : pending
                        ? "Retry acceptance"
                        : "Accept work"}
                  </button>
                  {pending && !saving && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={reload}
                    >
                      Reload work
                    </button>
                  )}
                </form>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
