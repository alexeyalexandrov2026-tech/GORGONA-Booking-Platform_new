"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import {
  decideAutonomyExecution,
  fetchAutonomyExecutions,
  fetchAutonomyPolicy,
  fetchPredictiveReports,
  generatePredictiveReport,
  runSafeAutonomyCycle,
  saveAutonomyPolicy,
  type AutonomyExecution,
  type AutonomyLevel,
  type AutonomyPolicy,
  type BriefWeekday,
  type PredictiveReport,
} from "../lib/autonomy-api";
import { formatDate, formatTime } from "../lib/management-api";
import "../app/us-release-v2.css";

const LEVEL_LABELS: Record<AutonomyLevel, string> = {
  observe_only: "Observe Only (AI suggests only)",
  strict_approval: "Strict Human Approval (every action queued)",
  safe_autopilot:
    "Safe Auto-Pilot (routine ops automated, finances Human-in-the-Loop)",
};

const ENGINE_LABELS: Record<string, string> = {
  cloudflare: "Cloudflare Llama 3.3 70B",
  gemini: "Google Gemini",
  byok_anthropic: "Anthropic Claude (BYOK)",
  byok_gemini: "Google Gemini (BYOK)",
  byok_openai: "OpenAI (BYOK)",
  grounded: "Grounded Live PG18",
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

export function SmartAutonomyPanel({ businessId }: { businessId: string }) {
  const [policy, setPolicy] = useState<AutonomyPolicy | null>(null);
  const [executions, setExecutions] = useState<AutonomyExecution[]>([]);
  const [reports, setReports] = useState<PredictiveReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [cycling, setCycling] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [busyExecId, setBusyExecId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Editable form state
  const [level, setLevel] = useState<AutonomyLevel>("observe_only");
  const [autoBookings, setAutoBookings] = useState(false);
  const [autoReminders, setAutoReminders] = useState(false);
  const [autoWaitlist, setAutoWaitlist] = useState(false);
  const [autoBrief, setAutoBrief] = useState(true);
  const [briefDay, setBriefDay] = useState<BriefWeekday>("monday");
  const [briefEmail, setBriefEmail] = useState("");
  const [periodDays, setPeriodDays] = useState(30);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [broadcastWebhooks, setBroadcastWebhooks] = useState(false);

  const levelId = useId();
  const dayId = useId();
  const emailId = useId();
  const periodId = useId();
  const webhookId = useId();

  useEffect(() => {
    let active = true;
    void Promise.all([
      fetchAutonomyPolicy(businessId),
      fetchAutonomyExecutions(businessId).catch(() => []),
      fetchPredictiveReports(businessId).catch(() => []),
    ])
      .then(([pol, execs, reps]) => {
        if (!active) return;
        setPolicy(pol);
        setLevel(pol.autonomy_level);
        setAutoBookings(pol.auto_confirm_open_bookings);
        setAutoReminders(pol.auto_send_invoice_reminders);
        setAutoWaitlist(pol.auto_offer_waitlist_slots);
        setAutoBrief(pol.auto_send_weekly_brief);
        setBriefDay(pol.weekly_brief_day);
        setBriefEmail(pol.weekly_brief_email ?? "");
        setExecutions(execs);
        setReports(reps);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(errText(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId]);

  async function onSavePolicy(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveAutonomyPolicy(businessId, {
        autonomy_level: level,
        auto_confirm_open_bookings: autoBookings,
        auto_send_invoice_reminders: autoReminders,
        auto_offer_waitlist_slots: autoWaitlist,
        auto_send_weekly_brief: autoBrief,
        weekly_brief_day: briefDay,
        weekly_brief_email: briefEmail.trim() || null,
      });
      setPolicy(saved);
      setNotice(
        `Smart Autonomy policy saved (${LEVEL_LABELS[saved.autonomy_level]}).`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSaving(false);
    }
  }

  async function onRunCycle() {
    setCycling(true);
    setError(null);
    setNotice(null);
    try {
      const created = await runSafeAutonomyCycle(businessId);
      const updated = await fetchAutonomyExecutions(businessId);
      setExecutions(updated);
      setNotice(
        created.length > 0
          ? `Safe autonomy sweep processed ${created.length} live item(s).`
          : "No overdue AR, waiting waitlist entries, or pending PO approvals found right now.",
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setCycling(false);
    }
  }

  async function onDecision(
    execId: string,
    decision: "approve" | "reject" | "rollback",
  ) {
    setBusyExecId(execId);
    setError(null);
    setNotice(null);
    try {
      const updated = await decideAutonomyExecution(
        businessId,
        execId,
        decision,
      );
      setExecutions((prev) =>
        prev.map((x) => (x.id === updated.id ? updated : x)),
      );
      setNotice(
        `Execution ${updated.target_reference} marked as ${updated.status}.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusyExecId(null);
    }
  }

  async function onGenerateReport(options: {
    sendEmail?: boolean;
    sendWebhook?: boolean;
  }) {
    setGenerating(true);
    setError(null);
    setNotice(null);
    try {
      const report = await generatePredictiveReport(businessId, {
        period_days: periodDays,
        send_email: options.sendEmail ?? false,
        recipient_email: briefEmail.trim() || undefined,
        webhook_url: options.sendWebhook
          ? webhookUrl.trim() || undefined
          : undefined,
        broadcast_to_webhooks: options.sendWebhook ? broadcastWebhooks : false,
      });
      setReports((prev) => [report, ...prev.slice(0, 9)]);
      const whDelivered = Number(
        report.metrics_snapshot["webhook_delivered_count"] ?? 0,
      );
      const whAttempted = Number(
        report.metrics_snapshot["webhook_attempted_count"] ?? 0,
      );
      const parts = [
        `Predictive executive brief generated (Health ${report.health_score}/100)`,
      ];
      if (report.emailed_to_masked) {
        parts.push(`emailed to ${report.emailed_to_masked}`);
      }
      if (whAttempted > 0) {
        parts.push(`delivered to ${whDelivered}/${whAttempted} webhook(s)`);
      }
      setNotice(`${parts.join(" · ")}.`);
    } catch (err) {
      setError(errText(err));
    } finally {
      setGenerating(false);
    }
  }

  const latestReport = reports[0] ?? null;

  return (
    <div className="usr-stack" style={{ margin: "20px 0" }}>
      <section className="usr-card" aria-labelledby="smart-autonomy-heading">
        <div className="usr-inline" style={{ justifyContent: "space-between" }}>
          <div>
            <h3 id="smart-autonomy-heading" style={{ margin: 0 }}>
              AI Smart Autonomy (Hybrid Trust Level)
            </h3>
            <p className="usr-muted" style={{ margin: "4px 0 0" }}>
              Delegate safe, reversible routine tasks to AI while keeping every
              dollar, contract, and Purchase Order strictly under
              Human-in-the-Loop approval.
            </p>
          </div>
          {policy && (
            <span
              className={`usr-badge ${
                policy.autonomy_level === "safe_autopilot"
                  ? "usr-badge-ai"
                  : "usr-badge-fallback"
              }`}
            >
              {policy.autonomy_level === "safe_autopilot"
                ? "Safe Auto-Pilot"
                : policy.autonomy_level === "strict_approval"
                  ? "Strict Approval"
                  : "Observe Only"}
            </span>
          )}
        </div>

        <p className="hold-note" style={{ margin: "12px 0" }}>
          <strong>Hard Financial Guardrail:</strong> All payments, refunds,
          contracts, and PO approvals above <strong>$0.00</strong> permanently
          require explicit human approval — regardless of autonomy mode.
        </p>

        {loading && (
          <p className="mgmt-loading" aria-live="polite">
            Loading AI Smart Autonomy settings…
          </p>
        )}

        {!loading && (
          <form
            onSubmit={(e) => void onSavePolicy(e)}
            aria-label="Configure AI Smart Autonomy policy"
          >
            <label htmlFor={levelId}>
              Trust level
              <select
                id={levelId}
                value={level}
                onChange={(e) => setLevel(e.target.value as AutonomyLevel)}
              >
                {Object.entries(LEVEL_LABELS).map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>
            </label>

            <fieldset className="usr-checks" style={{ marginTop: 12 }}>
              <legend>
                Allowed Safe Routine Actions (when Safe Auto-Pilot is active)
              </legend>
              <label className="usr-check">
                <input
                  type="checkbox"
                  checked={autoReminders}
                  onChange={(e) => setAutoReminders(e.target.checked)}
                />
                <span>Send overdue invoice &amp; AR payment reminders</span>
              </label>
              <label className="usr-check">
                <input
                  type="checkbox"
                  checked={autoWaitlist}
                  onChange={(e) => setAutoWaitlist(e.target.checked)}
                />
                <span>
                  Auto-offer open calendar slots to waiting waitlist clients
                </span>
              </label>
              <label className="usr-check">
                <input
                  type="checkbox"
                  checked={autoBookings}
                  onChange={(e) => setAutoBookings(e.target.checked)}
                />
                <span>
                  Auto-verify standard bookings when staff availability is open
                </span>
              </label>
              <label className="usr-check">
                <input
                  type="checkbox"
                  checked={autoBrief}
                  onChange={(e) => setAutoBrief(e.target.checked)}
                />
                <span>Send proactive weekly Predictive CFO Brief by email</span>
              </label>
            </fieldset>

            <div className="usr-grid" style={{ marginTop: 12 }}>
              <label htmlFor={dayId}>
                Weekly brief delivery day
                <select
                  id={dayId}
                  value={briefDay}
                  onChange={(e) => setBriefDay(e.target.value as BriefWeekday)}
                >
                  <option value="monday">Monday</option>
                  <option value="tuesday">Tuesday</option>
                  <option value="wednesday">Wednesday</option>
                  <option value="thursday">Thursday</option>
                  <option value="friday">Friday</option>
                  <option value="saturday">Saturday</option>
                  <option value="sunday">Sunday</option>
                </select>
              </label>
              <label htmlFor={emailId}>
                Executive brief email (optional)
                <input
                  id={emailId}
                  type="email"
                  maxLength={160}
                  value={briefEmail}
                  placeholder="owner@yourcompany.com"
                  onChange={(e) => setBriefEmail(e.target.value)}
                />
              </label>
            </div>

            <div className="usr-inline" style={{ marginTop: 12 }}>
              <button type="submit" disabled={saving}>
                {saving ? "Saving policy…" : "Save Smart Autonomy Policy"}
              </button>
              <button
                type="button"
                className="secondary usr-small-btn"
                disabled={cycling}
                onClick={() => void onRunCycle()}
              >
                {cycling ? "Scanning live ops…" : "Run Safe Autonomy Cycle"}
              </button>
            </div>
          </form>
        )}

        {executions.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <h4>Recent AI Autonomy Audit Log</h4>
            <div
              className="usr-table-wrap"
              tabIndex={0}
              aria-label="AI Autonomy executions"
            >
              <table className="usr-table">
                <thead>
                  <tr>
                    <th scope="col">Reference</th>
                    <th scope="col">Mode</th>
                    <th scope="col">Status</th>
                    <th scope="col">Summary</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {executions.slice(0, 8).map((ex) => (
                    <tr key={ex.id}>
                      <td>
                        <code>{ex.target_reference}</code>
                      </td>
                      <td>{ex.execution_mode.replace(/_/g, " ")}</td>
                      <td>
                        <span
                          className={`usr-badge ${
                            ex.status === "completed"
                              ? "usr-badge-ai"
                              : ex.status === "pending_approval"
                                ? "usr-badge-fallback"
                                : "usr-badge-off"
                          }`}
                        >
                          {ex.status.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td>{ex.summary}</td>
                      <td>
                        <div className="usr-inline">
                          {ex.status === "pending_approval" && (
                            <>
                              <button
                                type="button"
                                className="usr-small-btn"
                                disabled={busyExecId === ex.id}
                                onClick={() =>
                                  void onDecision(ex.id, "approve")
                                }
                              >
                                Approve
                              </button>
                              <button
                                type="button"
                                className="usr-danger usr-small-btn"
                                disabled={busyExecId === ex.id}
                                onClick={() => void onDecision(ex.id, "reject")}
                              >
                                Reject
                              </button>
                            </>
                          )}
                          {ex.status === "completed" && (
                            <button
                              type="button"
                              className="secondary usr-small-btn"
                              disabled={busyExecId === ex.id}
                              onClick={() => void onDecision(ex.id, "rollback")}
                            >
                              Rollback
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section
        className="usr-card"
        aria-labelledby="predictive-insights-heading"
      >
        <div className="usr-inline" style={{ justifyContent: "space-between" }}>
          <div>
            <h3 id="predictive-insights-heading" style={{ margin: 0 }}>
              Proactive Predictive Insights (AI CFO Brief)
            </h3>
            <p className="usr-muted" style={{ margin: "4px 0 0" }}>
              Automated anomaly detection across AR/AP aging, vendor PO 3-way
              variances, MRP II raw-material shortages, Predictive IoT Work
              Orders, Client Inbox backlog, US Payroll drafts, and
              Multi-Currency FX exposure.
            </p>
          </div>
          {latestReport && (
            <span
              className={`usr-badge ${
                latestReport.health_score >= 80
                  ? "usr-badge-ai"
                  : "usr-badge-fallback"
              }`}
            >
              Health {latestReport.health_score}/100 ·{" "}
              {ENGINE_LABELS[latestReport.engine] ?? latestReport.engine}
            </span>
          )}
        </div>

        {policy && (
          <p
            className="usr-muted"
            style={{ margin: "10px 0 0", fontSize: "0.86rem" }}
          >
            {policy.auto_send_weekly_brief
              ? `Automated Weekly Schedule: Active — runs every ${policy.weekly_brief_day.charAt(0).toUpperCase()}${policy.weekly_brief_day.slice(1)}${policy.weekly_brief_email ? ` (${policy.weekly_brief_email})` : ""} + active App Hub webhooks.`
              : "Automated Weekly Schedule: Paused — enable the weekly brief checkbox above to receive automatic executive digests."}
          </p>
        )}

        <div className="usr-grid" style={{ margin: "12px 0 8px" }}>
          <label htmlFor={webhookId}>
            Slack / Microsoft Teams / Zapier / n8n Webhook URL (optional)
            <input
              id={webhookId}
              type="url"
              maxLength={500}
              value={webhookUrl}
              placeholder="https://hooks.slack.com/services/..."
              onChange={(e) => setWebhookUrl(e.target.value)}
            />
          </label>
          <label
            className="usr-check"
            style={{ alignSelf: "end", paddingBottom: 8 }}
          >
            <input
              type="checkbox"
              checked={broadcastWebhooks}
              onChange={(e) => setBroadcastWebhooks(e.target.checked)}
            />
            <span>Also broadcast to active App Hub webhooks</span>
          </label>
        </div>

        <div className="usr-inline" style={{ margin: "8px 0 12px" }}>
          <label
            htmlFor={periodId}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              margin: 0,
            }}
          >
            <span>Window:</span>
            <select
              id={periodId}
              value={periodDays}
              onChange={(e) => setPeriodDays(Number(e.target.value))}
              style={{ width: "auto" }}
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={60}>Last 60 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          </label>
          <button
            type="button"
            disabled={generating}
            onClick={() => void onGenerateReport({ sendEmail: false })}
          >
            {generating ? "Analyzing PG18 data…" : "Generate Predictive Brief"}
          </button>
          <button
            type="button"
            className="secondary usr-small-btn"
            disabled={generating || !briefEmail.trim()}
            onClick={() => void onGenerateReport({ sendEmail: true })}
          >
            Generate &amp; Email Brief
          </button>
          <button
            type="button"
            className="secondary usr-small-btn"
            disabled={generating || (!webhookUrl.trim() && !broadcastWebhooks)}
            onClick={() =>
              void onGenerateReport({ sendEmail: false, sendWebhook: true })
            }
          >
            Send to Slack / Webhook
          </button>
        </div>

        {latestReport ? (
          <div className="usr-stack">
            <div className="hold-note" style={{ margin: 0 }}>
              <strong>{latestReport.headline}</strong>
              <p style={{ margin: "8px 0 0" }}>
                {latestReport.executive_summary}
              </p>
              <small className="usr-muted">
                Generated {formatDate(latestReport.created_at)}{" "}
                {formatTime(latestReport.created_at)}
                {latestReport.emailed_to_masked
                  ? ` · Emailed to ${latestReport.emailed_to_masked}`
                  : ""}
                {Number(
                  latestReport.metrics_snapshot["webhook_attempted_count"] ?? 0,
                ) > 0
                  ? ` · Webhooks ${String(latestReport.metrics_snapshot["webhook_delivered_count"] ?? 0)}/${String(latestReport.metrics_snapshot["webhook_attempted_count"])} delivered`
                  : ""}
              </small>
            </div>
            <ul
              className="usr-connector-grid"
              style={{ listStyle: "none", padding: 0, margin: 0 }}
            >
              {latestReport.signals.map((sig, idx) => (
                <li key={`${sig.category}-${idx}`} className="usr-connector">
                  <div
                    className="usr-inline"
                    style={{ justifyContent: "space-between" }}
                  >
                    <strong>{sig.title}</strong>
                    <span
                      className={`usr-badge ${
                        sig.severity === "positive"
                          ? "usr-badge-ai"
                          : "usr-badge-fallback"
                      }`}
                    >
                      {sig.metric_label}
                    </span>
                  </div>
                  <p style={{ margin: "6px 0" }}>{sig.recommendation}</p>
                  <Link
                    href={sig.action_path}
                    className="button secondary usr-small-btn"
                    style={{ alignSelf: "flex-start" }}
                  >
                    Inspect &amp; act →
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="usr-muted">
            Click <strong>Generate Predictive Brief</strong> to run a live
            cross-domain CFO anomaly audit across AR/AP, vendor variances,
            Stripe payments, and capacity.
          </p>
        )}

        {error && (
          <p className="usr-field-error" role="alert">
            {error}
          </p>
        )}
        <p role="status" className="usr-muted" style={{ marginBottom: 0 }}>
          {notice ?? ""}
        </p>
      </section>
    </div>
  );
}
