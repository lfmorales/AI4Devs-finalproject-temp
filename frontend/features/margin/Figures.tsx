import { useId } from "react";

import { formatInteger } from "@/lib/format/integer";
import { formatMoney, formatPercent } from "@/lib/format/decimal";
import type { MarginTotals } from "@/lib/api/margin";
import { ACCRUED_HELP, ACCRUED_LABEL, deliveryLegend } from "./messages";

/** The figures of a level, labelled, exactly as the server computed them, and what it delivered of what it sold. */
export function Figures({ figured }: { figured: MarginTotals }) {
  const helpId = useId();
  const entries: [string, string][] = [
    ["Venta contratada", formatMoney(figured.contracted_revenue)],
    [ACCRUED_LABEL, formatMoney(figured.revenue)],
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
          <span className="figure-label" aria-describedby={label === ACCRUED_LABEL ? helpId : undefined}>{label}</span>{" "}
          <span className="figure-value">{value}</span>
        </span>
      ))}
      <span id={helpId} hidden>{ACCRUED_HELP}</span>
      <span className="margin-delivery">
        {deliveryLegend(figured.delivered_impressions, figured.contracted_impressions)}
      </span>
    </span>
  );
}
