import { validYear } from "@/features/margin/filters";
import type { BillingMonth } from "@/lib/api/billing";

/** What the month controls hold, as text. It lives in the page's state: never in the address or in storage. */
export interface MonthFields {
  yearText: string;
  month: string;
}

export const NO_MONTH: MonthFields = { yearText: "", month: "" };

/** The month to read, once a complete year and a month are chosen; null until then. */
export function toMonth(fields: MonthFields): BillingMonth | null {
  const year = validYear(fields.yearText);
  if (year === undefined || fields.month === "") return null;
  return { year, month: Number(fields.month) };
}
