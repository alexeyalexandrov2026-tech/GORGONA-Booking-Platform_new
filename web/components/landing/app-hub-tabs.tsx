"use client";

import { useState } from "react";
import { LandingTabs, type TabSpec } from "./landing-tabs";

type TabKey = "keys" | "webhooks" | "mcp";

const SCOPES = [
  "mcp:read",
  "bookings:read",
  "bookings:write",
  "catalog:read",
  "finance:read",
  "webhooks:manage",
] as const;

const EVENTS = [
  "booking.created",
  "booking.cancelled",
  "waitlist.joined",
  "invoice.issued",
  "payment.recorded",
] as const;

const MCP_TOOLS = ["get_business_summary", "list_services"] as const;

const MCP_EXAMPLE = `POST /v1/mcp
Authorization: Bearer gorg_live_YOUR_KEY
Content-Type: application/json

{"jsonrpc":"2.0","id":1,"method":"tools/list"}`;

function Chips({ items }: { items: readonly string[] }) {
  return (
    <ul className="lp-code-chips">
      {items.map((item) => (
        <li key={item}>
          <code>{item}</code>
        </li>
      ))}
    </ul>
  );
}

const TABS: readonly TabSpec[] = [
  {
    key: "keys",
    label: "Scoped API keys",
    panel: (
      <>
        <p>
          Create one key per integration and give it only the access it needs.
          Revoke a key and it stops working at once. A key is shown once, when
          you create it.
        </p>
        <Chips items={SCOPES} />
        <pre className="lp-code">
          <code>Authorization: Bearer gorg_live_YOUR_KEY</code>
        </pre>
      </>
    ),
  },
  {
    key: "webhooks",
    label: "Signed webhooks",
    panel: (
      <>
        <p>
          Send booking, waitlist, invoice and payment events to your own tools.
          Each payload carries an HMAC-SHA256 signature, so your receiver can
          check that it came from AMARKAL Platform.
        </p>
        <Chips items={EVENTS} />
        <pre className="lp-code">
          <code>signature: v1=&lt;hex HMAC-SHA256 of the payload&gt;</code>
        </pre>
      </>
    ),
  },
  {
    key: "mcp",
    label: "Native MCP",
    panel: (
      <>
        <p>
          Connect any MCP-compatible AI agent or voice agent to your live
          services and business summary. The server speaks JSON-RPC 2.0 at{" "}
          <code>/v1/mcp</code>, needs a key with the <code>mcp:read</code>{" "}
          scope, and only ever sees your own business.
        </p>
        <Chips items={MCP_TOOLS} />
        <pre className="lp-code">
          <code>{MCP_EXAMPLE}</code>
        </pre>
      </>
    ),
  },
];

export function AppHubTabs() {
  const [tab, setTab] = useState<TabKey>("keys");
  return (
    <div className="lp-card lp-hub">
      <LandingTabs
        tabs={TABS}
        value={tab}
        onValueChange={(key) => setTab(key as TabKey)}
        label="App Hub building blocks"
      />
    </div>
  );
}
