"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { AmarkalLogo } from "../../../components/amarkal-logo";
import {
  accessToken,
  googleSendPasswordReset,
  googleSignInWithIdToken,
  googleSignInWithPassword,
  googleSignUpWithPassword,
  loadAuthConfig,
  signIn,
} from "../../../lib/auth";
import "../../us-release-v2.css";

type Mode = "signin" | "signup" | "reset";

interface GoogleAccountsId {
  initialize: (options: {
    client_id: string;
    callback: (response: { credential?: string }) => void;
    ux_mode?: "popup" | "redirect";
  }) => void;
  renderButton: (
    parent: HTMLElement,
    options: {
      theme?: "outline" | "filled_blue" | "filled_black";
      size?: "large" | "medium" | "small";
      text?: "continue_with" | "signin_with" | "signup_with";
      shape?: "rectangular" | "pill";
      width?: number;
    },
  ) => void;
}

declare global {
  interface Window {
    google?: { accounts?: { id?: GoogleAccountsId } };
  }
}

function safeNextPath(): string {
  if (typeof window === "undefined") return "/overview/";
  const raw = new URLSearchParams(window.location.search).get("next") ?? "";
  if (!raw.startsWith("/") || raw.startsWith("//")) return "/overview/";
  return raw;
}

function initialModeFromQuery(): Mode {
  if (typeof window === "undefined") return "signin";
  const raw = new URLSearchParams(window.location.search).get("mode");
  if (raw === "signup" || raw === "reset") return raw;
  return "signin";
}

export default function SignInPage() {
  const router = useRouter();
  const nameId = useId();
  const emailId = useId();
  const passwordId = useId();
  const googleBtnRef = useRef<HTMLDivElement | null>(null);

  const [mode, setMode] = useState<Mode>("signin");
  const [ready, setReady] = useState(false);
  const [isGoogleIdentity, setIsGoogleIdentity] = useState(false);
  const [googleOAuthClientId, setGoogleOAuthClientId] = useState<string | null>(
    null,
  );
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const [cfg, tok] = await Promise.all([loadAuthConfig(), accessToken()]);
      if (!active) return;
      if (tok) {
        router.replace(safeNextPath());
        return;
      }
      if (cfg?.provider === "google_identity") {
        setIsGoogleIdentity(true);
        setGoogleOAuthClientId(cfg.google_oauth_client_id ?? null);
      } else if (cfg) {
        await signIn(safeNextPath());
        return;
      }
      setMode(initialModeFromQuery());
      setReady(true);
    })();
    return () => {
      active = false;
    };
  }, [router]);

  useEffect(() => {
    if (
      !ready ||
      !isGoogleIdentity ||
      !googleOAuthClientId ||
      mode === "reset"
    ) {
      return;
    }
    let cancelled = false;

    const mountButton = () => {
      const gid = window.google?.accounts?.id;
      const container = googleBtnRef.current;
      if (!gid || !container || cancelled) return;
      container.innerHTML = "";
      gid.initialize({
        client_id: googleOAuthClientId,
        ux_mode: "popup",
        callback: (response) => {
          const cred = response.credential;
          if (!cred) {
            setError("Google did not return a credential. Please try again.");
            return;
          }
          setError(null);
          setBusy(true);
          void googleSignInWithIdToken(cred)
            .then(() => {
              if (!cancelled) router.replace(safeNextPath());
            })
            .catch((err: unknown) => {
              if (!cancelled) {
                setError(
                  err instanceof Error
                    ? err.message
                    : "Google sign-in failed. Please try again.",
                );
                setBusy(false);
              }
            });
        },
      });
      gid.renderButton(container, {
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        width: 340,
      });
    };

    if (window.google?.accounts?.id) {
      mountButton();
      return () => {
        cancelled = true;
      };
    }

    const existing = document.querySelector<HTMLScriptElement>(
      'script[src="https://accounts.google.com/gsi/client"]',
    );
    if (existing) {
      existing.addEventListener("load", mountButton);
      return () => {
        cancelled = true;
        existing.removeEventListener("load", mountButton);
      };
    }

    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = mountButton;
    document.head.appendChild(script);
    return () => {
      cancelled = true;
    };
  }, [ready, isGoogleIdentity, googleOAuthClientId, mode, router]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (mode === "signin") {
        await googleSignInWithPassword(email, password);
        router.replace(safeNextPath());
      } else if (mode === "signup") {
        if (!displayName.trim()) {
          setError("Enter your full name.");
          setBusy(false);
          return;
        }
        await googleSignUpWithPassword(displayName, email, password);
        router.replace(safeNextPath());
      } else {
        await googleSendPasswordReset(email);
        setNotice(
          "If an account exists for that email, a password reset link has been sent.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="management-shell">
      <header className="mgmt-header">
        <div className="mgmt-brand-area">
          <Link href="/" className="mgmt-brand">
            <AmarkalLogo variant="light" height={20} />
          </Link>
        </div>
        <div className="mgmt-header-actions">
          <Link href="/" className="mgmt-nav-link">
            Home
          </Link>
          <Link href="/onboarding/" className="mgmt-nav-link">
            Create business
          </Link>
        </div>
      </header>
      <main
        id="main-content"
        className="mgmt-main"
        style={{ maxWidth: "520px", margin: "2.5rem auto" }}
      >
        <section className="usr-card" aria-labelledby="signin-heading">
          <p className="eyebrow" style={{ marginTop: 0 }}>
            AMARKAL Workspace Access
          </p>
          <h1
            id="signin-heading"
            style={{ fontSize: "2rem", marginTop: "8px" }}
          >
            {mode === "signin"
              ? "Sign in to AMARKAL Platform"
              : mode === "signup"
                ? "Create your AMARKAL account"
                : "Reset your password"}
          </h1>
          <p className="usr-muted">
            {mode === "signin"
              ? "Access your US business workspace, AI Business Architect, and Stripe payments."
              : mode === "signup"
                ? "Register with your business email to launch your workspace immediately."
                : "Enter your account email and we will send a password reset link."}
          </p>

          {!ready ? (
            <p aria-live="polite">Checking sign-in configuration…</p>
          ) : !isGoogleIdentity ? (
            <p role="alert" className="usr-errors">
              Sign-in is not configured in this environment.
            </p>
          ) : (
            <>
              {googleOAuthClientId && mode !== "reset" && (
                <div style={{ marginBottom: "18px" }}>
                  <div
                    ref={googleBtnRef}
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      minHeight: "44px",
                    }}
                  />
                  <p
                    className="usr-muted"
                    style={{
                      textAlign: "center",
                      margin: "14px 0 0",
                      fontSize: "0.85rem",
                    }}
                  >
                    or continue with business email
                  </p>
                </div>
              )}

              <div
                className="usr-tablist usr-signin-tabs"
                role="tablist"
                aria-label="Authentication mode"
              >
                <button
                  type="button"
                  role="tab"
                  className="usr-tab"
                  aria-selected={mode === "signin"}
                  onClick={() => {
                    setMode("signin");
                    setError(null);
                    setNotice(null);
                  }}
                >
                  Sign in
                </button>
                <button
                  type="button"
                  role="tab"
                  className="usr-tab"
                  aria-selected={mode === "signup"}
                  onClick={() => {
                    setMode("signup");
                    setError(null);
                    setNotice(null);
                  }}
                >
                  Create account
                </button>
                <button
                  type="button"
                  role="tab"
                  className="usr-tab"
                  aria-selected={mode === "reset"}
                  onClick={() => {
                    setMode("reset");
                    setError(null);
                    setNotice(null);
                  }}
                >
                  Reset password
                </button>
              </div>

              {error && (
                <div className="usr-errors" role="alert">
                  <p style={{ margin: 0 }}>{error}</p>
                </div>
              )}
              {notice && (
                <p className="hold-note" role="status">
                  {notice}
                </p>
              )}

              <form
                onSubmit={(e) => void handleSubmit(e)}
                className="usr-stack"
              >
                {mode === "signup" && (
                  <label htmlFor={nameId}>
                    Full name
                    <input
                      id={nameId}
                      type="text"
                      autoComplete="name"
                      required
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                    />
                  </label>
                )}

                <label htmlFor={emailId}>
                  Business email
                  <input
                    id={emailId}
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>

                {mode !== "reset" && (
                  <label htmlFor={passwordId}>
                    Password
                    <input
                      id={passwordId}
                      type="password"
                      autoComplete={
                        mode === "signup" ? "new-password" : "current-password"
                      }
                      minLength={6}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </label>
                )}

                <button type="submit" disabled={busy}>
                  {busy
                    ? "Please wait…"
                    : mode === "signin"
                      ? "Sign in"
                      : mode === "signup"
                        ? "Create account"
                        : "Send reset email"}
                </button>
              </form>
            </>
          )}
        </section>
      </main>
      <footer className="mgmt-footer">
        <span>© 2026 Alexey AAA Logistics LLC — AMARKAL Platform</span>
        <Link href="/onboarding/">Create business</Link>
        <a href="mailto:support@amarkal-platform.com">Support</a>
        <Link href="/legal/terms/">Terms of Service</Link>
        <Link href="/legal/privacy/">Privacy Policy</Link>
      </footer>
    </div>
  );
}
