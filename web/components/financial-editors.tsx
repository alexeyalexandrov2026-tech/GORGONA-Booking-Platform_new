"use client";
import { useState, type ReactNode } from "react";
import { z } from "zod";
import type { LedgerAccount } from "../lib/ledger-contracts";
import { minorUnits } from "../lib/ledger-contracts";
import type { CounterpartyPage } from "../lib/counterparty-contracts";
import {
  financialCommandSchema,
  newCreditDraftLine,
  type FinancialCommand,
  type Invoice,
  type Credit,
  type Obligation,
  type Settlement,
  type Payment,
} from "../lib/financial-contracts";

export type SendFinancialCommand = (command: FinancialCommand) => Promise<void>;
type Common = {
  book: string;
  accounts: LedgerAccount[];
  disabled: boolean;
  send: SendFinancialCommand;
};
const today = () => new Date().toISOString().slice(0, 10);
const key = () => crypto.randomUUID();
export const money = (units: bigint, places: number) => {
  const digits = units.toString().padStart(places + 1, "0");
  return places
    ? `${digits.slice(0, -places)}.${digits.slice(-places)}`
    : digits;
};
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="financial-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function AccountSelect({
  value,
  onChange,
  accounts,
  label,
  required = true,
}: {
  value: string;
  onChange: (value: string) => void;
  accounts: LedgerAccount[];
  label: string;
  required?: boolean;
}) {
  return (
    <Field label={label}>
      <select
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Choose account</option>
        {accounts
          .filter((x) => !x.archived || x.account_id === value)
          .map((x) => (
            <option
              key={x.account_id}
              value={x.account_id}
              disabled={x.archived}
            >
              {x.code} · {x.name} ({x.type}){x.archived ? " · archived" : ""}
            </option>
          ))}
      </select>
    </Field>
  );
}
export function CommandForm({
  title,
  disabled,
  children,
  submit,
  label,
}: {
  title: string;
  disabled: boolean;
  children: ReactNode;
  submit: () => Promise<void>;
  label: string;
}) {
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      aria-label={title}
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        void submit().catch((e) =>
          setError(
            e instanceof z.ZodError
              ? "Check the required fields, exact amounts and selected saved versions."
              : e instanceof Error
                ? e.message
                : "Unable to save.",
          ),
        );
      }}
    >
      <fieldset disabled={disabled}>
        <legend>{title}</legend>
        {children}
        <button type="submit">{label}</button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
export function InvoiceEditor({
  book,
  accounts,
  disabled,
  send,
  parties,
  currencies,
  kind,
  document,
}: {
  kind: "invoice" | "manual_accrual";
  document: Invoice | null;
  parties: CounterpartyPage["items"];
  currencies: string[];
} & Common) {
  const [id] = useState(() => document?.document_id ?? crypto.randomUUID());
  const [direction, setDirection] = useState<"receivable" | "payable">(
    document?.direction ?? "receivable",
  );
  const [party, setParty] = useState(
    document
      ? `${document.counterparty_id}:${document.counterparty_revision}`
      : "",
  );
  const [currency, setCurrency] = useState(document?.currency ?? "");
  const [date, setDate] = useState(document?.invoice_date ?? today());
  const [due, setDue] = useState(document?.due_date ?? "");
  const [control, setControl] = useState(document?.control_account_id ?? "");
  const [title, setTitle] = useState(document?.title ?? "");
  const [number, setNumber] = useState(document?.number ?? "");
  const [lines, setLines] = useState(
    document?.lines ?? [
      {
        line_id: crypto.randomUUID(),
        counter_account_id: "",
        description: "",
        amount: "",
      },
    ],
  );
  const change = (i: number, patch: Partial<(typeof lines)[number]>) =>
    setLines(lines.map((x, n) => (n === i ? { ...x, ...patch } : x)));
  const selectedMissing =
    party &&
    !parties.some((x) => `${x.counterparty_id}:${x.revision}` === party);
  return (
    <CommandForm
      title={
        document
          ? `Edit ${kind === "invoice" ? "invoice" : "manual accrual"} draft revision ${document.revision}`
          : `New ${kind === "invoice" ? "invoice" : "manual accrual"}`
      }
      disabled={disabled}
      label="Save draft"
      submit={async () => {
        const [counterparty_id, counterparty_revision] = party.split(":");
        await send(
          financialCommandSchema.parse({
            book,
            subject: id,
            key: key(),
            operation: kind === "invoice" ? "invoice_draft" : "accrual_draft",
            body: {
              schema_version: 1,
              expected_revision: document?.revision ?? 0,
              direction,
              counterparty_id,
              counterparty_revision: Number(counterparty_revision),
              currency,
              invoice_date: date,
              due_date: due || null,
              control_account_id: control,
              title,
              number,
              lines,
            },
          }),
        );
      }}
    >
      <p>
        A draft records no payment or recognized revenue. Issuing creates one
        obligation and the chosen balanced journal.
      </p>
      <div className="financial-grid">
        <Field label="Direction">
          <select
            value={direction}
            onChange={(e) =>
              setDirection(e.target.value as "receivable" | "payable")
            }
          >
            <option value="receivable">
              Receivable · customer owes this business
            </option>
            <option value="payable">
              Payable · business owes counterparty
            </option>
          </select>
        </Field>
        <Field label="Counterparty version">
          <select
            required
            value={party}
            onChange={(e) => setParty(e.target.value)}
          >
            <option value="">Choose saved counterparty version</option>
            {selectedMissing && (
              <option value={party}>Previously selected version {party}</option>
            )}
            {parties
              .filter((x) => x.state === "active")
              .map((x) => (
                <option
                  key={x.counterparty_id}
                  value={`${x.counterparty_id}:${x.revision}`}
                >
                  {x.display_name} · revision {x.revision}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Currency">
          <select
            required
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            <option value="">Choose currency</option>
            {currencies.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </Field>
        <Field label="Document date">
          <input
            type="date"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </Field>
        <Field label="Due date (optional)">
          <input
            type="date"
            min={date}
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </Field>
        <Field label="Title">
          <input
            required
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Document number">
          <input
            required
            maxLength={64}
            value={number}
            onChange={(e) => setNumber(e.target.value)}
          />
        </Field>
        <AccountSelect
          label="Control account"
          value={control}
          onChange={setControl}
          accounts={accounts}
        />
      </div>
      {lines.map((line, i) => (
        <div className="financial-line" key={line.line_id}>
          <h3>Line {i + 1}</h3>
          <Field label={`Line ${i + 1} description`}>
            <input
              required
              maxLength={500}
              value={line.description}
              onChange={(e) => change(i, { description: e.target.value })}
            />
          </Field>
          <AccountSelect
            label={`Line ${i + 1} counter account`}
            value={line.counter_account_id}
            onChange={(v) => change(i, { counter_account_id: v })}
            accounts={accounts}
          />
          <Field label={`Line ${i + 1} amount`}>
            <input
              required
              inputMode="decimal"
              pattern="(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?"
              value={line.amount}
              onChange={(e) => change(i, { amount: e.target.value })}
            />
          </Field>
          <button
            type="button"
            className="secondary"
            disabled={lines.length === 1}
            onClick={() => setLines(lines.filter((_, n) => n !== i))}
          >
            Remove line {i + 1}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="secondary"
        disabled={lines.length >= 199}
        onClick={() =>
          setLines([
            ...lines,
            {
              line_id: crypto.randomUUID(),
              counter_account_id: "",
              description: "",
              amount: "",
            },
          ])
        }
      >
        Add invoice line
      </button>
    </CommandForm>
  );
}
export function DocumentIssue({
  document,
  book,
  accounts,
  disabled,
  send,
  obligation,
}: { document: Invoice | Credit; obligation?: Obligation | null } & Common) {
  const [date, setDate] = useState(today()),
    [attest, setAttest] = useState(false),
    [refundControl, setRefundControl] = useState("");
  const isCredit = "credited_obligation_id" in document;
  let refund = 0n;
  if (isCredit && obligation) {
    const total = minorUnits(document.total, document.minor_units) ?? 0n,
      unpaid =
        (minorUnits(obligation.principal, obligation.minor_units) ?? 0n) -
        (minorUnits(obligation.paid, obligation.minor_units) ?? 0n) -
        (minorUnits(obligation.credited, obligation.minor_units) ?? 0n);
    refund = total > unpaid ? total - unpaid : 0n;
  }
  return (
    <CommandForm
      title="Issue saved draft"
      disabled={disabled}
      label="Issue document"
      submit={async () => {
        if (!attest)
          throw new Error(
            "Confirm the selected account treatment before issuing.",
          );
        await send(
          financialCommandSchema.parse({
            book,
            subject: document.document_id,
            key: key(),
            operation: isCredit
              ? "credit_issue"
              : document.kind === "invoice"
                ? "invoice_issue"
                : "accrual_issue",
            body: {
              schema_version: 1,
              expected_revision: document.revision,
              entry_date: date,
              attestation: "confirmed_account_treatment",
              ...(isCredit
                ? {
                    refund_control_account_id:
                      refund > 0n ? refundControl : null,
                  }
                : {}),
            },
          }),
        );
      }}
    >
      <p>
        Issue exactly revision {document.revision}: {document.number} ·{" "}
        {document.total} {document.currency}. Revenue/expense follows the
        selected accounts; issuing is not a received payment.
      </p>
      <Field label="Posting date">
        <input
          required
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </Field>
      {isCredit && (
        <>
          <p>
            Current split preview: unpaid credit{" "}
            {money(
              (minorUnits(document.total, document.minor_units) ?? 0n) - refund,
              document.minor_units,
            )}
            , separate refund obligation {money(refund, document.minor_units)}{" "}
            {document.currency}. The server recalculates this atomically.
          </p>
          {refund > 0n && (
            <AccountSelect
              label="Refund control account"
              value={refundControl}
              onChange={setRefundControl}
              accounts={accounts}
            />
          )}
        </>
      )}
      <label className="financial-check">
        <input
          type="checkbox"
          required
          checked={attest}
          onChange={(e) => setAttest(e.target.checked)}
        />
        I confirm the account treatment and recognition policy for this saved
        version.
      </label>
    </CommandForm>
  );
}
export function CreditEditor({
  book,
  accounts,
  disabled,
  send,
  original,
  obligation,
  credit,
  partyRevision,
}: {
  original: Invoice;
  obligation: Obligation;
  credit: Credit | null;
  partyRevision: number;
} & Common) {
  const [id] = useState(() => credit?.document_id ?? crypto.randomUUID());
  const [date, setDate] = useState(credit?.credit_date ?? today()),
    [due, setDue] = useState(credit?.due_date ?? ""),
    [title, setTitle] = useState(credit?.title ?? ""),
    [number, setNumber] = useState(credit?.number ?? "");
  const [selectedPartyRevision, setSelectedPartyRevision] = useState(
    credit ? String(credit.counterparty_revision) : "",
  );
  const first = original.lines[0]!;
  const [lines, setLines] = useState(
    credit?.lines ?? [newCreditDraftLine(first)],
  );
  const change = (i: number, patch: Partial<(typeof lines)[number]>) =>
    setLines(lines.map((x, n) => (n === i ? { ...x, ...patch } : x)));
  return (
    <CommandForm
      title={
        credit
          ? `Edit credit draft revision ${credit.revision}`
          : "New credit note"
      }
      disabled={disabled}
      label="Save credit draft"
      submit={async () => {
        for (const line of lines) {
          const credited = original.lines.find(
            (x) => x.line_id === line.credited_line_id,
          );
          if (
            credited &&
            line.counter_account_id !== credited.counter_account_id &&
            !line.reason
          )
            throw new Error("A changed counter account requires a reason.");
        }
        await send(
          financialCommandSchema.parse({
            book,
            subject: id,
            key: key(),
            operation: "credit_draft",
            body: {
              schema_version: 1,
              expected_revision: credit?.revision ?? 0,
              credited_obligation_id: obligation.obligation_id,
              counterparty_revision: Number(selectedPartyRevision),
              credit_date: date,
              due_date: due || null,
              title,
              number,
              lines,
            },
          }),
        );
      }}
    >
      <p>
        Credits {original.number} revision {obligation.source_revision}, in{" "}
        {original.currency}; counterparty revision {partyRevision}. Active
        reserves require explicit resolution. A credit may create a refund
        obligation; it does not move cash.
      </p>
      <div className="financial-grid">
        <Field label="Credit counterparty version">
          <select
            required
            value={selectedPartyRevision}
            onChange={(e) => setSelectedPartyRevision(e.target.value)}
          >
            <option value="">Choose saved counterparty version</option>
            <option value={partyRevision}>
              Current saved revision {partyRevision}
            </option>
            {credit && credit.counterparty_revision !== partyRevision && (
              <option value={credit.counterparty_revision}>
                Selected draft revision {credit.counterparty_revision}
              </option>
            )}
          </select>
        </Field>
        <Field label="Credit date">
          <input
            required
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </Field>
        <Field label="Credit due date (optional)">
          <input
            type="date"
            min={date}
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </Field>
        <Field label="Credit title">
          <input
            required
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Credit number">
          <input
            required
            maxLength={64}
            value={number}
            onChange={(e) => setNumber(e.target.value)}
          />
        </Field>
      </div>
      {lines.map((line, i) => {
        const old = original.lines.find(
          (x) => x.line_id === line.credited_line_id,
        );
        return (
          <div className="financial-line" key={line.line_id}>
            <h3>Credit line {i + 1}</h3>
            <Field label={`Credit line ${i + 1} original line`}>
              <select
                value={line.credited_line_id}
                onChange={(e) => {
                  const selected = original.lines.find(
                    (x) => x.line_id === e.target.value,
                  )!;
                  change(i, {
                    ...newCreditDraftLine(selected),
                    line_id: line.line_id,
                  });
                }}
              >
                {original.lines.map((x, n) => (
                  <option key={x.line_id} value={x.line_id}>
                    {n + 1} · {x.description} · {x.amount}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={`Credit line ${i + 1} description`}>
              <input
                required
                maxLength={500}
                value={line.description}
                onChange={(e) => change(i, { description: e.target.value })}
              />
            </Field>
            <AccountSelect
              label={`Credit line ${i + 1} counter account`}
              value={line.counter_account_id}
              onChange={(v) => change(i, { counter_account_id: v })}
              accounts={accounts}
            />
            <p>
              Historical invoice counter account:{" "}
              {accounts.find((x) => x.account_id === old?.counter_account_id)
                ?.name ?? old?.counter_account_id}
              . Choose the current account explicitly; the original invoice is
              context for your decision.
            </p>
            <Field label={`Credit line ${i + 1} amount`}>
              <input
                required
                inputMode="decimal"
                pattern="(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?"
                value={line.amount}
                onChange={(e) => change(i, { amount: e.target.value })}
              />
            </Field>
            <Field label={`Credit line ${i + 1} account-change reason`}>
              <input
                required={
                  line.counter_account_id !== old?.counter_account_id ||
                  Boolean(line.reference_entry_id)
                }
                maxLength={500}
                value={line.reason ?? ""}
                onChange={(e) => change(i, { reason: e.target.value || null })}
              />
            </Field>
            <Field
              label={`Credit line ${i + 1} supporting journal id (optional)`}
            >
              <input
                value={line.reference_entry_id ?? ""}
                onChange={(e) =>
                  change(i, { reference_entry_id: e.target.value || null })
                }
              />
            </Field>
            <button
              type="button"
              className="secondary"
              disabled={lines.length === 1}
              onClick={() => setLines(lines.filter((_, n) => n !== i))}
            >
              Remove credit line {i + 1}
            </button>
          </div>
        );
      })}
      <button
        type="button"
        className="secondary"
        disabled={lines.length >= 198}
        onClick={() => setLines([...lines, newCreditDraftLine(first)])}
      >
        Add credit line
      </button>
    </CommandForm>
  );
}
export function CreditVoid({
  credit,
  disabled,
  send,
  book,
}: {
  credit: Credit;
  book: string;
  disabled: boolean;
  send: SendFinancialCommand;
}) {
  const [date, setDate] = useState(today()),
    [reason, setReason] = useState(""),
    [evidence, setEvidence] = useState(""),
    [attest, setAttest] = useState(false);
  return (
    <CommandForm
      title="Void erroneous credit"
      disabled={disabled}
      label="Void credit"
      submit={async () => {
        if (!attest)
          throw new Error("Attest that the credit was issued in error.");
        await send(
          financialCommandSchema.parse({
            book,
            subject: credit.document_id,
            key: key(),
            operation: "credit_void",
            body: {
              schema_version: 1,
              expected_revision: credit.revision,
              entry_date: date,
              attestation: "attested_erroneous_credit",
              reason,
              evidence_source: evidence,
            },
          }),
        );
      }}
    >
      <p>
        Records an exact historical mirror and cancels only an untouched refund
        claim. A paid, reserved or sent refund requires financial
        reconciliation.
      </p>
      <Field label="Credit void posting date">
        <input
          required
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </Field>
      <Field label="Credit void reason">
        <input
          required
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      <Field label="Credit void evidence source">
        <input
          required
          maxLength={200}
          value={evidence}
          onChange={(e) => setEvidence(e.target.value)}
        />
      </Field>
      <label className="financial-check">
        <input
          required
          type="checkbox"
          checked={attest}
          onChange={(e) => setAttest(e.target.checked)}
        />
        I attest this credit was issued in error.
      </label>
    </CommandForm>
  );
}
export function SettlementPrepare({
  obligations,
  selected,
  book,
  disabled,
  send,
}: {
  obligations: Obligation[];
  selected: Obligation;
  book: string;
  disabled: boolean;
  send: SendFinancialCommand;
}) {
  const candidates = obligations.filter(
    (x) =>
      x.direction === selected.direction &&
      x.currency === selected.currency &&
      x.counterparty_id === selected.counterparty_id,
  );
  const [amounts, setAmounts] = useState<Record<string, string>>({
    [selected.obligation_id]: "",
  });
  return (
    <CommandForm
      title="Prepare settlement"
      disabled={disabled}
      label="Prepare settlement"
      submit={async () => {
        const allocations = Object.entries(amounts)
          .filter(([, amount]) => amount !== "")
          .map(([obligation_id, amount]) => ({ obligation_id, amount }));
        for (const allocation of allocations) {
          const obligation = candidates.find(
            (x) => x.obligation_id === allocation.obligation_id,
          );
          if (
            !obligation ||
            (minorUnits(allocation.amount, obligation.minor_units) ?? -1n) <=
              0n ||
            (minorUnits(allocation.amount, obligation.minor_units) ?? 0n) >
              (minorUnits(obligation.available, obligation.minor_units) ?? 0n)
          )
            throw new Error(
              "Each amount must fit the current available obligation balance.",
            );
        }
        await send(
          financialCommandSchema.parse({
            book,
            subject: crypto.randomUUID(),
            key: key(),
            operation: "settlement_prepare",
            body: {
              schema_version: 1,
              expected_sequence: 0,
              direction: selected.direction,
              counterparty_id: selected.counterparty_id,
              currency: selected.currency,
              allocations,
            },
          }),
        );
      }}
    >
      <p>
        Plans immutable allocations for one party, direction and currency.
        Preparation and approval move no money.
      </p>
      {candidates.map((x) => (
        <Field
          key={x.obligation_id}
          label={`Allocation ${x.obligation_id} · available ${x.available} ${x.currency}`}
        >
          <input
            inputMode="decimal"
            pattern="(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?"
            value={amounts[x.obligation_id] ?? ""}
            onChange={(e) =>
              setAmounts({ ...amounts, [x.obligation_id]: e.target.value })
            }
          />
        </Field>
      ))}
    </CommandForm>
  );
}
export function SettlementActions({
  settlement,
  book,
  disabled,
  releaseDisabled,
  send,
}: {
  settlement: Settlement;
  book: string;
  disabled: boolean;
  releaseDisabled: boolean;
  send: SendFinancialCommand;
}) {
  const [reason, setReason] = useState(""),
    [evidence, setEvidence] = useState(""),
    [attest, setAttest] = useState(false);
  const action = async (
    operation: "settlement_approve" | "settlement_reserve" | "settlement_sent",
  ) =>
    send({
      book,
      subject: settlement.settlement_id,
      key: key(),
      operation,
      body: { schema_version: 1, expected_sequence: settlement.sequence },
    });
  return (
    <section aria-label="Settlement actions">
      <p>
        Approval, reserve and the “sent” marker record workflow facts. This
        platform sends no funds.
      </p>
      <div className="financial-actions">
        {settlement.status === "prepared" && (
          <button
            disabled={disabled}
            onClick={() => void action("settlement_approve")}
          >
            Approve settlement
          </button>
        )}
        {settlement.status === "approved" && (
          <button
            disabled={disabled}
            onClick={() => void action("settlement_reserve")}
          >
            Reserve settlement
          </button>
        )}
        {settlement.status === "reserved" && (
          <button
            disabled={disabled}
            onClick={() => void action("settlement_sent")}
          >
            Mark externally sent
          </button>
        )}
      </div>
      {["reserved", "sent", "partially_confirmed"].includes(
        settlement.status,
      ) && (
        <CommandForm
          title="Release remaining reserve"
          disabled={releaseDisabled}
          label="Release reserve"
          submit={async () => {
            if (settlement.outcome_unresolved && !attest)
              throw new Error(
                "A sent/unknown outcome requires an explicit no-payment attestation.",
              );
            await send(
              financialCommandSchema.parse({
                book,
                subject: settlement.settlement_id,
                key: key(),
                operation: "settlement_release",
                body: {
                  schema_version: 1,
                  expected_sequence: settlement.sequence,
                  resolution: attest ? "attested_no_payment" : null,
                  reason: attest ? reason : null,
                  evidence_source: attest ? evidence : null,
                },
              }),
            );
          }}
        >
          <p>
            {settlement.outcome_unresolved
              ? "External outcome is unresolved. Timeouts and disabling finance cannot release it."
              : "Releases only the unconfirmed remainder; existing payment facts remain."}
          </p>
          <label className="financial-check">
            <input
              type="checkbox"
              checked={attest}
              onChange={(e) => setAttest(e.target.checked)}
            />
            I verified that no payment exists for the remaining reserve.
          </label>
          <Field label="Release reason">
            <input
              required={attest}
              maxLength={500}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          <Field label="Release evidence source">
            <input
              required={attest}
              maxLength={200}
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
            />
          </Field>
        </CommandForm>
      )}
      {["prepared", "approved"].includes(settlement.status) && (
        <CommandForm
          title="Cancel settlement"
          disabled={releaseDisabled}
          label="Cancel settlement"
          submit={async () =>
            send({
              book,
              subject: settlement.settlement_id,
              key: key(),
              operation: "settlement_cancel",
              body: {
                schema_version: 1,
                expected_sequence: settlement.sequence,
                reason: reason || null,
              },
            })
          }
        >
          <Field label="Cancellation reason (optional)">
            <input
              maxLength={500}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        </CommandForm>
      )}
    </section>
  );
}
export function PaymentEditor({
  settlement,
  payment,
  mode,
  book,
  accounts,
  disabled,
  send,
}: {
  settlement: Settlement;
  payment: Payment | null;
  mode: "confirm" | "correct" | "void";
} & Common) {
  const last = payment?.revisions.at(-1);
  const [amount, setAmount] = useState(
      mode === "correct" ? (payment?.effective_amount ?? "") : "",
    ),
    [actual, setActual] = useState(
      last?.actual_external_date ?? payment?.actual_external_date ?? today(),
    ),
    [date, setDate] = useState(today()),
    [cash, setCash] = useState(
      last?.cash_account_id ?? payment?.cash_account_id ?? "",
    ),
    [alias, setAlias] = useState(""),
    [reference, setReference] = useState(""),
    [reason, setReason] = useState(""),
    [evidence, setEvidence] = useState(""),
    [attest, setAttest] = useState(false);
  const [allocated, setAllocated] = useState<Record<string, string>>(() =>
    mode === "correct"
      ? Object.fromEntries(
          payment?.effective_allocations.map((x) => [
            x.obligation_id,
            x.amount,
          ]) ?? [],
        )
      : {},
  );
  return (
    <CommandForm
      title={
        mode === "confirm"
          ? "Record external payment"
          : mode === "correct"
            ? "Correct erroneous confirmation"
            : "Void erroneous confirmation"
      }
      disabled={disabled}
      label={
        mode === "confirm"
          ? "Confirm external payment"
          : mode === "correct"
            ? "Record payment correction"
            : "Void payment confirmation"
      }
      submit={async () => {
        if (!attest)
          throw new Error("An explicit human attestation is required.");
        const allocations = Object.entries(allocated)
          .filter(([, value]) => value !== "")
          .map(([obligation_id, amount]) => ({ obligation_id, amount }));
        if (
          mode !== "void" &&
          (sumAllocation(allocations, settlement.minor_units) !==
            minorUnits(amount, settlement.minor_units) ||
            (minorUnits(amount, settlement.minor_units) ?? 0n) <= 0n)
        )
          throw new Error(
            "Positive allocated amounts must equal the payment exactly.",
          );
        const body = {
          schema_version: 1,
          expected_sequence: settlement.sequence,
          entry_date: date,
          ...(mode === "confirm"
            ? {
                attestation: "manual_attestation",
                amount,
                actual_external_date: actual,
                cash_account_id: cash,
                source_account_alias: alias,
                external_reference: reference,
                allocations,
              }
            : mode === "correct"
              ? {
                  attestation: "attested_erroneous_confirmation",
                  reason,
                  evidence_source: evidence,
                  amount,
                  actual_external_date: actual,
                  cash_account_id: cash,
                  allocations,
                }
              : {
                  attestation: "attested_erroneous_confirmation",
                  reason,
                  evidence_source: evidence,
                }),
        };
        await send(
          financialCommandSchema.parse({
            book,
            subject: settlement.settlement_id,
            key: key(),
            payment: payment?.payment_id ?? crypto.randomUUID(),
            operation:
              mode === "confirm"
                ? "settlement_confirm"
                : mode === "correct"
                  ? "settlement_payment_correct"
                  : "settlement_payment_void",
            body,
          }),
        );
      }}
    >
      <p>
        {mode === "confirm"
          ? "A human attests an external money fact. This is not a provider-verified payment and does not initiate a transfer."
          : "Corrects an erroneous attestation of the same external fact. Identity remains bound forever; this is not a physical refund."}
      </p>
      {payment && (
        <p>
          Permanent identity: {payment.source_account_alias} ·{" "}
          {payment.external_reference}; payment revision {payment.revision},
          settlement sequence {settlement.sequence}.
        </p>
      )}
      <div className="financial-grid">
        <Field label="Payment posting date">
          <input
            required
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </Field>
        {mode !== "void" && (
          <>
            <Field label="Actual external payment date">
              <input
                required
                type="date"
                value={actual}
                onChange={(e) => setActual(e.target.value)}
              />
            </Field>
            <Field label="Payment amount">
              <input
                required
                inputMode="decimal"
                pattern="(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </Field>
            <AccountSelect
              label="Cash or bank account"
              accounts={accounts}
              value={cash}
              onChange={setCash}
            />
          </>
        )}
        {mode === "confirm" && (
          <>
            <Field label="Source account alias">
              <input
                required
                maxLength={100}
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
              />
            </Field>
            <Field label="External receipt or transaction reference">
              <input
                required
                maxLength={200}
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </Field>
          </>
        )}
        {mode !== "confirm" && (
          <>
            <Field label="Payment correction reason">
              <input
                required
                maxLength={500}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </Field>
            <Field label="Payment correction evidence source">
              <input
                required
                maxLength={200}
                value={evidence}
                onChange={(e) => setEvidence(e.target.value)}
              />
            </Field>
          </>
        )}
      </div>
      {mode !== "void" &&
        settlement.allocations.map((x) => (
          <Field
            key={x.obligation_id}
            label={`Payment allocation ${x.obligation_id} · reserve ${x.reserved}`}
          >
            <input
              inputMode="decimal"
              pattern="(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?"
              value={allocated[x.obligation_id] ?? ""}
              onChange={(e) =>
                setAllocated({
                  ...allocated,
                  [x.obligation_id]: e.target.value,
                })
              }
            />
          </Field>
        ))}
      <label className="financial-check">
        <input
          type="checkbox"
          required
          checked={attest}
          onChange={(e) => setAttest(e.target.checked)}
        />
        {mode === "confirm"
          ? "I manually attest this external payment and its allocations."
          : "I attest the earlier confirmation was erroneous, based on the stated evidence."}
      </label>
    </CommandForm>
  );
}
function sumAllocation(lines: { amount: string }[], scale: number) {
  return lines.reduce<bigint | null>((total, x) => {
    const amount = minorUnits(x.amount, scale);
    return total === null || amount === null || amount <= 0n
      ? null
      : total + amount;
  }, 0n);
}
