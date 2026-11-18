import type { User, UserManagerSettings, UserProfile } from "oidc-client-ts";

import { buildEntraUserManagerSettings, readEntraConfig } from "@/lib/auth/entra-config";

/** The settings of the browser's sign-in, always Entra: they fail, naming the variable, without the tenant or the client. */
export function buildAuthSettings(origin: string): UserManagerSettings {
  return buildEntraUserManagerSettings(readEntraConfig(), origin);
}

/** The token the API expects as Bearer: the access token, or null when there is none. */
export function bearerTokenOf(user: User): string | null {
  return user.access_token ? user.access_token : null;
}

/** What the interface shows as the user's address: never fails, and is empty when the profile has nothing. */
export function displayEmailOf(profile: Partial<UserProfile>): string {
  return profile.email ?? profile.preferred_username ?? profile.name ?? "";
}
