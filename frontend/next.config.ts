import type { NextConfig } from "next";
import { PHASE_PRODUCTION_BUILD } from "next/constants";

import { readEntraConfig } from "./lib/auth/entra-config";

/**
 * The production build fails, naming the variable, when NEXT_PUBLIC_ENTRA_TENANT_ID or NEXT_PUBLIC_ENTRA_CLIENT_ID is
 * empty: Next.js inlines them into the bundle now, and without them the browser could not sign in. The development
 * server and the runtime image (which does not carry them) are not checked.
 */
export default function nextConfig(phase: string): NextConfig {
  if (phase === PHASE_PRODUCTION_BUILD) readEntraConfig();
  return {
    // Self-contained server bundle, so the runtime image needs no node_modules install.
    output: "standalone",
  };
}
