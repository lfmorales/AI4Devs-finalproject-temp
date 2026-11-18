import { test as base, expect, request, type APIRequestContext, type Page } from "@playwright/test";

import { BASE_URL } from "../playwright.config";
import { SESSIONS_PATH } from "./global-setup";
import { isMicrosoftSignIn, readSessions } from "./session";

/** The names of the E2E users (support/e2e-users.ts), whose sessions the global setup signs on every run. */
export type E2eUserName = "operations" | "business" | "finance" | "trading" | "finance-trading" | "business-trading";

function sessionOf(name: E2eUserName): { token: string; key: string; value: string } {
  const session = readSessions(SESSIONS_PATH)[name];
  if (session === undefined) throw new Error(`The global setup signed no session for the E2E user ${name}.`);
  return session;
}

/** Puts the E2E user's session in sessionStorage before any script of the application runs. */
export async function signInAs(page: Page, name: E2eUserName): Promise<Page> {
  const { key, value } = sessionOf(name);
  await page.addInitScript((entry) => window.sessionStorage.setItem(entry.key, entry.value), { key, value });
  return page;
}

interface Fixtures {
  /** A page that already holds the operations user's session, which may use every page and every route. */
  operationsSession: Page;
  /** The backend API behind /api, called with the operations user's token. */
  api: APIRequestContext;
  /** Fails the test if the browser sent any request to a Microsoft sign-in host; the E2E sign in through the test issuer. */
  noMicrosoftSignIn: void;
}

export const test = base.extend<Fixtures>({
  noMicrosoftSignIn: [
    async ({ context }, use) => {
      const hosts: string[] = [];
      await context.route(isMicrosoftSignIn, (route) => {
        // Only the host is kept: the path of a sign-in request carries the tenant.
        hosts.push(new URL(route.request().url()).hostname);
        return route.abort();
      });
      await use();
      expect(hosts, "requests to a Microsoft sign-in host").toEqual([]);
    },
    { auto: true },
  ],
  operationsSession: async ({ page }, use) => {
    await use(await signInAs(page, "operations"));
  },
  api: async ({}, use) => {
    const context = await request.newContext({
      baseURL: `${BASE_URL}/api/`,
      extraHTTPHeaders: { Authorization: `Bearer ${sessionOf("operations").token}` },
    });
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
