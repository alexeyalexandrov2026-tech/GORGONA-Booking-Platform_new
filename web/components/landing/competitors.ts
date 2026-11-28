export interface ComparisonRow {
  readonly capability: string;
  readonly amarkal: string;
  readonly competitor: string;
}

export interface CompetitorSpec {
  readonly slug: "zoho-one" | "odoo" | "monday" | "netsuite";
  readonly name: string;
  readonly seoTitle: string;
  readonly seoDescription: string;
  readonly headline: string;
  readonly subheadline: string;
  readonly whySwitch: readonly string[];
  readonly rows: readonly ComparisonRow[];
  readonly faq: ReadonlyArray<{ readonly q: string; readonly a: string }>;
}

export const COMPETITORS: Record<CompetitorSpec["slug"], CompetitorSpec> = {
  "zoho-one": {
    slug: "zoho-one",
    name: "Zoho One",
    seoTitle:
      "AMARKAL Platform vs Zoho One — Unified US Business OS (0% Commission)",
    seoDescription:
      "Compare AMARKAL Platform vs Zoho One: one unified PostgreSQL 18 Business OS with 0% commission, Hybrid Smart Autonomy AI, MRP II, IoT EAM, US Payroll Prep, and 11-tool Native MCP.",
    headline:
      "One cohesive US Business OS — instead of 45 disconnected Zoho apps.",
    subheadline:
      "Zoho One bundles dozens of separately built apps with different UIs, sync bridges, and paid add-ons. AMARKAL runs operations, MRP II, IoT maintenance, Omnichannel Inbox, US Payroll Prep, and double-entry USD finance on one isolated PostgreSQL 18 data model.",
    whySwitch: [
      "Single unified PostgreSQL 18 database with FORCE Row-Level Security — zero cross-app sync delays",
      "Built-in Enterprise MRP II (multi-level BOM) and Predictive IoT EAM without third-party plugins",
      "Hybrid Smart Autonomy AI + BYOK (Anthropic, Gemini, OpenAI) + 11-tool Native MCP included",
      "0% platform commission on direct Stripe US payouts and 1-click B2C Storefront checkout",
    ],
    rows: [
      {
        capability: "Architecture & Data Model",
        amarkal:
          "Single unified PostgreSQL 18 Business OS with ENABLE + FORCE RLS",
        competitor:
          "45+ separately built apps connected via internal sync connectors",
      },
      {
        capability: "AI Autonomy & Governance",
        amarkal:
          "Hybrid Smart Autonomy + Proactive Weekly Brief + BYOK AI + hard $0.00 financial guardrail",
        competitor:
          "Zia assistant locked to Zoho ecosystem; no native 11-tool MCP server",
      },
      {
        capability: "Heavy Manufacturing (MRP II) & IoT EAM",
        amarkal:
          "Multi-level BOM explosion, atomic stock reservations, IoT telemetry webhooks & auto Work Orders",
        competitor:
          "Limited native inventory; heavy MRP II and predictive EAM require external ERP tools",
      },
      {
        capability: "US Payroll & Multi-Currency FX",
        amarkal:
          "FLSA / California §510 / Union CBA payroll prep + Gusto/ADP CSV + live FX Gain/Loss ledger",
        competitor:
          "Separate Zoho Payroll add-on with limited US state/union CBA flexibility",
      },
      {
        capability: "Omnichannel Inbox & B2C Shop",
        amarkal:
          "Built-in Email, Virtual PBX, SMS/WhatsApp inbox + 1-click B2C shop with 0% commission",
        competitor:
          "Requires configuring separate Zoho Desk, Zoho Mail, Zoho Commerce, and telephony add-ons",
      },
      {
        capability: "US Bank Feeds & Auto-Reconciliation",
        amarkal:
          "Built-in OFX/QFX/QBO/CSV importer + encrypted Plaid BYOK connector with Human-in-the-Loop matching",
        competitor:
          "Direct bank feeds live inside Zoho Books separately from operational CRM & inventory modules",
      },
      {
        capability: "Plugin Marketplace & Partner Ecosystem",
        amarkal:
          "Clean Core 1-click Plugin Marketplace (Customs ACE, X12 EDI, ELD, Avalara, FHIR) + amarkal-plugin.json SDK + US Partner Network",
        competitor:
          "Large third-party extension store across 45+ disparate apps with inconsistent permissions",
      },
      {
        capability: "Data Migration",
        amarkal:
          "1-click CSV Migration Wizard (Zoho, QuickBooks, Excel) + instant [DEMO] sandbox",
        competitor:
          "Multi-app migration across CRM, Books, Inventory, and Desk modules",
      },
    ],
    faq: [
      {
        q: "How fast can we migrate from Zoho CRM or Zoho Books to AMARKAL?",
        a: "Export your customers, vendors, materials, or employee lists to CSV and upload them inside AMARKAL -> Migrate & Sandbox. You get a dry-run preview before importing a single record.",
      },
      {
        q: "Does AMARKAL lock us into one AI vendor?",
        a: "No. You can use AMARKAL's built-in grounded AI or connect your own Anthropic Claude, Google Gemini, or OpenAI API key inside the per-tenant AES-256-GCM Secret Vault.",
      },
    ],
  },
  odoo: {
    slug: "odoo",
    name: "Odoo",
    seoTitle:
      "AMARKAL Platform vs Odoo — Modern US ERP & Business OS (Zero Lock-In)",
    seoDescription:
      "Compare AMARKAL Platform vs Odoo: US-first NAICS ERP with built-in MRP II, Predictive IoT EAM, US Payroll compliance, No-Code Studio, B2C Shop, and 11-tool Native MCP without complex self-hosting.",
    headline:
      "Enterprise ERP depth without Odoo's upgrade pain or consultant lock-in.",
    subheadline:
      "Odoo delivers modular ERP features but often turns into costly custom Python module maintenance, painful major-version migrations, and fragmented third-party apps. AMARKAL gives US companies MRP II, IoT EAM, US Payroll Prep, FX accounting, and Hybrid AI ready out of the box.",
    whySwitch: [
      "US-native from day one: 39 NAICS 2022 industries, FLSA/CA §510/Union CBA payroll prep, and direct Stripe US ACH",
      "Strict PostgreSQL 18 FORCE RLS isolation and automated CI schema guards — zero fragile community plugins",
      "Built-in 11-tool Native MCP server, BYOK AI vault, and proactive weekly Slack/Email CFO briefs",
      "No-Code Kanban boards, typed custom fields, and 1-click B2C Storefront without writing custom XML views",
    ],
    rows: [
      {
        capability: "Deployment & Upgrades",
        amarkal:
          "Managed Google Cloud US platform with zero-downtime releases and zero custom-module breakage",
        competitor:
          "Custom Odoo modules frequently break across major version upgrades and need paid partners",
      },
      {
        capability: "MRP II & Predictive EAM / IoT",
        amarkal:
          "Multi-level BOM, atomic stock reservations, 1-click Draft POs, and native IoT webhook Work Orders",
        competitor:
          "MRP & Maintenance require paid Enterprise tier plus custom IoT Box hardware or add-ons",
      },
      {
        capability: "US Payroll & Compliance",
        amarkal:
          "Built-in FLSA weekly, California §510 daily OT/DT, Union CBA rules, and Gusto/ADP CSV export",
        competitor:
          "US state/union payroll typically requires third-party connectors or custom localization",
      },
      {
        capability: "AI Copilot & MCP Automation",
        amarkal:
          "Hybrid Smart Autonomy, Proactive Weekly Briefs (Email/Slack), BYOK AI & 11-tool Native MCP",
        competitor:
          "Basic text generation helpers; no native multi-tool MCP server with FORCE RLS",
      },
      {
        capability: "No-Code Customization",
        amarkal:
          "Visual Workspace Studio (Kanban, Custom Fields, Brand Themes) + 1-click B2C Storefront included",
        competitor:
          "Odoo Studio requires Enterprise licensing and can complicate future upgrades",
      },
      {
        capability: "Plugin Marketplace & Clean Core SDK",
        amarkal:
          "1-click verified extensions (EDI, Customs ACE, Samsara ELD, HL7 FHIR, Remote MCP) via isolated amarkal-plugin.json SDK — zero core code breakage",
        competitor:
          "Thousands of community Python modules that mutate core tables and frequently break across Odoo upgrades",
      },
      {
        capability: "Partner & Integrator Support",
        amarkal:
          "Self-deploy in minutes with AI Architect OR engage Certified US Partners & CPA Practices via native Multi-Client Delegations",
        competitor:
          "Complex implementations routinely depend on expensive multi-month Odoo partner retainers",
      },
      {
        capability: "Data Migration",
        amarkal:
          "Built-in Odoo CSV importer for counterparties, materials/SKUs, fleet assets, and payroll profiles",
        competitor:
          "Requires external migration scripts or Odoo partner engagement",
      },
    ],
    faq: [
      {
        q: "Does AMARKAL support multi-level Bill of Materials (BOM) like Odoo MRP?",
        a: "Yes. AMARKAL MRP II explodes multi-level BOM recipes in exact milli-units with scrap factors, atomically reserves warehouse stock, and creates 1-click Draft Purchase Orders for any shortages.",
      },
      {
        q: "Can we connect our existing ERP or accounting tools?",
        a: "Yes. QuickBooks Online, Xero, Microsoft 365, Slack, Zapier, Make, n8n, and custom signed webhooks are available optionally inside App Hub.",
      },
    ],
  },
  monday: {
    slug: "monday",
    name: "Monday.com",
    seoTitle:
      "AMARKAL Platform vs Monday.com — Full Business OS Beyond Kanban Boards",
    seoDescription:
      "Compare AMARKAL Platform vs Monday.com: get No-Code Kanban boards plus real double-entry USD accounting, MRP II, IoT EAM, US Payroll Prep, Omnichannel Inbox, and 0% commission B2C Shop.",
    headline:
      "No-Code Kanban boards backed by real ERP accounting, MRP II, and 0% checkout.",
    subheadline:
      "Monday.com excels at colorful task boards, but teams quickly hit a wall when they need double-entry accounting, multi-currency FX, US payroll compliance, warehouse reservations, or native B2C checkout. AMARKAL combines visual No-Code Studio with a complete US Business OS.",
    whySwitch: [
      "Visual No-Code Kanban boards & typed custom fields connected directly to real invoices, POs, and inventory",
      "Real double-entry USD & Multi-Currency FX ledger (DR = CR) — not just formula columns",
      "Built-in Omnichannel Client Inbox, Virtual PBX call logs, and 1-click B2C Storefront (0% commission)",
      "Hybrid Smart Autonomy AI that enforces strict human approval on every financial action",
    ],
    rows: [
      {
        capability: "Visual Boards & No-Code Studio",
        amarkal:
          "Drag-and-drop Kanban boards, typed custom fields, and WCAG-checked Brand Themes included",
        competitor:
          "Strong visual boards, but financial and ERP workflows require stacking paid products",
      },
      {
        capability: "Accounting, Invoicing & FX",
        amarkal:
          "Full FIN-03 double-entry ledger, PO 3-way match, AR/AP aging, and live FX Gain/Loss revaluation",
        competitor:
          "No native double-entry ledger, multi-currency FX accounting, or 3-way PO match",
      },
      {
        capability: "Manufacturing & Fleet IoT",
        amarkal:
          "Built-in MRP II BOM reservations and Predictive EAM IoT telemetry webhooks",
        competitor:
          "Task tracking only; no atomic warehouse stock reservations or IoT rule engine",
      },
      {
        capability: "US Payroll & Global Tax",
        amarkal:
          "FLSA / California §510 / Union CBA payroll prep + EU/UK VAT Reverse Charge engine",
        competitor: "Not supported natively",
      },
      {
        capability: "Customer Payments & B2C Shop",
        amarkal:
          "1-click retail/service B2C Storefront + direct Stripe US ACH/Cards at 0% AMARKAL commission",
        competitor:
          "Requires external ecommerce storefront and third-party checkout integrations",
      },
      {
        capability: "Visual BI, Gantt & Executive Dashboards",
        amarkal:
          "Live Executive BI (/analytics/) with Monthly Cashflow SVG charts, CPQ Sales Funnel, unified MRP II / EAM / Kanban Gantt, and Board Pack CSV/PDF",
        competitor:
          "Visual dashboards & Gantt charts over task boards, disconnected from double-entry accounting & bank feeds",
      },
      {
        capability: "AI Agent Integration",
        amarkal:
          "11-tool Native MCP server, BYOK AI keys, and proactive weekly Slack/Email executive digests",
        competitor:
          "Per-seat AI credit meters without tenant-isolated FORCE RLS MCP tools",
      },
    ],
    faq: [
      {
        q: "Can our team still manage work visually on Kanban boards?",
        a: "Yes. AMARKAL Workspace Studio gives every business drag-and-drop Kanban boards, custom fields, and custom branding — natively connected to CRM, invoicing, MRP II, and payroll.",
      },
      {
        q: "Can we test AMARKAL before migrating our live boards?",
        a: "Yes. Use the 1-click Sample Business Sandbox inside /migrate/ to populate realistic demo records across all modules and remove them cleanly anytime.",
      },
    ],
  },
  netsuite: {
    slug: "netsuite",
    name: "Oracle NetSuite",
    seoTitle:
      "AMARKAL Platform vs NetSuite — Modern Agile US Enterprise ERP (Zero Lock-In)",
    seoDescription:
      "Compare AMARKAL Platform vs Oracle NetSuite: launch Enterprise MRP II, Multi-Currency FX, US Payroll Prep, Global Tax, Predictive IoT EAM, and Hybrid AI in minutes instead of 9-month implementations.",
    headline:
      "Enterprise ERP rigor launched in minutes — without NetSuite's multi-quarter implementation.",
    subheadline:
      "Oracle NetSuite requires lengthy implementation consulting, steep annual lock-in contracts, and expensive module add-ons. AMARKAL delivers PostgreSQL 18 isolation, double-entry USD/FX accounting, MRP II, IoT EAM, US Payroll Prep, and governed AI ready on day one.",
    whySwitch: [
      "AI Business Architect configures your 39-NAICS workspace from plain English in minutes",
      "Multi-currency FX Mark-to-Market Gain/Loss + EU/UK VAT Reverse Charge + US Sales Tax built in",
      "PostgreSQL 18 FORCE RLS isolation with 1-click JSON/CSV data portability and zero vendor lock-in",
      "Native 11-tool MCP server and BYOK AI vault for modern agentic operations",
    ],
    rows: [
      {
        capability: "Time to Go Live",
        amarkal:
          "Self-serve onboarding + AI Business Architect + 1-click CSV migration in minutes",
        competitor:
          "Typically 3–9 month implementation cycles with external system integrators",
      },
      {
        capability: "Multi-Currency FX & Global Tax",
        amarkal:
          "Live Mark-to-Market FX Gain/Loss revaluation + US/EU/UK/CA/MX tax engine + SEPA/FPS rails",
        competitor:
          "Requires expensive OneWorld licensing tier and paid localization bundles",
      },
      {
        capability: "MRP II & Predictive EAM / IoT",
        amarkal:
          "Multi-level BOM explosion, atomic stock reservations, and real-time IoT predictive Work Orders",
        competitor:
          "Separate WIP/Routing and Fixed Asset / third-party EAM modules required",
      },
      {
        capability: "Modern AI & Agent Ecosystem",
        amarkal:
          "Hybrid Smart Autonomy, Proactive Slack/Email Briefs, BYOK AI, and 11-tool Native MCP",
        competitor:
          "Closed SuiteScript customization model without open BYOK AI vaults",
      },
      {
        capability: "Client Experience & B2C Shop",
        amarkal:
          "Built-in B2B Quote Portal (/portal/), 1-click B2C Shop (/shop/), and Omnichannel Inbox",
        competitor:
          "Requires separate SuiteCommerce licensing and external CRM/PBX tools",
      },
      {
        capability: "Multi-Entity Holding & Intercompany",
        amarkal:
          "Built-in Holding Consolidation (/holding/): unlimited US/EU/CA subsidiaries, FX translation to USD, mirrored Due To / Due From eliminations & NCI",
        competitor:
          "Requires high-cost NetSuite OneWorld enterprise add-on and multi-quarter consulting setup",
      },
      {
        capability: "Executive BI & Direct US Bank Feeds",
        amarkal:
          "Visual BI & Gantt (/analytics/) + Chase/BofA/Wells Fargo OFX/CSV & Plaid BYOK reconciliation (/banking/) included",
        competitor:
          "SuiteAnalytics Workbook & third-party bank feed bundles add recurring licensing fees",
      },
      {
        capability: "Data Ownership & Lock-In",
        amarkal:
          "Direct Stripe US payouts (0% commission) and 1-click JSON/CSV export anytime",
        competitor:
          "Multi-year lock-in agreements with complex data extraction procedures",
      },
    ],
    faq: [
      {
        q: "Can AMARKAL handle strict double-entry accounting and multi-currency revaluation?",
        a: "Yes. AMARKAL enforces double-entry accounting (DR = CR) across FIN-03 financial documents and automatically computes Unrealized and Realized FX Gain/Loss in USD whenever exchange rates update or entries settle.",
      },
      {
        q: "How does AMARKAL protect sensitive financial and payroll records?",
        a: "Every business runs under PostgreSQL 18 ENABLE + FORCE Row-Level Security, AES-256-GCM encrypted BYOK vaults, and a hard $0.00 Human-in-the-Loop guardrail on all financial and payroll actions.",
      },
    ],
  },
};

export const ALL_COMPETITOR_SLUGS: readonly CompetitorSpec["slug"][] = [
  "zoho-one",
  "odoo",
  "monday",
  "netsuite",
];
