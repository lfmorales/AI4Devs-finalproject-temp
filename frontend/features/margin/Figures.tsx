import { formatMoney, formatPercent } from "@/lib/format/decimal";
import type { FlightMargin, MarginTotals } from "@/lib/api/margin";

type Figured = Pick<MarginTotals, "revenue" | "media_cost" | "rebate" | "platform_cost" | "margin" | "margin_pct"> |
  Pick<FlightMargin, "revenue" | "media_cost" | "rebate" | "platform_cost" | "margin" | "margin_pct">;

/** The six figures of a level, labelled, exactly as the server computed them. */
export function Figures({ figured }: { figured: Figured }) {
  const entries: [string, string][] = [
    ["Ingreso", formatMoney(figured.revenue)],
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
          <span className="figure-label">{label}</span>{" "}
          <span className="figure-value">{value}</span>
        </span>
      ))}
    </span>
  );
}
