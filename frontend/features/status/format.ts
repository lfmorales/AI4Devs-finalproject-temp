import { formatInteger } from "@/lib/format/integer";

const percent = new Intl.NumberFormat("es-ES", { style: "percent", maximumFractionDigits: 1 });

export const NOT_AVAILABLE = "—";

export function formatImpressions(value: number): string {
  return formatInteger(value);
}

/** The API sends fractions (0.387); the browser only formats them and never recomputes them. */
export function formatFraction(value: number | null): string {
  return value === null ? NOT_AVAILABLE : percent.format(value);
}

export function formatPeriod(year: number, month: number): string {
  return `${String(month).padStart(2, "0")}/${year}`;
}
