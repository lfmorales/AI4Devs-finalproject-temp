import type { User, UserManagerSettings, UserProfile } from "oidc-client-ts";

import { buildUserManagerSettings, readCognitoConfig } from "@/lib/auth/cognito-config";
import { buildEntraUserManagerSettings, readEntraConfig } from "@/lib/auth/entra-config";

export type AuthProviderName = "cognito" | "entra";

const PROVIDERS: readonly AuthProviderName[] = ["cognito", "entra"];

/**
 * The identity provider the browser signs in with: "cognito" unless NEXT_PUBLIC_AUTH_PROVIDER says "entra".
 * A blank value means the default; any other value is a configuration error, not a silent fallback.
 */
export function readAuthProvider(): AuthProviderName {
  const value = process.env.NEXT_PUBLIC_AUTH_PROVIDER?.trim();
  if (!value) return "cognito";
  if ((PROVIDERS as readonly string[]).includes(value)) return value as AuthProviderName;
  throw new Error(`Invalid NEXT_PUBLIC_AUTH_PROVIDER: expected "cognito" or "entra"`);
}

export function buildProviderSettings(provider: AuthProviderName, origin: string): UserManagerSettings {
  return provider === "entra"
    ? buildEntraUserManagerSettings(readEntraConfig(), origin)
    : buildUserManagerSettings(readCognitoConfig(), origin);
}

/**
 * The token the API expects as Bearer: the access token for Entra, the ID token for Cognito.
 * Null when the token the provider needs is missing.
 */
export function bearerTokenOf(user: User, provider: AuthProviderName): string | null {
  const token = provider === "entra" ? user.access_token : user.id_token;
  return token ? token : null;
}

/** What the interface shows as the user's address: never fails, and is empty when the profile has nothing. */
export function displayEmailOf(profile: Partial<UserProfile>, provider: AuthProviderName): string {
  if (profile.email) return profile.email;
  if (provider === "entra") return profile.preferred_username ?? profile.name ?? "";
  return "";
}
