import { describe, expect, it } from "vitest";

import { filterExceptions, hasActiveFilter, normalizeText, NO_FILTER } from "@/features/exceptions/filter";
import type { IngestionException } from "@/lib/api/exceptions";

function exception(overrides: Partial<IngestionException> = {}): IngestionException {
  return {
    id: 1, exception_type: "unmatched_delivery", status: "open", ingestion_batch_id: 3, dsp_id: 1,
    external_campaign_id: "C-9", external_line_item_id: "L-9", campaign_line_id: null, campaign_period_id: null,
    first_date: null, last_date: null, days: 1, impressions_total: 1, clicks_total: 0,
    resolved_at: null, resolved_by: null, note: null, campaign_name: "Campaña Navidad", line_item_name: "Display Móvil", ...overrides,
  };
}

const MISSING = exception({
  id: 2, exception_type: "missing_delivery", dsp_id: null, external_campaign_id: null, external_line_item_id: null,
  campaign_line_id: 17, campaign_period_id: 4, campaign_name: null, line_item_name: null,
});
const OTHER = exception({ id: 3, dsp_id: 2, external_campaign_id: "K-1", external_line_item_id: "M-2", campaign_name: "Verano", line_item_name: "Vídeo" });
const ROWS = [exception(), MISSING, OTHER];

const ids = (text: string, type: "" | "unmatched_delivery" | "missing_delivery" = "") =>
  filterExceptions(ROWS, { text, type }).map((row) => row.id);

describe("normalizeText", () => {
  it("lowercases and removes accents", () => {
    expect(normalizeText("CAMPAÑA Móvil Ünï")).toBe("campana movil uni");
  });

  it("treats composed and decomposed accents the same", () => {
    expect(normalizeText("é")).toBe(normalizeText("é"));
  });
});

describe("filterExceptions", () => {
  it("shows everything for an empty or blank text", () => {
    expect(ids("")).toEqual([1, 2, 3]);
    expect(ids("   ")).toEqual([1, 2, 3]);
  });

  it("searches the campaign name and the line item name", () => {
    expect(ids("navidad")).toEqual([1]);
    expect(ids("vídeo")).toEqual([3]);
  });

  it("searches the DSP", () => {
    expect(ids("dsp 2")).toEqual([3]);
  });

  it("searches the external pair, whole or by part", () => {
    expect(ids("C-9 / L-9")).toEqual([1]);
    expect(ids("k-1")).toEqual([3]);
  });

  it("searches the text of an absence exception", () => {
    expect(ids("línea 17")).toEqual([2]);
    expect(ids("periodo 4")).toEqual([2]);
  });

  it("ignores case and accents on both sides", () => {
    expect(ids("CAMPANA")).toEqual([1]);
    expect(ids("movil")).toEqual([1]);
    expect(ids("video")).toEqual([3]);
    expect(ids("linea 17")).toEqual([2]);
  });

  it("needs every term, in any order", () => {
    expect(ids("display navidad")).toEqual([1]);
    expect(ids("navidad verano")).toEqual([]);
  });

  it("filters by type, alone and with a text", () => {
    expect(ids("", "missing_delivery")).toEqual([2]);
    expect(ids("", "unmatched_delivery")).toEqual([1, 3]);
    expect(ids("verano", "unmatched_delivery")).toEqual([3]);
    expect(ids("verano", "missing_delivery")).toEqual([]);
  });

  it("does not change the order or the rows", () => {
    expect(filterExceptions(ROWS, NO_FILTER)).toEqual(ROWS);
  });
});

describe("hasActiveFilter", () => {
  it("is false for no filter and for a blank text, true otherwise", () => {
    expect(hasActiveFilter(NO_FILTER)).toBe(false);
    expect(hasActiveFilter({ text: "  ", type: "" })).toBe(false);
    expect(hasActiveFilter({ text: "a", type: "" })).toBe(true);
    expect(hasActiveFilter({ text: "", type: "missing_delivery" })).toBe(true);
  });
});
