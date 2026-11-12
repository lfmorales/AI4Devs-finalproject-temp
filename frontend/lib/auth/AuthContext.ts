"use client";

import { createContext, useContext } from "react";

/** `bearerToken` is the token the API client sends: the ID token for Cognito, the access token for Entra. */
export type AuthSession =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "session_expired" }
  | { status: "authenticated"; email: string; bearerToken: string };

export interface AuthContextValue {
  session: AuthSession;
  /** Starts the hosted UI sign-in and returns to `returnTo` afterwards. */
  signIn: (returnTo?: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
