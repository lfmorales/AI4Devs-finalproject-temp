"use client";

import { UserManager } from "oidc-client-ts";

import { buildAuthSettings } from "@/lib/auth/auth-provider";

let userManager: UserManager | null = null;

/** One UserManager per browser tab, created lazily because it needs `window`. */
export function getUserManager(): UserManager {
  userManager ??= new UserManager(buildAuthSettings(window.location.origin));
  return userManager;
}
