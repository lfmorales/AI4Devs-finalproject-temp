import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { closeMonth, getMargin, marginPath } from "@/lib/api/margin";
import { margin } from "../../../helpers/margin-data";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("the margin paths", () => {
  it("has no query without filters", () => {
    expect(marginPath({})).toBe("/margin");
  });

  it("sends only the filters that have a value, with the names of the API", () => {
    expect(marginPath({ year: 2026, month: 8, campaignId: 7 })).toBe("/margin?year=2026&month=8&campaign_id=7");
    expect(marginPath({ year: 2026 })).toBe("/margin?year=2026");
    expect(marginPath({ campaignId: 7 })).toBe("/margin?campaign_id=7");
  });
});

describe("the margin calls", () => {
  it("reads the margin through the client and returns decimal amounts untouched, as strings", async () => {
    const fetchMock = stubFetch(200, margin());

    const result = await getMargin(createApiClient({ baseUrl: "http://api" }), { year: 2026, month: 8 });

    expect(fetchMock).toHaveBeenCalledWith("http://api/margin?year=2026&month=8", expect.objectContaining({ method: "GET" }));
    expect(result.totals.revenue).toBe("3631.01");
    expect(typeof result.campaigns[0]!.lines[0]!.flights[0]!.margin).toBe("string");
  });

  it("keeps an amount that a floating-point number could not hold, character for character", async () => {
    stubFetch(200, margin({ totals: { ...margin().totals, revenue: "12345678901234.56" } }));

    const result = await getMargin(createApiClient({ baseUrl: "http://api" }), {});

    expect(result.totals.revenue).toBe("12345678901234.56");
  });

  it("closes a month by posting its year and month", async () => {
    const fetchMock = stubFetch(200, { year: 2026, month: 8, closed: 3, already_closed: 0 });

    const result = await closeMonth(createApiClient({ baseUrl: "http://api" }), { year: 2026, month: 8 });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/margin/closings",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ year: 2026, month: 8 }) }),
    );
    expect(result).toEqual({ year: 2026, month: 8, closed: 3, already_closed: 0 });
  });
});
