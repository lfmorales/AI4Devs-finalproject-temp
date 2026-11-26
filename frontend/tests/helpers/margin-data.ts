/** Builders of GET /margin responses, shaped as the backend's OpenAPI schema (MarginResponse and its parts). */
import type {
  AppliedRates,
  CampaignMargin,
  DeliveryChange,
  FlightMargin,
  LineMargin,
  MarginResponse,
  MarginTotals,
} from "@/lib/api/margin";

/** What a line counted in impressions delivers in its own unit: the impressions, with the four decimals the API sends. */
function impressionsAsDelivered(impressions: number): string {
  return `${impressions}.0000`;
}

export function totals(overrides: Partial<MarginTotals> = {}): MarginTotals {
  const delivered_impressions = overrides.delivered_impressions ?? 700000;
  return {
    revenue: "3631.01",
    contracted_revenue: "3631.01",
    delivered_impressions,
    contracted_impressions: 726202,
    delivery_metric: "impressions",
    delivered: impressionsAsDelivered(delivered_impressions),
    media_cost: "1200.00",
    rebate: "907.75",
    platform_cost: "700.00",
    margin: "823.26",
    provisional: false,
    flights_counted: 1,
    below_cost_count: 0,
    zero_sale_count: 0,
    margin_pct: "22.67",
    volume_commitment: "committed",
    gross_revenue: null,
    gross_differs_count: 0,
    data_cost_count: 0,
    delivery_changed_count: 0,
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
  const delivered_impressions = overrides.delivered_impressions ?? 700000;
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
    contracted_revenue: "3631.01",
    accrued_days: 31,
    window_days: 31,
    delivered_impressions,
    contracted_impressions: 726202,
    delivery_metric: "impressions",
    delivered: impressionsAsDelivered(delivered_impressions),
    media_cost: "1200.00",
    rebate: "907.75",
    platform_cost: "700.00",
    margin: "823.26",
    margin_pct: "22.67",
    rates: rates(),
    volume_commitment: "committed",
    gross_revenue: null,
    gross_differs_from_buyer_spend: false,
    data_cost_reported: false,
    delivery_changed: false,
    delivery_change: null,
    billable: impressionsAsDelivered(delivered_impressions),
    billing_basis: "minimum",
    ...overrides,
  };
}

/** The check of a closed committed flight whose delivery did not change; override what moved. */
export function deliveryChange(overrides: Partial<DeliveryChange> = {}): DeliveryChange {
  return {
    delivered_difference: "0.0000",
    delivered_impressions_difference: 0,
    media_cost_difference: "0.00",
    reported_revenue_difference: null,
    buyer_spend_difference: null,
    current_margin: "823.26",
    margin_difference: "0.00",
    billable_difference: "0.0000",
    billing_difference: "0.00",
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
