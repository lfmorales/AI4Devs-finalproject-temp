import { useId } from "react";

import { formatInteger } from "@/lib/format/integer";
import { formatMoney, formatPercent } from "@/lib/format/decimal";
import type { MarginTotals } from "@/lib/api/margin";
import { BILLING_HELP, GROSS_LABEL, billingLabel, deliveryLegend, saleLabel } from "./messages";

/**
 * The figures of a level, labelled, exactly as the server computed them, and what it delivered of what it sold. The
 * sale of a target level is «Venta objetivo», and the gross of its target flights follows its revenue when it has one.
 * Its revenue is its billing, «Facturable a la fecha» when it includes a running flight.
 */
export function Figures({ figured, includesRunning }: { figured: MarginTotals; includesRunning: boolean }) {
  const helpId = useId();
  const billing = billingLabel(includesRunning);
  const gross: [string, string][] = figured.gross_revenue === null ? [] : [[GROSS_LABEL, formatMoney(figured.gross_revenue)]];
  const entries: [string, string][] = [
    [saleLabel(figured.volume_commitment), formatMoney(figured.contracted_revenue)],
    [billing, formatMoney(figured.revenue)],
    ...gross,
    ["Coste de medios", formatMoney(figured.media_cost)],
    ["Rebate", formatMoney(figured.rebate)],
    ["Coste de plataforma", formatMoney(figured.platform_cost)],
    ["Margen", formatMoney(figured.margin)],
    ["% de margen", formatPercent(figured.margin_pct)],
  ];
  return (
    <span className="margin-figures">
      {entries.map(([label, value]) => (
        <span key={label} className="margin-figure">
          <span className="figure-label" aria-describedby={label === billing ? helpId : undefined}>{label}</span>{" "}
          <span className="figure-value">{value}</span>
        </span>
      ))}
      <span id={helpId} hidden>{BILLING_HELP}</span>
      {figured.delivery_metric !== null && figured.delivered !== null && figured.contracted_impressions !== null && (
        <span className="margin-delivery">
          {deliveryLegend(figured.delivered, figured.contracted_impressions, figured.delivery_metric)}
        </span>
      )}
    </span>
  );
}
