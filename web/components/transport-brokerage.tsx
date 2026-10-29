"use client";

// N6 (package N, ADR-0034): brokerage on the transport screen. The broker authority, carriers with
// their profiles, the board of legs to cover, tenders with their rate confirmation versions, the
// carrier's pay and an order's margin. A company-wide owner or manager works here (transport.broker).
// Every command keeps its record id, time and key until it succeeds; refusals are shown in words.
import React, { useCallback, useEffect, useId, useState } from "react";
import { ManagementApiError } from "../lib/management-api";
import {
  accrueCarrierPay,
  answerTender,
  answerVersion,
  fetchAuthority,
  fetchBrokerEligibility,
  fetchCarrierEligibility,
  fetchCarrierPay,
  fetchConfirmation,
  fetchMargin,
  fetchProfile,
  fetchTenders,
  proposeVersion,
  saveAuthority,
  saveProfile,
  saveTender,
} from "../lib/brokerage-api";
import {
  reasonText,
  uncoveredLegs,
  type Authority,
  type CarrierPay,
  type CarrierProfile,
  type Confirmation,
  type Eligibility,
  type Margin,
  type Tender,
} from "../lib/brokerage-contracts";
import type { Order, Trip } from "../lib/transport-contracts";
import { BookSelect, useBooks } from "./transport-money";
import { AccountSelect, allActiveParties, type Party } from "./visit-billing";

type Notify = (text: string) => void;
type Source = "phone" | "email" | "load_board" | "other";

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

const today = () => new Date().toISOString().slice(0, 10);
const eligibilityText = (e: Eligibility, yes: string, no: string) =>
  e.eligible ? yes : `${no}: ${e.reasons.map(reasonText).join("; ")}.`;
const SOURCES: [Source, string][] = [
  ["phone", "Phone"],
  ["email", "Email"],
  ["load_board", "Load board"],
  ["other", "Other"],
];
const STATE: Record<Tender["state"], string> = {
  offered: "Offered",
  accepted: "Accepted",
  declined: "Declined",
  withdrawn: "Withdrawn",
  expired: "Expired",
};
const basisText = (basis: string, amount: string, currency: string) =>
  basis === "per_mile"
    ? `${amount} ${currency} per mile`
    : `${amount} ${currency} fixed`;

function SourceSelect({
  value,
  onChange,
}: {
  value: Source;
  onChange: (value: Source) => void;
}) {
  return (
    <label>
      Source
      <select
        aria-label="Source"
        value={value}
        onChange={(e) => onChange(e.target.value as Source)}
      >
        {SOURCES.map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  required = true,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  maxLength?: number;
}) {
  return (
    <label>
      {label}
      <input
        type={type}
        value={value}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
        required={required}
      />
    </label>
  );
}

function Alert({ text }: { text: string | null }) {
  return text ? (
    <p className="error" role="alert">
      {text}
    </p>
  ) : null;
}

// N1: the business's own broker authority -----------------------------------------------------

function AuthorityPanel({
  businessId,
  notify,
}: {
  businessId: string;
  notify: Notify;
}) {
  const headingId = useId();
  const [authority, setAuthority] = useState<Authority | null>(null);
  const [eligibility, setEligibility] = useState<Eligibility | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [jurisdiction, setJurisdiction] = useState("US");
  const [number, setNumber] = useState("");
  const [bond, setBond] = useState("");
  const [status, setStatus] = useState<"active" | "withdrawn">("active");
  const [from, setFrom] = useState("");
  const [until, setUntil] = useState("");
  const [source, setSource] = useState("");
  const [checked, setChecked] = useState(today);

  const read = useCallback(
    () =>
      Promise.all([
        fetchAuthority(businessId),
        fetchBrokerEligibility(businessId, today()),
      ]),
    [businessId],
  );
  const show = ([view, may]: [Authority, Eligibility]) => {
    setAuthority(view);
    setEligibility(may);
  };
  useEffect(() => {
    read()
      .then(show)
      .catch((failure: unknown) =>
        setError(`The broker authority could not be read: ${refusal(failure)}`),
      );
  }, [read]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await saveAuthority(businessId, {
        schema_version: 1,
        expected_revision: authority?.current?.revision ?? 0,
        jurisdiction,
        authority_number: number,
        bond_reference: bond,
        status,
        effective_from: from,
        expires_on: until || null,
        source,
        checked_on: checked,
      });
      show(await read());
      notify("Broker authority saved.");
    } catch (failure) {
      setError(`The authority was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const current = authority?.current;
  return (
    <section className="transport-panel" aria-labelledby={headingId}>
      <h2 id={headingId}>Broker authority</h2>
      {authority &&
        (current ? (
          <p>
            {`${current.jurisdiction} ${current.authority_number}, bond ${current.bond_reference}, ${current.status} from ${current.effective_from} (version ${current.revision} of ${authority.versions.length})`}
          </p>
        ) : (
          <p className="muted">No broker authority yet.</p>
        ))}
      {eligibility && (
        <p>
          {eligibilityText(
            eligibility,
            "May tender loads today.",
            "Cannot tender loads today",
          )}
        </p>
      )}
      <Alert text={error} />
      <form aria-label="Broker authority form" onSubmit={submit}>
        <Field
          label="Jurisdiction"
          value={jurisdiction}
          onChange={setJurisdiction}
          maxLength={2}
        />
        <Field
          label="Authority number"
          value={number}
          onChange={setNumber}
          maxLength={32}
        />
        <Field
          label="Bond reference"
          value={bond}
          onChange={setBond}
          maxLength={64}
        />
        <label>
          Status
          <select
            aria-label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value as typeof status)}
          >
            <option value="active">Active</option>
            <option value="withdrawn">Withdrawn</option>
          </select>
        </label>
        <Field
          label="Effective from"
          type="date"
          value={from}
          onChange={setFrom}
        />
        <Field
          label="Expires on"
          type="date"
          value={until}
          onChange={setUntil}
          required={false}
        />
        <Field
          label="Fact source"
          value={source}
          onChange={setSource}
          maxLength={32}
        />
        <Field
          label="Checked on"
          type="date"
          value={checked}
          onChange={setChecked}
        />
        <div className="mgmt-form-actions">
          {/* A save expects the revision that was read; until then it would guess. */}
          <button type="submit" disabled={busy || authority === null}>
            Save authority
          </button>
        </div>
      </form>
    </section>
  );
}

// N1: carriers and their profiles ----------------------------------------------------------------

type CarrierRow = {
  party: Party;
  profile: CarrierProfile | null;
  eligibility: Eligibility | null;
};
type Rating = "satisfactory" | "conditional" | "unsatisfactory" | "unrated";

function ProfileForm({
  businessId,
  row,
  onSaved,
  notify,
}: {
  businessId: string;
  row: CarrierRow;
  onSaved: () => void;
  notify: Notify;
}) {
  const current = row.profile?.current;
  const [jurisdiction, setJurisdiction] = useState(
    current?.jurisdiction ?? "US",
  );
  const [number, setNumber] = useState(current?.authority_number ?? "");
  const [liability, setLiability] = useState(
    current?.liability_expires_on ?? "",
  );
  const [cargo, setCargo] = useState(current?.cargo_expires_on ?? "");
  const [rating, setRating] = useState<Rating>(
    current?.safety_rating ?? "unrated",
  );
  const [source, setSource] = useState(current?.source ?? "");
  const [checked, setChecked] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await saveProfile(businessId, row.party.counterparty_id, {
        schema_version: 1,
        expected_revision: current?.revision ?? 0,
        jurisdiction,
        authority_number: number || null,
        liability_expires_on: liability || null,
        cargo_expires_on: cargo || null,
        safety_rating: rating,
        source,
        checked_on: checked,
      });
      onSaved();
      notify("Carrier profile saved.");
    } catch (failure) {
      setError(`The profile was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form aria-label={`Profile of ${row.party.display_name}`} onSubmit={submit}>
      <h3>{`Profile of ${row.party.display_name}`}</h3>
      <Alert text={error} />
      <Field
        label="Jurisdiction"
        value={jurisdiction}
        onChange={setJurisdiction}
        maxLength={2}
      />
      <Field
        label="Authority number"
        value={number}
        onChange={setNumber}
        required={false}
        maxLength={32}
      />
      <Field
        label="Liability insurance expires"
        type="date"
        value={liability}
        onChange={setLiability}
        required={false}
      />
      <Field
        label="Cargo insurance expires"
        type="date"
        value={cargo}
        onChange={setCargo}
        required={false}
      />
      <label>
        Safety rating
        <select
          aria-label="Safety rating"
          value={rating}
          onChange={(e) => setRating(e.target.value as Rating)}
        >
          <option value="satisfactory">Satisfactory</option>
          <option value="conditional">Conditional</option>
          <option value="unsatisfactory">Unsatisfactory</option>
          <option value="unrated">Unrated</option>
        </select>
      </label>
      <Field
        label="Fact source"
        value={source}
        onChange={setSource}
        maxLength={32}
      />
      <Field
        label="Checked on"
        type="date"
        value={checked}
        onChange={setChecked}
      />
      <div className="mgmt-form-actions">
        <button type="submit" disabled={busy}>
          Save profile
        </button>
      </div>
    </form>
  );
}

// N3: an answer to one proposed rate confirmation version ---------------------------------------

function VersionAnswer({
  businessId,
  tender,
  revision,
  onDone,
  notify,
}: {
  businessId: string;
  tender: string;
  revision: number;
  onDone: (c: Confirmation) => void;
  notify: Notify;
}) {
  const [kind, setKind] = useState<"agreed" | "declined">("agreed");
  const [source, setSource] = useState<Source>("phone");
  // The answer's time stays the same until it is recorded, so a retry is the same request.
  const [at] = useState(() => new Date().toISOString());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(
        await answerVersion(businessId, tender, revision, {
          schema_version: 1,
          kind,
          source,
          occurred_at: at,
        }),
      );
      notify("Version answer recorded.");
    } catch (failure) {
      setError(`The answer was not recorded: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form aria-label={`Answer to version ${revision}`} onSubmit={submit}>
      <Alert text={error} />
      <label>
        Answer
        <select
          aria-label="Answer"
          value={kind}
          onChange={(e) => setKind(e.target.value as typeof kind)}
        >
          <option value="agreed">Agreed</option>
          <option value="declined">Declined</option>
        </select>
      </label>
      <SourceSelect value={source} onChange={setSource} />
      <div className="mgmt-form-actions">
        <button type="submit" disabled={busy}>
          Record version answer
        </button>
      </div>
    </form>
  );
}

// N2-N5: one tender with its answers, rate confirmation versions and the carrier's pay ------------

function TenderPanel({
  businessId,
  tender,
  trip,
  carrier,
  onChange,
  notify,
}: {
  businessId: string;
  tender: Tender;
  trip: Trip;
  carrier: string;
  onChange: (t: Tender) => void;
  notify: Notify;
}) {
  const headingId = useId();
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [pay, setPay] = useState<CarrierPay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const offered = tender.state === "offered";
  const accepted = tender.state === "accepted";
  const [kind, setKind] = useState<"accepted" | "declined" | "withdrawn">(
    offered ? "accepted" : "withdrawn",
  );
  const [source, setSource] = useState<Source>("phone");
  const [answeredAt, setAnsweredAt] = useState(() => new Date().toISOString());
  const [basis, setBasis] = useState<"fixed" | "per_mile">("fixed");
  const [amount, setAmount] = useState("");
  const [terms, setTerms] = useState("");
  const [proposedAt, setProposedAt] = useState(() => new Date().toISOString());
  const { books, book, setBook, accounts } = useBooks(businessId, setError);
  const [expense, setExpense] = useState("");
  const [payable, setPayable] = useState("");
  const [date, setDate] = useState(today);
  const [number, setNumber] = useState("");
  const [miles, setMiles] = useState("");

  useEffect(() => {
    if (!accepted) return;
    let live = true;
    Promise.all([
      fetchConfirmation(businessId, tender.tender_id),
      fetchCarrierPay(businessId, tender.tender_id),
    ])
      .then(([c, p]) => {
        if (!live) return;
        setConfirmation(c);
        setPay(p);
      })
      .catch((failure: unknown) =>
        setError(
          `The rate confirmation could not be read: ${refusal(failure)}`,
        ),
      );
    return () => {
      live = false;
    };
  }, [businessId, tender.tender_id, accepted]);

  async function run(work: () => Promise<void>, failed: string) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (failure) {
      setError(`${failed}: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const answer = (event: React.FormEvent) => {
    event.preventDefault();
    void run(async () => {
      onChange(
        await answerTender(businessId, tender.tender_id, {
          schema_version: 1,
          kind,
          source,
          occurred_at: answeredAt,
        }),
      );
      setAnsweredAt(new Date().toISOString());
      notify("Answer recorded.");
    }, "The answer was not recorded");
  };
  const propose = (event: React.FormEvent) => {
    event.preventDefault();
    void run(async () => {
      setConfirmation(
        await proposeVersion(businessId, tender.tender_id, {
          schema_version: 1,
          expected_revision: confirmation?.versions.at(-1)?.revision ?? 0,
          basis,
          amount,
          terms,
          document_id: null,
          proposed_at: proposedAt,
        }),
      );
      setProposedAt(new Date().toISOString());
      setAmount("");
      setTerms("");
      notify("Version proposed.");
    }, "The version was not proposed");
  };
  const accrue = (event: React.FormEvent) => {
    event.preventDefault();
    void run(async () => {
      setPay(
        await accrueCarrierPay(businessId, tender.tender_id, {
          schema_version: 1,
          book_id: book,
          expense_account_id: expense,
          payable_account_id: payable,
          accrual_date: date,
          number,
          miles: miles || null,
        }),
      );
      notify("Carrier pay accrued.");
    }, "The carrier pay was not accrued");
  };

  const inForce = confirmation?.in_force;
  return (
    <section
      className="transport-panel"
      aria-labelledby={headingId}
      role="region"
    >
      <h3 id={headingId}>
        {`Tender to ${carrier} for ${trip.reference} leg ${tender.legs.join(", ")}`}
      </h3>
      <p>
        {`${STATE[tender.state]} · ${basisText(tender.basis, tender.amount, tender.currency)}`}
      </p>
      <Alert text={error} />
      {(offered || accepted) && (
        <form aria-label="Carrier answer" onSubmit={answer}>
          <label>
            Answer
            <select
              aria-label="Answer"
              value={kind}
              onChange={(e) => setKind(e.target.value as typeof kind)}
            >
              {offered && <option value="accepted">Accepted</option>}
              {offered && <option value="declined">Declined</option>}
              <option value="withdrawn">Withdrawn</option>
            </select>
          </label>
          <SourceSelect value={source} onChange={setSource} />
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              Record answer
            </button>
          </div>
        </form>
      )}
      {accepted && confirmation && (
        <>
          <p>
            {inForce
              ? `In force: version ${inForce.revision}, ${basisText(inForce.basis, inForce.amount, confirmation.currency)}`
              : "No version in force."}
          </p>
          <div
            className="mgmt-table-container"
            tabIndex={0}
            role="region"
            aria-label="Rate confirmation versions table"
          >
            <table
              className="mgmt-table"
              aria-label="Rate confirmation versions"
            >
              <thead>
                <tr>
                  <th scope="col">Version</th>
                  <th scope="col">Rate</th>
                  <th scope="col">State</th>
                </tr>
              </thead>
              <tbody>
                {confirmation.versions.map((v) => (
                  <tr key={v.revision}>
                    <td>{v.revision}</td>
                    <td>
                      {basisText(v.basis, v.amount, confirmation.currency)}
                    </td>
                    <td>{v.state}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {confirmation.versions
            .filter((v) => v.state === "proposed")
            .map((v) => (
              <VersionAnswer
                key={v.revision}
                businessId={businessId}
                tender={tender.tender_id}
                revision={v.revision}
                onDone={setConfirmation}
                notify={notify}
              />
            ))}
          <form aria-label="New version" onSubmit={propose}>
            <label>
              Basis
              <select
                aria-label="Basis"
                value={basis}
                onChange={(e) => setBasis(e.target.value as typeof basis)}
              >
                <option value="fixed">Fixed</option>
                <option value="per_mile">Per mile</option>
              </select>
            </label>
            <Field label="Amount" value={amount} onChange={setAmount} />
            <Field
              label="Terms"
              value={terms}
              onChange={setTerms}
              maxLength={2000}
            />
            <div className="mgmt-form-actions">
              <button type="submit" disabled={busy}>
                Propose version
              </button>
            </div>
          </form>
        </>
      )}
      {pay ? (
        <p>
          {`Carrier pay ${pay.accrual.total} ${pay.accrual.currency} for version ${pay.revision}, open ${pay.obligation?.available ?? pay.accrual.total}`}
        </p>
      ) : (
        accepted &&
        inForce && (
          <form aria-label="Accrue carrier pay" onSubmit={accrue}>
            <BookSelect books={books} value={book} onChange={setBook} />
            <AccountSelect
              label="Expense account"
              accounts={accounts}
              types={["expense"]}
              value={expense}
              onChange={setExpense}
            />
            <AccountSelect
              label="Payable account"
              accounts={accounts}
              types={["liability"]}
              value={payable}
              onChange={setPayable}
            />
            <Field
              label="Accrual date"
              type="date"
              value={date}
              onChange={setDate}
            />
            <Field
              label="Number"
              value={number}
              onChange={setNumber}
              maxLength={64}
            />
            <Field
              label="Miles"
              value={miles}
              onChange={setMiles}
              required={false}
            />
            <p className="muted">
              Miles are needed for a per-mile rate; the tendered legs must be
              closed.
            </p>
            <div className="mgmt-form-actions">
              <button type="submit" disabled={busy}>
                Accrue carrier pay
              </button>
            </div>
          </form>
        )
      )}
    </section>
  );
}

// N2: the board — a new tender for one leg to cover ---------------------------------------------

function TenderForm({
  businessId,
  trip,
  leg,
  carriers,
  onSaved,
  onDone,
  notify,
}: {
  businessId: string;
  trip: Trip;
  leg: number;
  carriers: CarrierRow[];
  onSaved: (t: Tender) => void;
  onDone: () => void;
  notify: Notify;
}) {
  // The record id and the offer time stay the same until the tender is saved.
  const [tender] = useState(() => crypto.randomUUID());
  const [offeredAt] = useState(() => new Date().toISOString());
  const [carrier, setCarrier] = useState("");
  const [basis, setBasis] = useState<"fixed" | "per_mile">("fixed");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [terms, setTerms] = useState("");
  const [expires, setExpires] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSaved(
        await saveTender(businessId, tender, {
          schema_version: 1,
          trip_id: trip.trip_id,
          legs: [leg],
          counterparty_id: carrier,
          currency,
          basis,
          amount,
          terms,
          offered_at: offeredAt,
          expires_at: new Date(expires).toISOString(),
        }),
      );
      notify("Tender sent.");
      onDone();
    } catch (failure) {
      setError(`The tender was not sent: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form aria-label="Tender" onSubmit={submit}>
      <h3>{`Tender ${trip.reference} leg ${leg}`}</h3>
      <Alert text={error} />
      <label>
        Carrier
        <select
          aria-label="Carrier"
          value={carrier}
          onChange={(e) => setCarrier(e.target.value)}
          required
        >
          <option value="">Choose a carrier</option>
          {carriers.map((c) => (
            <option
              key={c.party.counterparty_id}
              value={c.party.counterparty_id}
            >
              {c.eligibility?.eligible
                ? c.party.display_name
                : `${c.party.display_name} (not eligible)`}
            </option>
          ))}
        </select>
      </label>
      <label>
        Basis
        <select
          aria-label="Basis"
          value={basis}
          onChange={(e) => setBasis(e.target.value as typeof basis)}
        >
          <option value="fixed">Fixed</option>
          <option value="per_mile">Per mile</option>
        </select>
      </label>
      <Field label="Amount" value={amount} onChange={setAmount} />
      <Field
        label="Currency"
        value={currency}
        onChange={setCurrency}
        maxLength={3}
      />
      <Field label="Terms" value={terms} onChange={setTerms} maxLength={2000} />
      <Field
        label="Offer expires"
        type="datetime-local"
        value={expires}
        onChange={setExpires}
      />
      <div className="mgmt-form-actions">
        <button type="submit" disabled={busy}>
          Send tender
        </button>
        <button type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** N1-N5 on the screen: authority, carriers, the board of legs to cover and the tenders. */
export function Brokerage({
  businessId,
  trips,
  notify,
}: {
  businessId: string;
  trips: Trip[];
  notify: Notify;
}) {
  const carriersId = useId();
  const boardId = useId();
  const [carriers, setCarriers] = useState<CarrierRow[]>([]);
  const [tenders, setTenders] = useState<Record<string, Tender[]>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [covering, setCovering] = useState<{ trip: Trip; leg: number } | null>(
    null,
  );
  const [opened, setOpened] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const readCarriers = useCallback(async () => {
    // A carrier is an active counterparty with the supplier role.
    const parties = (await allActiveParties(businessId)).filter((p) =>
      p.roles.includes("supplier"),
    );
    const on = today();
    return Promise.all(
      parties.map(async (party) => ({
        party,
        profile: await fetchProfile(businessId, party.counterparty_id),
        eligibility: await fetchCarrierEligibility(
          businessId,
          party.counterparty_id,
          on,
        ),
      })),
    );
  }, [businessId]);
  useEffect(() => {
    readCarriers()
      .then(setCarriers)
      .catch((failure: unknown) =>
        setError(`The carriers could not be read: ${refusal(failure)}`),
      );
  }, [readCarriers]);
  useEffect(() => {
    let live = true;
    Promise.all(
      trips.map(
        async (t) =>
          [
            t.trip_id,
            (await fetchTenders(businessId, t.trip_id)).items,
          ] as const,
      ),
    )
      .then((pairs) => {
        if (live) setTenders(Object.fromEntries(pairs));
      })
      .catch((failure: unknown) =>
        setError(`The tenders could not be read: ${refusal(failure)}`),
      );
    return () => {
      live = false;
    };
  }, [businessId, trips]);

  const changed = useCallback((t: Tender) => {
    setTenders((all) => {
      const list = all[t.trip_id] ?? [];
      const next = list.some((x) => x.tender_id === t.tender_id)
        ? list.map((x) => (x.tender_id === t.tender_id ? t : x))
        : [...list, t];
      return { ...all, [t.trip_id]: next };
    });
  }, []);
  const carrierName = (id: string) =>
    carriers.find((c) => c.party.counterparty_id === id)?.party.display_name ??
    "Unknown carrier";

  const toCover = trips.flatMap((t) =>
    uncoveredLegs(t.legs, tenders[t.trip_id] ?? []).map((leg) => ({
      trip: t,
      leg,
    })),
  );
  const all = trips.flatMap((t) =>
    (tenders[t.trip_id] ?? []).map((x) => ({ trip: t, tender: x })),
  );
  const editingRow = carriers.find((c) => c.party.counterparty_id === editing);
  const openedRow = all.find((x) => x.tender.tender_id === opened);

  return (
    <>
      <AuthorityPanel businessId={businessId} notify={notify} />
      <Alert text={error} />
      <section className="transport-panel" aria-labelledby={carriersId}>
        <h2 id={carriersId}>Carriers</h2>
        {carriers.length === 0 ? (
          <p className="muted">No carriers among the active suppliers.</p>
        ) : (
          <div
            className="mgmt-table-container"
            tabIndex={0}
            role="region"
            aria-label="Carriers table"
          >
            <table className="mgmt-table" aria-label="Carriers">
              <thead>
                <tr>
                  <th scope="col">Carrier</th>
                  <th scope="col">Profile</th>
                  <th scope="col">Today</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {carriers.map((c) => {
                  const p = c.profile?.current;
                  return (
                    <tr key={c.party.counterparty_id}>
                      <td>{c.party.display_name}</td>
                      <td>
                        {p
                          ? `${p.jurisdiction} ${p.authority_number ?? "no authority"}, ${p.safety_rating} (version ${p.revision})`
                          : "No profile"}
                      </td>
                      <td>
                        {c.eligibility
                          ? eligibilityText(
                              c.eligibility,
                              "Eligible",
                              "Not eligible",
                            )
                          : "—"}
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => setEditing(c.party.counterparty_id)}
                        >
                          {`Profile for ${c.party.display_name}`}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {editingRow && (
          <ProfileForm
            key={`${editingRow.party.counterparty_id}-${editingRow.profile?.current?.revision ?? 0}`}
            businessId={businessId}
            row={editingRow}
            onSaved={() => {
              setEditing(null);
              readCarriers()
                .then(setCarriers)
                .catch((failure: unknown) =>
                  setError(
                    `The carriers could not be read: ${refusal(failure)}`,
                  ),
                );
            }}
            notify={notify}
          />
        )}
      </section>
      <section className="transport-panel" aria-labelledby={boardId}>
        <h2 id={boardId}>Loads to cover</h2>
        {toCover.length === 0 ? (
          <p className="muted">Every leg is covered.</p>
        ) : (
          <div
            className="mgmt-table-container"
            tabIndex={0}
            role="region"
            aria-label="Legs to cover table"
          >
            <table className="mgmt-table" aria-label="Legs to cover">
              <thead>
                <tr>
                  <th scope="col">Trip</th>
                  <th scope="col">Leg</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {toCover.map(({ trip, leg }) => (
                  <tr key={`${trip.trip_id}-${leg}`}>
                    <td>{trip.reference}</td>
                    <td>{leg}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => setCovering({ trip, leg })}
                      >
                        {`Tender ${trip.reference} leg ${leg}`}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {covering && (
          <TenderForm
            key={`${covering.trip.trip_id}-${covering.leg}`}
            businessId={businessId}
            trip={covering.trip}
            leg={covering.leg}
            carriers={carriers}
            onSaved={(t) => {
              changed(t);
              setOpened(t.tender_id);
            }}
            onDone={() => setCovering(null)}
            notify={notify}
          />
        )}
        {all.length > 0 && (
          <div
            className="mgmt-table-container"
            tabIndex={0}
            role="region"
            aria-label="Tenders table"
          >
            <table className="mgmt-table" aria-label="Tenders">
              <thead>
                <tr>
                  <th scope="col">Trip</th>
                  <th scope="col">Legs</th>
                  <th scope="col">Carrier</th>
                  <th scope="col">Rate</th>
                  <th scope="col">State</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {all.map(({ trip, tender }) => (
                  <tr key={tender.tender_id}>
                    <td>{trip.reference}</td>
                    <td>{tender.legs.join(", ")}</td>
                    <td>{carrierName(tender.counterparty_id)}</td>
                    <td>
                      {basisText(tender.basis, tender.amount, tender.currency)}
                    </td>
                    <td>{STATE[tender.state]}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => setOpened(tender.tender_id)}
                      >
                        {`Open tender ${trip.reference} leg ${tender.legs.join(", ")}`}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {openedRow && (
          <TenderPanel
            key={`${openedRow.tender.tender_id}-${openedRow.tender.state}`}
            businessId={businessId}
            tender={openedRow.tender}
            trip={openedRow.trip}
            carrier={carrierName(openedRow.tender.counterparty_id)}
            onChange={changed}
            notify={notify}
          />
        )}
      </section>
    </>
  );
}

/** N5: an order's margin, derived by the server and never stored. */
export function OrderMargin({
  businessId,
  order,
}: {
  businessId: string;
  order: Order;
}) {
  const headingId = useId();
  const [margin, setMargin] = useState<Margin | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    fetchMargin(businessId, order.order_id)
      .then((m) => {
        if (live) setMargin(m);
      })
      .catch((failure: unknown) =>
        setError(`The margin could not be read: ${refusal(failure)}`),
      );
    return () => {
      live = false;
    };
  }, [businessId, order.order_id]);
  const unit = margin?.currency ? ` ${margin.currency}` : "";
  return (
    <section
      className="transport-panel"
      aria-labelledby={headingId}
      role="region"
    >
      <h3 id={headingId}>{`Margin for ${order.reference}`}</h3>
      <Alert text={error} />
      {margin && (
        <dl className="transport-facts">
          <dt>Revenue</dt>
          <dd>
            {margin.revenue ? `${margin.revenue}${unit}` : "Not invoiced"}
          </dd>
          <dt>Carrier cost</dt>
          <dd>{`${margin.carrier_cost}${unit}`}</dd>
          <dt>Margin</dt>
          <dd>{margin.margin ? `${margin.margin}${unit}` : "Not known yet"}</dd>
          <dt>Shared tenders</dt>
          <dd>
            {margin.shared.length === 0
              ? "None"
              : margin.shared.map((s) => s.amount).join(", ")}
          </dd>
        </dl>
      )}
    </section>
  );
}
