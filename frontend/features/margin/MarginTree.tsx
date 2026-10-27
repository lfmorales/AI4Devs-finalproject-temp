import { AdformName } from "@/features/linking/AdformName";
import type { CampaignMargin, FlightMargin, FlightState, LineMargin, MarginResponse } from "@/lib/api/margin";
import { formatMoney, formatPercent } from "@/lib/format/decimal";
import { Figures } from "./Figures";
import { TotalsFlags } from "./Flags";

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

function twoDigits(month: number): string {
  return month < 10 ? `0${month}` : `${month}`;
}

function FlightRow({ flight }: { flight: FlightMargin }) {
  return (
    <tr>
      <td>{twoDigits(flight.period_month)}/{flight.period_year}</td>
      <td>{flight.flight_start} – {flight.flight_end}</td>
      <td><span className={STATE_CLASS[flight.state]}>{STATE_LABEL[flight.state]}</span></td>
      <td className="num">{formatMoney(flight.revenue)}</td>
      <td className="num">{formatMoney(flight.media_cost)}</td>
      <td className="num">{formatMoney(flight.rebate)}</td>
      <td className="num">{formatMoney(flight.platform_cost)}</td>
      <td className="num">{formatMoney(flight.margin)}</td>
      <td className="num">{formatPercent(flight.margin_pct)}</td>
      <td>
        {flight.below_cost && <span className="tag tag-warning">Margen negativo</span>}
        {flight.below_cost && flight.zero_sale ? " " : null}
        {flight.zero_sale && <span className="tag tag-info">Sin venta</span>}
      </td>
    </tr>
  );
}

function LineLevel({ campaign, line }: { campaign: CampaignMargin; line: LineMargin }) {
  return (
    <details className="margin-level margin-line" aria-label={`Línea ${line.line_number} de ${campaign.name}`}>
      <summary className="margin-summary">
        <span className="margin-title">
          Línea {line.line_number} · {line.channel} · {SCOPE_LABEL[line.scope] ?? line.scope}
        </span>
        <TotalsFlags totals={line.totals} />
        <Figures figured={line.totals} />
      </summary>
      <div className="table-scroll">
        <table aria-label={`Flights de la línea ${line.line_number} de ${campaign.name}`} className="compact">
          <thead>
            <tr>
              <th scope="col">Periodo</th>
              <th scope="col">Ventana</th>
              <th scope="col">Estado</th>
              <th scope="col">Ingreso</th>
              <th scope="col">Coste de medios</th>
              <th scope="col">Rebate</th>
              <th scope="col">Coste de plataforma</th>
              <th scope="col">Margen</th>
              <th scope="col">% de margen</th>
              <th scope="col">Avisos</th>
            </tr>
          </thead>
          <tbody>
            {line.flights.map((flight) => <FlightRow key={flight.flight_id} flight={flight} />)}
          </tbody>
        </table>
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
        <Figures figured={campaign.totals} />
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
          <Figures figured={margin.totals} />
        </div>
      </section>
      {margin.campaigns.map((campaign) => <CampaignLevel key={campaign.campaign_id} campaign={campaign} />)}
    </div>
  );
}
