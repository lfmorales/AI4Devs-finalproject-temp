"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { SignInState } from "@/lib/auth/AuthProvider";
import { getUserManager } from "@/lib/auth/user-manager";

function isSignInState(value: unknown): value is SignInState {
  return typeof value === "object" && value !== null && typeof (value as SignInState).returnTo === "string";
}

/** Completes the authorization code + PKCE exchange after the hosted UI redirects back. */
export default function CallbackPage() {
  const router = useRouter();
  const [failed, setFailed] = useState(false);
  // React strict mode runs effects twice in development; the code can only be exchanged once.
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    getUserManager()
      .signinRedirectCallback()
      .then((user) => {
        // Only same-site paths are accepted, so the state cannot redirect elsewhere.
        const returnTo = isSignInState(user.state) && user.state.returnTo.startsWith("/") ? user.state.returnTo : "/";
        router.replace(returnTo);
      })
      .catch(() => setFailed(true));
  }, [router]);

  if (failed) {
    return (
      <p role="alert" className="notice notice-error">
        Sign-in could not be completed. <a href="/">Return to the start page</a> and try again.
      </p>
    );
  }
  return <p role="status" className="notice notice-info">Completing sign-in…</p>;
}
