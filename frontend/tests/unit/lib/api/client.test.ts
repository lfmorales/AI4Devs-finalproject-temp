import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { User } from "oidc-client-ts";

import { ApiError, createApiClient } from "@/lib/api/client";

function stubFetch(status: number, body: unknown = {}) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// Mock getUserManager and userManager.removeUser
const mockRemoveUser = vi.fn();
const mockGetUser = vi.fn();

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: mockGetUser,
    removeUser: mockRemoveUser,
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createApiClient", () => {
  it("obtains the token from getUserManager().getUser() and sends the access token as Bearer", async () => {
    const user = {
      access_token: "test-access-token",
      expired: false,
    } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    const fetchMock = stubFetch(200, { status: "ok" });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const body = await client.get<{ status: string }>("/health");

    expect(body).toEqual({ status: "ok" });
    expect(mockGetUser).toHaveBeenCalled();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://localhost/api/health");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer test-access-token");
  });

  it("sends no Authorization header when there is no session", async () => {
    mockGetUser.mockResolvedValue(null);

    const fetchMock = stubFetch(200);
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    await client.get("/health");

    expect(mockGetUser).toHaveBeenCalled();
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
  });

  it("does not use expired token", async () => {
    const expiredUser = {
      access_token: "expired-token",
      expired: true,
    } as unknown as User;
    mockGetUser.mockResolvedValue(expiredUser);

    const fetchMock = stubFetch(200);
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    await client.get("/health");

    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
  });

  it.each([
    [401, "unauthenticated"],
    [403, "forbidden"],
    [500, "failed"],
  ] as const)("reports HTTP %i as a %s error", async (status, kind) => {
    const user = { access_token: "token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    stubFetch(status, { code: "x", message: "y" });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const failure = client.get("/anything");

    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ kind, status });
  });

  it("calls removeUser on 401 response", async () => {
    const user = { access_token: "token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    stubFetch(401, { code: "unauthorized" });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    try {
      await client.get("/campaigns");
    } catch (e) {
      // Expected to throw
    }

    expect(mockRemoveUser).toHaveBeenCalled();
  });

  it("supports POST requests with body and token", async () => {
    const user = { access_token: "test-token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    const fetchMock = stubFetch(201, { id: 1, name: "test" });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const body = await client.post<{ id: number; name: string }>("/campaigns", {
      name: "New Campaign",
      agency_id: 1,
    });

    expect(body).toEqual({ id: 1, name: "test" });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://localhost/api/campaigns");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer test-token");
    expect(init?.body).toBe(JSON.stringify({ name: "New Campaign", agency_id: 1 }));
  });

  it("includes error code and message in ApiError for error responses", async () => {
    const user = { access_token: "token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    stubFetch(409, { code: "duplicate_order_reference", message: "Order reference already exists" });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const failure = client.post("/campaigns", {});

    await expect(failure).rejects.toMatchObject({
      kind: "failed",
      status: 409,
      code: "duplicate_order_reference",
      message: "Order reference already exists",
    });
  });

  it("throws an error if baseUrl is empty", () => {
    expect(() => createApiClient({ baseUrl: "" })).toThrow("baseUrl must not be empty");
  });

  it("throws an error if baseUrl is whitespace only", () => {
    expect(() => createApiClient({ baseUrl: "   " })).toThrow("baseUrl must not be empty");
  });
});

describe("ApiError fieldErrors parsing", () => {
  const mockRemoveUser = vi.fn();
  const mockGetUser = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("parses single validation error into fieldErrors", async () => {
    const user = { access_token: "token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    stubFetch(422, {
      detail: [
        {
          type: "string_too_short",
          loc: ["body", "name"],
          msg: "String should have at least 1 character",
          input: "",
        },
      ],
    });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const failure = client.post("/campaigns", {});

    await expect(failure).rejects.toMatchObject({
      kind: "failed",
      status: 422,
      fieldErrors: { name: "Campo obligatorio" },
    });
  });

  it("parses multiple validation errors into fieldErrors", async () => {
    const user = { access_token: "token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    stubFetch(422, {
      detail: [
        { type: "missing", loc: ["body", "name"], msg: "Field required" },
        { type: "missing", loc: ["body", "agency_id"], msg: "Field required" },
      ],
    });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const failure = client.post("/campaigns", {});

    await expect(failure).rejects.toMatchObject({
      kind: "failed",
      fieldErrors: { name: "Campo obligatorio", agency_id: "Campo obligatorio" },
    });
  });

  it("parses nested validation error with array index", async () => {
    const user = { access_token: "token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    stubFetch(422, {
      detail: [
        {
          type: "too_short",
          loc: ["body", "lines", 0, "dsp_id"],
          msg: "List should have at least 1 item",
        },
      ],
    });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const failure = client.post("/campaigns", {});

    await expect(failure).rejects.toMatchObject({
      kind: "failed",
      fieldErrors: { "lines.0.dsp_id": "Debe contener al menos 1 elemento" },
    });
  });

  it("handles unknown error type with fallback to msg", async () => {
    const user = { access_token: "token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    stubFetch(422, {
      detail: [
        {
          type: "unknown_type",
          loc: ["body", "field"],
          msg: "Some custom error message",
        },
      ],
    });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const failure = client.post("/campaigns", {});

    await expect(failure).rejects.toMatchObject({
      kind: "failed",
      fieldErrors: { field: "Some custom error message" },
    });
  });

  it("preserves code and message for business errors (non-validation)", async () => {
    const user = { access_token: "token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    stubFetch(409, {
      code: "duplicate_order_reference",
      message: "Order reference already exists",
    });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const failure = client.post("/campaigns", {});

    await expect(failure).rejects.toMatchObject({
      kind: "failed",
      code: "duplicate_order_reference",
      fieldErrors: {},
    });
  });

  it("uses generic message for 422 validation errors, not [object Object]", async () => {
    const user = { access_token: "token", expired: false } as unknown as User;
    mockGetUser.mockResolvedValue(user);

    stubFetch(422, {
      detail: [
        {
          type: "too_short",
          loc: ["body", "lines"],
          msg: "List should have at least 1 item",
        },
      ],
    });
    const client = createApiClient({ baseUrl: "http://localhost/api" });

    const failure = client.post("/campaigns", {});

    await expect(failure).rejects.toMatchObject({
      kind: "failed",
      status: 422,
      message: "Hay campos con errores",
    });

    // Message should never contain [object Object]
    try {
      await failure;
    } catch (error) {
      if (error instanceof Error) {
        expect(error.message).not.toContain("[object Object]");
        expect(typeof error.message).toBe("string");
      }
    }
  });
});
