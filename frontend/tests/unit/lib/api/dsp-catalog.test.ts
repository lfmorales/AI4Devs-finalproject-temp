import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { User } from "oidc-client-ts";

import { ApiError, createApiClient } from "@/lib/api/client";
import {
  createDspMapping,
  listDspCatalog,
  listUnmappedLines,
  unlinkLine,
  type DspCatalogPage,
  type DspMapping,
  type UnmappedLine,
} from "@/lib/api/dsp-catalog";
import { linkException, type LinkExceptionResponse } from "@/lib/api/exceptions";

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

const PAGE: DspCatalogPage = {
  items: [{
    dsp_id: 1, external_campaign_id: "C-1", external_line_item_id: "L-1", campaign_name: "Campaña", line_item_name: "Línea",
    line_start_date: "2026-08-01", line_end_date: null, first_seen_date: "2026-08-02", last_seen_date: "2026-08-09",
    last_impressions_date: null, mapped_line_id: null,
  }],
  total: 1, limit: 50, offset: 0,
};
const UNMAPPED: UnmappedLine[] = [{
  id: 4, campaign_name: "Campaña A", line_number: 2, start_date: "2026-08-01", end_date: "2026-08-31", dsp_id: 1, dsp_name: "Adform",
}];
const MAPPING: DspMapping = {
  id: 9, campaign_line_id: 4, dsp_id: 1, external_campaign_id: "C-1", external_line_item_id: "L-1",
  validated_at: "2026-08-10T09:00:00", validation: "found", last_impressions_date: null, needs_history_load: false,
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

function lastCall(fetchMock: ReturnType<typeof stubFetch>) {
  const [url, init] = fetchMock.mock.calls[0]!;
  return { url: String(url), method: init?.method, body: init?.body };
}

describe("listDspCatalog", () => {
  it("gets /dsp-catalog with no query when no filter is given", async () => {
    const fetchMock = stubFetch(200, PAGE);

    await expect(listDspCatalog(client, {})).resolves.toEqual(PAGE);

    expect(lastCall(fetchMock)).toMatchObject({ url: "http://localhost/api/dsp-catalog", method: "GET" });
  });

  it("sends every filter with the backend's parameter names", async () => {
    const fetchMock = stubFetch(200, PAGE);

    await listDspCatalog(client, { q: "navidad", mapped: false, activeSince: "2026-08-01", limit: 25, offset: 50 });

    expect(lastCall(fetchMock).url).toBe(
      "http://localhost/api/dsp-catalog?q=navidad&mapped=false&active_since=2026-08-01&limit=25&offset=50",
    );
  });

  it("encodes the text and leaves out empty filters, but keeps mapped=true", async () => {
    const fetchMock = stubFetch(200, PAGE);

    await listDspCatalog(client, { q: "a&b 100%", mapped: true, activeSince: "" });

    expect(lastCall(fetchMock).url).toBe("http://localhost/api/dsp-catalog?q=a%26b+100%25&mapped=true");
  });

  it.each([[401, "unauthenticated"], [403, "forbidden"]])("rejects a %i as %s", async (status, kind) => {
    stubFetch(status, { code: "x", message: "x" });

    await expect(listDspCatalog(client, {})).rejects.toMatchObject({ kind, status });
  });
});

describe("listUnmappedLines", () => {
  it("gets /campaign-lines/unmapped", async () => {
    const fetchMock = stubFetch(200, UNMAPPED);

    await expect(listUnmappedLines(client)).resolves.toEqual(UNMAPPED);

    expect(lastCall(fetchMock)).toMatchObject({ url: "http://localhost/api/campaign-lines/unmapped", method: "GET" });
  });

  it("rejects a 403 as forbidden", async () => {
    stubFetch(403, { code: "missing_role", message: "x" });

    await expect(listUnmappedLines(client)).rejects.toMatchObject({ kind: "forbidden" });
  });
});

describe("linkException", () => {
  const RESPONSE = { mapping: { ...MAPPING, validation: undefined }, exception: {}, needs_history_load: true } as unknown as LinkExceptionResponse;

  it("posts the line id to the exception's link route", async () => {
    const fetchMock = stubFetch(200, RESPONSE);

    await expect(linkException(client, 5, 4)).resolves.toEqual(RESPONSE);

    const call = lastCall(fetchMock);
    expect(call).toMatchObject({ url: "http://localhost/api/ingestion-exceptions/5/link", method: "POST" });
    expect(JSON.parse(String(call.body))).toEqual({ campaign_line_id: 4 });
  });

  it.each([
    [409, "exception_already_resolved"], [404, "exception_not_found"], [409, "exception_not_linkable"],
    [404, "line_not_found"], [422, "line_dsp_mismatch"], [409, "mapping_pair_taken"],
  ])("keeps the backend code of a %i %s", async (status, code) => {
    stubFetch(status, { code, message: "backend text" });

    const error = await linkException(client, 5, 4).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status, code, kind: "failed" });
  });
});

describe("createDspMapping", () => {
  it("posts the pair to the line's mappings route", async () => {
    const fetchMock = stubFetch(201, MAPPING);

    await expect(createDspMapping(client, 4, { external_campaign_id: "C-1", external_line_item_id: "L-1" })).resolves.toEqual(MAPPING);

    const call = lastCall(fetchMock);
    expect(call).toMatchObject({ url: "http://localhost/api/campaign-lines/4/dsp-mappings", method: "POST" });
    expect(JSON.parse(String(call.body))).toEqual({ external_campaign_id: "C-1", external_line_item_id: "L-1" });
  });
});

describe("unlinkLine", () => {
  it("sends a DELETE to the line's mappings route and returns the removed days", async () => {
    const fetchMock = stubFetch(200, { campaign_line_id: 4, removed_delivery_days: 12 });

    await expect(unlinkLine(client, 4)).resolves.toEqual({ campaign_line_id: 4, removed_delivery_days: 12 });

    expect(lastCall(fetchMock)).toMatchObject({ url: "http://localhost/api/campaign-lines/4/dsp-mappings", method: "DELETE" });
  });

  it.each([[409, "ambiguous_mapping"], [404, "mapping_not_found"], [404, "line_not_found"]])(
    "keeps the backend code of a %i %s", async (status, code) => {
      stubFetch(status, { code, message: "backend text" });

      await expect(unlinkLine(client, 4)).rejects.toMatchObject({ status, code });
    },
  );
});
