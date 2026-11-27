"use client";

import { useState } from "react";

interface ScheduleRow {
  readonly label: string;
  readonly width: string;
  readonly offset?: string;
  readonly tone: "blue" | "gold";
  readonly tag: string;
}

interface WorkspacePreset {
  readonly id: string;
  readonly pill: string;
  readonly company: string;
  readonly bookingsLabel: string;
  readonly bookingsValue: string;
  readonly revenueValue: string;
  readonly calendarTitle: string;
  readonly rows: readonly ScheduleRow[];
  readonly aiQuestion: string;
  readonly aiReply: string;
  readonly floatTitle: string;
  readonly floatBody: string;
  readonly floatAction: string;
}

const PRESETS: readonly WorkspacePreset[] = [
  {
    id: "yacht",
    pill: "Yacht Charter",
    company: "Harbor Yacht Co.",
    bookingsLabel: "Bookings today",
    bookingsValue: "24",
    revenueValue: "$48,210",
    calendarTitle: "Fleet calendar · Sat",
    rows: [
      { label: "Aurora 42′", width: "56%", tone: "blue", tag: "10:00–16:00" },
      {
        label: "Sea Glass",
        width: "36%",
        offset: "14%",
        tone: "gold",
        tag: "11:30–14:30",
      },
      { label: "Nomad 38′", width: "70%", tone: "blue", tag: "09:00–17:30" },
      {
        label: "Tender 1",
        width: "28%",
        offset: "28%",
        tone: "gold",
        tag: "13:00–15:30",
      },
    ],
    aiQuestion: "Can I book a sunset charter for 8 on Saturday?",
    aiReply:
      "Aurora 42′ is free 6:00–9:00 PM. $1,450 · deposit 30%. Shall I hold it?",
    floatTitle: "Shift swap",
    floatBody: "Captain M. Reyes ⇄ J. Park",
    floatAction: "Approve",
  },
  {
    id: "freight",
    pill: "Freight & Logistics",
    company: "Apex Freight LLC",
    bookingsLabel: "Active loads",
    bookingsValue: "18",
    revenueValue: "$94,650",
    calendarTitle: "Dispatch board · Fri",
    rows: [
      {
        label: "Unit #402",
        width: "66%",
        tone: "blue",
        tag: "DAL → ATL · POD",
      },
      {
        label: "Unit #118",
        width: "44%",
        offset: "10%",
        tone: "gold",
        tag: "CHI → MEM",
      },
      {
        label: "Reefer #09",
        width: "58%",
        offset: "6%",
        tone: "blue",
        tag: "MIA → CLT",
      },
      {
        label: "Flatbed #4",
        width: "34%",
        offset: "24%",
        tone: "gold",
        tag: "HOU → AUS",
      },
    ],
    aiQuestion: "Which dry vans have open capacity in Dallas tomorrow?",
    aiReply:
      "Unit #402 clears Dallas dock at 14:00 CT. Drafted FIN-03 rate con ($2,850).",
    floatTitle: "Stripe settlement",
    floatBody: "Invoice #INV-4092 · $2,850",
    floatAction: "Match FIN-03",
  },
  {
    id: "hospitality",
    pill: "Property & Studio",
    company: "Mercer Suites NY",
    bookingsLabel: "Confirmed stays",
    bookingsValue: "31",
    revenueValue: "$32,940",
    calendarTitle: "Operations grid · Thu",
    rows: [
      { label: "Loft 4A", width: "62%", tone: "blue", tag: "Checked in" },
      {
        label: "Suite 8B",
        width: "40%",
        offset: "18%",
        tone: "gold",
        tag: "Housekeeping",
      },
      { label: "Studio 2C", width: "52%", tone: "blue", tag: "VIP arrival" },
      {
        label: "Penthouse",
        width: "36%",
        offset: "26%",
        tone: "gold",
        tag: "Inspection",
      },
    ],
    aiQuestion: "Extend Loft 4A by one night and send a Stripe link?",
    aiReply:
      "Loft 4A is open Friday ($480 USD, 0% fee). Checkout link ready for approval.",
    floatTitle: "AI proposal",
    floatBody: "Send checkout link · $480",
    floatAction: "Confirm",
  },
];

const SIDEBAR_ITEMS = [
  "Overview",
  "Calendar",
  "Orders",
  "Clients",
  "Staff & shifts",
  "Finance",
  "App Hub",
] as const;

export function MonolithHeroStage() {
  const [activeId, setActiveId] = useState<string>("yacht");
  const [approved, setApproved] = useState(false);

  const preset = PRESETS.find((item) => item.id === activeId) ?? PRESETS[0]!;

  return (
    <div className="lp-stage-wrap">
      <div
        className="lp-stage-switcher"
        role="tablist"
        aria-label="Preview AMARKAL workspace by industry"
      >
        {PRESETS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === preset.id}
            className="lp-stage-pill"
            onClick={() => {
              setActiveId(item.id);
              setApproved(false);
            }}
          >
            {item.pill}
          </button>
        ))}
      </div>

      <div className="lp-stage">
        <div className="lp-win">
          <aside className="lp-win-side" aria-label="Workspace modules preview">
            <div className="lp-mono lp-win-company">{preset.company}</div>
            <ul className="lp-win-menu">
              {SIDEBAR_ITEMS.map((label, idx) => (
                <li key={label} className={idx === 0 ? "is-active" : undefined}>
                  {label}
                </li>
              ))}
            </ul>
          </aside>

          <div className="lp-win-main">
            <div className="lp-win-kpis">
              <div className="lp-win-kpi">
                <span className="lp-mono">{preset.bookingsLabel}</span>
                <strong>{preset.bookingsValue}</strong>
              </div>
              <div className="lp-win-kpi">
                <span className="lp-mono">Revenue · USD</span>
                <strong>{preset.revenueValue}</strong>
              </div>
              <div className="lp-win-kpi">
                <span className="lp-mono">Commission</span>
                <strong className="lp-win-kpi--gold">0%</strong>
              </div>
            </div>

            <div className="lp-win-grid">
              <div className="lp-win-cal">
                <div className="lp-win-cal-head">
                  <span className="lp-mono">{preset.calendarTitle}</span>
                  <span className="lp-win-cal-live">Live occupancy</span>
                </div>
                <div className="lp-win-rows">
                  {preset.rows.map((row) => (
                    <div key={row.label} className="lp-win-row">
                      <span className="lp-win-row-label">{row.label}</span>
                      <div className="lp-win-bar-track">
                        <span
                          className={
                            "lp-win-bar" +
                            (row.tone === "gold" ? " lp-win-bar--gold" : "")
                          }
                          style={{
                            width: row.width,
                            marginLeft: row.offset ?? "0%",
                          }}
                        >
                          <span className="lp-win-bar-tag">{row.tag}</span>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="lp-win-ai">
                <div className="lp-mono lp-win-ai-label">
                  AMARKAL AI Assistant
                </div>
                <div className="lp-win-ai-q">{preset.aiQuestion}</div>
                <p className="lp-win-ai-a">{preset.aiReply}</p>
                <div className="lp-win-ai-status">
                  <span aria-hidden="true">●</span> Awaiting your approval
                </div>
              </div>
            </div>

            <div className="lp-win-float-bar">
              <div className="lp-win-float-card">
                <div className="lp-win-float-copy">
                  <span className="lp-mono">{preset.floatTitle}</span>
                  <strong>{preset.floatBody}</strong>
                </div>
                <button
                  type="button"
                  className={
                    "lp-win-float-btn" + (approved ? " is-approved" : "")
                  }
                  onClick={() => setApproved((prev) => !prev)}
                >
                  {approved ? "Approved ✓" : preset.floatAction}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <p className="lp-mono lp-stage-caption">
        Interactive preview · Illustrative US workspace data
      </p>
    </div>
  );
}
