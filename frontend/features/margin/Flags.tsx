import type { MarginTotals } from "@/lib/api/margin";
import { flightCount } from "./messages";

/** What a line, a campaign or the period includes: provisional figures, negative margins and flights without a price. */
export function TotalsFlags({ totals }: { totals: MarginTotals }) {
  if (!totals.provisional && totals.below_cost_count === 0 && totals.zero_sale_count === 0) return null;
  return (
    <span className="tags">
      {totals.provisional && <span className="tag tag-info">Incluye cifras provisionales</span>}
      {totals.below_cost_count > 0 && (
        <span className="tag tag-warning">Margen negativo: {flightCount(totals.below_cost_count)}</span>
      )}
      {totals.zero_sale_count > 0 && (
        <span className="tag tag-info">Sin venta: {flightCount(totals.zero_sale_count)}</span>
      )}
    </span>
  );
}
