"use client";

import type { User } from "oidc-client-ts";
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { bearerTokenOf, displayEmailOf } from "@/lib/auth/auth-provider";
import { AuthContext, type AuthContextValue, type AuthSession } from "@/lib/auth/AuthContext";
import { getUserManager } from "@/lib/auth/user-manager";

export interface SignInState {
  returnTo: string;
}

function toSession(user: User | null): AuthSession {
  if (user === null || user.expired) {
    return { status: "unauthenticated" };
  }
  const bearerToken = bearerTokenOf(user);
  if (bearerToken === null) {
    return { status: "unauthenticated" };
  }
  return { status: "authenticated", email: displayEmailOf(user.profile), bearerToken };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession>({ status: "loading" });

  useEffect(() => {
    const userManager = getUserManager();
    const handleUserLoaded = (user: User) => setSession(toSession(user));

    // When a session is lost involuntarily (not from explicit signOut), mark it as expired
    const handleUserUnloaded = () => {
      setSession((prev) => {
        // If user was authenticated, transition to session_expired (involuntary loss)
        if (prev.status === "authenticated") {
          return { status: "session_expired" };
        }
        // If already unauthenticated, stay that way
        return { status: "unauthenticated" };
      });
    };

    userManager.events.addUserLoaded(handleUserLoaded);
    userManager.events.addUserUnloaded(handleUserUnloaded);
    userManager.events.addSilentRenewError(handleUserUnloaded);
    void userManager.getUser().then((user) => setSession(toSession(user)));

    return () => {
      userManager.events.removeUserLoaded(handleUserLoaded);
      userManager.events.removeUserUnloaded(handleUserUnloaded);
      userManager.events.removeSilentRenewError(handleUserUnloaded);
    };
  }, []);

  const signIn = useCallback(async (returnTo: string = "/") => {
    const state: SignInState = { returnTo };
    await getUserManager().signinRedirect({ state });
  }, []);

  const signOut = useCallback(async () => {
    // Explicit signOut: go directly to unauthenticated, not session_expired
    setSession({ status: "unauthenticated" });
    // oidc-client-ts removes the user, then leaves for the end_session_endpoint of Entra's discovery document,
    // which returns to post_logout_redirect_uri (the application's origin).
    await getUserManager().signoutRedirect();
  }, []);

  const value = useMemo<AuthContextValue>(() => ({ session, signIn, signOut }), [session, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
