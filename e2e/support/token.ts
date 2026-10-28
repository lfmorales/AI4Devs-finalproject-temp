import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export const TOKEN_PATH = join(__dirname, "..", ".auth", "token.json");

/** The claims of the ID token that the session injection and the setup checks need. */
export interface TokenClaims {
  sub: string;
  email: string;
  iss: string;
  aud: string;
  iat: number;
  exp: number;
}

export interface StoredToken {
  idToken: string;
  claims: TokenClaims;
}

/** The token is only decoded to read its public claims; its signature is the backend's concern. */
export function decodeClaims(idToken: string): TokenClaims {
  const payload = idToken.split(".")[1];
  if (payload === undefined) throw new Error("The stored value is not a JWT.");
  return JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as TokenClaims;
}

export function readToken(): StoredToken {
  if (!existsSync(TOKEN_PATH)) throw new Error("e2e/.auth/token.json does not exist.");
  const stored = JSON.parse(readFileSync(TOKEN_PATH, "utf8")) as { id_token?: string };
  if (!stored.id_token) throw new Error("e2e/.auth/token.json has no id_token.");
  return { idToken: stored.id_token, claims: decodeClaims(stored.id_token) };
}

export function minutesLeft(claims: TokenClaims, nowMs: number = Date.now()): number {
  return Math.floor((claims.exp * 1000 - nowMs) / 60_000);
}
