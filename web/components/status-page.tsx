"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AmarkalLogo } from "./amarkal-logo";
import "../app/us-release-v2.css";

interface StatusComponent {
  id: string;
  name: string;
  status: string;
}

interface SystemStatusPayload {
  service: string;
  operator: string;
  overall: "operational" | "degraded";
  checked_at: string;
  components: StatusComponent[];
  security_invariants: string[];
}

export function StatusPageClient() {
  const [data, setData] = useState<SystemStatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let active = true;
    void fetch("/v1/status", { cache: "no-store" })
      .then(async (res) => {
        const body = (await res.json()) as SystemStatusPayload;
        if (active) {
          setData(body);
          setError(null);
        }
      })
      .catch(() => {
        if (active) {
          setError("Unable to reach the live status telemetry endpoint.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tick]);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#fbfbfd",
        padding: "24px 16px 56px",
      }}
    >
      <div style={{ maxWidth: "860px", margin: "0 auto" }}>
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "12px",
            marginBottom: "28px",
          }}
        >
          <Link href="/" style={{ textDecoration: "none" }}>
            <AmarkalLogo variant="light" height={22} />
          </Link>
          <div className="usr-inline">
            <button
              type="button"
              className="secondary usr-small-btn"
              onClick={() => {
                setLoading(true);
                setTick((t) => t + 1);
              }}
            >
              Refresh telemetry
            </button>
            <Link
              href="/overview/"
              className="button secondary usr-small-btn"
              style={{ textDecoration: "none" }}
            >
              Open Workspace
            </Link>
          </div>
        </header>

        <main id="main-content">
          <section className="usr-card" aria-labelledby="status-title">
            <div
              className="usr-inline"
              style={{ justifyContent: "space-between" }}
            >
              <div>
                <h1 id="status-title" style={{ margin: "0 0 6px" }}>
                  AMARKAL System Status &amp; Trust
                </h1>
                <p className="usr-muted" style={{ margin: 0 }}>
                  Live operational telemetry verified directly against
                  PostgreSQL 18 and production runtime dependencies.
                </p>
              </div>
              {data && (
                <span
                  className={
                    "usr-badge " +
                    (data.overall === "operational"
                      ? "usr-badge-ai"
                      : "usr-badge-fallback")
                  }
                >
                  {data.overall === "operational"
                    ? "All Systems Operational"
                    : "Degraded Performance"}
                </span>
              )}
            </div>

            {loading ? (
              <p className="usr-muted" style={{ marginTop: "20px" }}>
                Checking live services…
              </p>
            ) : error ? (
              <div
                className="usr-errors"
                role="alert"
                style={{ marginTop: "20px" }}
              >
                <p style={{ margin: 0 }}>{error}</p>
              </div>
            ) : data ? (
              <>
                <div
                  className="usr-table-wrap"
                  style={{ marginTop: "20px" }}
                  tabIndex={0}
                >
                  <table className="usr-table">
                    <thead>
                      <tr>
                        <th scope="col">Subsystem</th>
                        <th scope="col">Live State</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.components.map((comp) => (
                        <tr key={comp.id}>
                          <td>
                            <strong>{comp.name}</strong>
                          </td>
                          <td>
                            <span
                              className={
                                "usr-badge " +
                                (comp.status === "operational"
                                  ? "usr-badge-ai"
                                  : comp.status.startsWith("standby")
                                    ? "usr-badge-off"
                                    : "usr-badge-fallback")
                              }
                            >
                              {comp.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <h2 style={{ marginTop: "28px" }}>
                  Verified Security &amp; Governance Invariants
                </h2>
                <ul
                  style={{
                    margin: "8px 0 0",
                    paddingLeft: "20px",
                    display: "grid",
                    gap: "6px",
                  }}
                >
                  {data.security_invariants.map((inv) => (
                    <li key={inv}>{inv}</li>
                  ))}
                </ul>

                <p className="usr-muted" style={{ marginTop: "20px" }}>
                  Operated by {data.operator} · Last verified:{" "}
                  {new Date(data.checked_at).toLocaleString()} · Open A2A
                  discovery:{" "}
                  <a href="/.well-known/agent.json">/.well-known/agent.json</a>
                </p>
              </>
            ) : null}
          </section>
        </main>
      </div>
    </div>
  );
}
