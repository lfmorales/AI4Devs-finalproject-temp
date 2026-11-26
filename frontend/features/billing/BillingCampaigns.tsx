"use client";

import type { BillingCampaign, BillingFlight, BillingLine } from "@/lib/api/billing";
import { BILLING_HELP, billingLabel } from "@/features/margin/messages";
import { formatMoney, formatQuantity, NO_VALUE } from "@/lib/format/decimal";
import { metricLabel } from "@/lib/format/delivery-metric";
import { formatInteger } from "@/lib/format/integer";
import { formatMoment } from "@/lib/format/moment";
import { BASIS_LABEL, FLIGHT_STATE_LABEL, REVIEW_STATE_CLASS, REVIEW_STATE_LABEL, byUserAt } from "./messages";

/** What a campaign's or a flight's button asks the page to do; the page sends it and reads the month again. */
export interface BillingActions {
  review: (campaign: BillingCampaign) => void;
  withdraw: (campaign: BillingCampaign) => void;
  adjust: (flight: BillingFlight) => void;
  history: (flight: BillingFlight) => void;
  setBillable: (flight: BillingFlight, billable: boolean) => void;
  busy: boolean;
}

/** A line bills to date while one of its flights has not ended: it has not started or it runs. */
function lineIsToDate(line: BillingLine): boolean {
  return line.flights.some((flight) => flight.state === "running" || flight.state === "not_started");
}

function AdjustmentCell({ flight }: { flight: BillingFlight }) {
  const adjustment = flight.adjustment;
  if (adjustment === null) return <>{NO_VALUE}</>;
  return (
    <>
      <span className="tag tag-info">Ajustado</span>
      {`: ${BASIS_LABEL[adjustment.basis].toLowerCase()} · ${adjustment.reason} · usuario ${adjustment.created_by} · `}
      {formatMoment(adjustment.created_at)}
    </>
  );
}

function CarryoverCell({ flight, actions }: { flight: BillingFlight; actions: BillingActions }) {
  if (flight.carryover === null) return <>{NO_VALUE}</>;
  return (
    <>
      {formatInteger(flight.carryover)}
      {flight.carryover > 0 && (
        <label className="inline-check">
          <input
            type="checkbox"
            checked={flight.carryover_billable === true}
            disabled={flight.state === "closed" || actions.busy}
            onChange={(event) => actions.setBillable(flight, event.target.checked)}
          />
          Arrastre facturable
        </label>
      )}
    </>
  );
}

function FlightRow({ flight, actions }: { flight: BillingFlight; actions: BillingActions }) {
  const committed = flight.billing_basis !== "reported";
  return (
    <tr>
      <td>{flight.flight_start} – {flight.flight_end}</td>
      <td>{FLIGHT_STATE_LABEL[flight.state]}</td>
      <td className="num">{formatInteger(flight.contracted_impressions)} {metricLabel(flight.delivery_metric)}</td>
      <td className="num"><CarryoverCell flight={flight} actions={actions} /></td>
      <td className="num">{formatInteger(flight.delivery_target)}</td>
      <td className="num">{flight.delivered === null ? NO_VALUE : formatQuantity(flight.delivered)}</td>
      <td className="num">{flight.billable === null ? NO_VALUE : formatQuantity(flight.billable)}</td>
      <td className="num">{formatMoney(flight.sale_cpm)}</td>
      <td className="num">{flight.billing === null ? NO_VALUE : formatMoney(flight.billing)}</td>
      <td><AdjustmentCell flight={flight} /></td>
      <td>
        {flight.state === "pending_close" && committed && (
          <button type="button" disabled={actions.busy} onClick={() => actions.adjust(flight)}>Ajustar</button>
        )}
        {committed && flight.state !== "not_started" && (
          <button type="button" onClick={() => actions.history(flight)}>Historial</button>
        )}
      </td>
    </tr>
  );
}

function LineTable({ campaign, line, actions }: { campaign: BillingCampaign; line: BillingLine; actions: BillingActions }) {
  return (
    <div className="table-scroll">
      <h3>Línea {line.line_number}</h3>
      <table aria-label={`Flights de la línea ${line.line_number} de ${campaign.name}`} className="compact">
        <thead>
          <tr>
            <th scope="col">Ventana</th>
            <th scope="col">Estado</th>
            <th scope="col">Contratado</th>
            <th scope="col">Arrastre</th>
            <th scope="col">Objetivo de entrega</th>
            <th scope="col">Entregado</th>
            <th scope="col">Volumen facturable</th>
            <th scope="col">CPM</th>
            <th scope="col" title={BILLING_HELP}>{billingLabel(lineIsToDate(line))}</th>
            <th scope="col">Ajuste</th>
            <th scope="col">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {line.flights.map((flight) => <FlightRow key={flight.flight_id} flight={flight} actions={actions} />)}
        </tbody>
      </table>
    </div>
  );
}

function CampaignSection({ campaign, actions }: { campaign: BillingCampaign; actions: BillingActions }) {
  const reviewed = campaign.review_state === "reviewed" && campaign.review_set_by !== null && campaign.review_set_at !== null;
  return (
    <section aria-label={`Campaña ${campaign.name}`} className="billing-campaign">
      <h2>{campaign.name}</h2>
      <p>{campaign.agency} · {campaign.advertiser}</p>
      <p>
        <span className={REVIEW_STATE_CLASS[campaign.review_state]}>{REVIEW_STATE_LABEL[campaign.review_state]}</span>
        {reviewed && ` ${byUserAt(campaign.review_set_by ?? 0, formatMoment(campaign.review_set_at ?? ""))}`}
      </p>
      {campaign.review_state === "pending_review" && (
        <button type="button" className="btn-primary" disabled={actions.busy} onClick={() => actions.review(campaign)}>
          Marcar como revisada
        </button>
      )}
      {campaign.review_state === "reviewed" && (
        <button type="button" disabled={actions.busy} onClick={() => actions.withdraw(campaign)}>Quitar revisión</button>
      )}
      {campaign.lines.map((line) => <LineTable key={line.campaign_line_id} campaign={campaign} line={line} actions={actions} />)}
    </section>
  );
}

/** Each campaign of the month with its review state and its flights, exactly as the server read them. */
export function BillingCampaigns({ campaigns, actions }: { campaigns: BillingCampaign[]; actions: BillingActions }) {
  return <>{campaigns.map((campaign) => <CampaignSection key={campaign.campaign_id} campaign={campaign} actions={actions} />)}</>;
}
