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
import type { Delegation } from "../lib/delegation-contracts";
import { fetchDelegations, ManagementApiError } from "../lib/management-api";
import {
  fetchRentalCustomerCompany,
  refusal,
  rentalProblemsHref,
  saveRentalCustomerCompany,
  type RentalCustomerCompanyBody,
} from "../lib/rental-api";
import {
  rentalProposalLinkSchema,
  type Booking,
  type RentalCustomerCompany,
} from "../lib/rental-contracts";
import { RentalChangeOffers } from "./rental-change-offers";

type Access = {
  binding: RentalCustomerCompany;
  grants: Delegation[];
};

async function readAccess(business: string, booking: string): Promise<Access> {
  const binding = await fetchRentalCustomerCompany(business, booking);
  const grants: Delegation[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await fetchDelegations(business, after);
    grants.push(...page.items);
    if (!page.next_cursor) return { binding, grants };
    after = page.next_cursor;
  }
}

function grantMatches(
  grant: Delegation,
  business: string,
  binding: RentalCustomerCompany,
  pickup: string,
) {
  return (
    grant.owner_business_id === business &&
    grant.servicer_business_id === binding.company_id &&
    grant.status === "active" &&
    !grant.expired &&
    Date.parse(grant.expires_at) > Date.now() &&
    grant.permissions.includes("rental.customer_answer") &&
    (grant.location_id === null || grant.location_id === pickup) &&
    grant.delegates.length > 0
  );
}

export function RentalCustomerAccess({
  business,
  booking,
  zone,
}: {
  business: string;
  booking: Booking;
  zone: string;
}) {
  const heading = useId();
  const [open, setOpen] = useState(false);
  return (
    <section aria-labelledby={heading}>
      <h3 id={heading}>Customer proposal access</h3>
      <button
        type="button"
        className="secondary"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? "Close customer access" : "Manage customer access"}
      </button>
      {open && <AccessForm business={business} booking={booking} zone={zone} />}
    </section>
  );
}

function AccessForm({
  business,
  booking,
  zone,
}: {
  business: string;
  booking: Booking;
  zone: string;
}) {
  const {
    booking_id: bookingId,
    customer_id: customerId,
    pickup_location_id: pickup,
  } = booking;
  const [data, setData] = useState<Access | null>(null);
  const [company, setCompany] = useState("");
  const [grantId, setGrantId] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const [pending, setPending] = useState<RentalCustomerCompanyBody | null>(
    null,
  );
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const inFlight = useRef(false);

  const read = useCallback(async () => {
    const fresh = await readAccess(business, bookingId);
    if (fresh.binding.customer_id !== customerId)
      throw new ManagementApiError(
        "INVALID_RESPONSE",
        "Reload the booking before sharing a proposal.",
      );
    return fresh;
  }, [business, bookingId, customerId]);

  useEffect(() => {
    let active = true;
    read().then(
      (fresh) => {
        if (active) {
          setData(fresh);
          setCompany(fresh.binding.company_id ?? "");
        }
      },
      (failure: unknown) => {
        if (active) setError(refusal(failure));
      },
    );
    return () => {
      active = false;
    };
  }, [read, attempt]);

  const companyId = company.trim().toLowerCase();
  const valid =
    companyId === "" ||
    rentalProposalLinkSchema.shape.business.safeParse(companyId).success;
  const dirty = data !== null && companyId !== (data.binding.company_id ?? "");
  const grants = data
    ? data.grants.filter((grant) =>
        grantMatches(grant, business, data.binding, pickup),
      )
    : [];

  function reload() {
    setData(null);
    setError("");
    setNotice("");
    setGrantId("");
    setLink(null);
    setAttempt((value) => value + 1);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || !data || !valid || (!pending && !dirty)) return;
    const body: RentalCustomerCompanyBody = pending ?? {
      schema_version: 1,
      expected_revision: data.binding.revision,
      company_id: companyId || null,
    };
    inFlight.current = true;
    setPending(body);
    setBusy(true);
    setLink(null);
    setError("");
    setNotice("");
    try {
      const binding = await saveRentalCustomerCompany(
        business,
        bookingId,
        body,
      );
      setData({ binding, grants: data.grants });
      setCompany(binding.company_id ?? "");
      setGrantId("");
      setPending(null);
      setNotice("Customer company saved.");
    } catch (failure) {
      setError(refusal(failure));
      if (
        failure instanceof ManagementApiError &&
        failure.status &&
        failure.status >= 400 &&
        failure.status < 500
      ) {
        setPending(null);
        if (failure.status === 409) setData(null);
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function prepare() {
    if (inFlight.current || !data || dirty || pending || !grantId) return;
    inFlight.current = true;
    setBusy(true);
    setLink(null);
    setError("");
    setNotice("");
    try {
      const fresh = await read();
      setData(fresh);
      setCompany(fresh.binding.company_id ?? "");
      const grant = fresh.grants.find((item) => item.grant_id === grantId);
      if (!grant || !grantMatches(grant, business, fresh.binding, pickup)) {
        setGrantId("");
        throw new ManagementApiError(
          "ACCESS_UNAVAILABLE",
          "This grant is unavailable for the booking.",
        );
      }
      const query = new URLSearchParams({
        business,
        booking: bookingId,
        grant: grantId,
      });
      setLink(`/rental/customer/?${query}`);
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
      {!data && !error && <p role="status">Loading customer access…</p>}
      {data && (
        <>
          <form
            aria-label="Rental customer company"
            onSubmit={(event) => void save(event)}
          >
            <label>
              Customer business ID
              <input
                value={company}
                disabled={busy || pending !== null}
                onChange={(event) => {
                  setCompany(event.target.value);
                  setGrantId("");
                  setLink(null);
                }}
              />
            </label>
            <p className="muted">Leave blank to remove the company link.</p>
            <button
              type="submit"
              disabled={busy || !valid || (!dirty && !pending)}
            >
              {pending
                ? "Retry customer company save"
                : "Save customer company"}
            </button>
          </form>
          {data.binding.company_id && !dirty && !pending && (
            <>
              {grants.length ? (
                <>
                  <label>
                    Active rental grant
                    <select
                      value={grantId}
                      disabled={busy}
                      onChange={(event) => {
                        setGrantId(event.target.value);
                        setLink(null);
                      }}
                    >
                      <option value="">Choose a grant</option>
                      {grants.map((grant) => (
                        <option key={grant.grant_id} value={grant.grant_id}>
                          {grant.servicer_name ?? "Customer company"} ·{" "}
                          {grant.grant_id.slice(0, 8)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    disabled={busy || !grantId}
                    onClick={() => void prepare()}
                  >
                    Prepare proposal link
                  </button>
                </>
              ) : (
                <p>
                  No active rental grant matches this company and pickup
                  location.
                </p>
              )}
              {link && (
                <p>
                  <Link href={link}>Rental proposal link</Link> for the customer
                  delegate.
                </p>
              )}
              {link && (
                <p>
                  <Link
                    href={rentalProblemsHref({
                      business,
                      booking: bookingId,
                      grant: grantId,
                    })}
                  >
                    Problem report link
                  </Link>{" "}
                  for the same delegate.
                </p>
              )}
              <RentalChangeOffers
                key={data.binding.revision}
                business={business}
                booking={booking}
                zone={zone}
                bindingRevision={data.binding.revision}
                grants={grants}
                grantStillMatches={async (id) => {
                  const fresh = await read();
                  return (
                    fresh.binding.revision === data.binding.revision &&
                    fresh.grants.some(
                      (grant) =>
                        grant.grant_id === id &&
                        grantMatches(grant, business, fresh.binding, pickup),
                    )
                  );
                }}
              />
            </>
          )}
        </>
      )}
      <button
        type="button"
        className="secondary"
        disabled={busy || pending !== null}
        onClick={reload}
      >
        Reload customer access
      </button>
    </>
  );
}
