import type { DeliveryMetric } from "@/lib/format/delivery-metric";

import type { ApiClient } from "./client";
import { buildQuery } from "./query";
import type { VolumeCommitment } from "./volume-commitment";

// Shapes of GET /margin and POST /margin/closings, as published by the backend's OpenAPI schema
// (MarginResponse, CampaignMarginResponse, LineMarginResponse, FlightMarginResponse, TotalsResponse,
// AppliedRatesResponse, DeliveryChangeResponse, ClosingRequest and ClosingResponse). Every amount, rate and percentage is a decimal
// string: it is displayed as received and never converted to a number.

export type DecimalString = string;

export type FlightState = "closed" | "pending_close" | "running";

/**
 * How a flight's billing was reached: `minimum` (the lesser of delivered and its cap), `delivered`, `contracted` or
 * `custom` (an adjustment in force), `reported` (a target flight).
 */
export type BillingBasis = "minimum" | "delivered" | "contracted" | "custom" | "reported";

export interface MarginTotals {
  revenue: DecimalString;
  /** The sale of the whole flights, summed by the server. */
  contracted_revenue: DecimalString;
  /** The real impressions, always summed. */
  delivered_impressions: number;
  /** In the unit of `delivery_metric`; null when the totals mix metrics. */
  contracted_impressions: number | null;
  /** Null when the totals mix metrics or hold no flight. */
  delivery_metric: DeliveryMetric | null;
  /** In that unit, four decimals; null when the totals mix metrics. */
  delivered: string | null;
  media_cost: DecimalString;
  rebate: DecimalString;
  platform_cost: DecimalString;
  margin: DecimalString;
  provisional: boolean;
  flights_counted: number;
  below_cost_count: number;
  zero_sale_count: number;
  /** Computed by the server, in points of revenue; null when there is no revenue. */
  margin_pct: DecimalString | null;
  /** The one commitment of the flights below; null when they mix both. */
  volume_commitment: VolumeCommitment | null;
  /** The sum of the gross of the target flights below, by the server; null when there is none. */
  gross_revenue: DecimalString | null;
  /** How many flights below carry each warning. */
  gross_differs_count: number;
  data_cost_count: number;
  /** How many closed flights below had their delivery changed after closing («Cambió tras el cierre»). */
  delivery_changed_count: number;
}

/**
 * A closed flight compared with the delivery stored now, by the server: each difference is the current value less
 * the frozen one. Informative: the current margin uses the closing's rebate and rates, and no total adds it.
 */
export interface DeliveryChange {
  /** In the unit of the flight's `delivery_metric`, four decimals. */
  delivered_difference: string;
  delivered_impressions_difference: number;
  media_cost_difference: DecimalString;
  /** A target flight's only; null for a committed one. */
  reported_revenue_difference: DecimalString | null;
  buyer_spend_difference: DecimalString | null;
  current_margin: DecimalString;
  margin_difference: DecimalString;
  /** The billable volume in the flight's unit, four decimals; null for a target flight, a custom billing or an old closing. */
  billable_difference: string | null;
  /** The billing, two decimals; null for a target flight or an old closing. */
  billing_difference: DecimalString | null;
}

export interface AppliedRates {
  platform_rate: DecimalString;
  effective_rebate_rate: DecimalString;
  rebate_step: number;
  agency_exception: boolean;
  zero_reason: string | null;
  source_year: number | null;
}

export interface FlightMargin {
  flight_id: number;
  period_year: number;
  period_month: number;
  flight_start: string;
  flight_end: string;
  state: FlightState;
  provisional: boolean;
  /** A negative final margin ("Margen negativo"). */
  below_cost: boolean;
  /** A line without a price ("Sin venta"). */
  zero_sale: boolean;
  /** The billing: what the flight bills, to date while it runs; for a target flight, what its DSP reported. */
  revenue: DecimalString;
  /** The sale of the whole flight. */
  contracted_revenue: DecimalString;
  /** Contract days counted up to the day of the figures, and days of the whole flight. */
  accrued_days: number;
  window_days: number;
  delivered_impressions: number;
  /** The flight's contracted volume, in the unit of `delivery_metric`. */
  contracted_impressions: number;
  delivery_metric: DeliveryMetric;
  /** The line's delivery inside the window in that unit, four decimals, shown as received. */
  delivered: string;
  media_cost: DecimalString;
  rebate: DecimalString;
  platform_cost: DecimalString;
  margin: DecimalString;
  margin_pct: DecimalString | null;
  rates: AppliedRates;
  /** A target flight earns what its DSP reports, and its `contracted_revenue` is the sale of its target. */
  volume_commitment: VolumeCommitment;
  /** A target flight's served impressions at the line's CPM, the base of its rebate; null for a committed flight. */
  gross_revenue: DecimalString | null;
  /** The gross differs from the buyer's spend by more than 1 %, or there is no spend («Bruto distinto del gasto»). */
  gross_differs_from_buyer_spend: boolean;
  /** The DSP reports a third-party or audience data cost («Coste de datos»); never subtracted. */
  data_cost_reported: boolean;
  /** A closed flight whose delivery stored now moved beyond the tolerances («Cambió tras el cierre»). */
  delivery_changed: boolean;
  /** Null until the flight is closed. */
  delivery_change: DeliveryChange | null;
  /** The volume the billing was computed on, in the unit of `delivery_metric`, four decimals; null for a target
   * flight, a custom billing and a flight closed before the billing was frozen. */
  billable: string | null;
  /** Null for a flight closed before the billing was frozen. */
  billing_basis: BillingBasis | null;
}

export interface LineMargin {
  campaign_line_id: number;
  line_number: number;
  channel: string;
  scope: string;
  zero_sale: boolean;
  flights: FlightMargin[];
  totals: MarginTotals;
}

export interface CampaignMargin {
  campaign_id: number;
  name: string;
  status: string;
  zero_sale: boolean;
  lines: LineMargin[];
  totals: MarginTotals;
}

export interface MarginResponse {
  as_of: string;
  campaigns: CampaignMargin[];
  totals: MarginTotals;
}

export interface MarginFilters {
  year?: number;
  month?: number;
  campaignId?: number;
}

export interface ClosingRequest {
  year: number;
  month: number;
}

export interface ClosingResponse {
  year: number;
  month: number;
  closed: number;
  already_closed: number;
  /** The closing headers the month holds after the request: more than one when a late flight was closed later. */
  closings: number;
}

export function marginPath(filters: MarginFilters): string {
  return `/margin${buildQuery({ year: filters.year, month: filters.month, campaign_id: filters.campaignId })}`;
}

export function getMargin(client: ApiClient, filters: MarginFilters): Promise<MarginResponse> {
  return client.get<MarginResponse>(marginPath(filters));
}

/** Freezes the flights that ended in a month: their rates and their figures. Idempotent on the server. */
export function closeMonth(client: ApiClient, request: ClosingRequest): Promise<ClosingResponse> {
  return client.post<ClosingResponse>("/margin/closings", request);
}
