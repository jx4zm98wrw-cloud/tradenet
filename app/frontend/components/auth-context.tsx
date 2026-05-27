"use client";

import { useRouter, usePathname } from "next/navigation";
import * as React from "react";
import { type CurrentUser, login as apiLogin, logout as apiLogout, refresh } from "@/lib/auth";

type AuthState = {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = React.createContext<AuthState | null>(null);

/**
 * AuthProvider — wraps the app in layout.tsx.
 *
 * On mount, tries /auth/refresh once. If the user has a valid refresh
 * cookie, they're silently logged in (no flash of login page). Otherwise
 * `user` stays null and routes that need auth redirect to /login.
 *
 * Proactive refresh: every 10 min while logged in, mint a new access token
 * before the 15-min one expires. Cleaner UX than letting the fetch wrapper
 * 401-then-recover on every "first action after 15 min idle."
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<CurrentUser | null>(null);
  const [loading, setLoading] = React.useState(true);
  const router = useRouter();
  const pathname = usePathname();

  // Public pages that should NEVER trigger a redirect-to-login (otherwise
  // /login → /login loop). Add /forgot-password etc. here if added later.
  const publicPaths = React.useMemo(() => new Set(["/login"]), []);

  // Boot: silently try refresh.
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      const u = await refresh().catch(() => null);
      if (!cancelled) {
        setUser(u);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Proactive refresh while signed in.
  React.useEffect(() => {
    if (!user) return;
    const id = setInterval(
      () => {
        refresh()
          .then((u) => {
            if (!u) setUser(null);
          })
          .catch(() => setUser(null));
      },
      10 * 60 * 1000, // 10 min
    );
    return () => clearInterval(id);
  }, [user]);

  // If on a protected path and not authenticated, send to /login.
  React.useEffect(() => {
    if (loading) return;
    if (!user && !publicPaths.has(pathname)) {
      const next = encodeURIComponent(pathname);
      router.replace(`/login?next=${next}`);
    }
  }, [loading, user, pathname, publicPaths, router]);

  const value = React.useMemo<AuthState>(
    () => ({
      user,
      loading,
      login: async (email: string, password: string) => {
        const u = await apiLogin(email, password);
        setUser(u);
      },
      logout: async () => {
        await apiLogout();
        setUser(null);
        router.replace("/login");
      },
    }),
    [user, loading, router],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = React.useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
