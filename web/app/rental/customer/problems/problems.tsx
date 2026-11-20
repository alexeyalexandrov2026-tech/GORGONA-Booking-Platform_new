"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  EARLIEST_PROBLEM_DATE,
  pastInstant,
  problemKindLabels,
} from "../../../../components/rental-problem-reports";
import { businessDateTime, businessToday } from "../../../../lib/business-time";
import { ManagementApiError } from "../../../../lib/management-api";
import {
  fetchCustomerProblems,
  refusal,
  reportProblemAsCustomer,
  type CustomerProblemBody,
} from "../../../../lib/rental-api";
import {
  problemKinds,
  rentalProposalLinkSchema,
  type CustomerProblemList,
  type ProblemKind,
  type RentalProposalLink,
} from "../../../../lib/rental-contracts";
import {
  CustomerAccessFeedback,
  type CustomerProblem,
} from "../../../construction/customer/access";

// R-09 (RENT-01): a delegate of the customer company reports a problem with the rental through the
// company's live grant and sees the reports the company made. Times are entered and shown in the
// delegate's own time zone; the server stores the instant.
export function RentalProblemsPage() {
  const params = useSearchParams();
  const reference = rentalProposalLinkSchema.safeParse({
    business: params.get("business")?.toLowerCase(),
    booking: params.get("booking")?.toLowerCase(),
    grant: params.get("grant")?.toLowerCase(),
  });
  if (!reference.success)
    return (
      <p role="alert">This problem report link is incomplete or invalid.</p>
    );
  const query = new URLSearchParams(reference.data).toString();
  return (
    <Problems
      key={query}
      link={reference.data}
      returnPath={`/rental/customer/problems/?${query}`}
    />
  );
}

function unavailable(error: unknown): CustomerProblem | null {
  if (!(error instanceof ManagementApiError)) return null;
  if (error.status === 401 || error.code === "AUTHENTICATION_REQUIRED")
    return {
      message: "Sign in to see and report problems with this rental.",
      needsSignIn: true,
      hideDocument: true,
    };
  if (error.status === 403 || error.status === 404)
    return {
      message: "Problem reports are unavailable for your account.",
      hideDocument: true,
    };
  return null;
}

function loadFailure(error: unknown): CustomerProblem {
  return (
    unavailable(error) ?? {
      message: "We could not load the problem reports.",
      needsReload: true,
      hideDocument: true,
    }
  );
}

/** What went wrong with a report, and whether a retry must resend the same report. */
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
    if (error.code === "RENTAL_REVISION_CONFLICT")
      return {
        problem: {
          message: "The rental changed. Reload before reporting.",
          needsReload: true,
          hideDocument: true,
        },
        retry: false,
      };
    if (error.code === "RENTAL_BOOKING_CANCELLED")
      return {
        problem: {
          message:
            "This booking is cancelled, so problems can no longer be reported.",
          hideDocument: true,
        },
        retry: false,
      };
    return {
      problem: {
        message:
          error.code === "RENTAL_FUTURE_TIME"
            ? "Enter when the problem happened; it cannot be in the future."
            : "Check the details and try again.",
      },
      retry: false,
    };
  }
  return {
    problem: {
      message:
        "We could not confirm your report. Try again to check whether it was received.",
    },
    retry: true,
  };
}

function when(instant: string, zone: string) {
  try {
    const { date, time } = businessDateTime(instant, zone);
    return `${date} ${time} (${zone})`;
  } catch {
    return instant;
  }
}

function Problems({
  link: { business, booking, grant },
  returnPath,
}: {
  link: RentalProposalLink;
  returnPath: string;
}) {
  const [zone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [list, setList] = useState<CustomerProblemList | null>(null);
  const [problem, setProblem] = useState<CustomerProblem | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [kind, setKind] = useState<ProblemKind | "">("");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState(() => businessToday(zone));
  const [time, setTime] = useState("");
  const [pending, setPending] = useState<CustomerProblemBody | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const inFlight = useRef(false);
  const result = useRef<HTMLParagraphElement>(null);
  const locked = saving || pending !== null;

  useEffect(() => {
    const request = new AbortController();
    fetchCustomerProblems({ business, booking, grant }, request.signal).then(
      (data) => {
        if (!request.signal.aborted) setList(data);
      },
      (failure: unknown) => {
        if (!request.signal.aborted) setProblem(loadFailure(failure));
      },
    );
    return () => request.abort();
  }, [business, booking, grant, attempt]);

  useEffect(() => {
    if (notice) result.current?.focus();
  }, [notice]);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || !list) return;
    setNotice("");
    let body = pending;
    if (!body) {
      if (!kind) {
        setProblem({ message: "Choose the kind of problem." });
        return;
      }
      try {
        body = {
          schema_version: 1,
          binding_revision: list.binding_revision,
          kind,
          description: description.trim(),
          occurred_at: pastInstant(date, time, zone),
        };
      } catch (failure) {
        setProblem({ message: refusal(failure) });
        return;
      }
    }
    inFlight.current = true;
    setPending(body);
    setSaving(true);
    setProblem(null);
    try {
      const saved = await reportProblemAsCustomer(
        { business, booking, grant },
        body,
      );
      setList(
        (current) =>
          current && {
            ...current,
            items: [
              ...current.items.filter((item) => item.number !== saved.number),
              saved,
            ].sort((a, b) => a.number - b.number),
          },
      );
      setPending(null);
      setKind("");
      setDescription("");
      setTime("");
      setNotice(`Problem report ${saved.number} sent.`);
    } catch (failure) {
      const next = sendFailure(failure);
      if (!next.retry) setPending(null);
      if (next.problem.hideDocument) setList(null);
      setProblem(next.problem);
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  return (
    <>
      {!list && !problem && <p role="status">Loading problem reports…</p>}
      {problem && (
        <CustomerAccessFeedback
          problem={problem}
          returnPath={returnPath}
          onReload={() => {
            setProblem(null);
            setList(null);
            setPending(null);
            setAttempt((value) => value + 1);
          }}
        />
      )}
      {notice && (
        <p role="status" tabIndex={-1} ref={result}>
          {notice}
        </p>
      )}
      {list && (
        <>
          <h2>Your problem reports</h2>
          {list.items.length === 0 ? (
            <p>No problem reports yet.</p>
          ) : (
            <ol
              className="customer-proposal-lines"
              aria-label="Your problem reports"
            >
              {list.items.map((item) => (
                <li key={item.number}>
                  <h3>{`Report ${item.number}: ${problemKindLabels[item.kind]}`}</h3>
                  <p>{`Happened ${when(item.occurred_at, zone)}`}</p>
                  <p>{item.description}</p>
                </li>
              ))}
            </ol>
          )}
          <h2>Report a problem</h2>
          <form
            className="customer-proposal-form"
            aria-label="Report a problem"
            onSubmit={(event) => void send(event)}
          >
            <label>
              Kind
              <select
                value={kind}
                required
                disabled={locked}
                onChange={(event) =>
                  setKind(
                    problemKinds.find((item) => item === event.target.value) ??
                      "",
                  )
                }
              >
                <option value="">Choose a kind</option>
                {problemKinds.map((item) => (
                  <option key={item} value={item}>
                    {problemKindLabels[item]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              What happened
              <textarea
                value={description}
                required
                maxLength={2000}
                disabled={locked}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <label>
              Date
              <input
                type="date"
                value={date}
                min={EARLIEST_PROBLEM_DATE}
                required
                disabled={locked}
                onChange={(event) => setDate(event.target.value)}
              />
            </label>
            <label>
              Time
              <input
                type="time"
                value={time}
                required
                disabled={locked}
                onChange={(event) => setTime(event.target.value)}
              />
            </label>
            <p>{`Times are in your time zone (${zone}).`}</p>
            <button
              type="submit"
              disabled={saving || (!pending && !description.trim())}
            >
              {saving
                ? "Sending report…"
                : pending
                  ? "Retry problem report"
                  : "Send problem report"}
            </button>
          </form>
        </>
      )}
    </>
  );
}
