import type { MarginFilters } from "@/lib/api/margin";

/** What the filter controls hold, as text. It lives in the page's state: never in the address or in storage. */
export interface FilterFields {
  yearText: string;
  month: string;
  campaign: string;
}

export const NO_FILTERS: FilterFields = { yearText: "", month: "", campaign: "" };

const YEAR = /^\d{4}$/;
const FIRST_YEAR = 2000;
const LAST_YEAR = 2100;

/** A year is applied only once it is a complete year the server accepts; a half-typed one asks for nothing. */
export function validYear(yearText: string): number | undefined {
  if (!YEAR.test(yearText)) return undefined;
  const year = Number(yearText);
  return year >= FIRST_YEAR && year <= LAST_YEAR ? year : undefined;
}

export function toFilters(fields: FilterFields): MarginFilters {
  return {
    year: validYear(fields.yearText),
    month: fields.month === "" ? undefined : Number(fields.month),
    campaignId: fields.campaign === "" ? undefined : Number(fields.campaign),
  };
}

export function hasActiveFilter(fields: FilterFields): boolean {
  return fields.yearText !== "" || fields.month !== "" || fields.campaign !== "";
}
