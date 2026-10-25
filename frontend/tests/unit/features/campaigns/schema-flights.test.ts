import { describe, expect, it } from "vitest";

import {
  FLIGHT_MESSAGES,
  createCampaignSchema,
  manualVolumesSchema,
} from "@/features/campaigns/schema";

const baseLine = {
  dsp_id: 1,
  channel_id: 1,
  format_id: 1,
  scope: "national",
  market_description: "Nacional",
  contracted_impressions: 1000,
  sale_cpm: "5.00",
};

function campaignWith(line: Record<string, unknown>, dates = { start_date: "2026-08-01", end_date: "2026-09-30" }) {
  return {
    name: "C",
    display_name: "C",
    agency_id: 1,
    advertiser_id: 1,
    campaign_type_id: 1,
    sector_id: 1,
    sales_rep_id: 1,
    ...dates,
    order_reference: "PO-1",
    order_received_on: "2026-07-01",
    lines: [{ ...baseLine, ...line }],
  };
}

function issueFor(data: unknown, path: string) {
  const result = createCampaignSchema.safeParse(data);
  if (result.success) return undefined;
  return result.error.issues.find((issue) => issue.path.join(".") === path)?.message;
}

describe("line dates in the campaign schema", () => {
  it("accepts a line without dates of its own", () => {
    expect(createCampaignSchema.safeParse(campaignWith({})).success).toBe(true);
  });

  it("accepts own dates inside the campaign's, bounds included", () => {
    const line = { start_date: "2026-08-01", end_date: "2026-09-30" };
    expect(createCampaignSchema.safeParse(campaignWith(line)).success).toBe(true);
  });

  it("rejects a start before the campaign's start", () => {
    const line = { start_date: "2026-07-31", end_date: "2026-09-01" };
    expect(issueFor(campaignWith(line), "lines.0.start_date")).toBe(FLIGHT_MESSAGES.lineStartOutside);
  });

  it("rejects an end after the campaign's end", () => {
    const line = { start_date: "2026-08-10", end_date: "2026-10-01" };
    expect(issueFor(campaignWith(line), "lines.0.end_date")).toBe(FLIGHT_MESSAGES.lineEndOutside);
  });

  it("rejects an end before the start", () => {
    const line = { start_date: "2026-09-10", end_date: "2026-09-09" };
    expect(issueFor(campaignWith(line), "lines.0.end_date")).toBe(FLIGHT_MESSAGES.lineEndBeforeStart);
  });

  it("accepts a one-day line", () => {
    const line = { start_date: "2026-09-10", end_date: "2026-09-10" };
    expect(createCampaignSchema.safeParse(campaignWith(line)).success).toBe(true);
  });

  it("asks for the missing half when only one own date is given", () => {
    expect(issueFor(campaignWith({ start_date: "2026-08-10" }), "lines.0.end_date")).toBe(FLIGHT_MESSAGES.lineEndRequired);
    expect(issueFor(campaignWith({ end_date: "2026-08-10" }), "lines.0.start_date")).toBe(FLIGHT_MESSAGES.lineStartRequired);
  });

  it("does not compare line dates with a campaign whose own dates are invalid", () => {
    const data = campaignWith({ start_date: "2026-08-10", end_date: "2026-08-12" }, { start_date: "", end_date: "" });
    expect(issueFor(data, "lines.0.start_date")).toBeUndefined();
  });

  it("takes the messages from the schema in Spanish", () => {
    expect(FLIGHT_MESSAGES.lineStartOutside).toMatch(/dentro de las fechas de la campaña/);
  });
});

const MONTHS = [
  { year: 2026, month: 8 },
  { year: 2026, month: 9 },
];

function manual(volumes: { year: number; month: number; volume: number }[], total = 1000) {
  const result = manualVolumesSchema(MONTHS, total).safeParse(volumes);
  return result.success ? null : result.error.issues[0]?.message;
}

describe("manual split rules", () => {
  it("accepts a split that covers the months, is positive and adds up", () => {
    expect(manual([{ year: 2026, month: 8, volume: 400 }, { year: 2026, month: 9, volume: 600 }])).toBeNull();
  });

  it("rejects a missing month", () => {
    expect(manual([{ year: 2026, month: 8, volume: 1000 }])).toBe(FLIGHT_MESSAGES.incomplete);
  });

  it("rejects an extra month", () => {
    const volumes = [
      { year: 2026, month: 8, volume: 300 },
      { year: 2026, month: 9, volume: 300 },
      { year: 2026, month: 10, volume: 400 },
    ];
    expect(manual(volumes)).toBe(FLIGHT_MESSAGES.incomplete);
  });

  it("rejects a repeated month", () => {
    const volumes = [{ year: 2026, month: 8, volume: 500 }, { year: 2026, month: 8, volume: 500 }];
    expect(manual(volumes)).toBe(FLIGHT_MESSAGES.incomplete);
  });

  it("rejects a zero or negative volume", () => {
    expect(manual([{ year: 2026, month: 8, volume: 0 }, { year: 2026, month: 9, volume: 1000 }])).toBe(FLIGHT_MESSAGES.notPositive);
    expect(manual([{ year: 2026, month: 8, volume: -5 }, { year: 2026, month: 9, volume: 1005 }])).toBe(FLIGHT_MESSAGES.notPositive);
  });

  it("rejects a sum that differs from the total", () => {
    expect(manual([{ year: 2026, month: 8, volume: 400 }, { year: 2026, month: 9, volume: 500 }])).toBe(FLIGHT_MESSAGES.mismatch);
  });

  it("reports coverage before positivity before the sum, as the backend does", () => {
    expect(manual([{ year: 2026, month: 8, volume: 0 }])).toBe(FLIGHT_MESSAGES.incomplete);
    expect(manual([{ year: 2026, month: 8, volume: 0 }, { year: 2026, month: 9, volume: 5 }])).toBe(FLIGHT_MESSAGES.notPositive);
  });

  it("uses the same Spanish texts as the backend codes", () => {
    expect(FLIGHT_MESSAGES.mismatch).toBe("Los volúmenes mensuales deben sumar el total de la línea.");
    expect(FLIGHT_MESSAGES.notPositive).toBe("Cada volumen mensual debe ser positivo.");
    expect(FLIGHT_MESSAGES.incomplete).toBe("El reparto debe cubrir exactamente los meses en los que corre la línea.");
  });
});

describe("monthly volumes inside a line of the campaign schema", () => {
  it("accepts well-formed items", () => {
    const line = { monthly_volumes: [{ year: 2026, month: 8, volume: 400 }, { year: 2026, month: 9, volume: 600 }] };
    expect(createCampaignSchema.safeParse(campaignWith(line)).success).toBe(true);
  });

  it("rejects a month outside 1 to 12", () => {
    const line = { monthly_volumes: [{ year: 2026, month: 13, volume: 1000 }] };
    expect(createCampaignSchema.safeParse(campaignWith(line)).success).toBe(false);
  });
});
