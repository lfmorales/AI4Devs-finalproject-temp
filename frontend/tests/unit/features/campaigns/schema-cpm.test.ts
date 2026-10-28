import { describe, expect, it } from "vitest";

import { campaignLineSchema } from "@/features/campaigns/schema";

const LINE = {
  dsp_id: 1, channel_id: 1, format_id: 1, scope: "national", market_description: "Nacional",
  contracted_impressions: 1000, sale_cpm: "5.00",
};

function issueFor(overrides: Record<string, unknown>, field: string): string | undefined {
  const result = campaignLineSchema.safeParse({ ...LINE, ...overrides });
  if (result.success) return undefined;
  return result.error.issues.find((issue) => issue.path.includes(field))?.message;
}

describe("the sale CPM of a line", () => {
  it.each(["0", "0.0", "0.00", "5", "5.00", "25.50", "4.37"])("accepts %s", (cpm) => {
    expect(campaignLineSchema.safeParse({ ...LINE, sale_cpm: cpm }).success).toBe(true);
  });

  it("accepts a line without a price: a CPM of 0 with a volume above 0", () => {
    const result = campaignLineSchema.safeParse({ ...LINE, sale_cpm: "0.00", contracted_impressions: 500000 });

    expect(result.success).toBe(true);
  });

  it.each(["-1", "-1.00", "-0.01", "-100.5"])("refuses %s with its own message in Spanish", (cpm) => {
    expect(issueFor({ sale_cpm: cpm }, "sale_cpm")).toBe("El CPM (venta) no puede ser negativo");
  });

  it.each(["abc", "", "4.375", "1,5", "1e3"])("refuses %s as not a decimal number, not as negative", (cpm) => {
    expect(issueFor({ sale_cpm: cpm }, "sale_cpm")).toBe("CPM (venta) debe ser un número decimal válido");
  });

  it("keeps requiring a volume above 0, whatever the price", () => {
    expect(issueFor({ sale_cpm: "0.00", contracted_impressions: 0 }, "contracted_impressions"))
      .toBe("Impresiones contratadas debe ser mayor que 0");
    expect(issueFor({ sale_cpm: "5.00", contracted_impressions: 0 }, "contracted_impressions"))
      .toBe("Impresiones contratadas debe ser mayor que 0");
    expect(issueFor({ sale_cpm: "0.00", contracted_impressions: -5 }, "contracted_impressions"))
      .toBe("Impresiones contratadas debe ser mayor que 0");
  });
});
