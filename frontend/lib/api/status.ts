import type { DeliveryMetric } from "@/lib/format/delivery-metric";

import type { ApiClient } from "./client";
import type { VolumeCommitment } from "./volume-commitment";

// Shapes of GET /campaign-status, as published by the backend's OpenAPI schema
// (CampaignStatusResponse, NamedReference, FlightWindowResponse and PacingResponse).
// The response deliberately has no cost or margin field.

export interface NamedReference {
  id: number;
  name: string;
}

export interface FlightWindow {
  /** The flight, the row of the line in this month: the one that receives a carry-over. */
  id: number;
  campaign_period_id: number;
  year: number;
  month: number;
  start: string;
  end: string;
}

export type PacingStatus = "on_pace" | "under_delivering" | "over_delivering";

export interface Pacing {
  /** The volume a linear delivery would have reached, in the unit of the row's `delivery_metric`. */
  expected_impressions: number;
  /** A fraction (-0.2 is 20% under the expected delivery); null when nothing was expected yet. */
  deviation: number | null;
  days_remaining: number;
  status: PacingStatus;
}

/** One running flight of an active campaign. */
export interface CampaignStatusRow {
  campaign: NamedReference;
  agency: NamedReference;
  line_number: number;
  flight: FlightWindow;
  /** The flight's contracted volume, in the unit of `delivery_metric`. It never includes the carry-over. */
  contracted_impressions: number;
  /** The volume carried to this flight from the previous flight of its line, in that unit; 0 when none. */
  carryover: number;
  /** The contracted volume plus the carry-over: what the pacing and the ratio are measured against. */
  delivery_target: number;
  delivery_metric: DeliveryMetric;
  /** The delivery up to D-1 in that unit: a decimal string with four decimals, shown as received. */
  delivered: string;
  /** The real impressions over the same days, whatever the metric. */
  delivered_impressions: number;
  /** Delivered over the delivery target, as a fraction; null when it cannot be computed. */
  delivery_ratio: number | null;
  pacing: Pacing;
  /** Raised below a target, but never above it: a target line may deliver more than its target. */
  pacing_flag: boolean;
  missing_data_flag: boolean;
  /** The line's commitment: its volume is labelled «Objetivo» when it is a target. Not a cost figure. */
  volume_commitment: VolumeCommitment;
}

/** The daily status, already ordered by the server (rows with a flag first). */
export function getCampaignStatus(client: ApiClient): Promise<CampaignStatusRow[]> {
  return client.get<CampaignStatusRow[]>("/campaign-status");
}

export interface CarryoverRequest {
  /** A whole volume, zero or more, in the unit of the row's `delivery_metric`; zero removes the carry-over. */
  volume: number;
  reason: string;
}

/** What PUT /flights/{id}/carryover answers: volumes and a reason, never an amount or the billable flag. */
export interface CarryoverResponse {
  flight_id: number;
  delivery_metric: DeliveryMetric;
  contracted_impressions: number;
  carryover: number;
  delivery_target: number;
  reason: string;
  set_by: number;
  /** The author's name, or the email when the name is blank. */
  set_by_name: string;
  set_at: string;
}

/** Carries undelivered volume of the previous flight of the line to this one. Operations and trading only. */
export function putCarryover(client: ApiClient, flightId: number, request: CarryoverRequest): Promise<CarryoverResponse> {
  return client.put<CarryoverResponse>(`/flights/${flightId}/carryover`, request);
}
