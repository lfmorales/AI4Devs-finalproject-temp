"use client";

import { useId, useState } from "react";

import { monthNames } from "@/features/margin/messages";
import {
  billingPath,
  downloadExport,
  exportFileName,
  getBilling,
  reviewCampaign,
  setCarryoverBillable,
  withdrawReview,
  type BillingCampaign,
  type BillingFlight,
  type BillingMonth,
  type BillingResponse,
} from "@/lib/api/billing";
import { browserApiClient } from "@/lib/api/browser-client";
import type { ApiError } from "@/lib/api/client";
import { useApiCall } from "@/lib/api/useApiCall";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";
import { useRoles } from "@/lib/auth/RolesContext";
import { AccessDeniedPage } from "@/lib/components/AccessDeniedPage";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";
import { AdjustmentDialog } from "./AdjustmentDialog";
import { BillingCampaigns, type BillingActions } from "./BillingCampaigns";
import { previousMonthFields, toMonth, type MonthFields } from "./filters";
import { HistoryDialog } from "./HistoryDialog";
import { CHOOSE_MONTH, CSV_NEEDS_A_CLOSED_MONTH, billingErrorMessage } from "./messages";

type Outcome = { kind: "success"; text: string } | { kind: "error"; text: string };
type Dialog = { kind: "adjust"; flightId: number } | { kind: "history"; flightId: number } | null;

/** Whether a closing froze any flight of the month, read from the states the server reported: it then has a CSV. */
function hasClosedFlight(billing: BillingResponse): boolean {
  return billing.campaigns.some((campaign) => campaign.lines.some((line) => line.flights.some((flight) => flight.state === "closed")));
}

/** Saves a file the API answered with, under the name the server gave it. */
function save(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** The billing of a month per campaign, line and flight: the review, the adjustments, the billable flag and the CSV. */
export function BillingPage() {
  const [fields, setFields] = useState<MonthFields>(() => previousMonthFields(new Date()));
  const [reloads, setReloads] = useState(0);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [blocked, setBlocked] = useState<"forbidden" | "unauthenticated" | null>(null);
  const yearId = useId();
  const monthId = useId();
  const csvHintId = useId();

  // The billing is operations' and finance's: the screen refuses the other roles itself, as it reads nothing until a
  // month is chosen, and the backend refuses them again on every route.
  const roles = useRoles();
  const refusedByRole = roles.status === "ready" && !roles.roles.some((role) => role === "operations" || role === "finance");
  const month = refusedByRole ? null : toMonth(fields);
  const { state } = useApiCall(
    `${month === null ? "no-month" : billingPath(month)}#${reloads}`,
    (client) => (month === null ? Promise.resolve(null) : getBilling(client, month)),
  );

  const forbidden = refusedByRole || state.status === "forbidden" || blocked === "forbidden";
  useReportForbidden("/billing", forbidden);
  if (state.status === "unauthenticated" || blocked === "unauthenticated") return <SessionExpiredPage />;
  if (forbidden) return <AccessDeniedPage message="No tienes permiso para ver la facturación." />;

  const billing = state.status === "ready" ? state.data : null;

  /** Sends one action and reads the month again; a refusal is explained in Spanish, with what to do. */
  async function act(target: BillingMonth, send: () => Promise<unknown>, done: string, campaign?: string) {
    setBusy(true);
    setOutcome(null);
    try {
      await send();
      setOutcome({ kind: "success", text: done });
      setReloads((count) => count + 1);
    } catch (caught) {
      const failure = caught as Partial<ApiError>;
      if (failure.kind === "unauthenticated" || failure.kind === "forbidden") setBlocked(failure.kind);
      else setOutcome({ kind: "error", text: billingErrorMessage(failure.code, failure.message, { month: target, campaign }) });
    } finally {
      setBusy(false);
    }
  }

  const actions: BillingActions = {
    busy,
    review: (campaign: BillingCampaign) => {
      if (month === null) return;
      const request = { campaign_id: campaign.campaign_id, ...month };
      void act(month, () => reviewCampaign(browserApiClient(), request), `${campaign.name} queda revisada`, campaign.name);
    },
    withdraw: (campaign: BillingCampaign) => {
      if (month === null) return;
      const request = { campaign_id: campaign.campaign_id, ...month };
      void act(month, () => withdrawReview(browserApiClient(), request), `${campaign.name} vuelve a pendiente de revisión`, campaign.name);
    },
    adjust: (flight: BillingFlight) => setDialog({ kind: "adjust", flightId: flight.flight_id }),
    history: (flight: BillingFlight) => setDialog({ kind: "history", flightId: flight.flight_id }),
    setBillable: (flight: BillingFlight, billable: boolean) => {
      if (month === null) return;
      const done = billable ? "El arrastre es facturable" : "El arrastre ya no es facturable";
      void act(month, () => setCarryoverBillable(browserApiClient(), flight.flight_id, billable), done);
    },
  };

  async function downloadCsv(target: BillingMonth) {
    setOutcome(null);
    try {
      const file = await downloadExport(browserApiClient(), target);
      save(file.blob, file.fileName ?? exportFileName(target));
    } catch (caught) {
      const failure = caught as Partial<ApiError>;
      if (failure.kind === "unauthenticated" || failure.kind === "forbidden") setBlocked(failure.kind);
      else setOutcome({ kind: "error", text: billingErrorMessage(failure.code, failure.message, { month: target }) });
    }
  }

  const csvReady = billing !== null && hasClosedFlight(billing);

  return (
    <div>
      <h1>Facturación</h1>

      <div className="filters">
        <div>
          <label htmlFor={yearId}>Año</label>
          <input
            id={yearId}
            type="text"
            inputMode="numeric"
            maxLength={4}
            value={fields.yearText}
            onChange={(event) => setFields({ ...fields, yearText: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor={monthId}>Mes</label>
          <select id={monthId} value={fields.month} onChange={(event) => setFields({ ...fields, month: event.target.value })}>
            <option value="">Elige un mes</option>
            {monthNames().map((name, index) => <option key={name} value={String(index + 1)}>{name}</option>)}
          </select>
        </div>
        {month !== null && (
          <div>
            <button
              type="button"
              disabled={!csvReady}
              aria-describedby={csvReady ? undefined : csvHintId}
              onClick={() => void downloadCsv(month)}
            >
              Descargar CSV
            </button>
            {!csvReady && <p id={csvHintId} className="hint">{CSV_NEEDS_A_CLOSED_MONTH}</p>}
          </div>
        )}
      </div>

      {outcome?.kind === "success" && <div role="status" className="notice notice-success">{outcome.text}</div>}
      {outcome?.kind === "error" && dialog === null && <div role="alert" className="notice notice-error">{outcome.text}</div>}

      {month === null && <p className="hint">{CHOOSE_MONTH}</p>}
      {month !== null && state.status === "loading" && <div role="status" className="notice notice-info">Cargando facturación…</div>}
      {month !== null && state.status === "error" && (
        <div role="alert" className="notice notice-error">No se pudo cargar la facturación. Inténtalo de nuevo más tarde.</div>
      )}
      {billing !== null && billing.campaigns.length === 0 && (
        <div className="empty-state"><p>No hay campañas con flights en el mes elegido</p></div>
      )}
      {billing !== null && billing.campaigns.length > 0 && <BillingCampaigns campaigns={billing.campaigns} actions={actions} />}

      {dialog?.kind === "adjust" && month !== null && (
        <AdjustmentDialog
          flightId={dialog.flightId}
          month={month}
          onDone={() => {
            setDialog(null);
            setOutcome({ kind: "success", text: "Ajuste guardado" });
            setReloads((count) => count + 1);
          }}
          onCancel={() => setDialog(null)}
          onBlocked={(kind) => {
            setDialog(null);
            setBlocked(kind);
          }}
        />
      )}
      {dialog?.kind === "history" && <HistoryDialog flightId={dialog.flightId} onClose={() => setDialog(null)} />}
    </div>
  );
}
