import type { CampaignStatusRow } from "@/lib/api/status";

export type SortColumn = "period" | "agency";
export type SortDirection = "ascending" | "descending";
export interface SortState {
  column: SortColumn;
  direction: SortDirection;
}

/** Clicking a column cycles ascending, descending and back to the server order (null). */
export function nextSort(current: SortState | null, column: SortColumn): SortState | null {
  if (current?.column !== column) return { column, direction: "ascending" };
  return current.direction === "ascending" ? { column, direction: "descending" } : null;
}

function compare(column: SortColumn, a: CampaignStatusRow, b: CampaignStatusRow): number {
  if (column === "agency") return a.agency.name.localeCompare(b.agency.name, "es");
  return (
    a.flight.year * 100 + a.flight.month - (b.flight.year * 100 + b.flight.month) ||
    a.flight.start.localeCompare(b.flight.start)
  );
}

/** A sorted copy; the sort is stable, so ties keep the server's order. */
export function sortRows(rows: CampaignStatusRow[], sort: SortState | null): CampaignStatusRow[] {
  if (sort === null) return rows;
  const sign = sort.direction === "ascending" ? 1 : -1;
  return [...rows].sort((a, b) => sign * compare(sort.column, a, b));
}
