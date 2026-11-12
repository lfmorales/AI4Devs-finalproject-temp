import type { User } from "oidc-client-ts";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api/client";

const getUser = vi.fn();
const removeUser = vi.fn();

vi.mock("@/lib/auth/user-manager", () => ({ getUserManager: () => ({ getUser, removeUser }) }));

function stubFetch() {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
    new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const user = (fields: Record<string, unknown>) => ({ expired: false, ...fields }) as unknown as User;

async function authorizationSent(fetchMock: ReturnType<typeof stubFetch>) {
  const client = createApiClient({ baseUrl: "http://localhost/api" });
  await client.get("/health");
  return new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Authorization");
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("the Bearer token of the API client", () => {
  it("is the access token with entra, even when an identity token is present", async () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "entra");
    getUser.mockResolvedValue(user({ id_token: "token-de-identidad", access_token: "token-de-acceso" }));

    expect(await authorizationSent(stubFetch())).toBe("Bearer token-de-acceso");
  });

  it("is the identity token with cognito, even when an access token is present", async () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "cognito");
    getUser.mockResolvedValue(user({ id_token: "token-de-identidad", access_token: "token-de-acceso" }));

    expect(await authorizationSent(stubFetch())).toBe("Bearer token-de-identidad");
  });

  it("is the identity token when no provider is set", async () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", undefined);
    getUser.mockResolvedValue(user({ id_token: "token-de-identidad", access_token: "token-de-acceso" }));

    expect(await authorizationSent(stubFetch())).toBe("Bearer token-de-identidad");
  });

  it("is not sent with entra when the access token is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "entra");
    getUser.mockResolvedValue(user({ id_token: "token-de-identidad" }));

    expect(await authorizationSent(stubFetch())).toBeNull();
  });
});
