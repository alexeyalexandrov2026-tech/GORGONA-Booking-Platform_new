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
import { z } from "zod";
import {
  fetchCustomerCompany,
  fetchProject,
  refusal,
  saveCustomerCompany,
} from "../lib/construction-api";
import type {
  CustomerCompany,
  CustomerCompanyBody,
  Project,
} from "../lib/construction-contracts";
import {
  customerDocumentLinks,
  customerGrantMatches,
} from "../lib/construction-customer-access";
import type { Delegation } from "../lib/delegation-contracts";
import { fetchDelegations, ManagementApiError } from "../lib/management-api";

async function allAccess(business: string): Promise<Delegation[]> {
  const grants: Delegation[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await fetchDelegations(business, after);
    grants.push(...page.items);
    if (!page.next_cursor) return grants;
    after = page.next_cursor;
  }
}

type Access = { company: CustomerCompany; grants: Delegation[] };
type Prepared = ReturnType<typeof customerDocumentLinks>;

export function ConstructionCustomerAccess({
  business,
  project,
  hasProposal,
  hasContract,
  changes,
}: {
  business: string;
  project: Project;
  hasProposal: boolean;
  hasContract: boolean;
  changes: readonly number[];
}) {
  const heading = useId();
  const [data, setData] = useState<Access | null>(null);
  const [company, setCompany] = useState("");
  const [grantId, setGrantId] = useState("");
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [pending, setPending] = useState<CustomerCompanyBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const inFlight = useRef(false);

  const read = useCallback(async (): Promise<Access> => {
    const [binding, grants, fresh] = await Promise.all([
      fetchCustomerCompany(business, project.project_id),
      allAccess(business),
      fetchProject(business, project.project_id),
    ]);
    if (
      fresh.revision !== project.revision ||
      binding.customer_id !== fresh.customer_id
    )
      throw new ManagementApiError(
        "STALE_PROJECT",
        "The project changed. Reload the project before continuing.",
        409,
      );
    return { company: binding, grants };
  }, [business, project.project_id, project.revision]);

  useEffect(() => {
    let active = true;
    read().then(
      (value) => {
        if (active) {
          setData(value);
          setCompany(value.company.company_id ?? "");
          setError("");
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

  const normalizedCompany = company.trim().toLowerCase();
  const validCompany =
    normalizedCompany === "" || z.uuid().safeParse(normalizedCompany).success;
  const dirty = !!data && normalizedCompany !== (data.company.company_id ?? "");
  const grants =
    data?.grants.filter((grant) =>
      customerGrantMatches(
        grant,
        business,
        data.company.company_id,
        project.location_id,
      ),
    ) ?? [];

  function reload() {
    setPrepared(null);
    setData(null);
    setPending(null);
    setGrantId("");
    setError("");
    setNotice("");
    setAttempt((value) => value + 1);
  }

  async function save(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (inFlight.current || !data || !validCompany) return;
    const body: CustomerCompanyBody = pending ?? {
      schema_version: 1,
      expected_revision: data.company.revision,
      expected_customer_generation: data.company.customer_generation,
      company_id: normalizedCompany || null,
    };
    inFlight.current = true;
    setBusy(true);
    setPending(body);
    setPrepared(null);
    setError("");
    setNotice("");
    try {
      const binding = await saveCustomerCompany(
        business,
        project.project_id,
        body,
      );
      setData({ company: binding, grants: data.grants });
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
    if (inFlight.current || pending || !data || dirty) return;
    inFlight.current = true;
    setBusy(true);
    setPrepared(null);
    setError("");
    setNotice("");
    try {
      const value = await read();
      setData(value);
      setCompany(value.company.company_id ?? "");
      const grant = value.grants.find((item) => item.grant_id === grantId);
      if (
        !grant ||
        !customerGrantMatches(
          grant,
          business,
          value.company.company_id,
          project.location_id,
        )
      )
        throw new ManagementApiError(
          "ACCESS_UNAVAILABLE",
          "This access is no longer available for the customer's company and project branch.",
        );
      setPrepared(
        customerDocumentLinks(
          { business, project: project.project_id, grant: grantId },
          changes,
        ),
      );
    } catch (failure) {
      setError(refusal(failure));
      setGrantId("");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={heading}>
      <h3 id={heading}>Customer access</h3>
      <p>
        Link this project&apos;s customer to its business account, then share
        document links with its named delegates.
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!data && !error && <p role="status">Loading customer access…</p>}
      <button
        type="button"
        className="secondary"
        disabled={busy}
        onClick={reload}
      >
        Reload customer access
      </button>
      {data && (
        <>
          <form
            aria-label="Customer company"
            onSubmit={(event) => void save(event)}
          >
            <label>
              Customer business ID
              <input
                value={company}
                disabled={busy || pending !== null}
                onChange={(event) => {
                  setCompany(event.target.value);
                  setPrepared(null);
                  setGrantId("");
                }}
                aria-describedby={`${heading}-company-help`}
              />
            </label>
            <p id={`${heading}-company-help`} className="muted">
              Ask the customer for its business ID. Leave this field blank to
              remove the link.
            </p>
            <button
              type="submit"
              disabled={busy || pending !== null || !validCompany || !dirty}
            >
              Save customer company
            </button>
          </form>
          {pending && !busy && (
            <button type="button" onClick={() => void save()}>
              Retry customer company
            </button>
          )}
          <p>
            <Link href="/business/">Manage delegated access</Link> to offer the
            customer the right to answer construction documents. The customer
            accepts and chooses its delegates.
          </p>
          {data.company.company_id && (
            <>
              <label>
                Customer access grant
                <select
                  value={grantId}
                  disabled={busy || pending !== null || dirty}
                  onChange={(event) => {
                    setGrantId(event.target.value);
                    setPrepared(null);
                  }}
                >
                  <option value="">Choose active access</option>
                  {grants.map((grant) => (
                    <option key={grant.grant_id} value={grant.grant_id}>
                      {grant.servicer_name ?? grant.servicer_business_id} ·{" "}
                      {grant.location_id ? "Project branch" : "All branches"} ·
                      expires {new Date(grant.expires_at).toLocaleString()}
                    </option>
                  ))}
                </select>
              </label>
              {grants.length === 0 && (
                <p>
                  No active customer access matches this company and project
                  branch.
                </p>
              )}
              <button
                type="button"
                disabled={
                  busy || pending !== null || dirty || !grantId || !hasProposal
                }
                onClick={() => void prepare()}
              >
                Prepare customer links
              </button>
              {!hasProposal && (
                <p>Propose an estimate before sharing customer documents.</p>
              )}
            </>
          )}
          {prepared && (
            <div>
              <p>
                Share these links with the customer&apos;s delegates. Access is
                checked again when each document is opened or answered.
              </p>
              <ul>
                {hasProposal && (
                  <li>
                    <a
                      href={prepared.proposal}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Customer proposal
                    </a>
                  </li>
                )}
                {prepared.changes.map((item) => (
                  <li key={item.number}>
                    <a href={item.href} target="_blank" rel="noreferrer">
                      Customer change order {item.number}
                    </a>
                  </li>
                ))}
                {hasContract && (
                  <li>
                    <a
                      href={prepared.acceptance}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Customer work acceptance
                    </a>
                  </li>
                )}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
