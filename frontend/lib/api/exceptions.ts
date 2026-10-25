import type { ApiClient } from "./client";

// Shapes of the ingestion-exception endpoints, as published by the backend's OpenAPI schema
// (IngestionExceptionResponse and ResolveExceptionRequest). There is no cost field: it is finance-only.

export type ExceptionType = "unmatched_delivery" | "missing_delivery" | "channel_mismatch";
export type ExceptionStatus = "open" | "resolved";

export interface IngestionException {
  id: number;
  exception_type: ExceptionType;
  status: ExceptionStatus;
  ingestion_batch_id: number;
  dsp_id: number | null;
  external_campaign_id: string | null;
  external_line_item_id: string | null;
  campaign_line_id: number | null;
  campaign_period_id: number | null;
  first_date: string | null;
  last_date: string | null;
  days: number;
  impressions_total: number;
  clicks_total: number;
  resolved_at: string | null;
  resolved_by: number | null;
  note: string | null;
  /** Names the catalogue holds for the external pair; null when the pair is not in it. */
  campaign_name: string | null;
  line_item_name: string | null;
}

export function listIngestionExceptions(client: ApiClient, status: ExceptionStatus): Promise<IngestionException[]> {
  return client.get<IngestionException[]>(`/ingestion-exceptions?status=${status}`);
}

/** Marks the exception resolved. Nothing is reprocessed. */
export function resolveIngestionException(
  client: ApiClient,
  exceptionId: number,
  note: string | null,
): Promise<IngestionException> {
  return client.post<IngestionException>(`/ingestion-exceptions/${exceptionId}/resolve`, { note });
}

/** The mapping a link created. Unlike DspMapping it carries no validation: Adform is not asked. */
export interface LinkedMapping {
  id: number;
  campaign_line_id: number;
  dsp_id: number;
  external_campaign_id: string;
  external_line_item_id: string;
  validated_at: string;
}

export interface LinkExceptionResponse {
  mapping: LinkedMapping;
  exception: IngestionException;
  needs_history_load: boolean;
}

/** Maps the exception's external pair to a campaign line and resolves the exception, in one transaction. */
export function linkException(client: ApiClient, exceptionId: number, campaignLineId: number): Promise<LinkExceptionResponse> {
  return client.post<LinkExceptionResponse>(`/ingestion-exceptions/${exceptionId}/link`, { campaign_line_id: campaignLineId });
}
