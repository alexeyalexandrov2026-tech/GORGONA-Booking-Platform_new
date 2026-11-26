"use client";

import { useEffect, useState } from "react";
import { ManagementApiError } from "../lib/management-api";
import {
  fetchUnitEconomics,
  formatMarginPercent,
  formatUsdCents,
  type UnitEconomics,
} from "../lib/unit-economics-api";
import "../app/us-release-v2.css";

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: UnitEconomics }
  | { kind: "unavailable" }
  | { kind: "forbidden" }
  | { kind: "error"; message: string };

/** Live 30-day unit economics in USD from GET /growth/unit-economics. */
export function UnitEconomicsCard({ businessId }: { businessId: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let active = true;
    fetchUnitEconomics(businessId)
      .then((data) => {
        if (!active) return;
        setState(data ? { kind: "ready", data } : { kind: "unavailable" });
      })
      .catch((err: unknown) => {
        if (!active) return;
        if (err instanceof ManagementApiError && err.status === 403) {
          setState({ kind: "forbidden" });
          return;
        }
        setState({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Unable to load unit economics.",
        });
      });
    return () => {
      active = false;
    };
  }, [businessId, tick]);

  const windowDays = state.kind === "ready" ? state.data.window_days : 30;

  return (
    <section
      className="mgmt-kpi-card usr-ue"
      aria-labelledby="unit-economics-heading"
      aria-busy={state.kind === "loading"}
    >
      <div className="usr-inline" style={{ justifyContent: "space-between" }}>
        <div>
          <h3
            id="unit-economics-heading"
            style={{ margin: 0, fontSize: "1.1rem" }}
          >
            Live Unit Economics
          </h3>
          <p className="usr-muted" style={{ margin: "4px 0 0" }}>
            Last {windowDays} days in USD, calculated live from your bookings.
          </p>
        </div>
        <button
          type="button"
          className="secondary usr-small-btn"
          disabled={state.kind === "loading"}
          onClick={() => {
            setState({ kind: "loading" });
            setTick((t) => t + 1);
          }}
        >
          {state.kind === "loading" ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {state.kind === "loading" && (
        <p
          className="usr-muted"
          aria-live="polite"
          style={{ margin: "16px 0 0" }}
        >
          Loading unit economics…
        </p>
      )}
      {state.kind === "unavailable" && (
        <p className="usr-muted" style={{ margin: "16px 0 0" }}>
          Unit economics are not available on this server yet.
        </p>
      )}
      {state.kind === "forbidden" && (
        <p className="usr-muted" style={{ margin: "16px 0 0" }}>
          Unit economics include material costs, so they are visible only to
          company-wide members with finance access.
        </p>
      )}
      {state.kind === "error" && (
        <div
          className="mgmt-error-banner"
          role="alert"
          style={{ margin: "16px 0 0" }}
        >
          <p style={{ margin: 0 }}>{state.message}</p>
        </div>
      )}
      {state.kind === "ready" &&
        (state.data.bookings_count_30d === 0 &&
        state.data.gross_revenue_cents === 0 ? (
          <p className="usr-muted" style={{ margin: "16px 0 0" }}>
            No bookings in the last {state.data.window_days} days yet. Revenue,
            costs, and margin appear here as soon as bookings are confirmed.
          </p>
        ) : (
          <dl className="usr-ue-grid">
            <div>
              <dt>Gross revenue</dt>
              <dd>{formatUsdCents(state.data.gross_revenue_cents)}</dd>
            </div>
            <div>
              <dt>Material COGS</dt>
              <dd>{formatUsdCents(state.data.material_cogs_cents)}</dd>
            </div>
            <div>
              <dt>Net margin</dt>
              <dd
                className={
                  state.data.net_margin_cents < 0 ? "usr-negative" : undefined
                }
              >
                {formatUsdCents(state.data.net_margin_cents)}
              </dd>
            </div>
            <div>
              <dt>Margin</dt>
              <dd
                className={
                  (state.data.margin_percent ?? 0) < 0
                    ? "usr-negative"
                    : undefined
                }
              >
                {formatMarginPercent(state.data.margin_percent)}
              </dd>
            </div>
            <div>
              <dt>Average ticket</dt>
              <dd>
                {state.data.average_ticket_cents === null
                  ? "—"
                  : formatUsdCents(state.data.average_ticket_cents)}
              </dd>
            </div>
            <div>
              <dt>Bookings ({state.data.window_days} days)</dt>
              <dd>
                {new Intl.NumberFormat("en-US").format(
                  state.data.bookings_count_30d,
                )}
              </dd>
            </div>
          </dl>
        ))}
    </section>
  );
}
