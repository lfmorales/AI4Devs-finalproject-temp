"use client";

import { useEffect, useId, useState, type FormEvent } from "react";

import { AdformName } from "@/features/linking/AdformName";
import { LinePickerDialog, type FatalKind } from "@/features/linking/LinePickerDialog";
import { HISTORY_LOAD_WARNING } from "@/features/linking/messages";
import { createApiClient, type ApiError } from "@/lib/api/client";
import {
  createDspMapping,
  listDspCatalog,
  unlinkLine,
  type DspCatalogItem,
  type DspCatalogPage,
  type UnmappedLine,
} from "@/lib/api/dsp-catalog";
import { useApiCall } from "@/lib/api/useApiCall";
import { formatInteger } from "@/lib/format/integer";
import {
  MAPPING_ERROR_MESSAGES,
  MAPPING_FAILED_MESSAGE,
  NO_RECENT_DELIVERY,
  removedDaysMessage,
  UNLINK_ERROR_MESSAGES,
  UNLINK_FAILED_MESSAGE,
  unlinkLeavesTheRowUnlinked,
  VALIDATION_MESSAGES,
} from "./messages";
import { UnlinkDialog } from "./UnlinkDialog";

const PAGE_SIZE = 50;

interface Filters {
  q: string;
  mapped: "" | "true" | "false";
  activeSince: string;
}

const NO_FILTERS: Filters = { q: "", mapped: "", activeSince: "" };

function pairKey(item: DspCatalogItem): string {
  return `${item.dsp_id}/${item.external_campaign_id}/${item.external_line_item_id}`;
}

function formatLineDates(item: DspCatalogItem): string {
  return `${item.line_start_date ?? "—"} – ${item.line_end_date ?? "—"}`;
}

interface LinkOutcome {
  lineName: string;
  messages: string[];
  needsHistoryLoad: boolean;
}

/** The Adform catalogue: filters, pages, and linking an unlinked pair to a campaign line. */
export function CatalogueView({ onFatal }: { onFatal: (kind: FatalKind) => void }) {
  const [draft, setDraft] = useState<Filters>(NO_FILTERS);
  const [applied, setApplied] = useState<Filters>(NO_FILTERS);
  const [offset, setOffset] = useState(0);
  const [linkingKey, setLinkingKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<LinkOutcome | null>(null);
  const [unlinkingKey, setUnlinkingKey] = useState<string | null>(null);
  const [unlinkProblem, setUnlinkProblem] = useState<string | null>(null);
  const [unlinkNotice, setUnlinkNotice] = useState<string | null>(null);
  const searchId = useId();
  const mappedId = useId();
  const sinceId = useId();
  const sinceHintId = useId();

  const { state, setData } = useApiCall(JSON.stringify({ applied, offset }), (client) =>
    listDspCatalog(client, {
      q: applied.q.trim(),
      mapped: applied.mapped === "" ? undefined : applied.mapped === "true",
      activeSince: applied.activeSince,
      limit: PAGE_SIZE,
      offset,
    }),
  );
  const loadFailure = state.status === "unauthenticated" || state.status === "forbidden" ? state.status : null;

  useEffect(() => {
    if (loadFailure) onFatal(loadFailure);
  }, [loadFailure, onFatal]);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setApplied(draft);
    setOffset(0);
  }

  function withMappedLine(page: DspCatalogPage, item: DspCatalogItem, mappedLineId: number | null): DspCatalogPage {
    return { ...page, items: page.items.map((row) => (pairKey(row) === pairKey(item) ? { ...row, mapped_line_id: mappedLineId } : row)) };
  }

  async function unlink(page: DspCatalogPage, item: DspCatalogItem) {
    if (item.mapped_line_id === null) return;
    setSubmitting(true);
    setUnlinkProblem(null);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!baseUrl) throw new Error("API URL not configured");
      const result = await unlinkLine(createApiClient({ baseUrl }), item.mapped_line_id);
      setOutcome(null);
      setUnlinkNotice(removedDaysMessage(result.removed_delivery_days));
      setData(withMappedLine(page, item, null));
      setUnlinkingKey(null);
    } catch (caught) {
      const error = caught as Partial<ApiError>;
      if (error.kind === "unauthenticated" || error.kind === "forbidden") {
        onFatal(error.kind);
        return;
      }
      if (unlinkLeavesTheRowUnlinked(error.code)) setData(withMappedLine(page, item, null));
      setUnlinkProblem((error.code && UNLINK_ERROR_MESSAGES[error.code]) || UNLINK_FAILED_MESSAGE);
    } finally {
      setSubmitting(false);
    }
  }

  async function link(page: DspCatalogPage, item: DspCatalogItem, line: UnmappedLine) {
    setSubmitting(true);
    setProblem(null);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!baseUrl) throw new Error("API URL not configured");
      const result = await createDspMapping(createApiClient({ baseUrl }), line.id, {
        external_campaign_id: item.external_campaign_id,
        external_line_item_id: item.external_line_item_id,
      });
      const messages = [VALIDATION_MESSAGES[result.validation]];
      if (result.last_impressions_date === null) messages.push(NO_RECENT_DELIVERY);
      setUnlinkNotice(null);
      setOutcome({ lineName: `${line.campaign_name}, línea ${line.line_number}`, messages, needsHistoryLoad: result.needs_history_load });
      setData(withMappedLine(page, item, line.id));
      setLinkingKey(null);
    } catch (caught) {
      const error = caught as Partial<ApiError>;
      if (error.kind === "unauthenticated" || error.kind === "forbidden") {
        onFatal(error.kind);
        return;
      }
      setProblem((error.code && MAPPING_ERROR_MESSAGES[error.code]) || MAPPING_FAILED_MESSAGE);
    } finally {
      setSubmitting(false);
    }
  }

  function body() {
    if (state.status === "loading") return <div role="status" className="notice notice-info">Cargando catálogo…</div>;
    if (state.status === "error") {
      return <div role="alert" className="notice notice-error">No se pudo cargar el catálogo. Inténtalo de nuevo más tarde.</div>;
    }
    if (state.status !== "ready") return null;

    const page = state.data;
    if (page.items.length === 0) {
      return (
        <div className="empty-state">
          <p>No hay parejas que mostrar</p>
        </div>
      );
    }
    const linking = page.items.find((item) => pairKey(item) === linkingKey) ?? null;
    const unlinking = page.items.find((item) => pairKey(item) === unlinkingKey) ?? null;
    return (
      <>
        <div className="table-scroll">
        <table aria-label="Catálogo Adform">
          <thead>
            <tr>
              <th scope="col">Campaña</th>
              <th scope="col">Línea</th>
              <th scope="col">Fechas de la línea</th>
              <th scope="col">Última fecha con impresiones</th>
              <th scope="col">Vinculada</th>
              <th scope="col">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((item) => (
              <tr key={pairKey(item)}>
                <td><AdformName name={item.campaign_name} /></td>
                <td><AdformName name={item.line_item_name} /></td>
                <td>{formatLineDates(item)}</td>
                <td>{item.last_impressions_date ?? "—"}</td>
                <td>{item.mapped_line_id === null ? "No" : "Sí"}</td>
                <td>
                  {item.mapped_line_id !== null && (
                    <button
                      type="button"
                      className="btn-danger"
                      aria-label={`Desvincular: ${item.campaign_name} / ${item.line_item_name}`}
                      onClick={() => { setUnlinkProblem(null); setUnlinkingKey(pairKey(item)); }}
                    >
                      Desvincular
                    </button>
                  )}
                  {item.mapped_line_id === null && (
                    <button
                      type="button"
                      aria-label={`Vincular a una línea: ${item.campaign_name} / ${item.line_item_name}`}
                      onClick={() => { setProblem(null); setLinkingKey(pairKey(item)); }}
                    >
                      Vincular a una línea
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        <nav aria-label="Paginación del catálogo">
          <button type="button" disabled={page.offset === 0} onClick={() => setOffset(Math.max(0, page.offset - PAGE_SIZE))}>Anterior</button>
          <span>Mostrando {formatInteger(page.offset + 1)}–{formatInteger(page.offset + page.items.length)} de {formatInteger(page.total)}</span>
          <button type="button" disabled={page.offset + page.items.length >= page.total} onClick={() => setOffset(page.offset + PAGE_SIZE)}>Siguiente</button>
        </nav>
        {unlinking && (
          <UnlinkDialog
            campaignName={unlinking.campaign_name}
            lineItemName={unlinking.line_item_name}
            submitting={submitting}
            problem={unlinkProblem}
            onConfirm={() => void unlink(page, unlinking)}
            onCancel={() => setUnlinkingKey(null)}
          />
        )}
        {linking && (
          <LinePickerDialog
            label="Vincular la pareja a una línea"
            submitting={submitting}
            problem={problem}
            onConfirm={(line) => void link(page, linking, line)}
            onCancel={() => setLinkingKey(null)}
            onFatal={onFatal}
          />
        )}
      </>
    );
  }

  return (
    <div>
      <form className="filters" onSubmit={applyFilters}>
        <div>
          <label htmlFor={searchId}>Buscar por nombre</label>
          <input id={searchId} type="search" value={draft.q} onChange={(event) => setDraft({ ...draft, q: event.target.value })} />
        </div>
        <div>
          <label htmlFor={mappedId}>Vinculación</label>
          <select id={mappedId} value={draft.mapped} onChange={(event) => setDraft({ ...draft, mapped: event.target.value as Filters["mapped"] })}>
            <option value="">Todas</option>
            <option value="true">Vinculadas</option>
            <option value="false">Sin vincular</option>
          </select>
        </div>
        <div>
          <label htmlFor={sinceId}>Activas desde</label>
          <input id={sinceId} type="date" aria-describedby={sinceHintId} value={draft.activeSince} onChange={(event) => setDraft({ ...draft, activeSince: event.target.value })} />
          <p id={sinceHintId} className="hint">
            Se compara con la última fecha con fila en Adform, no actividad real.
          </p>
        </div>
        <button type="submit" className="btn-primary">Filtrar</button>
      </form>
      {outcome && (
        <div role="status" className="notice notice-success">
          <p>Pareja vinculada a {outcome.lineName}.</p>
          {outcome.messages.map((message) => <p key={message}>{message}</p>)}
        </div>
      )}
      {unlinkNotice && (
        <div role="status" className="notice notice-success">
          <p>{unlinkNotice}</p>
        </div>
      )}
      {outcome?.needsHistoryLoad && (
        <div role="alert" className="notice notice-warning">{HISTORY_LOAD_WARNING}</div>
      )}
      {body()}
    </div>
  );
}
