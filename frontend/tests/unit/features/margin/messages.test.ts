import { describe, expect, it } from "vitest";

import {
  GENERIC_CLOSING_ERROR, closingErrorMessage, closingsMessage, deliveryLegend, monthName, monthOfYear,
} from "@/features/margin/messages";

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

describe("the delivery legend", () => {
  it("reads «Entregado 280.000,5 de 300.000 OTS» for a DOOH flight", () => {
    expect(deliveryLegend("280000.5000", 300000, "ots")).toBe("Entregado 280.000,5 de 300.000 OTS");
  });

  it("reads «… impresiones» for a flight counted in impressions", () => {
    expect(deliveryLegend("198500.0000", 200000, "impressions")).toBe("Entregado 198.500 de 200.000 impresiones");
  });
});


describe("the closing of a month whose delivery is not loaded up to its last day", () => {
  const november = { year: 2026, month: 11 };

  it("names the month and the DSP of month_delivery_not_loaded in Spanish and says what to wait for", () => {
    const message = closingErrorMessage(
      "month_delivery_not_loaded",
      "The delivery of 2026-11 from Equativ is not loaded up to its last day. Load it, then close the month.",
      november,
    );

    expect(message).toBe(
      "No se puede cerrar noviembre de 2026: Equativ aún no ha cargado la entrega de su último día. "
      + "Espera a la ingesta de ese día y vuelve a cerrar el mes.",
    );
    expect(message).not.toContain("not loaded");
  });

  it("still names the month being closed when the backend's message cannot be read", () => {
    expect(closingErrorMessage("month_delivery_not_loaded", undefined, november)).toBe(
      "No se puede cerrar noviembre de 2026: falta cargar la entrega de su último día. "
      + "Espera a la ingesta de ese día y vuelve a cerrar el mes.",
    );
  });
});

describe("the closings a month holds", () => {
  const closing = { year: 2026, month: 8 };

  it("says nothing of a month closed once, or not closed", () => {
    expect(closingsMessage(1, closing)).toBeNull();
    expect(closingsMessage(0, closing)).toBeNull();
  });

  it("warns when a month holds more than one closing", () => {
    expect(closingsMessage(2, closing)).toBe(
      "agosto de 2026 tiene 2 cierres: se cerró un flight dado de alta después de un cierre anterior. Las cifras de "
      + "los cierres anteriores no cambian.",
    );
  });
});
