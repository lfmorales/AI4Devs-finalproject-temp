import type { ApiClient } from "./client";
import { buildQuery } from "./query";

// Shapes of the Adform catalogue endpoints, as published by the backend's OpenAPI schema
// (DspCatalogPageResponse, DspCatalogItemResponse, UnmappedLineResponse, DspMappingCreateRequest,
// DspMappingResponse and UnlinkLineResponse). There is no cost field.

export interface DspCatalogItem {
  dsp_id: number;
  external_campaign_id: string;
  external_line_item_id: string;
  campaign_name: string;
  line_item_name: string;
  line_start_date: string | null;
  line_end_date: string | null;
  first_seen_date: string;
  /** The last date with a row in Adform: not real activity. */
  last_seen_date: string;
  last_impressions_date: string | null;
  /** The campaign line the pair is mapped to; null when it is not mapped. */
  mapped_line_id: number | null;
}

export interface DspCatalogPage {
  items: DspCatalogItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface DspCatalogFilters {
  dspId?: number;
  q?: string;
  mapped?: boolean;
  activeSince?: string;
  limit?: number;
  offset?: number;
}

export function listDspCatalog(client: ApiClient, filters: DspCatalogFilters): Promise<DspCatalogPage> {
  const query = buildQuery({
    dsp_id: filters.dspId,
    q: filters.q,
    mapped: filters.mapped,
    active_since: filters.activeSince,
    limit: filters.limit,
    offset: filters.offset,
  });
  return client.get<DspCatalogPage>(`/dsp-catalog${query}`);
}

export interface UnmappedLine {
  id: number;
  campaign_name: string;
  line_number: number;
  start_date: string;
  end_date: string;
  dsp_id: number;
  dsp_name: string;
}

/** The campaign lines that have no DSP mapping at all. */
export function listUnmappedLines(client: ApiClient): Promise<UnmappedLine[]> {
  return client.get<UnmappedLine[]>("/campaign-lines/unmapped");
}

export type IdentifierCheck = "found" | "unknown" | "unreachable";

export interface DspMappingRequest {
  external_campaign_id: string;
  external_line_item_id: string;
}

export interface DspMapping {
  id: number;
  campaign_line_id: number;
  dsp_id: number;
  external_campaign_id: string;
  external_line_item_id: string;
  validated_at: string | null;
  validation: IdentifierCheck;
  /** Null when the pair is not in the catalogue or never delivered. */
  last_impressions_date: string | null;
  needs_history_load: boolean;
}

export function createDspMapping(client: ApiClient, campaignLineId: number, pair: DspMappingRequest): Promise<DspMapping> {
  return client.post<DspMapping>(`/campaign-lines/${campaignLineId}/dsp-mappings`, pair);
}

export interface UnlinkLineResponse {
  campaign_line_id: number;
  removed_delivery_days: number;
}

/** Deletes the line's only mapping together with the delivery days ingested through it. */
export function unlinkLine(client: ApiClient, campaignLineId: number): Promise<UnlinkLineResponse> {
  return client.delete<UnlinkLineResponse>(`/campaign-lines/${campaignLineId}/dsp-mappings`);
}
