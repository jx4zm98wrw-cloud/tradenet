/**
 * Auth state — client-side.
 *
 * Storage model:
 *   - **Access token**: in-memory only. Lost on full page reload (expected;
 *     we then call /refresh to mint a new one from the refresh cookie).
 *     NOT in localStorage — any XSS would exfiltrate persistent tokens.
 *   - **Refresh token**: httpOnly cookie set by the backend on login /
 *     refresh. JavaScript can't read it (XSS-resistant). Browser sends
 *     it automatically on requests to /api/v1/auth.
 *   - **User profile**: in-memory, mirrored from the access-token claims +
 *     /auth/me response. Re-fetched on app boot via /refresh + /auth/me.
 *
 * The access token is 15-minute TTL. A simple proactive refresh runs every
 * 10 minutes from `AuthProvider` so the user never sees a 401 from token
 * expiry mid-action. On 401 from any other cause (token_version bump after
 * logout-all, server restart with new secret), the fetch wrapper redirects
 * to /login.
 */

export type Role = "admin" | "editor" | "viewer";

export type CurrentUser = {
  id: string;
  email: string;
  name: string;
  role: Role;
};

export type LoginResponse = {
  accessToken: string;
  user: CurrentUser;
};

// Module-scoped state — accessed by the api.ts fetch wrapper. Not exported
// directly; callers go through getAccessToken() / setAccessToken().
let _accessToken: string | null = null;

export function getAccessToken(): string | null {
  return _accessToken;
}

export function setAccessToken(t: string | null): void {
  _accessToken = t;
}

/** POST /auth/login. Sets the access token + (server-side) refresh cookie. */
export async function login(email: string, password: string): Promise<CurrentUser> {
  const r = await fetch("/api/v1/auth/login", {
    method: "POST",
    credentials: "include", // for the refresh cookie
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) {
    const body = (await r.json().catch(() => null)) as { error?: { message?: string }; detail?: string } | null;
    throw new Error(body?.error?.message ?? body?.detail ?? "Login failed");
  }
  const data = (await r.json()) as LoginResponse;
  _accessToken = data.accessToken;
  return data.user;
}

/** POST /auth/refresh. Used on app boot and proactively before token expiry. */
export async function refresh(): Promise<CurrentUser | null> {
  const r = await fetch("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) {
    _accessToken = null;
    return null;
  }
  const data = (await r.json()) as LoginResponse;
  _accessToken = data.accessToken;
  return data.user;
}

/** POST /auth/logout. Clears the access token + refresh cookie + bumps
 * server-side token_version (revokes any outstanding tokens for the user). */
export async function logout(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "include",
      headers: _accessToken ? { Authorization: `Bearer ${_accessToken}` } : {},
    });
  } finally {
    _accessToken = null;
  }
}
