"use client";

import { useId, useState } from "react";

import { namesAreMasked } from "@/features/linking/AdformName";
import { closeMonth, getMargin, marginPath, type MarginResponse } from "@/lib/api/margin";
import { createApiClient, type ApiError } from "@/lib/api/client";
import { useApiCall } from "@/lib/api/useApiCall";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";
import { AccessDeniedPage } from "@/lib/components/AccessDeniedPage";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";
import { CloseMonthDialog } from "./CloseMonthDialog";
import { hasActiveFilter, NO_FILTERS, toFilters, type FilterFields } from "./filters";
import { MarginTree } from "./MarginTree";
import { closedFlightsMessage, closingErrorMessage, monthNames } from "./messages";

const NOTHING_TO_CLOSE = "No hay flights pendientes de cierre en este mes";
const REMOVE_CAMPAIGN_FILTER = "Quita el filtro de campaña para cerrar el mes";
const NOTICE = "Las cifras provisionales pueden cambiar hasta el cierre del mes";

interface CampaignOption {
  id: number;
  name: string;
}

/** Whether any flight of the margin the API returned is waiting to be closed; only the state it reports is read. */
function hasPendingClose(margin: MarginResponse): boolean {
  return margin.campaigns.some((campaign) =>
    campaign.lines.some((line) => line.flights.some((flight) => flight.state === "pending_close")),
  );
}

type Outcome = { kind: "success"; lines: string[] } | { kind: "error"; text: string };

function apiClient() {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) throw new Error("API URL not configured");
  return createApiClient({ baseUrl });
}

/** The margin per campaign, line and flight, with its filters and the closing of a month. */
export function MarginPage() {
  const [fields, setFields] = useState<FilterFields>(NO_FILTERS);
  const [reloads, setReloads] = useState(0);
  const [offeredFrom, setOfferedFrom] = useState<MarginResponse | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [blocked, setBlocked] = useState<"forbidden" | "unauthenticated" | null>(null);
  const yearId = useId();
  const monthId = useId();
  const campaignId = useId();
  const hintId = useId();
  const nothingToCloseId = useId();
  const campaignFilterId = useId();

  const filters = toFilters(fields);
  const { state } = useApiCall(`${marginPath(filters)}#${reloads}`, (client) => getMargin(client, filters));

  // The campaigns on offer are those of the last margin loaded without a campaign filter, so that choosing one
  // does not hide the others (it is used for nothing else). Adjusted while rendering (not in an effect) so the first screen already has them.
  if (state.status === "ready" && filters.campaignId === undefined && state.data !== offeredFrom) {
    setOfferedFrom(state.data);
  }
  const options: CampaignOption[] = (offeredFrom?.campaigns ?? []).map((campaign) => ({ id: campaign.campaign_id, name: campaign.name }));

  const forbidden = state.status === "forbidden" || blocked === "forbidden";
  useReportForbidden("/margin", forbidden);

  if (state.status === "unauthenticated" || blocked === "unauthenticated") return <SessionExpiredPage />;
  if (forbidden) return <AccessDeniedPage message="No tienes permiso para ver el margen." />;

  const target = filters.year !== undefined && filters.month !== undefined ? { year: filters.year, month: filters.month } : null;
  const masked = namesAreMasked();
  // Closing acts on the whole month, so a campaign filter, which narrows the flights loaded, rules it out.
  const campaignFiltered = filters.campaignId !== undefined;
  const nothingToClose = !campaignFiltered && target !== null && (state.status !== "ready" || !hasPendingClose(state.data));

  async function confirmClosing() {
    if (target === null) return;
    setSubmitting(true);
    try {
      const result = await closeMonth(apiClient(), target);
      setDialogOpen(false);
      const lines = [closedFlightsMessage(result.closed, target)];
      if (result.closed === 0 && result.already_closed > 0) lines.push(`Ya estaban cerrados: ${result.already_closed}`);
      setOutcome({ kind: "success", lines });
      setReloads((count) => count + 1);
    } catch (caught) {
      setDialogOpen(false);
      const error = caught as Partial<ApiError>;
      if (error.kind === "unauthenticated") setBlocked("unauthenticated");
      else if (error.kind === "forbidden") setBlocked("forbidden");
      else setOutcome({ kind: "error", text: closingErrorMessage(error.code, error.message, target) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1>Margen</h1>
      <p className="notice notice-info">{NOTICE}</p>

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
            <option value="">Todos</option>
            {monthNames().map((name, index) => <option key={name} value={String(index + 1)}>{name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={campaignId}>Campaña</label>
          <select id={campaignId} value={fields.campaign} onChange={(event) => setFields({ ...fields, campaign: event.target.value })}>
            <option value="">Todas</option>
            {options.map((option) => (
              <option key={option.id} value={String(option.id)}>{masked ? `Campaña ${option.id}` : option.name}</option>
            ))}
          </select>
        </div>
        <button type="button" disabled={!hasActiveFilter(fields)} onClick={() => setFields(NO_FILTERS)}>Limpiar filtros</button>
        <div>
          <button
            type="button"
            className="btn-primary"
            disabled={target === null || campaignFiltered || nothingToClose || submitting}
            aria-describedby={campaignFiltered ? campaignFilterId : target === null ? hintId : nothingToClose ? nothingToCloseId : undefined}
            onClick={() => setDialogOpen(true)}
          >
            Cerrar mes
          </button>
          {campaignFiltered && <p id={campaignFilterId} className="hint">{REMOVE_CAMPAIGN_FILTER}</p>}
          {!campaignFiltered && target === null && <p id={hintId} className="hint">Elige año y mes para cerrar un mes</p>}
          {nothingToClose && <p id={nothingToCloseId} className="hint">{NOTHING_TO_CLOSE}</p>}
        </div>
      </div>

      {outcome?.kind === "success" && (
        <div role="status" className="notice notice-success">
          {outcome.lines.map((line) => <p key={line}>{line}</p>)}
        </div>
      )}
      {outcome?.kind === "error" && <div role="alert" className="notice notice-error">{outcome.text}</div>}

      {state.status === "loading" && <div role="status" className="notice notice-info">Cargando margen…</div>}
      {state.status === "error" && (
        <div role="alert" className="notice notice-error">
          No se pudo cargar el margen. Inténtalo de nuevo más tarde.
        </div>
      )}
      {state.status === "ready" && state.data.campaigns.length === 0 && (
        <div className="empty-state">
          <p>No hay margen para el periodo elegido</p>
        </div>
      )}
      {state.status === "ready" && state.data.campaigns.length > 0 && <MarginTree margin={state.data} />}

      {dialogOpen && target !== null && (
        <CloseMonthDialog target={target} submitting={submitting} onConfirm={() => void confirmClosing()} onCancel={() => setDialogOpen(false)} />
      )}
    </div>
  );
}
