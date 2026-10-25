import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { User } from "oidc-client-ts";

import { ApiError, createApiClient } from "@/lib/api/client";
import { previewFlights, type FlightPreviewResponse } from "@/lib/api/flights";

const mockRemoveUser = vi.fn();

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "t", expired: false } as unknown as User),
    removeUser: mockRemoveUser,
  }),
}));

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const client = createApiClient({ baseUrl: "http://localhost/api" });
const REQUEST = { campaign_start_date: "2026-08-01", campaign_end_date: "2026-09-30", contracted_impressions: 6100 };
const RESPONSE: FlightPreviewResponse = {
  start_date: "2026-08-01",
  end_date: "2026-09-30",
  flights: [
    { period_year: 2026, period_month: 8, flight_start: "2026-08-01", flight_end: "2026-08-31", contracted_impressions: 3100 },
    { period_year: 2026, period_month: 9, flight_start: "2026-09-01", flight_end: "2026-09-30", contracted_impressions: 3000 },
  ],
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("previewFlights", () => {
  it("posts to /flights/preview and returns the typed flights", async () => {
    const fetchMock = stubFetch(200, RESPONSE);

    const result = await previewFlights(client, REQUEST);

    expect(result).toEqual(RESPONSE);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://localhost/api/flights/preview");
    expect(init?.method).toBe("POST");
  });

  it("sends no line dates when the line inherits the campaign's", async () => {
    const fetchMock = stubFetch(200, RESPONSE);

    await previewFlights(client, REQUEST);

    const body = JSON.parse(String(fetchMock.mock.calls[0]![1]?.body));
    expect(body).toEqual(REQUEST);
    expect(Object.keys(body)).not.toContain("start_date");
    expect(Object.keys(body)).not.toContain("end_date");
  });

  it("sends the line's own dates when it has them", async () => {
    const fetchMock = stubFetch(200, RESPONSE);

    await previewFlights(client, { ...REQUEST, start_date: "2026-08-10", end_date: "2026-09-10" });

    const body = JSON.parse(String(fetchMock.mock.calls[0]![1]?.body));
    expect(body).toMatchObject({ start_date: "2026-08-10", end_date: "2026-09-10" });
  });

  it.each([
    "line_dates_outside_campaign",
    "line_dates_invalid",
    "volume_too_small_for_flights",
  ])("rejects with the %s code of a 422", async (code) => {
    stubFetch(422, { code, message: "fixed backend text" });

    const error = await previewFlights(client, REQUEST).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "failed", status: 422, code });
  });

  it("rejects as unauthenticated on 401 and removes the session", async () => {
    stubFetch(401, { code: "unauthenticated", message: "Missing or invalid credentials" });

    const error = await previewFlights(client, REQUEST).catch((e: unknown) => e);

    expect(error).toMatchObject({ kind: "unauthenticated", status: 401 });
    expect(mockRemoveUser).toHaveBeenCalled();
  });

  it("rejects as forbidden on 403", async () => {
    stubFetch(403, { code: "forbidden", message: "Insufficient permissions" });

    const error = await previewFlights(client, REQUEST).catch((e: unknown) => e);

    expect(error).toMatchObject({ kind: "forbidden", status: 403 });
  });
});
