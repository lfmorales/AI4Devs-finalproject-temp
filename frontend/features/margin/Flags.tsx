import type { MarginTotals } from "@/lib/api/margin";
import { DATA_COST_LABEL, GROSS_DIFFERS_LABEL, flightCount } from "./messages";

/**
 * What a line, a campaign or the period includes: provisional figures, negative margins, flights without a price,
 * and target flights whose gross differs from the buyer's spend or that report a data cost.
 */
export function TotalsFlags({ totals }: { totals: MarginTotals }) {
  const quiet = !totals.provisional && totals.below_cost_count === 0 && totals.zero_sale_count === 0
    && totals.gross_differs_count === 0 && totals.data_cost_count === 0;
  if (quiet) return null;
  return (
    <span className="tags">
      {totals.provisional && <span className="tag tag-info">Incluye cifras provisionales</span>}
      {totals.below_cost_count > 0 && (
        <span className="tag tag-warning">Margen negativo: {flightCount(totals.below_cost_count)}</span>
      )}
      {totals.zero_sale_count > 0 && (
        <span className="tag tag-info">Sin venta: {flightCount(totals.zero_sale_count)}</span>
      )}
      {totals.gross_differs_count > 0 && (
        <span className="tag tag-warning">{GROSS_DIFFERS_LABEL}: {flightCount(totals.gross_differs_count)}</span>
      )}
      {totals.data_cost_count > 0 && (
        <span className="tag tag-info">{DATA_COST_LABEL}: {flightCount(totals.data_cost_count)}</span>
      )}
    </span>
  );
}
