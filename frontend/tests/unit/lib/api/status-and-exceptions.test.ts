import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { User } from "oidc-client-ts";

import { ApiError, createApiClient } from "@/lib/api/client";
import { getCampaignStatus, type CampaignStatusRow } from "@/lib/api/status";
import {
  listIngestionExceptions,
  resolveIngestionException,
  type IngestionException,
} from "@/lib/api/exceptions";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "t", expired: false } as unknown as User),
    removeUser: vi.fn(),
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

const STATUS_ROW: CampaignStatusRow = {
  campaign: { id: 1, name: "Campaña A" },
  agency: { id: 2, name: "Agencia A" },
  line_number: 1,
  flight: { campaign_period_id: 7, year: 2026, month: 8, start: "2026-08-01", end: "2026-08-31" },
  contracted_impressions: 3100,
  delivered_impressions: 1200,
  delivery_ratio: 0.387,
  pacing: { expected_impressions: 1500.5, deviation: -0.2, days_remaining: 20, status: "under_delivering" },
  pacing_flag: true,
  missing_data_flag: false,
};

const EXCEPTION: IngestionException = {
  id: 5,
  exception_type: "unmatched_delivery",
  status: "open",
  ingestion_batch_id: 3,
  dsp_id: 1,
  external_campaign_id: "9",
  external_line_item_id: "9",
  campaign_line_id: null,
  campaign_period_id: null,
  first_date: "2026-08-03",
  last_date: "2026-08-08",
  days: 3,
  impressions_total: 400,
  clicks_total: 11,
  resolved_at: null,
  resolved_by: null,
  note: null,
  campaign_name: null,
  line_item_name: null,
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("getCampaignStatus", () => {
  it("gets /campaign-status and returns the typed rows", async () => {
    const fetchMock = stubFetch(200, [STATUS_ROW]);

    const rows = await getCampaignStatus(client);

    expect(rows).toEqual([STATUS_ROW]);
    expect(fetchMock.mock.calls[0]![0]).toBe("http://localhost/api/campaign-status");
    expect(fetchMock.mock.calls[0]![1]?.method).toBe("GET");
  });

  it("keeps contracted and delivered as distinct fields", async () => {
    stubFetch(200, [STATUS_ROW]);

    const [row] = await getCampaignStatus(client);

    expect(row!.contracted_impressions).toBe(3100);
    expect(row!.delivered_impressions).toBe(1200);
  });

  it("raises a forbidden ApiError on 403 and an unauthenticated one on 401", async () => {
    stubFetch(403, { code: "missing_role", message: "no" });
    await expect(getCampaignStatus(client)).rejects.toMatchObject({ kind: "forbidden" });

    stubFetch(401, { code: "invalid_token", message: "no" });
    const error = await getCampaignStatus(client).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe("unauthenticated");
  });
});

describe("listIngestionExceptions", () => {
  it("passes the status as a query parameter", async () => {
    const fetchMock = stubFetch(200, [EXCEPTION]);

    const rows = await listIngestionExceptions(client, "open");

    expect(rows).toEqual([EXCEPTION]);
    expect(fetchMock.mock.calls[0]![0]).toBe("http://localhost/api/ingestion-exceptions?status=open");
  });

  it("asks for resolved exceptions", async () => {
    const fetchMock = stubFetch(200, []);

    await listIngestionExceptions(client, "resolved");

    expect(fetchMock.mock.calls[0]![0]).toBe("http://localhost/api/ingestion-exceptions?status=resolved");
  });
});

describe("resolveIngestionException", () => {
  it("posts the note to the resolve path of the exception", async () => {
    const resolved = { ...EXCEPTION, status: "resolved" as const, note: "Typo" };
    const fetchMock = stubFetch(200, resolved);

    const result = await resolveIngestionException(client, 5, "Typo");

    expect(result).toEqual(resolved);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://localhost/api/ingestion-exceptions/5/resolve");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ note: "Typo" });
  });

  it("sends a null note when none is given", async () => {
    const fetchMock = stubFetch(200, EXCEPTION);

    await resolveIngestionException(client, 5, null);

    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ note: null });
  });

  it("surfaces the backend error code on 409 and 404", async () => {
    stubFetch(409, { code: "exception_already_resolved", message: "x" });
    await expect(resolveIngestionException(client, 5, null)).rejects.toMatchObject({ code: "exception_already_resolved" });

    stubFetch(404, { code: "exception_not_found", message: "x" });
    await expect(resolveIngestionException(client, 5, null)).rejects.toMatchObject({ code: "exception_not_found" });
  });
});

describe("fetch is only called by the API client", () => {
  function sourceFiles(directory: string): string[] {
    return readdirSync(directory).flatMap((name) => {
      const path = join(directory, name);
      if (statSync(path).isDirectory()) return sourceFiles(path);
      return /\.(ts|tsx)$/.test(name) ? [path] : [];
    });
  }

  it("has no fetch call in app/ or features/", () => {
    const offenders = ["app", "features"]
      .flatMap((directory) => sourceFiles(join(process.cwd(), directory)))
      .filter((path) => /\bfetch\s*\(/.test(readFileSync(path, "utf8")));

    expect(offenders).toEqual([]);
  });
});
