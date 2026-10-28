import { test as base, expect, request, type APIRequestContext, type Page } from "@playwright/test";

import { BASE_URL } from "../playwright.config";
import { readToken } from "./token";

/** The text oidc-client-ts keeps under its sessionStorage key: a stored User. */
function storedUser(idToken: string, claims: ReturnType<typeof readToken>["claims"]): { key: string; value: string } {
  return {
    // UserStore prefix "oidc." + "user:<authority>:<client_id>"; Cognito's iss and aud are exactly those two.
    key: `oidc.user:${claims.iss}:${claims.aud}`,
    value: JSON.stringify({
      id_token: idToken,
      // The application only reads id_token; the ID token stands in for the access token it never uses.
      access_token: idToken,
      token_type: "Bearer",
      scope: "openid email",
      profile: { sub: claims.sub, iss: claims.iss, aud: claims.aud, exp: claims.exp, iat: claims.iat, email: claims.email },
      expires_at: claims.exp,
    }),
  };
}

interface Fixtures {
  /** A page that already holds the finance user's session before any script of the application runs. */
  financeSession: Page;
  /** The backend API behind /api, called with the same token. */
  api: APIRequestContext;
}

export const test = base.extend<Fixtures>({
  financeSession: async ({ page }, use) => {
    const { idToken, claims } = readToken();
    await page.addInitScript((user) => window.sessionStorage.setItem(user.key, user.value), storedUser(idToken, claims));
    await use(page);
  },
  api: async ({}, use) => {
    const { idToken } = readToken();
    const context = await request.newContext({ baseURL: `${BASE_URL}/api/`, extraHTTPHeaders: { Authorization: `Bearer ${idToken}` } });
    await use(context);
    await context.dispose();
  },
});

export { expect };

/** Answers every call of the API under `path` with the given status, to simulate a lost session or a missing role. */
export async function failApiCalls(page: Page, path: string, status: 401 | 403): Promise<void> {
  const matching = new RegExp(`/api${path}(\\?|$)`);
  await page.route(matching, (route) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ code: status === 401 ? "unauthenticated" : "forbidden", message: "simulated" }) }));
}
