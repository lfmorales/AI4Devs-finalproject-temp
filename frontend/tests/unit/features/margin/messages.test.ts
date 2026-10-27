import { describe, expect, it } from "vitest";

import { GENERIC_CLOSING_ERROR, closingErrorMessage, monthName, monthOfYear } from "@/features/margin/messages";

describe("the months in Spanish", () => {
  it("names the twelve months", () => {
    expect([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(monthName)).toEqual([
      "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]);
  });

  it("writes a month of a year", () => {
    expect(monthOfYear(2026, 8)).toBe("agosto de 2026");
  });
});

describe("the messages of the closing", () => {
  const closing = { year: 2026, month: 8 };

  it("names the blocking month of previous_month_open", () => {
    expect(closingErrorMessage("previous_month_open", "An earlier month is still open: 2026-06. Close it first.", closing))
      .toBe("Hay un mes anterior sin cerrar: junio de 2026. Ciérralo antes de cerrar agosto de 2026.");
  });

  it("gives every code of the backend its own Spanish message", () => {
    const codes = [
      "previous_month_open", "validation_error", "campaign_not_found", "platform_rate_not_configured",
      "identity_provider_unavailable", "internal_error", "bracket_table_empty", "bracket_table_must_start_at_zero",
      "bracket_table_not_contiguous", "last_bracket_must_be_open", "overlapping_schedules", "schedule_overlaps_existing",
      "reference_not_found", "revenue_must_not_be_negative", "duplicate_flight_id", "validity_ends_before_it_starts",
      "not_found", "method_not_allowed", "http_error",
    ];

    const messages = codes.map((code) => closingErrorMessage(code, "backend text", closing));

    expect(new Set(messages).size).toBe(codes.length);
    expect(messages.every((message) => message !== GENERIC_CLOSING_ERROR && !message.includes("backend text"))).toBe(true);
  });

  it("falls back to a generic message for an unknown or missing code", () => {
    expect(closingErrorMessage("something_new", "x", closing)).toBe(GENERIC_CLOSING_ERROR);
    expect(closingErrorMessage(undefined, "x", closing)).toBe(GENERIC_CLOSING_ERROR);
  });
});
