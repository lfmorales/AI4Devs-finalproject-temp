/** Builders of GET /margin responses, shaped as the backend's OpenAPI schema (MarginResponse and its parts). */
import type {
  AppliedRates,
  CampaignMargin,
  FlightMargin,
  LineMargin,
  MarginResponse,
  MarginTotals,
} from "@/lib/api/margin";

export function totals(overrides: Partial<MarginTotals> = {}): MarginTotals {
  return {
    revenue: "3631.01",
    media_cost: "1200.00",
    rebate: "907.75",
    platform_cost: "700.00",
    margin: "823.26",
    provisional: false,
    flights_counted: 1,
    below_cost_count: 0,
    zero_sale_count: 0,
    margin_pct: "22.67",
    ...overrides,
  };
}

export function rates(overrides: Partial<AppliedRates> = {}): AppliedRates {
  return {
    platform_rate: "1.000000",
    effective_rebate_rate: "0.25",
    rebate_step: 6,
    agency_exception: false,
    zero_reason: null,
    source_year: 2026,
    ...overrides,
  };
}

export function flight(overrides: Partial<FlightMargin> = {}): FlightMargin {
  return {
    flight_id: 1,
    period_year: 2026,
    period_month: 8,
    flight_start: "2026-08-01",
    flight_end: "2026-08-31",
    state: "closed",
    provisional: false,
    below_cost: false,
    zero_sale: false,
    revenue: "3631.01",
    media_cost: "1200.00",
    rebate: "907.75",
    platform_cost: "700.00",
    margin: "823.26",
    margin_pct: "22.67",
    rates: rates(),
    ...overrides,
  };
}

export function line(overrides: Partial<LineMargin> = {}): LineMargin {
  return {
    campaign_line_id: 10,
    line_number: 1,
    channel: "Directo",
    scope: "national",
    zero_sale: false,
    flights: [flight()],
    totals: totals(),
    ...overrides,
  };
}

export function campaign(overrides: Partial<CampaignMargin> = {}): CampaignMargin {
  return {
    campaign_id: 1,
    name: "Campaña A",
    status: "active",
    zero_sale: false,
    lines: [line()],
    totals: totals(),
    ...overrides,
  };
}

export function margin(overrides: Partial<MarginResponse> = {}): MarginResponse {
  return {
    as_of: "2026-08-31",
    campaigns: [campaign()],
    totals: totals(),
    ...overrides,
  };
}
