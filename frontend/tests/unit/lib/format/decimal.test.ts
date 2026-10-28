import { describe, expect, it } from "vitest";

import { formatDecimal, formatMoney, formatPercent, NO_VALUE } from "@/lib/format/decimal";

describe("formatDecimal", () => {
  it("groups thousands with a dot and uses a comma for the decimals", () => {
    expect(formatDecimal("3631.01")).toBe("3.631,01");
    expect(formatDecimal("1200.00")).toBe("1.200,00");
    expect(formatDecimal("999.99")).toBe("999,99");
    expect(formatDecimal("1000000.5")).toBe("1.000.000,5");
  });

  it("shows a value beyond what a floating-point number holds exactly, whole", () => {
    expect(formatDecimal("12345678901234.56")).toBe("12.345.678.901.234,56");
    expect(formatDecimal("123456789012345678.99")).toBe("123.456.789.012.345.678,99");
    expect(formatDecimal("9007199254740993.01")).toBe("9.007.199.254.740.993,01");
  });

  it("keeps the digits it was given: it neither rounds nor trims", () => {
    expect(formatDecimal("0.10")).toBe("0,10");
    expect(formatDecimal("0.005")).toBe("0,005");
    expect(formatDecimal("12.345678901234567890")).toBe("12,345678901234567890");
    expect(formatDecimal("7")).toBe("7");
  });

  it("keeps the sign", () => {
    expect(formatDecimal("-5.00")).toBe("-5,00");
    expect(formatDecimal("-1234567.89")).toBe("-1.234.567,89");
    expect(formatDecimal("-0.01")).toBe("-0,01");
  });

  it("shows zero as zero", () => {
    expect(formatDecimal("0.00")).toBe("0,00");
    expect(formatDecimal("0")).toBe("0");
  });

  it("returns what is not a decimal string unchanged, so a surprise is visible", () => {
    expect(formatDecimal("abc")).toBe("abc");
    expect(formatDecimal("")).toBe("");
    expect(formatDecimal("1e5")).toBe("1e5");
  });
});

describe("formatMoney and formatPercent", () => {
  it("adds the euro sign after a no-break space", () => {
    expect(formatMoney("3631.01")).toBe("3.631,01 €");
    expect(formatMoney("-520.00")).toBe("-520,00 €");
  });

  it("adds the percent sign after a no-break space, and shows a dash for no value", () => {
    expect(formatPercent("22.67")).toBe("22,67 %");
    expect(formatPercent("-5.00")).toBe("-5,00 %");
    expect(formatPercent(null)).toBe(NO_VALUE);
    expect(NO_VALUE).toBe("—");
  });
});
