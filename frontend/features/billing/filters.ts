import { validYear } from "@/features/margin/filters";
import type { BillingMonth } from "@/lib/api/billing";

/** What the month controls hold, as text. It lives in the page's state: never in the address or in storage. */
export interface MonthFields {
  yearText: string;
  month: string;
}

/** The month to read, once a complete year and a month are chosen; null until then. */
export function toMonth(fields: MonthFields): BillingMonth | null {
  const year = validYear(fields.yearText);
  if (year === undefined || fields.month === "") return null;
  return { year, month: Number(fields.month) };
}

const MADRID_YEAR_MONTH = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Madrid", year: "numeric", month: "numeric" });

/** The month before `today`'s in Madrid, the month Finance reviews most often: December of the year before in January. */
export function previousMonthFields(today: Date): MonthFields {
  const parts = MADRID_YEAR_MONTH.formatToParts(today);
  const year = Number(parts.find((part) => part.type === "year")?.value);
  const month = Number(parts.find((part) => part.type === "month")?.value);
  return month === 1 ? { yearText: String(year - 1), month: "12" } : { yearText: String(year), month: String(month - 1) };
}
