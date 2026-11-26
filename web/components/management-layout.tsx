"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  accessToken,
  authManager,
  isAuthConfigured,
  signIn,
  signOut,
} from "../lib/auth";
import {
  fetchMe,
  getActiveSalonId,
  setActiveSalonId,
  MembershipView,
  MeView,
} from "../lib/management-api";

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
  readonly moduleId?: string;
}

const NAV_ITEMS: readonly NavItem[] = [
  { href: "/business/", label: "Business profile", group: "Core" },
  { href: "/overview/", label: "Overview", group: "Core" },
  { href: "/calendar/", label: "Calendar", group: "Core" },
  { href: "/bookings/", label: "Bookings", group: "Core" },
  { href: "/services/", label: "Services", group: "Core" },
  { href: "/clients/", label: "Clients", group: "Core" },
  { href: "/staff/", label: "Staff", group: "Team" },
  {
    href: "/reservations/",
    label: "Reservations",
    group: "Team",
    moduleId: "resource_reservations",
  },
  {
    href: "/schedule/",
    label: "Schedule",
    group: "Team",
    moduleId: "workforce_scheduling",
  },
  {
    href: "/my-shifts/",
    label: "My shifts",
    group: "Team",
    moduleId: "workforce_scheduling",
  },
  {
    href: "/timesheets/",
    label: "Timesheets",
    group: "Team",
    moduleId: "workforce_scheduling",
  },
  {
    href: "/materials/",
    label: "Materials",
    group: "Finance",
    moduleId: "inventory",
  },
  {
    href: "/stock-documents/",
    label: "Stock documents",
    group: "Finance",
    moduleId: "inventory",
  },
  { href: "/counterparties/", label: "Counterparties", group: "Finance" },
  { href: "/documents/", label: "Documents", group: "Finance" },
  { href: "/ledger/", label: "Ledger", group: "Finance" },
  { href: "/finance/", label: "Financial documents", group: "Finance" },
  { href: "/prepaid/", label: "Prepaid", group: "Finance" },
  {
    href: "/transport/",
    label: "Transport",
    group: "Industry",
    moduleId: "transport",
  },
  {
    href: "/construction/",
    label: "Construction",
    group: "Industry",
    moduleId: "construction",
  },
  {
    href: "/rental/",
    label: "Rental",
    group: "Industry",
    moduleId: "rental",
  },
  {
    href: "/property/",
    label: "Property",
    group: "Industry",
    moduleId: "property_management",
  },
  {
    href: "/restaurant/",
    label: "Restaurant",
    group: "Industry",
    moduleId: "restaurant_operations",
  },
  {
    href: "/projects/",
    label: "Projects",
    group: "Industry",
    moduleId: "project_delivery",
  },
  {
    href: "/supply/",
    label: "Supply Chain",
    group: "Industry",
    moduleId: "supply_chain",
  },
  {
    href: "/marketplace/",
    label: "Marketplace",
    group: "Industry",
    moduleId: "marketplace_operations",
  },
  {
    href: "/enterprise/",
    label: "Enterprise",
    group: "Industry",
    moduleId: "enterprise_governance",
  },
  {
    href: "/specialized/",
    label: "Specialized",
    group: "Industry",
    moduleId: "specialized_operations",
  },
  {
    href: "/provider-admission/",
    label: "Provider admission",
    group: "Platform",
  },
  { href: "/integrations/", label: "App Hub", group: "Platform" },
  { href: "/settings/", label: "Settings", group: "Platform" },
];

export function ManagementLayout({ children }: ManagementLayoutProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<MeView | null>(null);
  const [salonId, setSalonId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [authBusy, setAuthBusy] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [paletteIndex, setPaletteIndex] = useState(0);
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

  const paletteEntries = (() => {
    const base = navItems.map((item) => ({
      href: item.href,
      label: item.label,
      group: item.group as string,
    }));
    const actions = [
      {
        href: "/onboarding/",
        label: "Create new business (AI Business Architect)",
        group: "Action",
      },
      {
        href: "/book/",
        label: "Client portal",
        group: "Action",
      },
    ];
    const all = [...base, ...actions];
    const q = paletteQuery.trim().toLowerCase();
    if (!q) return all;
    return all.filter(
      (entry) =>
        entry.label.toLowerCase().includes(q) ||
        entry.group.toLowerCase().includes(q) ||
        entry.href.toLowerCase().includes(q),
    );
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
            setError(
              "Your sign-in is verified but not linked to a business yet. Create your business workspace to get started.",
            );
          } else {
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

  const openPalette = () => {
    setPaletteQuery("");
    setPaletteIndex(0);
    setPaletteOpen(true);
  };

  const navigateFromPalette = (href: string) => {
    setPaletteOpen(false);
    setPaletteQuery("");
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
            AMARKAL <span>Platform</span>
          </Link>
          {me && me.memberships.length > 1 ? (
            <select
              className="mgmt-salon-select"
              aria-label="Active Business"
              value={salonId ?? ""}
              onChange={(e) => {
                setActiveSalonId(e.target.value);
                setSalonId(e.target.value);
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
      <nav className="mgmt-nav" aria-label="Management Navigation">
        <ul className="mgmt-nav-list">
          {navItems.map((item, idx) => {
            const prev = idx > 0 ? navItems[idx - 1] : null;
            const groupChanged = Boolean(prev && prev.group !== item.group);
            return (
              <li
                key={item.href}
                className={groupChanged ? "mgmt-nav-group-start" : undefined}
              >
                <Link
                  href={item.href}
                  className={
                    "mgmt-nav-link" + (pathname === item.href ? " active" : "")
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
            You are serving {delegation.business_name} through access granted to{" "}
            {delegation.servicer_name ?? "your business"} until{" "}
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
            {!me ? (
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
                  Your account has no active business membership yet. Register a
                  new business workspace yourself, or ask an owner for an
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
      {paletteOpen && (
        <div
          className="mgmt-modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) setPaletteOpen(false);
          }}
        >
          <div
            className="mgmt-modal-card mgmt-cmd-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Quick navigation"
          >
            <div className="mgmt-cmd-head">
              <label htmlFor="mgmt-cmd-input" className="mgmt-cmd-label">
                Jump to screen or action
              </label>
              <button
                type="button"
                className="secondary mgmt-btn-small"
                onClick={() => setPaletteOpen(false)}
              >
                Close
              </button>
            </div>
            <input
              ref={paletteInputRef}
              id="mgmt-cmd-input"
              type="search"
              className="mgmt-cmd-input"
              placeholder="Type a module, screen, or action (e.g. App Hub, Finance, Transport)…"
              value={paletteQuery}
              onChange={(event) => {
                setPaletteQuery(event.target.value);
                setPaletteIndex(0);
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
                <li className="mgmt-cmd-empty">No matching screens found.</li>
              ) : (
                paletteEntries.map((entry, idx) => (
                  <li key={`${entry.group}-${entry.href}`}>
                    <button
                      type="button"
                      className={
                        "mgmt-cmd-item" +
                        (idx === paletteIndex ? " selected" : "")
                      }
                      onMouseEnter={() => setPaletteIndex(idx)}
                      onClick={() => navigateFromPalette(entry.href)}
                    >
                      <span>{entry.label}</span>
                      <span className="mgmt-cmd-meta">{entry.group}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          </div>
        </div>
      )}
      <footer
        style={{
          padding: "1rem 1.5rem",
          fontSize: "0.85rem",
          color: "#3f3832",
          display: "flex",
          flexWrap: "wrap",
          gap: "1rem",
          borderTop: "1px solid rgba(0,0,0,0.12)",
        }}
      >
        <span>AMARKAL Platform</span>
        <Link href="/onboarding/">Register business</Link>
        <Link href="/integrations/">App Hub</Link>
        <Link href="/legal/terms/">Terms of Service</Link>
        <Link href="/legal/privacy/">Privacy Policy</Link>
      </footer>
    </div>
  );
}
