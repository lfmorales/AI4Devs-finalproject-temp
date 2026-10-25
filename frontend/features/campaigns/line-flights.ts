import { z } from "zod";

import type { FlightPreviewFlight, FlightPreviewRequest } from "@/lib/api/flights";
import { lineDateIssues, manualVolumesSchema, type MonthlyVolume } from "./schema";

const ISO_DATE = z.string().date();

/** The fields of the form a line's preview depends on. */
export interface PreviewSource {
  campaignStart: string;
  campaignEnd: string;
  inheritDates: boolean;
  lineStart: string;
  lineEnd: string;
  total: string;
}

/** What the user sees for a line after «Calcular reparto». */
export interface LinePreview {
  /** The request that produced it. If the form no longer produces this request, the preview is stale. */
  request: FlightPreviewRequest;
  flights: FlightPreviewFlight[];
  /** The editable volumes, as typed, one per flight. */
  volumes: string[];
  manual: boolean;
}

/**
 * The request the form would send for a line, or null while the campaign's dates, the line's dates
 * (own or inherited) or the total volume are not valid.
 */
export function previewRequestFor(source: PreviewSource): FlightPreviewRequest | null {
  const { campaignStart, campaignEnd } = source;
  if (!ISO_DATE.safeParse(campaignStart).success || !ISO_DATE.safeParse(campaignEnd).success) return null;
  if (campaignStart > campaignEnd) return null;

  const total = Number(source.total);
  if (source.total.trim() === "" || !Number.isInteger(total) || total <= 0) return null;

  const request: FlightPreviewRequest = {
    campaign_start_date: campaignStart,
    campaign_end_date: campaignEnd,
    contracted_impressions: total,
  };
  if (source.inheritDates) return request;

  const own = { start_date: source.lineStart || undefined, end_date: source.lineEnd || undefined };
  const campaign = { start_date: campaignStart, end_date: campaignEnd };
  if (!ISO_DATE.safeParse(source.lineStart).success || !ISO_DATE.safeParse(source.lineEnd).success) return null;
  if (lineDateIssues(campaign, own).length > 0) return null;
  return { ...request, start_date: source.lineStart, end_date: source.lineEnd };
}

/** A preview is current only while the form still produces exactly the request that made it. */
export function isStale(preview: LinePreview, current: FlightPreviewRequest | null): boolean {
  return current === null || JSON.stringify(current) !== JSON.stringify(preview.request);
}

export function newPreview(request: FlightPreviewRequest, flights: FlightPreviewFlight[]): LinePreview {
  return { request, flights, volumes: flights.map((f) => String(f.contracted_impressions)), manual: false };
}

export function editVolume(preview: LinePreview, index: number, value: string): LinePreview {
  return { ...preview, volumes: preview.volumes.map((v, i) => (i === index ? value : v)), manual: true };
}

export function resetToProportional(preview: LinePreview): LinePreview {
  return newPreview(preview.request, preview.flights);
}

export function volumesSum(preview: LinePreview): number {
  return preview.volumes.reduce((sum, value) => sum + (Number(value) || 0), 0);
}

/** The monthly volumes of a manual split, in the shape the registration expects. */
export function monthlyVolumesOf(preview: LinePreview): MonthlyVolume[] {
  return preview.flights.map((flight, index) => ({
    year: flight.period_year,
    month: flight.period_month,
    volume: Number(preview.volumes[index]),
  }));
}

/** The first problem of a manual split, in Spanish, or null when it is acceptable. */
export function manualSplitProblem(preview: LinePreview): string | null {
  const volumes = monthlyVolumesOf(preview);
  if (volumes.some((v) => !Number.isInteger(v.volume))) return "Cada volumen mensual debe ser un número entero.";
  const months = preview.flights.map((f) => ({ year: f.period_year, month: f.period_month }));
  const result = manualVolumesSchema(months, preview.request.contracted_impressions).safeParse(volumes);
  return result.success ? null : (result.error.issues[0]?.message ?? null);
}

export function monthLabel(flight: FlightPreviewFlight): string {
  return `${String(flight.period_month).padStart(2, "0")}/${flight.period_year}`;
}
