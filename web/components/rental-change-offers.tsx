"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { businessDateTime, businessTimeToInstant } from "../lib/business-time";
import { currencyPlaces, formatMinor } from "../lib/construction-rules";
import type { Delegation } from "../lib/delegation-contracts";
import { ManagementApiError } from "../lib/management-api";
import {
  fetchAgreement,
  fetchLatestRentalChange,
  fetchRateCards,
  issueRentalChange,
  refusal,
  rentalChangeHref,
  type RentalChangeOfferBody,
} from "../lib/rental-api";
import type {
  Agreement,
  Booking,
  RateCard,
  RentalChangeOffer,
} from "../lib/rental-contracts";

type Props = {
  business: string;
  booking: Booking;
  zone: string;
  bindingRevision: number;
  grants: readonly Delegation[];
  grantStillMatches: (grant: string) => Promise<boolean>;
};

type Context = {
  agreement: Agreement;
  version: Agreement["versions"][number];
  offer: RentalChangeOffer | null;
  card: RateCard;
};

export function RentalChangeOffers(props: Props) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="secondary"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? "Close agreement changes" : "Manage agreement changes"}
      </button>
      {open && <ChangeOffers {...props} />}
    </>
  );
}

function ChangeOffers(props: Props) {
  const { business, booking } = props;
  const heading = useId();
  const [data, setData] = useState<Context | null | undefined>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  const read = useCallback(async (): Promise<Context | null> => {
    const [agreement, offer] = await Promise.all([
      fetchAgreement(business, booking.booking_id),
      fetchLatestRentalChange(business, booking.booking_id),
    ]);
    if (!agreement) return null;
    const version = agreement.versions.find(
      (item) => item.version === agreement.current_version,
    );
    if (!version || agreement.booking_id !== booking.booking_id)
      throw new ManagementApiError(
        "INVALID_RESPONSE",
        "Unable to read the current agreement.",
      );
    const cards = await fetchRateCards(business, booking.class_id);
    const card = cards.items.find(
      (item) => item.rate_card_id === version.rate_card_id,
    );
    if (!card)
      throw new ManagementApiError(
        "INVALID_RESPONSE",
        "Unable to read the agreed rate card.",
      );
    return { agreement, version, offer, card };
  }, [business, booking.booking_id, booking.class_id]);

  useEffect(() => {
    let live = true;
    read().then(
      (value) => {
        if (live) setData(value);
      },
      (failure: unknown) => {
        if (live) setError(refusal(failure));
      },
    );
    return () => {
      live = false;
    };
  }, [read, attempt]);

  function reload() {
    setData(undefined);
    setError("");
    setAttempt((value) => value + 1);
  }

  return (
    <section aria-labelledby={heading}>
      <h4 id={heading}>Agreement change offer</h4>
      {error && <p role="alert">{error}</p>}
      {error && (
        <button type="button" onClick={reload}>
          Reload agreement
        </button>
      )}
      {data === undefined && !error && (
        <p role="status">Loading agreement changes…</p>
      )}
      {data === null && (
        <p>Record or accept the first agreement before proposing a change.</p>
      )}
      {data && <OfferForm {...props} data={data} onReload={reload} />}
    </section>
  );
}

function localTime(instant: string, zone: string) {
  try {
    return businessDateTime(instant, zone);
  } catch {
    return { date: "", time: "" };
  }
}

function editedInstant(
  value: ReturnType<typeof localTime>,
  original: string,
  zone: string,
) {
  const initial = localTime(original, zone);
  // Keep the agreed instant if its local fields were left alone, including seconds and DST folds.
  if (
    value.date &&
    value.time &&
    value.date === initial.date &&
    value.time === initial.time
  )
    return original;
  return businessTimeToInstant(value.date, value.time, zone);
}

function OfferForm({
  business,
  booking,
  zone,
  bindingRevision,
  grants,
  grantStillMatches,
  data,
  onReload,
}: Props & { data: Context; onReload: () => void }) {
  const version = data.version;
  const [offer, setOffer] = useState(data.offer);
  const [changePeriod, setChangePeriod] = useState(false);
  const [start, setStart] = useState(() => localTime(version.starts_at, zone));
  const [end, setEnd] = useState(() => localTime(version.ends_at, zone));
  const [reason, setReason] = useState("");
  const [quantities, setQuantities] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      version.extras.map((item) => [item.code, String(item.quantity)]),
    ),
  );
  const [pending, setPending] = useState<RentalChangeOfferBody | null>(null);
  const [grant, setGrant] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const shareable =
    offer?.agreement_version === data.agreement.current_version &&
    offer.binding_revision === bindingRevision;

  function buildOffer(): RentalChangeOfferBody {
    const period = changePeriod
      ? {
          starts_at: editedInstant(start, version.starts_at, zone),
          ends_at: editedInstant(end, version.ends_at, zone),
        }
      : null;
    if (period && Date.parse(period.ends_at) <= Date.parse(period.starts_at))
      throw new Error("The return must be after pickup.");
    const extras = data.card.extras.flatMap((item) => {
      const quantity = Number(quantities[item.code] || "0");
      if (!Number.isInteger(quantity) || quantity < 0 || quantity > 100)
        throw new Error(`Enter a quantity from 0 to 100 for ${item.name}.`);
      return quantity === 0 ? [] : [{ code: item.code, quantity }];
    });
    return {
      schema_version: 1,
      expected_previous_offer_revision: offer?.revision ?? 0,
      expected_agreement_version: data.agreement.current_version,
      expected_binding_revision: bindingRevision,
      period,
      extras,
      reason: reason.trim(),
    };
  }

  async function issue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || (!pending && !reason.trim())) return;
    setNotice("");
    setError("");
    setLink(null);
    inFlight.current = true;
    setBusy(true);
    try {
      const body = pending ?? buildOffer();
      setPending(body);
      const issued = await issueRentalChange(
        business,
        booking.booking_id,
        body,
      );
      setOffer(issued);
      setGrant("");
      setPending(null);
      setNotice("Change offer saved.");
    } catch (failure) {
      setError(refusal(failure));
      if (
        failure instanceof ManagementApiError &&
        failure.status &&
        failure.status >= 400 &&
        failure.status < 500
      )
        setPending(null);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function prepareLink() {
    if (inFlight.current || pending || !offer || !shareable || !grant) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setLink(null);
    try {
      const [latest, agreement, allowed] = await Promise.all([
        fetchLatestRentalChange(business, booking.booking_id),
        fetchAgreement(business, booking.booking_id),
        grantStillMatches(grant),
      ]);
      if (
        !allowed ||
        latest?.revision !== offer.revision ||
        latest.review_hash !== offer.review_hash ||
        agreement?.current_version !== offer.agreement_version
      ) {
        throw new Error(
          "This offer or grant changed. Reload the agreement before sharing.",
        );
      }
      setLink(
        rentalChangeHref({
          business,
          booking: booking.booking_id,
          revision: offer.revision,
          grant,
        }),
      );
    } catch (failure) {
      setError(refusal(failure));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <form
        aria-label="Prepare agreement change"
        onSubmit={(event) => void issue(event)}
      >
        <fieldset disabled={busy || pending !== null}>
          <legend>Proposed terms</legend>
          <label>
            <input
              type="checkbox"
              checked={changePeriod}
              disabled={!zone}
              onChange={(event) => setChangePeriod(event.target.checked)}
            />
            Change rental period
          </label>
          {changePeriod && (
            <>
              <p>Times use {zone}.</p>
              <label>
                Pickup date
                <input
                  type="date"
                  required
                  value={start.date}
                  onChange={(event) =>
                    setStart({ ...start, date: event.target.value })
                  }
                />
              </label>
              <label>
                Pickup time
                <input
                  type="time"
                  required
                  value={start.time}
                  onChange={(event) =>
                    setStart({ ...start, time: event.target.value })
                  }
                />
              </label>
              <label>
                Return date
                <input
                  type="date"
                  required
                  value={end.date}
                  onChange={(event) =>
                    setEnd({ ...end, date: event.target.value })
                  }
                />
              </label>
              <label>
                Return time
                <input
                  type="time"
                  required
                  value={end.time}
                  onChange={(event) =>
                    setEnd({ ...end, time: event.target.value })
                  }
                />
              </label>
            </>
          )}
          {data.card.extras.map((item) => (
            <label key={item.code}>
              {item.name}
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                value={quantities[item.code] ?? "0"}
                onChange={(event) =>
                  setQuantities({
                    ...quantities,
                    [item.code]: event.target.value,
                  })
                }
              />
            </label>
          ))}
          <label>
            Reason shown to customer
            <textarea
              rows={3}
              maxLength={500}
              required
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
        </fieldset>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy || (!pending && !reason.trim())}>
            {pending ? "Retry offer save" : "Save change offer"}
          </button>
          <button
            type="button"
            className="secondary"
            disabled={busy || pending !== null}
            onClick={onReload}
          >
            Reload agreement
          </button>
        </div>
      </form>
      {shareable && offer && (
        <>
          <p>
            Proposed total:{" "}
            <strong>
              {offer.quote.currency}{" "}
              {formatMinor(
                offer.quote.total,
                currencyPlaces(offer.quote.currency) ?? 2,
              )}
            </strong>
          </p>
          {grants.length > 0 ? (
            <>
              <label>
                Grant for change offer
                <select
                  value={grant}
                  disabled={busy}
                  onChange={(event) => {
                    setGrant(event.target.value);
                    setLink(null);
                  }}
                >
                  <option value="">Choose a grant</option>
                  {grants.map((item) => (
                    <option key={item.grant_id} value={item.grant_id}>
                      {item.servicer_name ?? "Customer company"} ·{" "}
                      {item.grant_id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={() => void prepareLink()}
                disabled={busy || pending !== null || !grant}
              >
                Prepare change link
              </button>
            </>
          ) : (
            <p>No active rental grant matches this booking.</p>
          )}
          {link && (
            <p>
              <Link href={link}>Rental change link</Link> for the customer
              delegate.
            </p>
          )}
        </>
      )}
    </>
  );
}
