import type { ExceptionType, IngestionException } from "@/lib/api/exceptions";
import { formatDsp, formatExternalPair } from "./labels";

/** The types the «Tipo» selector offers; an empty string means all of them. */
export type TypeFilter = "" | Extract<ExceptionType, "unmatched_delivery" | "missing_delivery">;

export interface ExceptionFilter {
  text: string;
  type: TypeFilter;
}

export const NO_FILTER: ExceptionFilter = { text: "", type: "" };

/** Lowercase without accents: decomposes (NFD) and drops the combining marks. */
export function normalizeText(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

export function hasActiveFilter(filter: ExceptionFilter): boolean {
  return filter.text.trim() !== "" || filter.type !== "";
}

/** Everything the search looks in: the catalogue names, the DSP, the external pair and the absence text. */
function searchableText(row: IngestionException): string {
  return [
    row.campaign_name,
    row.line_item_name,
    formatDsp(row.dsp_id),
    row.external_campaign_id,
    row.external_line_item_id,
    formatExternalPair(row),
  ]
    .filter((part): part is string => part !== null)
    .join(" ");
}

/** Keeps the rows of the chosen type that contain every term of the text, in their order. */
export function filterExceptions(rows: IngestionException[], filter: ExceptionFilter): IngestionException[] {
  const terms = normalizeText(filter.text).split(/\s+/).filter((term) => term !== "");
  return rows.filter((row) => {
    if (filter.type !== "" && row.exception_type !== filter.type) return false;
    if (terms.length === 0) return true;
    const haystack = normalizeText(searchableText(row));
    return terms.every((term) => haystack.includes(term));
  });
}
