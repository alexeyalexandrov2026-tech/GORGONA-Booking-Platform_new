"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  answerCustomerChange,
  fetchCustomerChange,
} from "../../../../lib/construction-api";
import {
  customerProposalLinkSchema,
  type CustomerProposalLink,
  type CustomerChange,
  type CustomerChangeAnswer,
} from "../../../../lib/construction-contracts";
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

export function CustomerChangePage() {
  const params = useSearchParams();
  const parsed = customerProposalLinkSchema.safeParse({
    business: params.get("business"),
    project: params.get("project"),
    grant: params.get("grant"),
  });
  const number = params.get("number") ?? "";
  if (
    !parsed.success ||
    !/^[1-9]\d{0,5}$/.test(number) ||
    Number(number) > 100_000
  )
    return <p role="alert">This change order link is incomplete or invalid.</p>;
  const query = new URLSearchParams({ ...parsed.data, number }).toString();
  return (
    <Change
      key={query}
      reference={parsed.data}
      number={Number(number)}
      returnPath={`/construction/customer/change/?${query}`}
    />
  );
}

function Change({
  reference: { business, project, grant },
  number,
  returnPath,
}: {
  reference: CustomerProposalLink;
  number: number;
  returnPath: string;
}) {
  const [change, setChange] = useState<CustomerChange | null>(null);
  const [problem, setProblem] = useState<CustomerProblem | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [decision, setDecision] = useState<"approved" | "rejected" | "">("");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<CustomerChangeAnswer | null>(null);
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);
  const result = useRef<HTMLParagraphElement>(null);
  const focusResult = useRef(false);

  useEffect(() => {
    const request = new AbortController();
    fetchCustomerChange(
      { business, project, grant },
      number,
      request.signal,
    ).then(
      (data) => {
        if (!request.signal.aborted) setChange(data);
      },
      (error: unknown) => {
        if (!request.signal.aborted)
          setProblem(customerFailure(error, false, "change order"));
      },
    );
    return () => request.abort();
  }, [business, project, grant, number, attempt]);

  useEffect(() => {
    if (change && change.state !== "proposed" && focusResult.current) {
      result.current?.focus();
      focusResult.current = false;
    }
  }, [change]);

  function reload() {
    setChange(null);
    setProblem(null);
    setPending(null);
    setDecision("");
    setNote("");
    setAttempt(attempt + 1);
  }

  async function answer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || !change || change.state !== "proposed" || !decision)
      return;
    const body: CustomerChangeAnswer = pending ?? {
      schema_version: 1,
      decision,
      expected_customer_generation: change.customer_generation,
      note: note.trim() || null,
    };
    inFlight.current = true;
    setSaving(true);
    setPending(body);
    setProblem(null);
    try {
      const answered = await answerCustomerChange(
        { business, project, grant },
        number,
        body,
      );
      focusResult.current = true;
      setChange(answered);
      setPending(null);
    } catch (error) {
      const refused = customerFailure(error, true, "change order");
      if (refused.hideDocument) setChange(null);
      setProblem(refused);
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  const places = change && currencyPlaces(change.currency);
  const amount = (minor: number) =>
    places === null ? `${minor} minor units` : formatMinor(minor, places ?? 0);

  return (
    <>
      {!change && !problem && <p role="status">Loading change order…</p>}
      {problem && (
        <CustomerAccessFeedback
          problem={problem}
          returnPath={returnPath}
          onReload={reload}
        />
      )}
      {change && (
        <>
          <h2>{change.title}</h2>
          {change.reason && <p>{change.reason}</p>}
          <p>
            Change order {change.number} · Price change{" "}
            <strong>
              {change.currency} {amount(change.price_minor)}
            </strong>
          </p>
          <p>
            Schedule change <strong>{change.days_delta} days</strong>
          </p>
          {change.state !== "proposed" && (
            <p role="status" ref={result} tabIndex={-1}>
              {change.state === "approved"
                ? "Change order approved."
                : change.state === "rejected"
                  ? "Change order rejected."
                  : "Change order withdrawn."}
            </p>
          )}
          <h2>Scope changes</h2>
          <ol className="customer-proposal-lines">
            {change.lines.map((line) => (
              <li key={line.position}>
                <h3>
                  {line.action === "add" ? "Add" : "Remove"} ·{" "}
                  {line.description}
                </h3>
                <p>{line.phase}</p>
                <p>
                  {quantityText(line.quantity)} {line.unit} × {change.currency}{" "}
                  {amount(line.unit_price_minor)}
                  {" · "}
                  <strong>
                    {change.currency} {amount(line.price_minor)}
                  </strong>
                </p>
              </li>
            ))}
          </ol>
          {change.state === "proposed" && (
            <form
              className="customer-proposal-form"
              aria-label="Answer change order"
              onSubmit={(event) => void answer(event)}
            >
              <fieldset disabled={saving || pending !== null}>
                <legend>Your decision</legend>
                <label>
                  <input
                    type="radio"
                    name="decision"
                    value="approved"
                    required
                    checked={decision === "approved"}
                    onChange={() => setDecision("approved")}
                  />{" "}
                  Approve change order
                </label>
                <label>
                  <input
                    type="radio"
                    name="decision"
                    value="rejected"
                    required
                    checked={decision === "rejected"}
                    onChange={() => setDecision("rejected")}
                  />{" "}
                  Reject change order
                </label>
              </fieldset>
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
              <button type="submit" disabled={saving || !decision}>
                {saving
                  ? "Sending answer…"
                  : pending
                    ? "Retry answer"
                    : "Send answer"}
              </button>
              {pending && !saving && (
                <button type="button" className="secondary" onClick={reload}>
                  Reload change order
                </button>
              )}
            </form>
          )}
        </>
      )}
    </>
  );
}
