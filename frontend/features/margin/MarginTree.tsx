import { useId } from "react";

import { AdformName } from "@/features/linking/AdformName";
import type {
  CampaignMargin,
  DeliveryChange,
  FlightMargin,
  FlightState,
  LineMargin,
  MarginResponse,
} from "@/lib/api/margin";
import { formatMoney, formatPercent, formatQuantity } from "@/lib/format/decimal";
import { metricLabel, type DeliveryMetric } from "@/lib/format/delivery-metric";
import { formatInteger } from "@/lib/format/integer";
import { Figures } from "./Figures";
import { TotalsFlags } from "./Flags";
import {
  ADJUSTED_LABEL,
  BILLING_HELP,
  DATA_COST_HELP,
  DATA_COST_LABEL,
  DELIVERY_CHANGED_HELP,
  DELIVERY_CHANGED_LABEL,
  DELIVERY_CHANGE_NOTE,
  GROSS_DIFFERS_HELP,
  GROSS_DIFFERS_LABEL,
  GROSS_LABEL,
  adjustedHelp,
  billingLabel,
  daysLegend,
  deliveryLegend,
  isAdjusted,
  saleLabel,
} from "./messages";

const STATE_LABEL: Record<FlightState, string> = {
  closed: "Cerrado",
  pending_close: "Pendiente de cierre",
  running: "En curso (provisional)",
};

const STATE_CLASS: Record<FlightState, string> = {
  closed: "tag",
  pending_close: "tag tag-warning",
  running: "tag tag-info",
};

const SCOPE_LABEL: Record<string, string> = { national: "Nacional", international: "Internacional" };

/** Whether a level holds a running flight, read from the states the server reported: its billing is then to date. */
function lineRuns(line: LineMargin): boolean {
  return line.flights.some((flight) => flight.state === "running");
}

function campaignRuns(campaign: CampaignMargin): boolean {
  return campaign.lines.some(lineRuns);
}

function twoDigits(month: number): string {
  return month < 10 ? `0${month}` : `${month}`;
}

/** A warning of a flight, with what to check as its accessible description. */
function Warning({ label, help, className }: { label: string; help: string; className: string }) {
  const helpId = useId();
  return (
    <>
      <span className={className} aria-describedby={helpId} title={help}>{label}</span>
      <span id={helpId} hidden>{help}</span>
    </>
  );
}

/** What changed after the closing, as the server computed it: the current margin and each difference. */
function DeliveryChangeDetail({ change, metric }: { change: DeliveryChange; metric: DeliveryMetric }) {
  const entries: [string, string][] = [
    ["Margen informativo", formatMoney(change.current_margin)],
    ["Diferencia de margen", formatMoney(change.margin_difference)],
    ["Diferencia de entrega", `${formatQuantity(change.delivered_difference)} ${metricLabel(metric)}`],
    ["Diferencia de impresiones", formatInteger(change.delivered_impressions_difference)],
    ["Diferencia de coste de medios", formatMoney(change.media_cost_difference)],
  ];
  if (change.reported_revenue_difference !== null) {
    entries.push(["Diferencia de ingreso comunicado", formatMoney(change.reported_revenue_difference)]);
  }
  if (change.buyer_spend_difference !== null) {
    entries.push(["Diferencia de gasto del comprador", formatMoney(change.buyer_spend_difference)]);
  }
  if (change.billable_difference !== null) {
    entries.push(["Diferencia de volumen facturable", `${formatQuantity(change.billable_difference)} ${metricLabel(metric)}`]);
  }
  if (change.billing_difference !== null) {
    entries.push(["Diferencia de facturación", formatMoney(change.billing_difference)]);
  }
  return (
    <span className="delivery-change">
      {entries.map(([label, value]) => (
        <span key={label} className="change-figure">
          <span className="change-label">{label}</span>{" "}
          <span className="change-value">{value}</span>
        </span>
      ))}
      <span className="change-note">{DELIVERY_CHANGE_NOTE}</span>
    </span>
  );
}

function FlightRow({ flight, showGross }: { flight: FlightMargin; showGross: boolean }) {
  return (
    <tr>
      <td>{twoDigits(flight.period_month)}/{flight.period_year}</td>
      <td>{flight.flight_start} – {flight.flight_end}</td>
      <td>
        <span className={STATE_CLASS[flight.state]}>{STATE_LABEL[flight.state]}</span>
        {flight.state === "running" && (
          <span className="flight-legend">{daysLegend(flight.accrued_days, flight.window_days)}</span>
        )}
      </td>
      <td className="num">{formatMoney(flight.contracted_revenue)}</td>
      <td className="num">{formatMoney(flight.revenue)}</td>
      {showGross && <td className="num">{flight.gross_revenue === null ? "—" : formatMoney(flight.gross_revenue)}</td>}
      <td className="num">{formatMoney(flight.media_cost)}</td>
      <td className="num">{formatMoney(flight.rebate)}</td>
      <td className="num">{formatMoney(flight.platform_cost)}</td>
      <td className="num">{formatMoney(flight.margin)}</td>
      <td className="num">{formatPercent(flight.margin_pct)}</td>
      <td>
        {flight.below_cost && <span className="tag tag-warning">Margen negativo</span>}
        {flight.below_cost && flight.zero_sale ? " " : null}
        {flight.zero_sale && <span className="tag tag-info">Sin venta</span>}
        {flight.gross_differs_from_buyer_spend && (
          <Warning label={GROSS_DIFFERS_LABEL} help={GROSS_DIFFERS_HELP} className="tag tag-warning" />
        )}
        {flight.data_cost_reported && <Warning label={DATA_COST_LABEL} help={DATA_COST_HELP} className="tag tag-info" />}
        {isAdjusted(flight.billing_basis) && (
          <Warning label={ADJUSTED_LABEL} help={adjustedHelp(flight.billing_basis)} className="tag tag-info" />
        )}
        {flight.delivery_changed && flight.delivery_change !== null && (
          <>
            <Warning label={DELIVERY_CHANGED_LABEL} help={DELIVERY_CHANGED_HELP} className="tag tag-warning" />
            <DeliveryChangeDetail change={flight.delivery_change} metric={flight.delivery_metric} />
          </>
        )}
      </td>
      <td>{deliveryLegend(flight.delivered, flight.contracted_impressions, flight.delivery_metric)}</td>
    </tr>
  );
}

function LineLevel({ campaign, line }: { campaign: CampaignMargin; line: LineMargin }) {
  const helpId = useId();
  // A line has one commitment: a target line names its sale «Venta objetivo» and shows the gross of its flights.
  const target = line.totals.volume_commitment === "target";
  const runs = lineRuns(line);
  return (
    <details className="margin-level margin-line" aria-label={`Línea ${line.line_number} de ${campaign.name}`}>
      <summary className="margin-summary">
        <span className="margin-title">
          Línea {line.line_number} · {line.channel} · {SCOPE_LABEL[line.scope] ?? line.scope}
        </span>
        <TotalsFlags totals={line.totals} />
        <Figures figured={line.totals} includesRunning={runs} />
      </summary>
      <div className="table-scroll">
        <table aria-label={`Flights de la línea ${line.line_number} de ${campaign.name}`} className="compact">
          <thead>
            <tr>
              <th scope="col">Periodo</th>
              <th scope="col">Ventana</th>
              <th scope="col">Estado</th>
              <th scope="col">{saleLabel(line.totals.volume_commitment)}</th>
              <th scope="col" aria-describedby={helpId} title={BILLING_HELP}>{billingLabel(runs)}</th>
              {target && <th scope="col">{GROSS_LABEL}</th>}
              <th scope="col">Coste de medios</th>
              <th scope="col">Rebate</th>
              <th scope="col">Coste de plataforma</th>
              <th scope="col">Margen</th>
              <th scope="col">% de margen</th>
              <th scope="col">Avisos</th>
              <th scope="col">Entrega</th>
            </tr>
          </thead>
          <tbody>
            {line.flights.map((flight) => <FlightRow key={flight.flight_id} flight={flight} showGross={target} />)}
          </tbody>
        </table>
        <span id={helpId} hidden>{BILLING_HELP}</span>
      </div>
    </details>
  );
}

function CampaignLevel({ campaign }: { campaign: CampaignMargin }) {
  return (
    <details className="margin-level margin-campaign" aria-label={`Campaña ${campaign.name}`}>
      <summary className="margin-summary">
        <span className="margin-title"><AdformName name={campaign.name} /></span>
        <TotalsFlags totals={campaign.totals} />
        <Figures figured={campaign.totals} includesRunning={campaignRuns(campaign)} />
      </summary>
      {campaign.lines.map((line) => <LineLevel key={line.campaign_line_id} campaign={campaign} line={line} />)}
    </details>
  );
}

/** The totals of the period and, below them, the campaigns, their lines and their flights. */
export function MarginTree({ margin }: { margin: MarginResponse }) {
  return (
    <div className="margin-tree">
      <section aria-label="Totales del periodo" className="margin-period">
        <h2>Totales del periodo</h2>
        <div className="margin-summary">
          <TotalsFlags totals={margin.totals} />
          <Figures figured={margin.totals} includesRunning={margin.campaigns.some(campaignRuns)} />
        </div>
      </section>
      {margin.campaigns.map((campaign) => <CampaignLevel key={campaign.campaign_id} campaign={campaign} />)}
    </div>
  );
}
