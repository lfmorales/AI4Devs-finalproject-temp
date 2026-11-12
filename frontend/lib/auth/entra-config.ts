import type { UserManagerSettings } from "oidc-client-ts";

import { CALLBACK_PATH } from "@/lib/auth/cognito-config";

export interface EntraConfig {
  tenantId: string;
  clientId: string;
}

const ENTRA_VARIABLES: Record<keyof EntraConfig, string> = {
  tenantId: "NEXT_PUBLIC_ENTRA_TENANT_ID",
  clientId: "NEXT_PUBLIC_ENTRA_CLIENT_ID",
};

/**
 * Reads the public Entra settings. Each variable is referenced literally
 * because Next.js only inlines NEXT_PUBLIC_* values written out in full.
 */
export function readEntraConfig(): EntraConfig {
  const config: Record<keyof EntraConfig, string | undefined> = {
    tenantId: process.env.NEXT_PUBLIC_ENTRA_TENANT_ID?.trim(),
    clientId: process.env.NEXT_PUBLIC_ENTRA_CLIENT_ID?.trim(),
  };
  const missing = (Object.keys(config) as (keyof EntraConfig)[])
    .filter((name) => !config[name])
    .map((name) => ENTRA_VARIABLES[name]);
  if (missing.length > 0) {
    throw new Error(`Missing Entra configuration: ${missing.join(", ")}`);
  }
  return config as EntraConfig;
}

export function buildEntraUserManagerSettings(config: EntraConfig, origin: string): UserManagerSettings {
  return {
    authority: `https://login.microsoftonline.com/${config.tenantId}/v2.0`,
    client_id: config.clientId,
    redirect_uri: `${origin}${CALLBACK_PATH}`,
    // Must be registered in the Entra application besides the callback URL.
    post_logout_redirect_uri: origin,
    // Authorization code flow; oidc-client-ts adds PKCE. The registration is a public client.
    response_type: "code",
    // The API scope makes the access token one the backend accepts. No offline_access: no refresh token.
    scope: `openid profile email api://${config.clientId}/access_as_user`,
    // Without a refresh token a silent renewal would need a hidden iframe: when the token expires, the user signs in again.
    automaticSilentRenew: false,
  };
}
