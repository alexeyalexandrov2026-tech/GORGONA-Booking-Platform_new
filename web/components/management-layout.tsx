"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import { accessToken, authManager, signIn, signOut } from "../lib/auth";
import {
  fetchMe,
  getActiveSalonId,
  setActiveSalonId,
  MeView,
} from "../lib/management-api";

interface ManagementLayoutProps {
  children: (props: {
    salonId: string;
    me: MeView;
    refresh: () => void;
  }) => React.ReactNode;
}
const NAV_ITEMS = [
  { href: "/business/", label: "Business profile" },
  { href: "/overview/", label: "Overview" },
  { href: "/calendar/", label: "Calendar" },
  { href: "/bookings/", label: "Bookings" },
  { href: "/services/", label: "Services" },
  { href: "/staff/", label: "Staff" },
  { href: "/clients/", label: "Clients" },
  { href: "/settings/", label: "Settings" },
];

export function ManagementLayout({ children }: ManagementLayoutProps) {
  const pathname = usePathname();
  const [me, setMe] = useState<MeView | null>(null);
  const [salonId, setSalonId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [authBusy, setAuthBusy] = useState(false);
  const membership = me?.memberships.find((item) => item.salon_id === salonId);
  // Work for another business through its grant (ADR-0016); the server decides each request.
  const delegated =
    membership === undefined
      ? me?.delegations.filter((item) => item.business_id === salonId)
      : undefined;
  const delegation = delegated?.[0];
  const delegatedPermissions = new Set(
    delegated?.flatMap((item) => item.permissions) ?? [],
  );
  const locationLimited =
    membership?.location_id != null ||
    (delegated !== undefined &&
      delegated.length > 0 &&
      delegated.every((item) => item.location_id !== null));
  const navItems = delegation
    ? NAV_ITEMS.filter(
        (item) =>
          delegatedPermissions.has("booking.read") &&
          ["/overview/", "/calendar/", "/bookings/", "/clients/"].includes(
            item.href,
          ),
      )
    : locationLimited
      ? NAV_ITEMS.filter(
          (item) =>
            !["/business/", "/settings/", "/services/"].includes(item.href),
        )
      : NAV_ITEMS;
  const choices = me
    ? [
        ...me.memberships.map((m) => ({
          id: m.salon_id,
          label: `${m.salon_name ?? "Salon"} (${m.role})`,
        })),
        ...me.delegations
          .filter(
            (d, index, all) =>
              all.findIndex((other) => other.business_id === d.business_id) ===
                index &&
              !me.memberships.some((m) => m.salon_id === d.business_id),
          )
          .map((d) => ({
            id: d.business_id,
            label: `${d.purpose} (delegated)`,
          })),
      ]
    : [];
  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    setTick((t) => t + 1);
  }, []);
  useEffect(() => {
    let active = true;
    let removeExpired: (() => void) | undefined;
    void (async () => {
      const manager = await authManager();
      if (!active) return;
      setConfigured(Boolean(manager));
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
      const memberships = data.memberships.filter((m) => m.status === "active");
      const available = [
        ...memberships.map((m) => m.salon_id),
        ...data.delegations.map((d) => d.business_id),
      ];
      const remembered = getActiveSalonId();
      const selected =
        available.find((id) => id === remembered) ?? available[0] ?? null;
      setMe({ ...data, memberships });
      setSalonId(selected);
      setActiveSalonId(selected);
    })()
      .catch(() => {
        if (active) {
          setMe(null);
          setError("We couldn’t verify your account. Sign in again or retry.");
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
            GORGONA <span>Studio Manager</span>
          </Link>
          {me && choices.length > 1 ? (
            <select
              className="mgmt-salon-select"
              aria-label="Active Salon"
              value={salonId ?? ""}
              onChange={(e) => {
                setActiveSalonId(e.target.value);
                setSalonId(e.target.value);
              }}
            >
              {choices.map((choice) => (
                <option key={choice.id} value={choice.id}>
                  {choice.label}
                </option>
              ))}
            </select>
          ) : me && salonId ? (
            <div className="mgmt-salon-badge">
              <strong>
                {membership?.salon_name ??
                  delegation?.purpose ??
                  "Active Salon"}
              </strong>
            </div>
          ) : null}
        </div>
        <div className="mgmt-header-actions">
          {me ? (
            <>
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
          {navItems.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className={
                  "mgmt-nav-link " + (pathname === item.href ? "active" : "")
                }
                aria-current={pathname === item.href ? "page" : undefined}
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <main className="mgmt-main" id="main-content">
        {delegation ? (
          <p className="hold-note delegated-note">
            You are working for another business: {delegation.purpose}. Its
            records stay with that business, your actions are recorded, and
            access ends {new Date(delegation.valid_until).toLocaleString()} or
            earlier if either business stops it.
          </p>
        ) : (
          locationLimited && (
            <p className="hold-note">
              You have access to your assigned location. Company settings are
              managed by the business owner.
            </p>
          )
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
                <h1>Manage your studio</h1>
                <p>
                  {configured
                    ? "Sign in with your studio account to manage bookings, services and clients."
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
                <h2>No active studios</h2>
                <p>
                  Your account has no active salon membership. Contact your
                  studio owner for access.
                </p>
              </section>
            ) : (
              children({ salonId, me, refresh })
            )}
          </>
        )}
      </main>
    </div>
  );
}
