"use client";
import { useEffect, useState } from "react";
import { ManagementApiError } from "../lib/management-api";
import type { LedgerAccount } from "../lib/ledger-contracts";
import { minorUnits } from "../lib/ledger-contracts";
import { businessDateTime } from "../lib/business-time";
import * as api from "../lib/financial-api";
import {
  financialCommandSchema,
  type ProviderAttentionItem,
  type ProviderConnection,
  type ProviderOperation,
  type ProviderOperationDetail,
  type Settlement,
} from "../lib/financial-contracts";
import {
  AccountSelect,
  CommandForm,
  Field,
  type SendFinancialCommand,
} from "./financial-editors";

type State = ProviderOperation["state"];
const STATES: readonly (readonly [State, string])[] = [
  ["observed", "Observed by the provider, not applied yet"],
  ["pending", "Provider events still being decided"],
  ["not_final", "No final provider success yet"],
  ["needs_review", "Provider events disagree; manual review needed"],
  ["revoked", "Connection or verification revoked; cannot move money"],
  ["needs_link", "Already recorded by hand; link it to the manual payment"],
  ["applied", "Applied to a settlement"],
  [
    "applied_with_conflict",
    "Applied; later provider data disagrees — manual review needed",
  ],
  ["linked", "Linked to the manual payment that recorded it"],
];
const LINK_MISMATCH: Record<string, string> = {
  amount: "Its amount differs from the provider's amount.",
  currency: "Its currency differs from the provider's currency.",
  direction:
    "A provider payment links to a received payment, a refund to a paid one.",
  date: "Its date is more than 3 days from the provider's date.",
  voided: "It was voided.",
  payment_linked: "It is already linked to another provider operation.",
  not_manual: "It is not a manually recorded payment.",
  reference: "Its reference does not name this provider ID.",
  facts: "The provider facts changed while linking; reload and compare again.",
};
const stateText = (state: State) =>
  STATES.find(([value]) => value === state)?.[1] ?? state;
const kindText = (x: ProviderOperation) =>
  x.kind === "payment"
    ? `Payment ${x.provider_object_id}`
    : `Refund ${x.provider_object_id} of ${x.parent_object_id}`;

const NOT_READY: Record<string, string> = {
  revoked:
    "The provider connection or its verification was revoked; this operation cannot move money.",
  not_admitted:
    "The provider connection is not admitted for this operation; the owner records test access first.",
  pending:
    "Some provider events of this operation are still being decided. Try again later.",
  needs_review:
    "Provider events of this operation disagree; it needs manual review and cannot move money.",
  delivery_conflict:
    "A later delivery of a provider event differs from the original; manual review is needed.",
  not_final: "The provider has not reported a final success yet.",
};
const MISMATCH: Record<string, string> = {
  currency: "The provider currency differs from the settlement currency.",
  direction:
    "A provider payment applies to a receivable settlement and a refund to a payable one.",
  obligation_kind:
    "A provider refund applies only to the refund obligation of a credit note.",
  refund_parent:
    "The refund's original provider payment is not applied in this book.",
  counterparty:
    "The refund's original provider payment belongs to another counterparty.",
  refund_cap: "Applied refunds would exceed the original provider payment.",
};
/** Plain words for every provider refusal; the code stays visible for support. */
export function providerRefusal(e: ManagementApiError): string | null {
  const reason =
    typeof e.details?.reason === "string" ? e.details.reason : undefined;
  const text =
    e.code === "PROVIDER_OPERATION_NOT_READY"
      ? (NOT_READY[reason ?? ""] ?? "This operation cannot move money yet.")
      : e.code === "PROVIDER_OPERATION_APPLIED"
        ? "This provider operation already moved money. It is applied at most once."
        : e.code === "PROVIDER_PAYMENT_MISMATCH"
          ? (MISMATCH[reason ?? ""] ??
            "The provider facts do not match this settlement.")
          : e.code === "PROVIDER_CLEARING_ACCOUNT_REQUIRED"
            ? "Register the connection's clearing account under Provider operations first."
            : e.code === "PROVIDER_CLEARING_ACCOUNT_REGISTERED"
              ? "This connection already has its clearing account. It cannot be changed."
              : e.code === "PROVIDER_PAYMENT_LINK_REQUIRED"
                ? "A manual payment in this book already names this provider ID. Nothing was applied; link the operation to that payment from its Details."
                : e.code === "PROVIDER_ATTENTION_ACKNOWLEDGED"
                  ? "This event was already acknowledged with another note."
                  : e.code === "PROVIDER_ATTENTION_NOT_NEEDED"
                    ? "This event needs no acknowledgement: it belongs to an operation or is not decided yet."
                    : e.code === "PROVIDER_OPERATION_LINKED"
                      ? "This provider operation is linked to a manual payment and never moves money itself."
                      : e.code === "PROVIDER_LINK_MISMATCH"
                        ? `This manual payment does not match the provider operation. ${LINK_MISMATCH[reason ?? ""] ?? ""}`.trim()
                        : null;
  return text && `${text} (${e.code})`;
}
const failure = (e: unknown) =>
  e instanceof ManagementApiError
    ? (providerRefusal(e) ?? `${e.message} (${e.code})`)
    : "Unable to verify the provider response. Refresh to see the actual state.";

const REASONS: Record<string, string> = {
  success: "final success",
  not_final: "not final yet",
  conflicting_facts: "its facts disagree with earlier events of this operation",
  unkeyed_operation: "no payment to attach it to",
  refund_without_payment: "a refund without its payment",
};
const FIELDS: Record<string, string> = {
  "resource.amount_minor": "Amount (minor units)",
  "resource.amount_received_minor": "Amount received (minor units)",
  "resource.amount_refunded_minor": "Amount refunded (minor units)",
  "resource.currency": "Currency",
  "resource.status": "Status",
  event_type: "Event type",
  created: "Created",
};
const fieldText = (field: string) => FIELDS[field] ?? field;

/** Follow the cursor to the end: connections are few and all of them are shown. */
async function allConnections(business: string, book: string) {
  const items: ProviderConnection[] = [];
  let after: string | undefined;
  do {
    const page = await api.fetchProviderConnections(business, book, after);
    items.push(...page.items);
    after = page.next_cursor ?? undefined;
  } while (after);
  return items;
}

export function ProviderOperations({
  businessId,
  bookId,
  accounts,
  disabled,
  refresh,
}: {
  businessId: string;
  bookId: string;
  accounts: LedgerAccount[];
  disabled: boolean;
  refresh: number;
}) {
  const [filter, setFilter] = useState<State | "">(""),
    [page, setPage] = useState<{
      key: string;
      items: ProviderOperation[];
      next: string | null;
    } | null>(null),
    [connections, setConnections] = useState<{
      key: string;
      items: ProviderConnection[];
    } | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [local, setLocal] = useState(0),
    [detail, setDetail] = useState<ProviderOperationDetail | null>(null);
  const key = `${bookId}:${filter}:${refresh}:${local}`;
  useEffect(() => {
    let active = true;
    Promise.all([
      api.fetchProviderOperations(businessId, bookId, filter || undefined),
      allConnections(businessId, bookId),
    ])
      .then(([operations, links]) => {
        if (!active) return;
        setPage({
          key,
          items: operations.items,
          next: operations.next_cursor,
        });
        setConnections({ key, items: links });
      })
      .catch((e) => {
        if (active) setError(failure(e));
      });
    return () => {
      active = false;
    };
  }, [businessId, bookId, filter, key]);
  const current = page?.key === key ? page : null;
  const links = connections?.key === key ? connections.items : null;
  const more = async () => {
    if (!current?.next) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.fetchProviderOperations(
        businessId,
        bookId,
        filter || undefined,
        current.next,
      );
      setPage({
        key,
        items: [...current.items, ...next.items],
        next: next.next_cursor,
      });
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  };
  const open = async (operation: string) => {
    setBusy(true);
    setError(null);
    try {
      setDetail(
        await api.fetchProviderOperation(businessId, bookId, operation),
      );
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  };
  const account = (id: string) => {
    const x = accounts.find((a) => a.account_id === id);
    return x ? `${x.code} · ${x.name}` : id;
  };
  return (
    <section aria-label="Provider operations">
      <h2>Provider operations</h2>
      <p>
        Payments and refunds that the payment provider reported in signed
        events. They are not bank payouts. A finance user applies an observed
        operation from its reserved settlement; the amount, currency and date
        always come from the provider.
      </p>
      {error && (
        <p role="alert" className="mgmt-error-banner">
          {error}
        </p>
      )}
      <h3>Connections</h3>
      {links === null && !error && (
        <p role="status">Loading provider connections…</p>
      )}
      {links?.length === 0 && <p>No provider connection for this book.</p>}
      <ul className="financial-records">
        {links?.map((x) => (
          <li key={x.connection_id}>
            <p>
              Connection {x.account_id} ·{" "}
              {x.revoked ? "revoked: no new money" : "active, test mode"}
            </p>
            {x.clearing_account ? (
              <p>
                Clearing account {account(x.clearing_account.account_id)} ·
                registered{" "}
                {new Date(x.clearing_account.registered_at).toLocaleString()} by{" "}
                {x.clearing_account.registered_by}. It cannot be changed.
              </p>
            ) : x.revoked ? (
              <p>No clearing account. A revoked connection takes none.</p>
            ) : (
              <ClearingAccountForm
                businessId={businessId}
                bookId={bookId}
                connection={x}
                accounts={accounts.filter((a) => a.type === "asset")}
                disabled={disabled || busy}
                done={() => setLocal((n) => n + 1)}
              />
            )}
          </li>
        ))}
      </ul>
      <ProviderAttention
        businessId={businessId}
        bookId={bookId}
        disabled={disabled}
        refresh={refresh}
      />
      <h3>Operations</h3>
      <Field label="Operation state">
        <select
          value={filter}
          disabled={busy}
          onChange={(e) => {
            setError(null);
            setFilter(e.target.value as State | "");
          }}
        >
          <option value="">All states</option>
          {STATES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      {current === null && !error && (
        <p role="status">Loading provider operations…</p>
      )}
      {current?.items.length === 0 && (
        <p>No provider operation in this view.</p>
      )}
      <ul className="financial-records" aria-label="Provider operation list">
        {current?.items.map((x) => (
          <li key={x.operation_id} className="provider-operation">
            <p>
              <strong>{kindText(x)}</strong> ·{" "}
              {x.amount === null
                ? "no observed amount"
                : `${x.amount} ${x.currency}`}{" "}
              · first seen {new Date(x.created_at).toLocaleDateString()}
            </p>
            <p>
              {stateText(x.state)}
              {x.payment_id && ` · payment ${x.payment_id}`}
            </p>
            {x.state === "applied_with_conflict" && (
              <p className="provider-conflict">
                <strong>Manual review needed.</strong> Money already moved and
                later provider data does not change it. Compare this payment
                with the provider&apos;s records; if it is wrong, correct or
                void it from its settlement. The provider record stays in its
                history.
              </p>
            )}
            <button
              className="secondary"
              disabled={busy}
              aria-label={`Details of ${x.provider_object_id}`}
              onClick={() => void open(x.operation_id)}
            >
              Details
            </button>
          </li>
        ))}
      </ul>
      {current?.next && (
        <button disabled={busy} onClick={() => void more()}>
          Load more provider operations
        </button>
      )}
      {detail && (
        <OperationDetail
          businessId={businessId}
          bookId={bookId}
          detail={detail}
          disabled={disabled || busy}
          linked={(operation) => {
            setLocal((n) => n + 1);
            void open(operation);
          }}
          close={() => setDetail(null)}
        />
      )}
    </section>
  );
}

function OperationDetail({
  businessId,
  bookId,
  detail,
  disabled,
  linked,
  close,
}: {
  businessId: string;
  bookId: string;
  detail: ProviderOperationDetail;
  disabled: boolean;
  linked: (operation: string) => void;
  close: () => void;
}) {
  const operation = detail.operation;
  const review =
    operation.state === "needs_review" ||
    operation.state === "applied_with_conflict";
  const disagreements = detail.events.flatMap((event) => [
    ...(event.decision?.reason === "conflicting_facts"
      ? [`${event.event_type}: ${REASONS.conflicting_facts}.`]
      : []),
    ...event.deliveries.flatMap((delivery) =>
      delivery.differences.map(
        (x) =>
          `${event.event_type}, delivery ${delivery.digest}: ${fieldText(x.field)} ${x.original} → ${x.delivered}.`,
      ),
    ),
  ]);
  return (
    <section
      className="financial-detail"
      aria-label="Provider operation detail"
    >
      <h3>
        {kindText(operation)} · {stateText(operation.state)}
      </h3>
      {review && (
        <section className="provider-conflict" aria-label="What disagrees">
          <p>
            <strong>What disagrees.</strong> Nothing here changes money or a
            decision; review it against the provider&apos;s records.
          </p>
          <ul>
            {disagreements.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      )}
      <ol>
        {detail.events.map((event) => (
          <li key={event.event_id}>
            <p>
              {event.event_type} · created{" "}
              {new Date(event.created).toLocaleString()} ·{" "}
              {event.decision
                ? `${event.decision.outcome === "observed" ? "observed" : "needs review"}: ${REASONS[event.decision.reason] ?? event.decision.reason}`
                : "not decided yet"}
            </p>
            <ul>
              {event.deliveries.map((delivery) => (
                <li key={delivery.digest}>
                  Delivery {delivery.digest} · received{" "}
                  {new Date(delivery.received_at).toLocaleString()} ·{" "}
                  {delivery.matches_original
                    ? "same facts as the first delivery"
                    : `differs: ${delivery.differences
                        .map(
                          (x) =>
                            `${fieldText(x.field)} ${x.original} → ${x.delivered}`,
                        )
                        .join("; ")}`}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
      {detail.manual_payments.length > 0 && (
        <section aria-label="Manual payments naming this ID">
          <h4>Manual payments naming this ID</h4>
          <ul>
            {detail.manual_payments.map((x) => (
              <li key={x.payment_id}>
                {x.amount} {x.currency} · {x.actual_external_date} · {x.state} ·{" "}
                {x.external_reference} · payment {x.payment_id}
              </li>
            ))}
          </ul>
        </section>
      )}
      {detail.link && (
        <p>
          Linked to manual payment {detail.link.payment_id}: {detail.link.note}{" "}
          · by {detail.link.linked_by} ·{" "}
          {new Date(detail.link.linked_at).toLocaleString()}. No money moved for
          this operation.
        </p>
      )}
      {operation.state === "needs_link" && !detail.link && (
        <LinkForm
          businessId={businessId}
          bookId={bookId}
          detail={detail}
          disabled={disabled}
          done={() => linked(operation.operation_id)}
        />
      )}
      <button className="secondary" onClick={close}>
        Close details
      </button>
    </section>
  );
}

/** K3b: link only (owner decision 1); the comparison is the server's, the note the user's. */
function LinkForm({
  businessId,
  bookId,
  detail,
  disabled,
  done,
}: {
  businessId: string;
  bookId: string;
  detail: ProviderOperationDetail;
  disabled: boolean;
  done: () => void;
}) {
  const operation = detail.operation;
  const [payment, setPayment] = useState(""),
    [note, setNote] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  return (
    <form
      aria-label="Link to a manual payment"
      onSubmit={(e) => {
        e.preventDefault();
        if (!confirmed) return;
        setBusy(true);
        setError(null);
        void api
          .linkProviderOperation(
            businessId,
            bookId,
            operation.operation_id,
            payment,
            note.trim(),
          )
          .then(done, (e) => setError(failure(e)))
          .finally(() => setBusy(false));
      }}
    >
      <fieldset disabled={disabled || busy}>
        <legend>Link to a manual payment</legend>
        <p>
          The provider reported {operation.amount} {operation.currency}. Link
          the manual payment that recorded it: amounts must be equal and the
          dates at most 3 days apart. No money moves; the operation is never
          applied.
        </p>
        <Field label="Manual payment">
          <select
            required
            value={payment}
            onChange={(e) => setPayment(e.target.value)}
          >
            <option value="">Choose payment</option>
            {detail.manual_payments
              .filter((x) => x.state !== "voided")
              .map((x) => (
                <option key={x.payment_id} value={x.payment_id}>
                  {x.amount} {x.currency} · {x.actual_external_date} ·{" "}
                  {x.external_reference}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Link note">
          <input
            required
            maxLength={500}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </Field>
        <label className="financial-check">
          <input
            type="checkbox"
            required
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I compared this manual payment with the provider operation; the link
          is permanent.
        </label>
        <button type="submit">Link to manual payment</button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}

/** Events waiting for a decision and decisions without an operation (owner decision 2). */
function ProviderAttention({
  businessId,
  bookId,
  disabled,
  refresh,
}: {
  businessId: string;
  bookId: string;
  disabled: boolean;
  refresh: number;
}) {
  const [page, setPage] = useState<{
      key: string;
      items: ProviderAttentionItem[];
      next: string | null;
    } | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [local, setLocal] = useState(0);
  const key = `${bookId}:${refresh}:${local}`;
  useEffect(() => {
    let active = true;
    api
      .fetchProviderAttention(businessId, bookId)
      .then((first) => {
        if (active)
          setPage({ key, items: first.items, next: first.next_cursor });
      })
      .catch((e) => {
        if (active) setError(failure(e));
      });
    return () => {
      active = false;
    };
  }, [businessId, bookId, key]);
  const current = page?.key === key ? page : null;
  const more = async () => {
    if (!current?.next) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.fetchProviderAttention(
        businessId,
        bookId,
        current.next,
      );
      setPage({
        key,
        items: [...current.items, ...next.items],
        next: next.next_cursor,
      });
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-label="Needs attention">
      <h3>Needs attention</h3>
      <p>
        Provider events that are not decided yet, and decisions that have no
        payment or refund to attach to. None of them moves money.
      </p>
      {error && <p role="alert">{error}</p>}
      {current === null && !error && (
        <p role="status">Loading events that need attention…</p>
      )}
      {current?.items.length === 0 && <p>Nothing needs attention.</p>}
      <ul className="financial-records" aria-label="Attention list">
        {current?.items.map((x) => (
          <li key={x.event_id}>
            <p>
              <strong>
                {x.event_type} {x.object_id}
              </strong>{" "}
              · created {new Date(x.created).toLocaleDateString()}
            </p>
            {x.kind === "undecided" ? (
              <p>
                Waiting for the receipt worker. It is decided automatically;
                there is nothing to acknowledge.
              </p>
            ) : x.acknowledgement ? (
              <p>
                Decided: {REASONS[x.reason ?? ""] ?? x.reason}. Handled:{" "}
                {x.acknowledgement.note} · by{" "}
                {x.acknowledgement.acknowledged_by} ·{" "}
                {new Date(x.acknowledgement.acknowledged_at).toLocaleString()}
              </p>
            ) : (
              <AcknowledgeForm
                businessId={businessId}
                bookId={bookId}
                item={x}
                disabled={disabled || busy}
                done={() => setLocal((n) => n + 1)}
              />
            )}
          </li>
        ))}
      </ul>
      {current?.next && (
        <button disabled={busy} onClick={() => void more()}>
          Load more attention items
        </button>
      )}
    </section>
  );
}

function AcknowledgeForm({
  businessId,
  bookId,
  item,
  disabled,
  done,
}: {
  businessId: string;
  bookId: string;
  item: ProviderAttentionItem;
  disabled: boolean;
  done: () => void;
}) {
  const [note, setNote] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  return (
    <form
      aria-label={`Acknowledge ${item.object_id}`}
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        // Safe to repeat: the same note again returns the existing record.
        void api
          .acknowledgeProviderEvent(
            businessId,
            bookId,
            item.event_id,
            note.trim(),
          )
          .then(done, (e) => setError(failure(e)))
          .finally(() => setBusy(false));
      }}
    >
      <fieldset disabled={disabled || busy}>
        <legend>Acknowledge as handled</legend>
        <p>
          Decided: {REASONS[item.reason ?? ""] ?? item.reason}. Record what you
          checked; the note is permanent and changes no money.
        </p>
        <Field label="Acknowledgement note">
          <input
            required
            maxLength={500}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </Field>
        <button type="submit">Acknowledge</button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}

function ClearingAccountForm({
  businessId,
  bookId,
  connection,
  accounts,
  disabled,
  done,
}: {
  businessId: string;
  bookId: string;
  connection: ProviderConnection;
  accounts: LedgerAccount[];
  disabled: boolean;
  done: () => void;
}) {
  const [account, setAccount] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  return (
    <form
      aria-label={`Clearing account for ${connection.account_id}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (!confirmed) return;
        setBusy(true);
        setError(null);
        // Safe to repeat: the same account returns the existing registration.
        void api
          .registerClearingAccount(
            businessId,
            bookId,
            connection.connection_id,
            account,
          )
          .then(done, (e) => setError(failure(e)))
          .finally(() => setBusy(false));
      }}
    >
      <fieldset disabled={disabled || busy}>
        <legend>Register clearing account</legend>
        <p>
          No clearing account is registered, so observed money cannot be
          applied. Observed gross amounts go to this asset account. It is
          registered once and cannot be changed later.
        </p>
        <AccountSelect
          label="Clearing asset account"
          accounts={accounts}
          value={account}
          onChange={setAccount}
        />
        <label className="financial-check">
          <input
            type="checkbox"
            required
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I confirm this account for {connection.account_id}; it cannot be
          changed later.
        </label>
        <button type="submit">Register clearing account</button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}

/** Typed input kept by the workspace while it reloads after a refusal (U-05). */
export type ProviderDraft = {
  chosen: string;
  date: string;
  allocated: Record<string, string>;
};

/** From a reserved settlement: apply one observed operation of the fitting kind (owner decision 1). */
export function ProviderApplyEditor({
  businessId,
  settlement,
  book,
  timezone,
  disabled,
  send,
  draft,
  onDraft,
}: {
  businessId: string;
  settlement: Settlement;
  book: string;
  /** The business time zone from the financial overview: "today" is its date. */
  timezone: string;
  disabled: boolean;
  send: SendFinancialCommand;
  draft: ProviderDraft | null;
  onDraft: (draft: ProviderDraft) => void;
}) {
  const kind = settlement.direction === "receivable" ? "payment" : "refund";
  const [options, setOptions] = useState<{
      items: ProviderOperation[];
      next: string | null;
    } | null>(null),
    [loadError, setLoadError] = useState<string | null>(null),
    [form, setFormState] = useState<ProviderDraft>(
      () =>
        draft ?? {
          chosen: "",
          date: businessDateTime(new Date(), timezone).date,
          allocated: {},
        },
    ),
    [attest, setAttest] = useState(false);
  const { chosen, date, allocated } = form;
  const setForm = (next: ProviderDraft) => {
    setFormState(next);
    onDraft(next);
  };
  useEffect(() => {
    let active = true;
    api
      .fetchProviderOperations(businessId, book, "observed")
      .then((page) => {
        if (active) setOptions({ items: page.items, next: page.next_cursor });
      })
      .catch((e) => {
        if (active) setLoadError(failure(e));
      });
    return () => {
      active = false;
    };
  }, [businessId, book]);
  const more = async () => {
    if (!options?.next) return;
    try {
      const page = await api.fetchProviderOperations(
        businessId,
        book,
        "observed",
        options.next,
      );
      setOptions({
        items: [...options.items, ...page.items],
        next: page.next_cursor,
      });
    } catch (e) {
      setLoadError(failure(e));
    }
  };
  const fitting =
    options?.items.filter(
      (x) => x.kind === kind && x.currency === settlement.currency,
    ) ?? [];
  const operation = fitting.find((x) => x.operation_id === chosen) ?? null;
  return (
    <CommandForm
      title="Apply provider operation"
      label="Apply provider operation"
      disabled={disabled}
      submit={async () => {
        if (!operation || operation.amount === null)
          throw new Error("Choose an observed provider operation.");
        if (!attest)
          throw new Error(
            "An explicit confirmation by a finance user is required.",
          );
        const allocations = Object.entries(allocated)
          .filter(([, value]) => value !== "")
          .map(([obligation_id, amount]) => ({ obligation_id, amount }));
        const scale = settlement.minor_units;
        const total = allocations.reduce<bigint | null>((sum, x) => {
          const units = minorUnits(x.amount, scale);
          return sum === null || units === null || units <= 0n
            ? null
            : sum + units;
        }, 0n);
        if (total === null || total !== minorUnits(operation.amount, scale))
          throw new Error(
            "Positive allocated amounts must equal the provider amount exactly.",
          );
        await send(
          financialCommandSchema.parse({
            book,
            subject: settlement.settlement_id,
            key: crypto.randomUUID(),
            payment: crypto.randomUUID(),
            operation: "settlement_provider_confirm",
            body: {
              schema_version: 1,
              expected_sequence: settlement.sequence,
              operation_id: operation.operation_id,
              entry_date: date,
              allocations,
            },
          }),
        );
      }}
    >
      <p>
        Applies one {kind} that the provider reported. The amount, currency and
        external date come from the provider and cannot be typed; the money goes
        to the connection&apos;s clearing account. This does not start a
        transfer.
      </p>
      {loadError && <p role="alert">{loadError}</p>}
      {options === null && !loadError && (
        <p role="status">Loading observed provider operations…</p>
      )}
      {options && fitting.length === 0 && (
        <p>
          No observed provider {kind} in {settlement.currency} is waiting to be
          applied.
        </p>
      )}
      <Field label="Observed provider operation">
        <select
          required
          value={chosen}
          onChange={(e) => setForm({ ...form, chosen: e.target.value })}
        >
          <option value="">Choose operation</option>
          {fitting.map((x) => (
            <option key={x.operation_id} value={x.operation_id}>
              {kindText(x)} · {x.amount} {x.currency}
            </option>
          ))}
        </select>
      </Field>
      {options?.next && (
        <button type="button" className="secondary" onClick={() => void more()}>
          Load more observed operations
        </button>
      )}
      {operation && (
        <p>
          Amount from the provider: {operation.amount} {operation.currency}{" "}
          (cannot be changed).
        </p>
      )}
      <Field label="Payment posting date">
        <input
          required
          type="date"
          value={date}
          onChange={(e) => setForm({ ...form, date: e.target.value })}
        />
      </Field>
      {settlement.allocations.map((x) => (
        <Field
          key={x.obligation_id}
          label={`Provider allocation ${x.obligation_id} · reserve ${x.reserved}`}
        >
          <input
            inputMode="decimal"
            pattern="(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?"
            value={allocated[x.obligation_id] ?? ""}
            onChange={(e) =>
              setForm({
                ...form,
                allocated: { ...allocated, [x.obligation_id]: e.target.value },
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
        I apply this observed provider operation with these allocations.
      </label>
    </CommandForm>
  );
}
