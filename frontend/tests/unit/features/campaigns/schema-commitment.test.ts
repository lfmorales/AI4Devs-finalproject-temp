import { describe, expect, it } from "vitest";

import { campaignLineSchema } from "@/features/campaigns/schema";

const LINE = {
  dsp_id: 1, channel_id: 1, format_id: 1, scope: "national", market_description: "Nacional",
  contracted_impressions: 1000, sale_cpm: "5.00",
};

describe("the volume commitment of a line in the request schema", () => {
  it.each(["committed", "target"])("accepts %s", (commitment) => {
    expect(campaignLineSchema.safeParse({ ...LINE, volume_commitment: commitment }).success).toBe(true);
  });

  it("refuses a line without it, because the API has no default", () => {
    expect(campaignLineSchema.safeParse(LINE).success).toBe(false);
  });

  it.each(["maybe", "Target", ""])("refuses %j", (commitment) => {
    expect(campaignLineSchema.safeParse({ ...LINE, volume_commitment: commitment }).success).toBe(false);
  });
});
