/**
 * Helpers for page tests that use the real API client over a simulated fetch.
 * The test file must mock "@/lib/auth/user-manager" itself (vi.mock is per file).
 */
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";

export const API_URL = "http://localhost/api";

export interface FakeReply {
  status: number;
  body: unknown;
}

export interface RecordedRequest {
  method: string;
  path: string;
  body: unknown;
}

/** A route answers now, or later by returning a promise (to hold a page in its loading state). */
export type Route = (request: RecordedRequest) => FakeReply | Promise<FakeReply>;

export function reply(status: number, body: unknown): FakeReply {
  return { status, body };
}

/** Replace fetch with a router keyed "METHOD /path?query". An unrouted call fails the test loudly. */
export function installRoutes(routes: Record<string, Route>): RecordedRequest[] {
  const requests: RecordedRequest[] = [];
  process.env.NEXT_PUBLIC_API_URL = API_URL;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(API_URL, "");
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
      const request = { method, path, body };
      requests.push(request);
      const route = routes[`${method} ${path}`];
      if (!route) throw new Error(`Unrouted request ${method} ${path}`);
      const answer = await route(request);
      return new Response(JSON.stringify(answer.body), {
        status: answer.status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return requests;
}

export function renderAuthenticated(ui: ReactElement) {
  const value: AuthContextValue = {
    session: { status: "authenticated", email: "user@example.com", idToken: "token" },
    signIn: vi.fn(),
    signOut: vi.fn(),
  };
  return render(<AuthContext.Provider value={value}>{ui}</AuthContext.Provider>);
}

/** The text of a cell with every kind of whitespace (including no-break spaces) collapsed to one space. */
export function plain(element: Element | null): string {
  return (element?.textContent ?? "").replace(/\s+/g, " ").trim();
}
