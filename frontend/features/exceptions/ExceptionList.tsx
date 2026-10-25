"use client";

import { useEffect, useState } from "react";

import { AdformName } from "@/features/linking/AdformName";
import { LinePickerDialog, type FatalKind } from "@/features/linking/LinePickerDialog";
import { HISTORY_LOAD_WARNING, LINK_ERROR_MESSAGES, LINK_FAILED_MESSAGE, linkLeavesTheOpenQueue } from "@/features/linking/messages";
import type { UnmappedLine } from "@/lib/api/dsp-catalog";
import { createApiClient, type ApiError } from "@/lib/api/client";
import { linkException, listIngestionExceptions, resolveIngestionException, type ExceptionStatus, type IngestionException } from "@/lib/api/exceptions";
import { useApiCall } from "@/lib/api/useApiCall";
import { formatInteger } from "@/lib/format/integer";
import { formatCatalogueName, formatDsp, formatExternalPair, leavesTheOpenQueue, RESOLVE_ERROR_MESSAGES, RESOLVE_FAILED_MESSAGE, TYPE_LABELS } from "./labels";
import { FilterBar } from "./FilterBar";
import { filterExceptions, type ExceptionFilter } from "./filter";
import { ResolveDialog } from "./ResolveDialog";


/** The two failures that replace the whole page: the session is gone, or the user lacks the role. */
export type { FatalKind };

function CatalogueName({ row, name }: { row: IngestionException; name: string | null }) {
  return row.exception_type === "unmatched_delivery" && name !== null ? <AdformName name={name} /> : <>{formatCatalogueName(row, name)}</>;
}

/** One tab of the queue: loads its own list, and resolves open exceptions without reloading it. */
export function ExceptionList({ status, filter, onFilterChange, onFatal }: {
  status: ExceptionStatus;
  filter: ExceptionFilter;
  onFilterChange: (filter: ExceptionFilter) => void;
  onFatal: (kind: FatalKind) => void;
}) {
  const { state, setData } = useApiCall(`exceptions-${status}`, (client) => listIngestionExceptions(client, status));
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [linkingId, setLinkingId] = useState<number | null>(null);
  const [linkProblem, setLinkProblem] = useState<string | null>(null);
  const [historyWarnings, setHistoryWarnings] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const loadFailure = state.status === "unauthenticated" || state.status === "forbidden" ? state.status : null;

  useEffect(() => {
    if (loadFailure) onFatal(loadFailure);
  }, [loadFailure, onFatal]);

  if (state.status === "unauthenticated" || state.status === "forbidden") return null;
  if (state.status === "loading") return <div role="status" className="notice notice-info">Cargando excepciones…</div>;
  if (state.status === "error") {
    return <div role="alert" className="notice notice-error">No se pudo cargar la cola de excepciones. Inténtalo de nuevo más tarde.</div>;
  }

  const allRows = state.data;
  const rows = filterExceptions(allRows, filter);
  const without = (id: number) => allRows.filter((row) => row.id !== id);

  async function confirm(exceptionId: number, note: string | null) {
    setSubmitting(true);
    setNotice(null);
    setProblem(null);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!baseUrl) throw new Error("API URL not configured");
      await resolveIngestionException(createApiClient({ baseUrl }), exceptionId, note);
      setData(without(exceptionId));
      setNotice(`Excepción ${exceptionId} resuelta.`);
    } catch (caught) {
      const error = caught as Partial<ApiError>;
      if (error.kind === "unauthenticated" || error.kind === "forbidden") {
        onFatal(error.kind);
        return;
      }
      if (leavesTheOpenQueue(error.code)) setData(without(exceptionId));
      setProblem((error.code && RESOLVE_ERROR_MESSAGES[error.code]) || RESOLVE_FAILED_MESSAGE);
    } finally {
      setSubmitting(false);
      setResolvingId(null);
    }
  }

  async function link(exceptionId: number, line: UnmappedLine) {
    setSubmitting(true);
    setNotice(null);
    setLinkProblem(null);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!baseUrl) throw new Error("API URL not configured");
      const result = await linkException(createApiClient({ baseUrl }), exceptionId, line.id);
      const lineName = `${line.campaign_name}, línea ${line.line_number}`;
      setData(without(exceptionId));
      setLinkingId(null);
      setNotice(`Excepción ${exceptionId} vinculada a ${lineName}.`);
      if (result.needs_history_load) setHistoryWarnings((current) => [...current, `${lineName}: ${HISTORY_LOAD_WARNING}`]);
    } catch (caught) {
      const error = caught as Partial<ApiError>;
      if (error.kind === "unauthenticated" || error.kind === "forbidden") {
        onFatal(error.kind);
        return;
      }
      if (linkLeavesTheOpenQueue(error.code)) setData(without(exceptionId));
      setLinkProblem((error.code && LINK_ERROR_MESSAGES[error.code]) || LINK_FAILED_MESSAGE);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      {historyWarnings.map((warning) => (
        <div key={warning} role="alert" className="notice notice-warning">{warning}</div>
      ))}
      {notice && <div role="status" className="notice notice-success">{notice}</div>}
      {problem && <div role="alert" className="notice notice-error">{problem}</div>}
      {allRows.length > 0 && <FilterBar filter={filter} shown={rows.length} total={allRows.length} onChange={onFilterChange} />}
      {allRows.length === 0 ? (
        <div className="empty-state">
          <p>{status === "open" ? "No hay excepciones abiertas" : "No hay excepciones resueltas"}</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="empty-state">
          <p>No hay excepciones que coincidan con la búsqueda</p>
        </div>
      ) : (
        <div className="table-scroll">
        <table aria-label="Cola de excepciones">
          <thead>
            <tr>
              <th scope="col">Tipo</th>
              <th scope="col">DSP</th>
              <th scope="col">Pareja externa</th>
              <th scope="col">Campaña Adform</th>
              <th scope="col">Línea Adform</th>
              <th scope="col">Primera fecha</th>
              <th scope="col">Última fecha</th>
              <th scope="col" className="num">Días</th>
              <th scope="col" className="num">Impresiones</th>
              <th scope="col" className="num">Clics</th>
              <th scope="col">{status === "open" ? "Acciones" : "Nota"}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{TYPE_LABELS[row.exception_type]}</td>
                <td>{formatDsp(row.dsp_id)}</td>
                <td>{formatExternalPair(row)}</td>
                <td><CatalogueName row={row} name={row.campaign_name} /></td>
                <td><CatalogueName row={row} name={row.line_item_name} /></td>
                <td>{row.first_date ?? "—"}</td>
                <td>{row.last_date ?? "—"}</td>
                <td className="num">{row.days}</td>
                <td className="num">{formatInteger(row.impressions_total)}</td>
                <td className="num">{formatInteger(row.clicks_total)}</td>
                <td>
                  {status === "open" ? (
                    <span className="row-actions">
                      {row.exception_type === "unmatched_delivery" && (
                        <button
                          type="button"
                          aria-label={`Vincular a una línea (excepción ${row.id})`}
                          onClick={() => { setLinkProblem(null); setLinkingId(row.id); }}
                        >
                          Vincular a una línea
                        </button>
                      )}
                      <button type="button" aria-label={`Resolver excepción ${row.id}`} onClick={() => setResolvingId(row.id)}>
                        Resolver
                      </button>
                    </span>
                  ) : (
                    row.note ?? "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
      {linkingId !== null && (
        <LinePickerDialog
          label={`Vincular la excepción ${linkingId} a una línea`}
          submitting={submitting}
          problem={linkProblem}
          onConfirm={(line) => void link(linkingId, line)}
          onCancel={() => setLinkingId(null)}
          onFatal={onFatal}
        />
      )}
      {resolvingId !== null && (
        <ResolveDialog
          exceptionId={resolvingId}
          submitting={submitting}
          onConfirm={(note) => void confirm(resolvingId, note)}
          onCancel={() => setResolvingId(null)}
        />
      )}
    </div>
  );
}
