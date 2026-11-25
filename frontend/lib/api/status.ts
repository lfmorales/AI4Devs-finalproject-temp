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
  /** The flight's contracted volume, in the unit of `delivery_metric`. */
  contracted_impressions: number;
  delivery_metric: DeliveryMetric;
  /** The delivery up to D-1 in that unit: a decimal string with four decimals, shown as received. */
  delivered: string;
  /** The real impressions over the same days, whatever the metric. */
  delivered_impressions: number;
  /** Delivered over contracted, as a fraction; null when it cannot be computed. */
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
