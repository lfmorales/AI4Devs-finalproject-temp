"use client";

import type { ReactNode } from "react";

import { useAuth } from "@/lib/auth/AuthContext";

/**
 * Hides a view from users without a session. This is usability, not security:
 * every API call behind the view is authorised again by the backend.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, signIn } = useAuth();

  if (session.status === "loading") {
    return <p role="status" className="notice notice-info">Checking your session…</p>;
  }

  if (session.status === "unauthenticated") {
    return (
      <section>
        <p>You need to sign in to see this page.</p>
        <button type="button" onClick={() => void signIn(window.location.pathname)}>
          Sign in
        </button>
      </section>
    );
  }

  return <>{children}</>;
}
