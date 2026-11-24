import { describe, expect, it } from "vitest";
import { createCampaignSchema } from "@/features/campaigns/schema";

describe("Campaign Schema Validation", () => {
  it("shows translated scope error message from Zod 4", () => {
    const invalidData = {
      name: "Test Campaign",
      display_name: "Test",
      agency_id: 1,
      advertiser_id: 1,
      campaign_type_id: 1,
      sector_id: 1,
      sales_rep_id: 1,
      start_date: "2026-01-01",
      end_date: "2026-03-31",
      order_reference: "ORD-001",
      order_received_on: "2026-01-01",
      lines: [
        {
          dsp_id: 1,
          channel_id: 1,
          format_id: 1,
          scope: "", // Empty scope - invalid enum
          market_description: "Market",
          contracted_impressions: 1000,
          sale_cpm: "25.50",
          volume_commitment: "committed",
        },
      ],
    };

    const result = createCampaignSchema.safeParse(invalidData);
    expect(result.success).toBe(false);

    if (!result.success) {
      const scopeError = result.error.issues.find((issue) =>
        issue.path.includes("scope")
      );
      expect(scopeError).toBeDefined();
      // Verify the message is in Spanish and user-friendly
      expect(scopeError?.message).toBe("Selecciona el ámbito");
      // Verify it's NOT the English Zod message
      expect(scopeError?.message).not.toContain("Invalid option");
      expect(scopeError?.message).not.toContain("expected one of");
    }
  });
});
