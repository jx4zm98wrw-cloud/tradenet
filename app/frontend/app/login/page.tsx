"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useAuth } from "@/components/auth-context";

export default function LoginPageShell() {
  // Wrap the real page in Suspense because useSearchParams suspends.
  return (
    <Suspense fallback={null}>
      <LoginPage />
    </Suspense>
  );
}

function LoginPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const { login, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // If we're already authenticated (e.g., came via /login while logged in),
  // skip the form and bounce to the requested destination. Done in an effect
  // because router.replace() is a setState — calling it during render
  // triggers React 19's "Cannot update a component while rendering a
  // different component" error. The effect runs after commit, which is
  // when navigation is safe.
  useEffect(() => {
    if (user) {
      // `/` is the public marketing landing post-PR 1 (Route Group split).
      // Authed users with no `?next=` should land on the in-app home, not
      // bounce back to the marketing page.
      const next = sp.get("next") ?? "/today";
      router.replace(next);
    }
  }, [user, sp, router]);

  // Hide the form during the redirect frame to avoid flashing it.
  if (user) {
    return null;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      // Same fallback as the already-authed redirect above: /today is the
      // in-app home; marketing's / would dump the user back onto the public
      // landing they just signed in from.
      const next = sp.get("next") ?? "/today";
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-[calc(100vh-60px)] grid place-items-center px-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm bg-surface border border-line rounded-lg shadow-sm p-6 space-y-4"
      >
        <div>
          <h1 className="head-serif text-[22px] font-semibold tracking-tight">Sign in</h1>
          <p className="text-[12.5px] text-mute mt-1">
            Tradenet — Vietnam NOIP trademark gazette workbench
          </p>
        </div>

        <label className="block">
          <span className="text-[12px] text-mute font-medium">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
            autoComplete="email"
            className="mt-1 w-full text-[13.5px] px-3 py-2 border border-line rounded bg-paper-2 focus:bg-surface focus:border-stamp-line outline-none"
          />
        </label>

        <label className="block">
          <span className="text-[12px] text-mute font-medium">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            minLength={8}
            className="mt-1 w-full text-[13.5px] px-3 py-2 border border-line rounded bg-paper-2 focus:bg-surface focus:border-stamp-line outline-none"
          />
        </label>

        {error && (
          <div className="text-[12.5px] text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full bg-stamp text-white font-medium py-2 rounded hover:bg-stamp-deep disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <p className="text-[11px] text-mute text-center">
          No self-registration — accounts are created by an admin via the
          <code className="ml-1 px-1 py-0.5 bg-paper-2 rounded font-mono">create_user</code> CLI.
        </p>
      </form>
    </div>
  );
}
