"use client";

// O7a (package O): the construction list, the project form and the project page. Every figure the
// screen shows is the server's (totals and contract sums are derived there, never added up here); a
// command keeps its record id and Idempotency-Key until it succeeds (ADR-0030).
import React, { useCallback, useEffect, useId, useState } from "react";
import { fetchCounterparties } from "../lib/counterparty-api";
import { fetchWorkspace, type LocationItem } from "../lib/management-api";
import {
  fetchAllProjects,
  fetchBudget,
  fetchChangeOrders,
  fetchCommitments,
  fetchDailyReports,
  fetchMeasurements,
  fetchProgress,
  fetchSchedule,
  fetchContract,
  fetchEstimate,
  fetchEstimates,
  fetchProject,
  refusal,
  saveProject,
} from "../lib/construction-api";
import type {
  Budget,
  ChangeOrderSummary,
  CommitmentSummary,
  DailyReportList,
  Measurement,
  Progress,
  Schedule,
  Contract,
  Estimate,
  EstimateSummary,
  Project,
} from "../lib/construction-contracts";
import { currencyPlaces } from "../lib/construction-rules";
import {
  ContractPanel,
  EstimateEditor,
  Estimates,
} from "./construction-estimates";
import { ChangeOrders } from "./construction-changes";
import { BudgetPanel, Commitments } from "./construction-budget";
import {
  DailyReports,
  ProgressPanel,
  SchedulePanel,
} from "./construction-execution";

export type Customer = { id: string; name: string };
/** An active counterparty with its roles (customer, contractor, supplier, ...). */
export type Party = Customer & { roles: string[] };

async function allParties(businessId: string): Promise<Party[]> {
  const parties: Party[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await fetchCounterparties(businessId, "", "active", after);
    for (const c of page.items)
      parties.push({
        id: c.counterparty_id,
        name: c.display_name,
        roles: c.roles,
      });
    if (!page.next_cursor) return parties;
    after = page.next_cursor;
  }
}

function upsert(list: Project[], item: Project): Project[] {
  return list.some((x) => x.project_id === item.project_id)
    ? list.map((x) => (x.project_id === item.project_id ? item : x))
    : [...list, item];
}

export function ConstructionScreen({ businessId }: { businessId: string }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Project | null>(null);
  const [editing, setEditing] = useState<Project | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchAllProjects(businessId),
      // Without the counterparties module there is no customer to choose; the list still works.
      allParties(businessId).catch(() => [] as Party[]),
      fetchWorkspace(businessId).then((w) => w.locations),
    ])
      .then(([list, people, places]) => {
        if (!live) return;
        setProjects(list);
        setParties(people);
        setLocations(places);
        setLoaded(true);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The projects could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [businessId]);

  const customerName = useCallback(
    (id: string) =>
      parties.find((c) => c.id === id)?.name ?? "Unknown customer",
    [parties],
  );
  const branchName = (id: string) =>
    locations.find((l) => l.id === id)?.name ?? "Unknown branch";
  const changed = useCallback((project: Project) => {
    setProjects((list) => upsert(list, project));
    setSelected((current) =>
      current?.project_id === project.project_id ? project : current,
    );
  }, []);

  async function open(project: Project) {
    setError(null);
    try {
      setSelected(await fetchProject(businessId, project.project_id));
    } catch (failure) {
      setError(`The project could not be read: ${refusal(failure)}`);
    }
  }

  return (
    <div className="construction-screen">
      <h1>Construction</h1>
      <p className="muted">
        Projects with their estimate versions, the customer&apos;s contract and
        change orders.
      </p>
      <p className="construction-status" role="status">
        {notice}
      </p>
      {!loaded && !error && (
        <p className="muted" role="status">
          Loading the projects…
        </p>
      )}
      {loaded &&
        (projects.length === 0 ? (
          <p className="muted">No projects yet.</p>
        ) : (
          <div
            className="mgmt-table-container"
            role="region"
            aria-label="Projects table"
            tabIndex={0}
          >
            <table className="mgmt-table" aria-label="Projects">
              <thead>
                <tr>
                  <th scope="col">Number</th>
                  <th scope="col">Name</th>
                  <th scope="col">Customer</th>
                  <th scope="col">Branch</th>
                  <th scope="col">Currency</th>
                  <th scope="col">Latest estimate</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((project) => (
                  <tr key={project.project_id}>
                    <th scope="row">
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => void open(project)}
                      >
                        {project.number}
                      </button>
                    </th>
                    <td>{project.name}</td>
                    <td>{customerName(project.customer_id)}</td>
                    <td>{branchName(project.location_id)}</td>
                    <td>{project.currency}</td>
                    <td>
                      {project.latest_version
                        ? `Version ${project.latest_version}`
                        : "None"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {selected && (
        <ProjectPage
          key={selected.project_id}
          businessId={businessId}
          project={selected}
          customerName={customerName(selected.customer_id)}
          branchName={branchName(selected.location_id)}
          parties={parties}
          onChange={changed}
          onEdit={setEditing}
          notify={setNotice}
        />
      )}
      {loaded && (
        <ProjectForm
          key={editing?.project_id ?? "new"}
          businessId={businessId}
          editing={editing}
          customers={parties.filter((p) => p.roles.includes("customer"))}
          locations={locations}
          onSaved={(project) => {
            changed(project);
            setEditing(null);
            setNotice(`Project ${project.number} saved.`);
          }}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function ProjectForm({
  businessId,
  editing,
  customers,
  locations,
  onSaved,
  onCancel,
}: {
  businessId: string;
  editing: Project | null;
  customers: Customer[];
  locations: LocationItem[];
  onSaved: (project: Project) => void;
  onCancel: () => void;
}) {
  const headingId = useId();
  // A new project keeps its id until the save succeeds, so a retry saves it once.
  const [projectId, setProjectId] = useState(
    () => editing?.project_id ?? crypto.randomUUID(),
  );
  const [number, setNumber] = useState(editing?.number ?? "");
  const [name, setName] = useState(editing?.name ?? "");
  const [customer, setCustomer] = useState(editing?.customer_id ?? "");
  const [location, setLocation] = useState(editing?.location_id ?? "");
  const [address, setAddress] = useState(editing?.site_address ?? "");
  const [zone, setZone] = useState(editing?.time_zone ?? "");
  const [currency, setCurrency] = useState(editing?.currency ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const saved = await saveProject(businessId, projectId, {
        schema_version: 1,
        expected_revision: editing?.revision ?? 0,
        number: number.trim(),
        name: name.trim(),
        customer_id: customer,
        location_id: location,
        site_address: address.trim(),
        time_zone: zone.trim(),
        currency: currency.trim().toUpperCase(),
      });
      onSaved(saved);
      if (!editing) {
        setProjectId(crypto.randomUUID());
        setNumber("");
        setName("");
        setAddress("");
      }
    } catch (failure) {
      setError(`The project was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h2 id={headingId}>
        {editing ? `Edit project ${editing.number}` : "New project"}
      </h2>
      <form aria-label="Project" onSubmit={submit}>
        <label>
          Number
          <input
            value={number}
            maxLength={64}
            onChange={(e) => setNumber(e.target.value)}
            required
          />
        </label>
        <label>
          Name
          <input
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <label>
          Customer
          <select
            value={customer}
            onChange={(e) => setCustomer(e.target.value)}
            required
          >
            <option value="">Choose</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Branch
          <select
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            required
          >
            <option value="">Choose</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Site address
          <input
            value={address}
            maxLength={500}
            onChange={(e) => setAddress(e.target.value)}
            required
          />
        </label>
        <label>
          Time zone
          <input
            value={zone}
            maxLength={64}
            placeholder="America/Chicago"
            onChange={(e) => setZone(e.target.value)}
            required
          />
        </label>
        <label>
          Currency
          <input
            value={currency}
            maxLength={3}
            pattern="[A-Za-z]{3}"
            placeholder="USD"
            onChange={(e) => setCurrency(e.target.value)}
            required
          />
        </label>
        <div className="mgmt-form-actions">
          {editing && (
            <button type="button" onClick={onCancel}>
              New project instead
            </button>
          )}
          <button type="submit" disabled={busy}>
            Save project
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

/** What the project page knows; every part is the server's answer. */
type Loaded = {
  estimates: EstimateSummary[];
  latest: Estimate | null;
  contract: Contract | null;
  original: Estimate | null;
  orders: ChangeOrderSummary[];
  /** O7b: present once the project has a contract. */
  execution: Execution | null;
};
type Execution = {
  budget: Budget;
  commitments: CommitmentSummary[];
  schedule: Schedule;
  reports: DailyReportList["items"];
  progress: Progress;
  measurements: Measurement[];
};

async function loadExecution(
  businessId: string,
  id: string,
): Promise<Execution> {
  const [budget, commitments, schedule, reports, progress, measurements] =
    await Promise.all([
      fetchBudget(businessId, id),
      fetchCommitments(businessId, id),
      fetchSchedule(businessId, id),
      fetchDailyReports(businessId, id),
      fetchProgress(businessId, id),
      fetchMeasurements(businessId, id),
    ]);
  return { budget, commitments, schedule, reports, progress, measurements };
}

/** Everything the project page shows, read from the server; nothing is set here. */
async function loadProject(
  businessId: string,
  id: string,
): Promise<{ fresh: Project; loaded: Loaded }> {
  const fresh = await fetchProject(businessId, id);
  const [list, contract] = await Promise.all([
    fetchEstimates(businessId, id),
    fetchContract(businessId, id),
  ]);
  const [latest, original, orders, execution] = await Promise.all([
    fresh.latest_version
      ? fetchEstimate(businessId, id, fresh.latest_version)
      : Promise.resolve(null),
    contract
      ? fetchEstimate(businessId, id, contract.version)
      : Promise.resolve(null),
    contract
      ? fetchChangeOrders(businessId, id).then((o) => o.items)
      : Promise.resolve([] as ChangeOrderSummary[]),
    contract ? loadExecution(businessId, id) : Promise.resolve(null),
  ]);
  return {
    fresh,
    loaded: {
      estimates: list.items,
      latest,
      contract,
      original,
      orders,
      execution,
    },
  };
}

function ProjectPage({
  businessId,
  project,
  customerName,
  branchName,
  parties,
  onChange,
  onEdit,
  notify,
}: {
  businessId: string;
  project: Project;
  customerName: string;
  branchName: string;
  parties: Party[];
  onChange: (project: Project) => void;
  onEdit: (project: Project) => void;
  notify: (text: string) => void;
}) {
  const headingId = useId();
  const [state, setState] = useState<Loaded | null>(null);
  const [shown, setShown] = useState<Estimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const places = currencyPlaces(project.currency) ?? 2;
  const id = project.project_id;

  const apply = useCallback(
    ({ fresh, loaded }: { fresh: Project; loaded: Loaded }) => {
      onChange(fresh);
      setState(loaded);
      setShown(loaded.latest);
    },
    [onChange],
  );

  useEffect(() => {
    let live = true;
    loadProject(businessId, id)
      .then((result) => {
        if (live) apply(result);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The project could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [businessId, id, apply]);

  /** After a command: the server's new state, or why it could not be read. */
  const refresh = useCallback(
    async (text: string) => {
      notify(text);
      try {
        setError(null);
        apply(await loadProject(businessId, id));
      } catch (failure) {
        setError(`The project could not be read: ${refusal(failure)}`);
      }
    },
    [notify, apply, businessId, id],
  );

  async function show(version: number) {
    setError(null);
    try {
      setShown(await fetchEstimate(businessId, id, version));
    } catch (failure) {
      setError(`The version could not be read: ${refusal(failure)}`);
    }
  }

  return (
    <section className="construction-project" aria-labelledby={headingId}>
      <h2 id={headingId}>{`Project ${project.number}`}</h2>
      <p>
        {project.name} · {customerName} · {branchName}
      </p>
      <p className="muted">
        Site: {project.site_address} · {project.time_zone} · {project.currency}
      </p>
      <div className="mgmt-form-actions">
        <button type="button" onClick={() => onEdit(project)}>
          Edit project
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!state && !error && (
        <p className="muted" role="status">
          Loading the project…
        </p>
      )}
      {state && (
        <>
          <Estimates
            businessId={businessId}
            project={project}
            places={places}
            estimates={state.estimates}
            shown={shown}
            contracted={state.contract !== null}
            onShow={(version) => void show(version)}
            onChanged={refresh}
          />
          {!state.contract && (
            <EstimateEditor
              key={`${id}:${project.latest_version}`}
              businessId={businessId}
              project={project}
              places={places}
              latest={state.latest}
              onSaved={(version) =>
                void refresh(`Version ${version} of ${project.number} saved.`)
              }
            />
          )}
          <ContractPanel
            businessId={businessId}
            project={project}
            places={places}
            estimates={state.estimates}
            contract={state.contract}
            onChanged={refresh}
          />
          {state.contract && state.original && (
            <ChangeOrders
              businessId={businessId}
              project={project}
              places={places}
              original={state.original}
              orders={state.orders}
              onChanged={refresh}
            />
          )}
          {state.execution && (
            <>
              <BudgetPanel
                project={project}
                places={places}
                budget={state.execution.budget}
              />
              <Commitments
                businessId={businessId}
                project={project}
                places={places}
                budget={state.execution.budget}
                commitments={state.execution.commitments}
                parties={parties}
                onChanged={refresh}
              />
              <SchedulePanel
                key={`schedule:${state.execution.schedule.revision}`}
                businessId={businessId}
                project={project}
                schedule={state.execution.schedule}
                phases={state.execution.budget.phases.map((p) => p.phase)}
                onChanged={refresh}
              />
              <DailyReports
                businessId={businessId}
                project={project}
                reports={state.execution.reports}
                onChanged={refresh}
              />
              <ProgressPanel
                businessId={businessId}
                project={project}
                places={places}
                progress={state.execution.progress}
                measurements={state.execution.measurements}
                onChanged={refresh}
              />
            </>
          )}
        </>
      )}
    </section>
  );
}
