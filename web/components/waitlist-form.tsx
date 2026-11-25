"use client";

import React, { useId, useState } from "react";
import { joinCustomerWaitlist } from "../lib/growth-api";

export function WaitlistForm({
  locationId,
  variantId,
  resourceId,
  day,
}: {
  locationId: string;
  variantId: string;
  resourceId: string | null;
  day: string;
}) {
  const [name, setName] = useState("");
  const [channel, setChannel] = useState<"email" | "sms">("email");
  const [contact, setContact] = useState("");
  const [preferredWindow, setPreferredWindow] = useState<
    "any" | "morning" | "afternoon" | "evening"
  >("any");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [joinedMasked, setJoinedMasked] = useState<string | null>(null);

  const nameId = useId();
  const channelId = useId();
  const contactId = useId();
  const windowId = useId();
  const notesId = useId();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!variantId || !day) return;
    setSubmitting(true);
    setError(null);
    try {
      const entry = await joinCustomerWaitlist({
        location_id: locationId,
        variant_id: variantId,
        preferred_resource_id: resourceId,
        preferred_day: day,
        preferred_window: preferredWindow,
        customer_name: name.trim(),
        contact_channel: channel,
        contact_value: contact.trim(),
        notes: notes.trim(),
      });
      setJoinedMasked(entry.contact_masked);
      setName("");
      setContact("");
      setNotes("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <details
      className="policy"
      style={{
        marginTop: "16px",
        padding: "12px 14px",
        borderRadius: "8px",
        border: "1px solid var(--line)",
        background: "var(--ivory)",
      }}
    >
      <summary style={{ cursor: "pointer", fontWeight: 600, color: "#1f1a17" }}>
        Don&apos;t see your ideal time? Join the Smart Waitlist
      </summary>
      <div style={{ marginTop: "12px" }}>
        {joinedMasked ? (
          <p
            role="status"
            style={{
              margin: 0,
              padding: "10px 12px",
              borderRadius: "6px",
              background: "#eef6ee",
              color: "#1b4d1b",
              border: "1px solid #b8d8b8",
            }}
          >
            You&apos;re on the waitlist for {day}. We will alert {joinedMasked}{" "}
            if a matching opening appears.
          </p>
        ) : (
          <form
            onSubmit={(e) => void handleSubmit(e)}
            style={{ display: "grid", gap: "10px" }}
          >
            {error && (
              <p role="alert" className="error" style={{ margin: 0 }}>
                {error}
              </p>
            )}
            <label htmlFor={nameId}>
              Your name
              <input
                id={nameId}
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={160}
              />
            </label>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
                gap: "10px",
              }}
            >
              <label htmlFor={windowId}>
                Preferred time of day
                <select
                  id={windowId}
                  value={preferredWindow}
                  onChange={(e) =>
                    setPreferredWindow(
                      e.target.value as
                        "any" | "morning" | "afternoon" | "evening",
                    )
                  }
                >
                  <option value="any">Any time</option>
                  <option value="morning">Morning (before 12 PM)</option>
                  <option value="afternoon">Afternoon (12–5 PM)</option>
                  <option value="evening">Evening (after 5 PM)</option>
                </select>
              </label>
              <label htmlFor={channelId}>
                Notify via
                <select
                  id={channelId}
                  value={channel}
                  onChange={(e) =>
                    setChannel(e.target.value as "email" | "sms")
                  }
                >
                  <option value="email">Email</option>
                  <option value="sms">SMS (+1...)</option>
                </select>
              </label>
            </div>
            <label htmlFor={contactId}>
              {channel === "email" ? "Email address" : "Mobile number (E.164)"}
              <input
                id={contactId}
                type={channel === "email" ? "email" : "tel"}
                value={contact}
                onChange={(e) => setContact(e.target.value)}
                placeholder={
                  channel === "email" ? "you@example.com" : "+13055550199"
                }
                required
              />
            </label>
            <label htmlFor={notesId}>
              Optional notes
              <input
                id={notesId}
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                maxLength={400}
                placeholder="Flexible timing or special request"
              />
            </label>
            <button type="submit" disabled={submitting}>
              {submitting ? "Joining waitlist..." : "Join waitlist"}
            </button>
          </form>
        )}
      </div>
    </details>
  );
}
