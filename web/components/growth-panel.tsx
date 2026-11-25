"use client";

import React, { useEffect, useId, useState } from "react";
import { money } from "../lib/api";
import {
  fetchGrowthSettings,
  fetchWaitlist,
  saveGrowthSettings,
  updateWaitlistEntryStatus,
  type WaitlistEntry,
} from "../lib/growth-api";

export function GrowthPanel({ salonId }: { salonId: string }) {
  const [googleReviewUrl, setGoogleReviewUrl] = useState("");
  const [reminderHours, setReminderHours] = useState(24);
  const [reviewDelayHours, setReviewDelayHours] = useState(2);
  const [rebookingDays, setRebookingDays] = useState(28);
  const [waitlistAutoOffer, setWaitlistAutoOffer] = useState(true);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [aiTone, setAiTone] = useState<
    "warm_professional" | "concise_direct" | "luxury_concierge"
  >("warm_professional");
  const [waitlist, setWaitlist] = useState<WaitlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const reviewId = useId();
  const remId = useId();
  const revDelayId = useId();
  const rebookId = useId();
  const toneId = useId();

  useEffect(() => {
    let active = true;
    Promise.all([fetchGrowthSettings(salonId), fetchWaitlist(salonId)])
      .then(([s, w]) => {
        if (!active) return;
        setGoogleReviewUrl(s.google_review_url ?? "");
        setReminderHours(s.reminder_hours_before);
        setReviewDelayHours(s.review_delay_hours);
        setRebookingDays(s.rebooking_days_after);
        setWaitlistAutoOffer(s.waitlist_auto_offer);
        setAiEnabled(s.ai_concierge_enabled);
        setAiTone(
          s.ai_concierge_tone as
            "warm_professional" | "concise_direct" | "luxury_concierge",
        );
        setWaitlist(w);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [salonId]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFeedback(null);
    setError(null);
    try {
      await saveGrowthSettings(salonId, {
        google_review_url: googleReviewUrl.trim() || null,
        reminder_hours_before: reminderHours,
        review_delay_hours: reviewDelayHours,
        rebooking_days_after: rebookingDays,
        waitlist_auto_offer: waitlistAutoOffer,
        ai_concierge_enabled: aiEnabled,
        ai_concierge_tone: aiTone,
      });
      setFeedback("Growth, Google Review, and AI Concierge settings saved.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleStatus(
    entryId: string,
    nextStatus: "booked" | "cancelled",
  ) {
    setError(null);
    try {
      const updated = await updateWaitlistEntryStatus(
        salonId,
        entryId,
        nextStatus,
      );
      setWaitlist((prev) =>
        prev.map((row) => (row.id === entryId ? updated : row)),
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <section
      aria-labelledby="growth-automation-heading"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        paddingTop: "16px",
        borderTop: "1px solid rgba(0,0,0,0.12)",
      }}
    >
      <div>
        <h3
          id="growth-automation-heading"
          style={{ margin: "0 0 6px", fontSize: "1.1rem" }}
        >
          AI Concierge, Google Reviews &amp; Smart Waitlist
        </h3>
        <p style={{ margin: 0, color: "#3f3832", fontSize: "0.9rem" }}>
          Control customer AI booking concierge, post-visit Google review
          booster, automated reminder cadence, and cancellation recovery
          waitlist.
        </p>
      </div>

      {error && (
        <div role="alert" className="mgmt-error-banner">
          {error}
        </div>
      )}
      {feedback && (
        <div
          role="status"
          style={{
            padding: "10px 12px",
            borderRadius: "6px",
            background: "#eef6ee",
            color: "#1b4d1b",
            border: "1px solid #b8d8b8",
            fontSize: "0.9rem",
          }}
        >
          {feedback}
        </div>
      )}

      {loading ? (
        <p style={{ color: "#3f3832" }}>Loading growth settings...</p>
      ) : (
        <>
          <form
            onSubmit={(e) => void handleSave(e)}
            className="mgmt-kpi-card"
            style={{ padding: "18px", display: "grid", gap: "14px" }}
          >
            <label htmlFor={reviewId} style={{ display: "grid", gap: "4px" }}>
              Google Business Profile Review URL (https://...)
              <input
                id={reviewId}
                type="url"
                value={googleReviewUrl}
                onChange={(e) => setGoogleReviewUrl(e.target.value)}
                placeholder="https://g.page/r/your-business/review"
              />
            </label>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
                gap: "12px",
              }}
            >
              <label htmlFor={remId} style={{ display: "grid", gap: "4px" }}>
                Reminder before visit (hours)
                <input
                  id={remId}
                  type="number"
                  min={1}
                  max={168}
                  value={reminderHours}
                  onChange={(e) => setReminderHours(Number(e.target.value))}
                />
              </label>
              <label
                htmlFor={revDelayId}
                style={{ display: "grid", gap: "4px" }}
              >
                Review request delay (hours)
                <input
                  id={revDelayId}
                  type="number"
                  min={0}
                  max={168}
                  value={reviewDelayHours}
                  onChange={(e) => setReviewDelayHours(Number(e.target.value))}
                />
              </label>
              <label htmlFor={rebookId} style={{ display: "grid", gap: "4px" }}>
                Rebooking nudge (days)
                <input
                  id={rebookId}
                  type="number"
                  min={7}
                  max={365}
                  value={rebookingDays}
                  onChange={(e) => setRebookingDays(Number(e.target.value))}
                />
              </label>
              <label htmlFor={toneId} style={{ display: "grid", gap: "4px" }}>
                AI Concierge tone
                <select
                  id={toneId}
                  value={aiTone}
                  onChange={(e) =>
                    setAiTone(
                      e.target.value as
                        | "warm_professional"
                        | "concise_direct"
                        | "luxury_concierge",
                    )
                  }
                >
                  <option value="warm_professional">
                    Warm &amp; Professional
                  </option>
                  <option value="concise_direct">Concise &amp; Direct</option>
                  <option value="luxury_concierge">Luxury Concierge</option>
                </select>
              </label>
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", gap: "18px" }}>
              <label
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
              >
                <input
                  type="checkbox"
                  checked={aiEnabled}
                  onChange={(e) => setAiEnabled(e.target.checked)}
                />
                Enable Customer AI Booking Concierge on /book/
              </label>
              <label
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
              >
                <input
                  type="checkbox"
                  checked={waitlistAutoOffer}
                  onChange={(e) => setWaitlistAutoOffer(e.target.checked)}
                />
                Suggest Smart Waitlist when slots are full
              </label>
            </div>

            <div>
              <button type="submit" disabled={saving}>
                {saving ? "Saving..." : "Save growth settings"}
              </button>
            </div>
          </form>

          <div>
            <h4 style={{ margin: "0 0 8px", fontSize: "1rem" }}>
              Active Waitlist Queue ({waitlist.length})
            </h4>
            <div className="mgmt-table-container" tabIndex={0}>
              <table className="mgmt-table">
                <thead>
                  <tr>
                    <th scope="col">Customer</th>
                    <th scope="col">Service</th>
                    <th scope="col">Preferred Day</th>
                    <th scope="col">Contact (masked)</th>
                    <th scope="col">Status</th>
                    <th scope="col">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {waitlist.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        style={{ textAlign: "center", color: "#3f3832" }}
                      >
                        No waitlist entries yet.
                      </td>
                    </tr>
                  ) : (
                    waitlist.map((w) => (
                      <tr key={w.id}>
                        <td>
                          <strong>{w.customer_name}</strong>
                          {w.notes && (
                            <div
                              style={{ fontSize: "0.8rem", color: "#3f3832" }}
                            >
                              {w.notes}
                            </div>
                          )}
                        </td>
                        <td>
                          {w.service_name} ({w.variant_name}) ·{" "}
                          {money(w.price_cents, w.currency)}
                        </td>
                        <td>
                          {w.preferred_day} ({w.preferred_window})
                        </td>
                        <td>
                          <code>{w.contact_masked}</code> ({w.contact_channel})
                        </td>
                        <td>
                          <span className="mgmt-status-pill status-draft">
                            {w.status}
                          </span>
                        </td>
                        <td>
                          {w.status === "waiting" || w.status === "offered" ? (
                            <div style={{ display: "flex", gap: "6px" }}>
                              <button
                                type="button"
                                className="secondary mgmt-btn-small"
                                onClick={() =>
                                  void handleStatus(w.id, "booked")
                                }
                              >
                                Mark booked
                              </button>
                              <button
                                type="button"
                                className="secondary mgmt-btn-small"
                                onClick={() =>
                                  void handleStatus(w.id, "cancelled")
                                }
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <span style={{ color: "#3f3832" }}>—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
