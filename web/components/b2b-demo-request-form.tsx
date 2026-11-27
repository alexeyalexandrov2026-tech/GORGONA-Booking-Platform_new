"use client";

import { useId, useState } from "react";
import "../app/us-release-v2.css";

const INDUSTRIES_SHORT = [
  "Transport & Logistics (NAICS 48-49)",
  "Construction & Field Services (NAICS 23)",
  "Commercial & Residential Property (NAICS 53)",
  "Equipment, Fleet & Yacht Rental (NAICS 532)",
  "Manufacturing, 3PL & Wholesale (NAICS 31-42)",
  "Professional, Legal & Advisory (NAICS 54)",
  "Hospitality, Food & Venues (NAICS 72)",
  "Healthcare, Wellness & Clinics (NAICS 62)",
  "Other US Industry (39 NAICS Supported)",
];

export function B2bDemoRequestForm({
  defaultIndustry = "Transport & Logistics (NAICS 48-49)",
  sourcePath = "/",
}: {
  defaultIndustry?: string;
  sourcePath?: string;
}) {
  const nameId = useId();
  const companyId = useId();
  const emailId = useId();
  const indId = useId();
  const sizeId = useId();
  const notesId = useId();

  const [fullName, setFullName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [workEmail, setWorkEmail] = useState("");
  const [industry, setIndustry] = useState(defaultIndustry);
  const [teamSize, setTeamSize] = useState("10-50");
  const [notes, setNotes] = useState("");
  const [website, setWebsite] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setConfirmation(null);
    setBusy(true);
    try {
      const res = await fetch("/v1/public/demo-requests", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          full_name: fullName.trim(),
          company_name: companyName.trim(),
          work_email: workEmail.trim(),
          industry,
          team_size: teamSize,
          notes: notes.trim(),
          source_path: sourcePath,
          website,
        }),
      });
      const data = (await res.json().catch(() => null)) as {
        message?: string;
        detail?: string;
      } | null;
      if (!res.ok) {
        throw new Error(
          data?.detail || "Could not submit your request. Please check fields.",
        );
      }
      setConfirmation(
        data?.message ||
          "Request received. Our team will reach out with a tailored B2B walkthrough.",
      );
      setFullName("");
      setCompanyName("");
      setWorkEmail("");
      setNotes("");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to send request right now.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="usr-card" style={{ marginBottom: 0 }}>
      <p className="lp-mono" style={{ marginTop: 0 }}>
        Founding B2B Partner Pilot
      </p>
      <h3 style={{ margin: "0 0 8px", fontSize: "1.45rem" }}>
        Request a tailored Business OS walkthrough
      </h3>
      <p className="usr-muted" style={{ marginTop: 0 }}>
        Tell us your NAICS industry and operational stack. We will prepare a
        live sandbox with your workflows, 0% transaction commission, and zero
        vendor lock-in.
      </p>

      {error && (
        <div className="usr-errors" role="alert">
          <p style={{ margin: 0 }}>{error}</p>
        </div>
      )}
      {confirmation && (
        <p role="status" className="hold-note">
          {confirmation}
        </p>
      )}

      <form onSubmit={(e) => void handleSubmit(e)} className="usr-stack">
        {/* Hidden anti-bot honeypot */}
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            left: "-10000px",
            width: "1px",
            height: "1px",
            overflow: "hidden",
          }}
        >
          <label>
            Website
            <input
              type="text"
              tabIndex={-1}
              autoComplete="off"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
            />
          </label>
        </div>

        <div className="usr-grid">
          <label htmlFor={nameId}>
            Full name
            <input
              id={nameId}
              type="text"
              required
              minLength={2}
              placeholder="Jordan Rivera"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </label>
          <label htmlFor={companyId}>
            Company name
            <input
              id={companyId}
              type="text"
              required
              minLength={2}
              placeholder="Midwest Freight Logistics LLC"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
            />
          </label>
          <label htmlFor={emailId}>
            Work email
            <input
              id={emailId}
              type="email"
              required
              placeholder="ops@yourcompany.us"
              value={workEmail}
              onChange={(e) => setWorkEmail(e.target.value)}
            />
          </label>
        </div>

        <div className="usr-grid">
          <label htmlFor={indId}>
            Primary industry (NAICS 2022)
            <select
              id={indId}
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
            >
              {INDUSTRIES_SHORT.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={sizeId}>
            Team size
            <select
              id={sizeId}
              value={teamSize}
              onChange={(e) => setTeamSize(e.target.value)}
            >
              <option value="1-9">1–9 team members</option>
              <option value="10-50">10–50 team members</option>
              <option value="51-250">51–250 team members</option>
              <option value="250+">250+ / Multi-entity group</option>
            </select>
          </label>
        </div>

        <label htmlFor={notesId}>
          What tools or workflows would you like to consolidate? (optional)
          <textarea
            id={notesId}
            rows={3}
            className="usr-textarea"
            style={{ minHeight: "88px" }}
            placeholder="e.g. Dispatch, B2B CPQ quotes, vendor PO 3-way match, FIN-03 accounting, Stripe ACH..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>

        <div className="usr-inline">
          <button type="submit" disabled={busy}>
            {busy ? "Sending request…" : "Request B2B Walkthrough"}
          </button>
          <span className="usr-muted">
            Direct response from Alexey AAA Logistics LLC · No obligation
          </span>
        </div>
      </form>
    </div>
  );
}
