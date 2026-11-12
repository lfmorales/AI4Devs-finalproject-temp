"use client";

import { UserManager } from "oidc-client-ts";

import { buildProviderSettings, readAuthProvider } from "@/lib/auth/auth-provider";
import { buildLogoutUrl, readCognitoConfig } from "@/lib/auth/cognito-config";

let userManager: UserManager | null = null;

/** One UserManager per browser tab, created lazily because it needs `window`. */
export function getUserManager(): UserManager {
  userManager ??= new UserManager(buildProviderSettings(readAuthProvider(), window.location.origin));
  return userManager;
}

/** Cognito only: Entra signs out through UserManager.signoutRedirect and its own end_session_endpoint. */
export function getLogoutUrl(): string {
  return buildLogoutUrl(readCognitoConfig(), window.location.origin);
}
