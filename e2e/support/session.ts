import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

/** The frontend's Entra registration, as it was built (NEXT_PUBLIC_ENTRA_* come from ENTRA_* in .env). */
export interface EntraSettings {
  tenantId: string;
  clientId: string;
}

const VARIABLES = { tenantId: "ENTRA_TENANT_ID", clientId: "ENTRA_CLIENT_ID" } as const;

/** One value by name: the last assignment, without carriage returns, trimmed, unquoted and trimmed again. */
function valueOf(envText: string, name: string): string {
  const assignments = envText.split("\n").filter((line) => line.startsWith(`${name}=`));
  const raw = assignments.at(-1)?.slice(name.length + 1) ?? "";
  return raw.replace(/\r/g, "").trim().replace(/^(["'])(.*)\1$/, "$2").trim();
}

/**
 * Reads the tenant and client of the frontend's Entra registration from the text of .env, by name; the file is never
 * sourced. Errors name the variables only: the values appear in no message and no log.
 */
export function readEntraSettings(envText: string): EntraSettings {
  const settings = { tenantId: valueOf(envText, VARIABLES.tenantId), clientId: valueOf(envText, VARIABLES.clientId) };
  const missing = (Object.keys(VARIABLES) as (keyof EntraSettings)[]).filter((field) => settings[field] === "").map((field) => VARIABLES[field]);
  if (missing.length > 0) throw new Error(`.env has no value for ${missing.join(" and ")}, which the frontend's Entra session needs.`);
  return settings;
}

const decodeClaims = (token: string): Record<string, unknown> => {
  const payload = token.split(".")[1];
  if (payload === undefined) throw new Error("The session token is not a JWT.");
  return JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as Record<string, unknown>;
};

/**
 * The entry oidc-client-ts keeps in sessionStorage for a signed-in user: its key is "oidc." + "user:<authority>:<client_id>"
 * with the authority of entra-config.ts. The token is the access token the API receives; expires_at is its expiry, so no
 * renewal is due during a run.
 */
export function sessionStorageEntry(settings: EntraSettings, token: string): { key: string; value: string } {
  const claims = decodeClaims(token);
  return {
    key: `oidc.user:https://login.microsoftonline.com/${settings.tenantId}/v2.0:${settings.clientId}`,
    value: JSON.stringify({
      access_token: token,
      token_type: "Bearer",
      scope: `openid profile email api://${settings.clientId}/access_as_user`,
      profile: { sub: claims.oid, oid: claims.oid, email: claims.email, iss: claims.iss, aud: claims.aud, iat: claims.iat, exp: claims.exp },
      expires_at: claims.exp,
    }),
  };
}

/** The hosts of a Microsoft sign-in. The E2E sign in through the test issuer only: any request to them is a failure. */
const MICROSOFT_SIGN_IN = /^https:\/\/login\.microsoft(online)?\.com\//;

export function isMicrosoftSignIn(url: string): boolean {
  return MICROSOFT_SIGN_IN.test(url);
}

/** What the global setup leaves for one E2E user: its token and its sessionStorage entry. */
export interface StoredSession {
  token: string;
  key: string;
  value: string;
}

export type StoredSessions = Record<string, StoredSession>;

/** Written by the global setup on every run, in e2e/.auth (ignored by git); tokens of the test issuer only. */
export function writeSessions(path: string, sessions: StoredSessions): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(sessions), { mode: 0o600 });
}

export function readSessions(path: string): StoredSessions {
  if (!existsSync(path)) throw new Error(`${path} does not exist: the global setup writes it, so run the specs with npx playwright test.`);
  return JSON.parse(readFileSync(path, "utf8")) as StoredSessions;
}
