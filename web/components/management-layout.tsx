"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";
import { AmarkalLogo } from "./amarkal-logo";
import {
  accessToken,
  authManager,
  isAuthConfigured,
  signIn,
  signOut,
} from "../lib/auth";
import {
  authorizedResponse,
  fetchConfiguration,
  fetchMe,
  getActiveSalonId,
  setActiveSalonId,
  MembershipView,
  MeView,
} from "../lib/management-api";

interface GlobalSearchHit {
  kind:
    | "counterparty"
    | "document"
    | "invoice"
    | "service"
    | "payment"
    | "quote"
    | "purchase_order"
    | "mrp_material"
    | "eam_asset"
    | "inbox_thread"
    | "payroll_profile"
    | "fx_entry"
    | "bank_transaction"
    | "holding_subsidiary"
    | "intercompany_tx"
    | "marketplace_plugin";
  id: string;
  title: string;
  subtitle: string;
  path: string;
  status: string | null;
}

const SEARCH_KIND_LABEL: Record<GlobalSearchHit["kind"], string> = {
  counterparty: "Counterparty",
  document: "Document",
  invoice: "FIN-03 Invoice",
  service: "Catalog",
  payment: "Stripe Payment",
  quote: "Commercial Quote",
  purchase_order: "Purchase Order",
  mrp_material: "MRP Material",
  eam_asset: "IoT Asset",
  inbox_thread: "Client Inbox",
  payroll_profile: "US Payroll",
  fx_entry: "FX Ledger",
  bank_transaction: "US Bank Feed",
  holding_subsidiary: "Holding Entity",
  intercompany_tx: "Intercompany",
  marketplace_plugin: "Plugin",
};

interface ManagementLayoutProps {
  children: (props: {
    salonId: string;
    me: MeView;
    refresh: () => void;
  }) => React.ReactNode;
}

interface NavItem {
  readonly href: string;
  readonly label: string;
  readonly group: "Core" | "Team" | "Finance" | "Industry" | "Platform";
  readonly moduleIds?: readonly string[];
}

const FOCUS_MODE_STORAGE_KEY = "amarkal_focus_mode";

const NAV_ITEMS: readonly NavItem[] = [
  { href: "/business/", label: "Business profile", group: "Core" },
  { href: "/overview/", label: "Overview", group: "Core" },
  { href: "/calendar/", label: "Calendar", group: "Core" },
  { href: "/bookings/", label: "Bookings", group: "Core" },
  { href: "/services/", label: "Services", group: "Core" },
  { href: "/clients/", label: "Clients", group: "Core" },
  { href: "/inbox/", label: "Client Inbox", group: "Core" },
  { href: "/staff/", label: "Staff", group: "Team" },
  {
    href: "/reservations/",
    label: "Reservations",
    group: "Team",
    moduleIds: ["booking_resources"],
  },
  {
    href: "/schedule/",
    label: "Schedule",
    group: "Team",
    moduleIds: ["workforce"],
  },
  {
    href: "/my-shifts/",
    label: "My shifts",
    group: "Team",
    moduleIds: ["workforce"],
  },
  {
    href: "/timesheets/",
    label: "Timesheets",
    group: "Team",
    moduleIds: ["workforce"],
  },
  {
    href: "/analytics/",
    label: "BI & Analytics",
    group: "Finance",
  },
  {
    href: "/banking/",
    label: "US Bank Feeds",
    group: "Finance",
  },
  {
    href: "/holding/",
    label: "Holding & Multi-Entity",
    group: "Finance",
  },
  {
    href: "/materials/",
    label: "Materials",
    group: "Finance",
    moduleIds: ["inventory"],
  },
  {
    href: "/stock-documents/",
    label: "Stock documents",
    group: "Finance",
    moduleIds: ["inventory"],
  },
  {
    href: "/counterparties/",
    label: "Counterparties",
    group: "Finance",
    moduleIds: ["counterparties"],
  },
  {
    href: "/documents/",
    label: "Documents",
    group: "Finance",
    moduleIds: ["documents"],
  },
  {
    href: "/ledger/",
    label: "Ledger",
    group: "Finance",
    moduleIds: ["finance"],
  },
  {
    href: "/finance/",
    label: "Financial documents",
    group: "Finance",
    moduleIds: ["finance_documents"],
  },
  {
    href: "/commercial/",
    label: "Commercial & PO",
    group: "Finance",
  },
  {
    href: "/global-finance/",
    label: "Payroll & FX Tax",
    group: "Finance",
  },
  {
    href: "/prepaid/",
    label: "Prepaid",
    group: "Finance",
    moduleIds: ["finance_documents"],
  },
  {
    href: "/transport/",
    label: "Transport",
    group: "Industry",
    moduleIds: ["transport"],
  },
  {
    href: "/construction/",
    label: "Construction",
    group: "Industry",
    moduleIds: ["construction"],
  },
  {
    href: "/rental/",
    label: "Rental",
    group: "Industry",
    moduleIds: ["rental"],
  },
  {
    href: "/property/",
    label: "Property",
    group: "Industry",
    moduleIds: ["property"],
  },
  {
    href: "/restaurant/",
    label: "Restaurant",
    group: "Industry",
    moduleIds: ["restaurant"],
  },
  {
    href: "/projects/",
    label: "Projects",
    group: "Industry",
    moduleIds: ["projects"],
  },
  {
    href: "/supply/",
    label: "Supply Chain",
    group: "Industry",
    moduleIds: ["supply"],
  },
  {
    href: "/industrial/",
    label: "MRP II & EAM IoT",
    group: "Industry",
  },
  {
    href: "/marketplace/",
    label: "Marketplace",
    group: "Industry",
    moduleIds: ["storefronts"],
  },
  {
    href: "/enterprise/",
    label: "Enterprise",
    group: "Industry",
    moduleIds: ["analytics"],
  },
  {
    href: "/specialized/",
    label: "Specialized",
    group: "Industry",
    moduleIds: [
      "assets",
      "hospitality_events",
      "clinical_care",
      "public_civic",
    ],
  },
  {
    href: "/provider-admission/",
    label: "Provider admission",
    group: "Platform",
  },
  { href: "/workspace/", label: "Workspace Studio", group: "Platform" },
  { href: "/migrate/", label: "Migrate & Sandbox", group: "Platform" },
  { href: "/integrations/", label: "App Hub", group: "Platform" },
  { href: "/app-marketplace/", label: "Plugin Marketplace", group: "Platform" },
  { href: "/partners/", label: "Partner Network", group: "Platform" },
  {
    href: "/access-control/",
    label: "Access Matrix (ABAC)",
    group: "Platform",
  },
  {
    href: "/workflows/",
    label: "Workflows (BPMN)",
    group: "Platform",
  },
  { href: "/settings/", label: "Settings", group: "Platform" },
];

export function ManagementLayout({ children }: ManagementLayoutProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<MeView | null>(null);
  const [salonId, setSalonId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState(false);
  const [unlinkedAccount, setUnlinkedAccount] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [authBusy, setAuthBusy] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [searchHits, setSearchHits] = useState<GlobalSearchHit[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [focusModules, setFocusModules] = useState<string[] | null>(null);
  const [focusBusy, setFocusBusy] = useState(false);
  const paletteInputRef = useRef<HTMLInputElement | null>(null);

  const membership = me?.memberships.find((item) => item.salon_id === salonId);
  const locationLimited = membership?.location_id != null;
  const delegation = membership?.delegation;
  const isCompanyManager =
    !locationLimited &&
    !delegation &&
    ["owner", "manager"].includes(membership?.role ?? "");
  const granted = (right: string) =>
    delegation?.permissions.some((p) => p === right) ?? false;

  // Delegated work is limited to what the grant names (bookings, transport since M6b);
  // company areas stay with the owner business.
  const permittedNav = NAV_ITEMS.filter(
    (item) =>
      (![
        "/counterparties/",
        "/documents/",
        "/ledger/",
        "/finance/",
        "/commercial/",
        "/provider-admission/",
        "/integrations/",
      ].includes(item.href) ||
        isCompanyManager) &&
      // Resource reservations, the schedule and materials are staff management, also
      // within one branch. Own shifts and time belong to every member, never a delegate.
      (![
        "/reservations/",
        "/schedule/",
        "/materials/",
        "/stock-documents/",
        "/transport/",
        "/construction/",
        "/rental/",
        "/property/",
      ].includes(item.href) ||
        (!delegation &&
          ["owner", "manager"].includes(membership?.role ?? "")) ||
        (item.href === "/transport/" && granted("transport.read"))),
  );
  const navItems = delegation
    ? permittedNav.filter(
        (item) =>
          item.href === "/overview/" ||
          (["/calendar/", "/bookings/"].includes(item.href) &&
            granted("booking.read")) ||
          (item.href === "/transport/" && granted("transport.read")),
      )
    : locationLimited
      ? permittedNav.filter(
          (item) =>
            ![
              "/business/",
              "/settings/",
              "/services/",
              "/integrations/",
            ].includes(item.href),
        )
      : permittedNav;

  const visibleNavItems =
    focusMode && focusModules !== null
      ? navItems.filter(
          (item) =>
            !item.moduleIds ||
            item.href === pathname ||
            item.moduleIds.some((id) => focusModules.includes(id)),
        )
      : navItems;

  const saveFocusPreference = (enabled: boolean) => {
    try {
      localStorage.setItem(FOCUS_MODE_STORAGE_KEY, enabled ? "1" : "0");
    } catch {
      /* ignore restricted localStorage */
    }
  };

  useEffect(() => {
    if (!salonId || delegation) return;
    let saved = false;
    try {
      saved = localStorage.getItem(FOCUS_MODE_STORAGE_KEY) === "1";
    } catch {
      saved = false;
    }
    if (!saved) return;
    let active = true;
    void fetchConfiguration(salonId)
      .then((cfg) => {
        if (active) {
          setFocusModules(cfg.effective_module_ids);
          setFocusMode(true);
        }
      })
      .catch(() => {
        if (active) setFocusMode(false);
      });
    return () => {
      active = false;
    };
  }, [salonId, delegation]);

  const toggleFocusMode = async () => {
    if (focusMode) {
      setFocusMode(false);
      saveFocusPreference(false);
      return;
    }
    if (!salonId) return;
    if (focusModules !== null) {
      setFocusMode(true);
      saveFocusPreference(true);
      return;
    }
    setFocusBusy(true);
    try {
      const cfg = await fetchConfiguration(salonId);
      setFocusModules(cfg.effective_module_ids);
      setFocusMode(true);
      saveFocusPreference(true);
    } catch {
      setFocusMode(false);
      saveFocusPreference(false);
    } finally {
      setFocusBusy(false);
    }
  };

  const paletteEntries = (() => {
    const base = navItems.map((item) => ({
      key: `nav-${item.href}`,
      href: item.href,
      label: item.label,
      subtitle: undefined as string | undefined,
      group: item.group as string,
    }));
    const actions = [
      {
        key: "act-onboarding",
        href: "/onboarding/",
        label: "Create new business (AI Business Architect)",
        subtitle: undefined as string | undefined,
        group: "Action",
      },
      {
        key: "act-book",
        href: "/book/",
        label: "Client portal",
        subtitle: undefined as string | undefined,
        group: "Action",
      },
    ];
    const all = [...base, ...actions];
    const q = paletteQuery.trim().toLowerCase();
    const matchedScreens = q
      ? all.filter(
          (entry) =>
            entry.label.toLowerCase().includes(q) ||
            entry.group.toLowerCase().includes(q) ||
            entry.href.toLowerCase().includes(q),
        )
      : all;
    const recordHits =
      q.length >= 2
        ? searchHits.map((hit) => ({
            key: `hit-${hit.kind}-${hit.id}`,
            href: hit.path,
            label: hit.title,
            subtitle: hit.subtitle,
            group: SEARCH_KIND_LABEL[hit.kind],
          }))
        : [];
    return [...matchedScreens, ...recordHits];
  })();

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    setTick((t) => t + 1);
  }, []);

  useEffect(() => {
    let active = true;
    let removeExpired: (() => void) | undefined;
    void (async () => {
      const [manager, ready] = await Promise.all([
        authManager(),
        isAuthConfigured(),
      ]);
      if (!active) return;
      setConfigured(ready);
      const expired = () => {
        setMe(null);
        setSalonId(null);
        setError("Your session expired. Please sign in again.");
      };
      manager?.events.addAccessTokenExpired(expired);
      removeExpired = () => manager?.events.removeAccessTokenExpired(expired);
      if (!(await accessToken())) {
        setMe(null);
        return;
      }
      const data = await fetchMe();
      if (!active) return;
      const own = data.memberships.filter((m) => m.status === "active");
      const delegated: MembershipView[] = data.delegations
        .filter((d) => !own.some((m) => m.salon_id === d.business_id))
        .map((d) => ({
          salon_id: d.business_id,
          salon_name: d.business_name,
          role: "delegated",
          status: "active",
          location_id: d.location_id,
          delegation: d,
        }));
      const memberships = [...own, ...delegated];
      const selected =
        memberships.find((m) => m.salon_id === getActiveSalonId()) ??
        memberships[0];
      setMe({ ...data, memberships });
      setUnlinkedAccount(false);
      setSalonId(selected?.salon_id ?? null);
      setActiveSalonId(selected?.salon_id ?? null);
    })()
      .catch((err: unknown) => {
        if (active) {
          setMe(null);
          const msg = err instanceof Error ? err.message : "";
          if (
            msg.includes("not linked") ||
            msg.includes("IDENTITY_NOT_LINKED")
          ) {
            setUnlinkedAccount(true);
            setError(null);
          } else {
            setUnlinkedAccount(false);
            setError(
              "We couldn’t verify your account. Sign in again or retry.",
            );
          }
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      removeExpired?.();
    };
  }, [tick]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        if (!me) return;
        event.preventDefault();
        setPaletteOpen((open) => !open);
        setPaletteQuery("");
        setPaletteIndex(0);
      } else if (event.key === "Escape" && paletteOpen) {
        event.preventDefault();
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [me, paletteOpen]);

  useEffect(() => {
    if (paletteOpen) {
      paletteInputRef.current?.focus();
    }
  }, [paletteOpen]);

  useEffect(() => {
    const q = paletteQuery.trim();
    if (!paletteOpen || !salonId || q.length < 2) {
      return;
    }
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      if (!active) return;
      setSearchBusy(true);
      void authorizedResponse(
        `/v1/businesses/${encodeURIComponent(salonId)}/search?q=${encodeURIComponent(q)}&limit=5`,
        { signal: controller.signal },
      )
        .then((res) => res.json() as Promise<{ hits?: GlobalSearchHit[] }>)
        .then((data) => {
          if (active) setSearchHits(data.hits ?? []);
        })
        .catch(() => {
          if (active) setSearchHits([]);
        })
        .finally(() => {
          if (active) setSearchBusy(false);
        });
    }, 220);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [paletteOpen, salonId, paletteQuery]);

  const closePalette = () => {
    setPaletteOpen(false);
    setPaletteQuery("");
    setSearchHits([]);
    setSearchBusy(false);
  };

  const openPalette = () => {
    setPaletteQuery("");
    setPaletteIndex(0);
    setSearchHits([]);
    setSearchBusy(false);
    setPaletteOpen(true);
  };

  const navigateFromPalette = (href: string) => {
    closePalette();
    router.push(href);
  };

  const startSignIn = async () => {
    setAuthBusy(true);
    setError(null);
    try {
      await signIn();
    } catch {
      setError("We couldn’t reach the sign-in provider. Please try again.");
      setAuthBusy(false);
    }
  };
  const startSignOut = async () => {
    setAuthBusy(true);
    setMe(null);
    setSalonId(null);
    setPaletteOpen(false);
    setFocusMode(false);
    setFocusModules(null);
    try {
      await signOut();
    } catch {
      setError(
        "You’re signed out here. The account provider could not be reached.",
      );
    } finally {
      setAuthBusy(false);
    }
  };

  return (
    <div className="management-shell">
      <a className="skip" href="#main-content">
        Skip to content
      </a>
      <header className="mgmt-header">
        <div className="mgmt-brand-area">
          <Link href="/overview/" className="mgmt-brand">
            <AmarkalLogo variant="light" height={20} />
          </Link>
          {me && me.memberships.length > 1 ? (
            <select
              className="mgmt-salon-select"
              aria-label="Active Business"
              value={salonId ?? ""}
              onChange={(e) => {
                setActiveSalonId(e.target.value);
                setSalonId(e.target.value);
                setFocusMode(false);
                setFocusModules(null);
              }}
            >
              {me.memberships.map((m) => (
                <option key={m.salon_id} value={m.salon_id}>
                  {m.salon_name ?? "Business"} ({m.role})
                </option>
              ))}
            </select>
          ) : me && salonId ? (
            <div className="mgmt-salon-badge">
              <strong>
                {me.memberships.find((m) => m.salon_id === salonId)
                  ?.salon_name ?? "Active Business"}
              </strong>
            </div>
          ) : null}
        </div>
        <div className="mgmt-header-actions">
          {me ? (
            <>
              <button
                type="button"
                className="secondary mgmt-cmd-trigger"
                onClick={openPalette}
                aria-haspopup="dialog"
                aria-expanded={paletteOpen}
              >
                <span>Quick jump</span>
                <kbd aria-hidden="true">⌘K</kbd>
              </button>
              {salonId && !delegation && (
                <button
                  type="button"
                  className={
                    "secondary mgmt-cmd-trigger" + (focusMode ? " active" : "")
                  }
                  aria-pressed={focusMode}
                  disabled={focusBusy}
                  onClick={() => void toggleFocusMode()}
                  title="Show only Core and active industry modules for this workspace"
                >
                  <span>
                    {focusBusy
                      ? "Loading…"
                      : focusMode
                        ? `Focused (${visibleNavItems.length}/${navItems.length})`
                        : "Focus mode"}
                  </span>
                </button>
              )}
              <Link href="/onboarding/" className="mgmt-nav-link">
                + New business
              </Link>
              <span>{me.display_name}</span>
              <button
                className="secondary"
                disabled={authBusy}
                onClick={() => void startSignOut()}
              >
                Sign out
              </button>
            </>
          ) : (
            <button
              disabled={loading || !configured || authBusy}
              onClick={() => void startSignIn()}
            >
              {authBusy ? "Opening sign-in…" : "Sign in"}
            </button>
          )}
        </div>
      </header>
      <div className="mgmt-body">
        <nav className="mgmt-nav" aria-label="Management Navigation">
          <ul className="mgmt-nav-list">
            {visibleNavItems.map((item, idx) => {
              const prev = idx > 0 ? visibleNavItems[idx - 1] : null;
              const groupChanged = Boolean(prev && prev.group !== item.group);
              return (
                <li
                  key={item.href}
                  className={groupChanged ? "mgmt-nav-group-start" : undefined}
                >
                  <Link
                    href={item.href}
                    className={
                      "mgmt-nav-link" +
                      (pathname === item.href ? " active" : "")
                    }
                    aria-current={pathname === item.href ? "page" : undefined}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <main className="mgmt-main" id="main-content">
          {delegation && (
            <p className="hold-note" role="note">
              You are serving {delegation.business_name} through access granted
              to {delegation.servicer_name ?? "your business"} until{" "}
              {new Date(delegation.expires_at).toLocaleDateString()}. Only
              bookings are available, and access ends at once if it is revoked.
            </p>
          )}
          {locationLimited && !delegation && (
            <p className="hold-note">
              You have access to your assigned location. Company settings are
              managed by the business owner.
            </p>
          )}
          {loading ? (
            <div className="mgmt-loading" aria-live="polite">
              <p>Verifying your account…</p>
            </div>
          ) : (
            <>
              {error && (
                <div className="mgmt-error-banner" role="alert">
                  <p>{error}</p>
                  <button className="secondary" onClick={refresh}>
                    Retry
                  </button>
                </div>
              )}
              {!me && unlinkedAccount ? (
                <section className="mgmt-empty-state">
                  <h1>Welcome to AMARKAL Platform</h1>
                  <p>
                    You are signed in. Launch your US business workspace in 60
                    seconds with AI Business Architect across 39 industries — 0%
                    platform commission, direct Stripe payouts, and zero
                    lock-in.
                  </p>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      justifyContent: "center",
                      gap: "12px",
                      marginTop: "20px",
                    }}
                  >
                    <Link href="/onboarding/" className="button">
                      Launch with AI Business Architect →
                    </Link>
                    <button
                      type="button"
                      className="secondary"
                      disabled={authBusy}
                      onClick={() => void startSignOut()}
                    >
                      Sign out
                    </button>
                  </div>
                </section>
              ) : !me ? (
                <section className="mgmt-auth-gate">
                  <h1>Manage your business</h1>
                  <p>
                    {configured
                      ? "Sign in with your business account to manage bookings, services and clients."
                      : "Staff sign-in is not available in this environment yet. The account provider must be configured before the dashboard can be used."}
                  </p>
                  {configured && (
                    <button
                      disabled={authBusy}
                      onClick={() => void startSignIn()}
                    >
                      Sign in with your account
                    </button>
                  )}
                </section>
              ) : !salonId ? (
                <section className="mgmt-empty-state">
                  <h2>No active businesses yet</h2>
                  <p>
                    Your account has no active business membership yet. Register
                    a new business workspace yourself, or ask an owner for an
                    invitation.
                  </p>
                  <Link href="/onboarding/" className="mgmt-nav-link active">
                    Create your business workspace
                  </Link>
                </section>
              ) : (
                children({ salonId, me, refresh })
              )}
            </>
          )}
        </main>
      </div>
      {paletteOpen && (
        <div
          className="mgmt-modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) closePalette();
          }}
        >
          <div
            className="mgmt-modal-card mgmt-cmd-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Quick navigation and global business search"
          >
            <div className="mgmt-cmd-head">
              <label htmlFor="mgmt-cmd-input" className="mgmt-cmd-label">
                Search screens, counterparties, invoices, documents
              </label>
              <button
                type="button"
                className="secondary mgmt-btn-small"
                onClick={closePalette}
              >
                Close
              </button>
            </div>
            <input
              ref={paletteInputRef}
              id="mgmt-cmd-input"
              type="search"
              className="mgmt-cmd-input"
              placeholder="Search screens or business records (e.g. Apex, INV-1042, App Hub)…"
              value={paletteQuery}
              onChange={(event) => {
                const next = event.target.value;
                setPaletteQuery(next);
                setPaletteIndex(0);
                if (next.trim().length < 2) {
                  setSearchHits([]);
                  setSearchBusy(false);
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setPaletteIndex((idx) =>
                    paletteEntries.length
                      ? (idx + 1) % paletteEntries.length
                      : 0,
                  );
                } else if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setPaletteIndex((idx) =>
                    paletteEntries.length
                      ? (idx - 1 + paletteEntries.length) %
                        paletteEntries.length
                      : 0,
                  );
                } else if (event.key === "Enter") {
                  const chosen = paletteEntries[paletteIndex];
                  if (chosen) {
                    event.preventDefault();
                    navigateFromPalette(chosen.href);
                  }
                }
              }}
            />
            <ul className="mgmt-cmd-list" role="listbox" aria-label="Results">
              {paletteEntries.length === 0 ? (
                <li className="mgmt-cmd-empty">
                  {searchBusy
                    ? "Searching business records…"
                    : "No matching screens or records found."}
                </li>
              ) : (
                paletteEntries.map((entry, idx) => (
                  <li key={entry.key}>
                    <button
                      type="button"
                      className={
                        "mgmt-cmd-item" +
                        (idx === paletteIndex ? " selected" : "")
                      }
                      onMouseEnter={() => setPaletteIndex(idx)}
                      onClick={() => navigateFromPalette(entry.href)}
                    >
                      <span className="mgmt-cmd-item-main">
                        <span>{entry.label}</span>
                        {entry.subtitle ? (
                          <span className="mgmt-cmd-sub">{entry.subtitle}</span>
                        ) : null}
                      </span>
                      <span className="mgmt-cmd-meta">{entry.group}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
            {searchBusy && paletteEntries.length > 0 && (
              <p
                className="usr-muted"
                style={{ margin: "8px 0 0", fontSize: "0.78rem" }}
              >
                Searching live business records…
              </p>
            )}
          </div>
        </div>
      )}
      <footer className="mgmt-footer">
        <span>AMARKAL Platform</span>
        <Link href="/onboarding/">Register business</Link>
        <Link href="/integrations/">App Hub</Link>
        <Link href="/status/">System Status</Link>
        <Link href="/legal/terms/">Terms of Service</Link>
        <Link href="/legal/privacy/">Privacy Policy</Link>
      </footer>
    </div>
  );
}
