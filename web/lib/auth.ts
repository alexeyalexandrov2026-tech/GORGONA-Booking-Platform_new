import {
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
} from "oidc-client-ts";
import { z } from "zod";

const configSchema = z.object({
  authority: z.string().url(),
  client_id: z.string().min(1).max(255),
  scope: z.string().min(1).max(1024).default("openid profile email"),
  resource: z.string().max(1024).optional(),
  provider: z.enum(["oidc", "google_identity"]).optional(),
  api_key: z.string().min(10).max(255).optional(),
});
export type AuthConfig = z.infer<typeof configSchema>;

interface GoogleSession {
  idToken: string;
  expiresAt: number;
  email: string;
  displayName: string;
}

const GOOGLE_SESSION_KEY = "amarkal_gid_session";
let configPromise: Promise<AuthConfig | null> | null = null;
let managerPromise: Promise<UserManager | null> | null = null;
let callbackPromise: Promise<string> | null = null;
let memoryGoogleSession: GoogleSession | null = null;

function localReturnPath(value: unknown): string | undefined {
  if (typeof value !== "string" || !value.startsWith("/")) return undefined;
  try {
    const target = new URL(value, window.location.origin);
    if (
      target.origin === window.location.origin &&
      !target.pathname.startsWith("//")
    )
      return target.pathname + target.search + target.hash;
  } catch {
    return undefined;
  }
}

function validateConfig(value: unknown): AuthConfig | null {
  const parsed = configSchema.safeParse(value);
  if (!parsed.success) return null;
  const authority = new URL(parsed.data.authority);
  const local = ["localhost", "127.0.0.1", "[::1]"];
  const localTest =
    local.includes(window.location.hostname) &&
    local.includes(authority.hostname);
  if (
    (authority.protocol !== "https:" &&
      !(localTest && authority.protocol === "http:")) ||
    authority.username ||
    authority.password ||
    authority.search ||
    authority.hash ||
    !parsed.data.scope.split(/\s+/).includes("openid") ||
    parsed.data.scope.split(/\s+/).includes("offline_access")
  )
    return null;
  if (parsed.data.provider === "google_identity" && !parsed.data.api_key)
    return null;
  return parsed.data;
}

export function loadAuthConfig(): Promise<AuthConfig | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  configPromise ??= (async () => {
    // Remove credentials left by the obsolete developer-only token form.
    localStorage.removeItem("gorgona_staff_token");
    let config = validateConfig({
      authority: process.env.NEXT_PUBLIC_OIDC_AUTHORITY,
      client_id: process.env.NEXT_PUBLIC_OIDC_CLIENT_ID,
      scope: process.env.NEXT_PUBLIC_OIDC_SCOPE ?? "openid profile email",
      resource: process.env.NEXT_PUBLIC_OIDC_RESOURCE,
    });
    if (!config) {
      try {
        const response = await fetch("/auth-config.json", {
          cache: "no-store",
          credentials: "same-origin",
          signal: AbortSignal.timeout(10000),
        });
        if (response.ok) config = validateConfig(await response.json());
      } catch {
        /* Unconfigured deployments fail closed; no test credentials. */
      }
    }
    return config;
  })();
  return configPromise;
}

function readGoogleSession(): GoogleSession | null {
  if (typeof window === "undefined") return null;
  const now = Date.now() / 1000;
  if (memoryGoogleSession) {
    if (memoryGoogleSession.expiresAt > now + 15) return memoryGoogleSession;
    memoryGoogleSession = null;
  }
  try {
    const raw = sessionStorage.getItem(GOOGLE_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<GoogleSession>;
    if (
      typeof parsed.idToken === "string" &&
      typeof parsed.expiresAt === "number" &&
      parsed.expiresAt > now + 15
    ) {
      memoryGoogleSession = {
        idToken: parsed.idToken,
        expiresAt: parsed.expiresAt,
        email: typeof parsed.email === "string" ? parsed.email : "",
        displayName:
          typeof parsed.displayName === "string" ? parsed.displayName : "",
      };
      return memoryGoogleSession;
    }
    sessionStorage.removeItem(GOOGLE_SESSION_KEY);
  } catch {
    sessionStorage.removeItem(GOOGLE_SESSION_KEY);
  }
  return null;
}

function writeGoogleSession(session: GoogleSession): void {
  memoryGoogleSession = session;
  try {
    sessionStorage.setItem(GOOGLE_SESSION_KEY, JSON.stringify(session));
  } catch {
    /* keep in memory if sessionStorage is restricted */
  }
}

function clearGoogleSession(): void {
  memoryGoogleSession = null;
  try {
    sessionStorage.removeItem(GOOGLE_SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export async function isAuthConfigured(): Promise<boolean> {
  const config = await loadAuthConfig();
  return Boolean(config);
}

export function authManager(): Promise<UserManager | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  managerPromise ??= (async () => {
    const config = await loadAuthConfig();
    if (!config || config.provider === "google_identity") return null;
    const manager = new UserManager({
      authority: config.authority,
      client_id: config.client_id,
      redirect_uri: `${window.location.origin}/auth/callback/`,
      post_logout_redirect_uri: `${window.location.origin}/auth/logout/`,
      response_type: "code",
      scope: config.scope,
      resource: config.resource,
      disablePKCE: false,
      loadUserInfo: false,
      automaticSilentRenew: false,
      monitorSession: false,
      userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
      stateStore: new WebStorageStateStore({ store: sessionStorage }),
      staleStateAgeInSeconds: 300,
      requestTimeoutInSeconds: 15,
    });
    await manager.clearStaleState();
    return manager;
  })();
  return managerPromise;
}

export async function accessToken(): Promise<string | null> {
  const config = await loadAuthConfig();
  if (config?.provider === "google_identity") {
    return readGoogleSession()?.idToken ?? null;
  }
  const manager = await authManager();
  const user = await manager?.getUser();
  if (
    !user ||
    user.expired ||
    !user.expires_at ||
    user.expires_at <= Date.now() / 1000
  ) {
    if (user) await manager?.removeUser();
    return null;
  }
  return user.access_token;
}

export async function signIn(returnPath?: string): Promise<void> {
  const config = await loadAuthConfig();
  if (!config)
    throw new Error("Account sign-in is not configured for this environment.");
  const next =
    localReturnPath(returnPath) ??
    localReturnPath(
      `${window.location.pathname}${window.location.search}${window.location.hash}`,
    ) ??
    "/overview/";
  if (config.provider === "google_identity") {
    const dest = new URL("/auth/signin/", window.location.origin);
    dest.searchParams.set("next", next);
    window.location.assign(dest.href);
    return;
  }
  const manager = await authManager();
  if (!manager)
    throw new Error("Account sign-in is not configured for this environment.");
  await manager.signinRedirect({ state: next });
}

export async function signOut(): Promise<void> {
  const config = await loadAuthConfig();
  clearGoogleSession();
  sessionStorage.removeItem("gorgona_active_salon");
  if (config?.provider === "google_identity") {
    const dest = new URL("/auth/logout/", window.location.origin);
    window.location.assign(dest.href);
    return;
  }
  const manager = await authManager();
  if (!manager) return;
  const user = await manager.getUser();
  await manager.removeUser();
  if (await manager.metadataService.getEndSessionEndpoint()) {
    await manager.signoutRedirect({ id_token_hint: user?.id_token });
  }
}

export function completeSignIn(): Promise<string> {
  callbackPromise ??= (async () => {
    const config = await loadAuthConfig();
    if (config?.provider === "google_identity") {
      return (await accessToken()) ? "/overview/" : "/auth/signin/";
    }
    const manager = await authManager();
    if (!manager)
      throw new Error(
        "Account sign-in is not configured for this environment.",
      );
    const callbackUrl = window.location.href;
    history.replaceState(null, "", "/auth/callback/");
    const user = await manager.signinRedirectCallback(callbackUrl);
    if (!(await accessToken()))
      throw new Error("No valid access token was returned.");
    return localReturnPath(user.state) ?? "/overview/";
  })();
  return callbackPromise;
}

export async function completeSignOut(): Promise<void> {
  clearGoogleSession();
  const manager = await authManager();
  const callbackUrl = window.location.href;
  history.replaceState(null, "", "/auth/logout/");
  if (manager && new URL(callbackUrl).searchParams.has("state"))
    await manager.signoutRedirectCallback(callbackUrl);
  await manager?.removeUser();
}

function mapGoogleAuthError(code: string): string {
  const clean = code.split(":")[0]?.trim() ?? "";
  switch (clean) {
    case "EMAIL_NOT_FOUND":
    case "INVALID_PASSWORD":
    case "INVALID_LOGIN_CREDENTIALS":
      return "Incorrect email or password.";
    case "EMAIL_EXISTS":
      return "An account with this email already exists. Switch to Sign in.";
    case "WEAK_PASSWORD":
      return "Password must be at least 6 characters.";
    case "INVALID_EMAIL":
      return "Enter a valid email address.";
    case "USER_DISABLED":
      return "This account has been disabled.";
    case "TOO_MANY_ATTEMPTS_TRY_LATER":
      return "Too many attempts. Please wait a few minutes and try again.";
    default:
      return "Could not complete authentication. Please try again.";
  }
}

async function googleIdentityPost(
  endpoint: string,
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const config = await loadAuthConfig();
  if (config?.provider !== "google_identity" || !config.api_key) {
    throw new Error("Google Identity authentication is not enabled.");
  }
  const response = await fetch(
    `https://identitytoolkit.googleapis.com/v1/${endpoint}?key=${encodeURIComponent(config.api_key)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  const data = (await response.json()) as {
    error?: { message?: string };
  } & Record<string, unknown>;
  if (!response.ok) {
    throw new Error(mapGoogleAuthError(data.error?.message ?? ""));
  }
  return data;
}

export async function googleSignInWithPassword(
  email: string,
  password: string,
): Promise<void> {
  const data = await googleIdentityPost("accounts:signInWithPassword", {
    email: email.trim(),
    password,
    returnSecureToken: true,
  });
  const idToken = String(data.idToken ?? "");
  const expiresIn = Number(data.expiresIn ?? 3600);
  if (!idToken) throw new Error("No identity token returned.");
  writeGoogleSession({
    idToken,
    expiresAt: Date.now() / 1000 + expiresIn,
    email: String(data.email ?? email.trim()),
    displayName: String(data.displayName ?? ""),
  });
}

export async function googleSignUpWithPassword(
  displayName: string,
  email: string,
  password: string,
): Promise<void> {
  const created = await googleIdentityPost("accounts:signUp", {
    email: email.trim(),
    password,
    returnSecureToken: true,
  });
  let idToken = String(created.idToken ?? "");
  let expiresIn = Number(created.expiresIn ?? 3600);
  if (!idToken) throw new Error("No identity token returned.");
  const cleanName = displayName.trim();
  if (cleanName) {
    const updated = await googleIdentityPost("accounts:update", {
      idToken,
      displayName: cleanName,
      returnSecureToken: true,
    });
    if (typeof updated.idToken === "string" && updated.idToken) {
      idToken = updated.idToken;
      expiresIn = Number(updated.expiresIn ?? expiresIn);
    }
  }
  writeGoogleSession({
    idToken,
    expiresAt: Date.now() / 1000 + expiresIn,
    email: String(created.email ?? email.trim()),
    displayName: cleanName,
  });
}

export async function googleSendPasswordReset(email: string): Promise<void> {
  await googleIdentityPost("accounts:sendOobCode", {
    requestType: "PASSWORD_RESET",
    email: email.trim(),
  });
}
