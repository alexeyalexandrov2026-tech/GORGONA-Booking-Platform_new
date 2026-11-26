"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import {
  accessToken,
  googleSendPasswordReset,
  googleSignInWithPassword,
  googleSignUpWithPassword,
  loadAuthConfig,
  signIn,
} from "../../../lib/auth";
import "../../us-release-v2.css";

type Mode = "signin" | "signup" | "reset";

function safeNextPath(): string {
  if (typeof window === "undefined") return "/overview/";
  const raw = new URLSearchParams(window.location.search).get("next") ?? "";
  if (!raw.startsWith("/") || raw.startsWith("//")) return "/overview/";
  return raw;
}

export default function SignInPage() {
  const router = useRouter();
  const nameId = useId();
  const emailId = useId();
  const passwordId = useId();

  const [mode, setMode] = useState<Mode>("signin");
  const [ready, setReady] = useState(false);
  const [isGoogleIdentity, setIsGoogleIdentity] = useState(false);
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
      } else if (cfg) {
        await signIn(safeNextPath());
        return;
      }
      setReady(true);
    })();
    return () => {
      active = false;
    };
  }, [router]);

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
            AMARKAL <span>Platform</span>
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
            Google Cloud Identity
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
              <div
                className="usr-tablist"
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
    </div>
  );
}
