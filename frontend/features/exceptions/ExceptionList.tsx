"use client";

import { useEffect, useState } from "react";

import { LinePickerDialog, type FatalKind } from "@/features/linking/LinePickerDialog";
import { HISTORY_LOAD_WARNING, LINK_ERROR_MESSAGES, LINK_FAILED_MESSAGE, linkLeavesTheOpenQueue } from "@/features/linking/messages";
import type { UnmappedLine } from "@/lib/api/dsp-catalog";
import { createApiClient, type ApiError } from "@/lib/api/client";
import { linkException, listIngestionExceptions, resolveIngestionException, type ExceptionStatus } from "@/lib/api/exceptions";
import { useApiCall } from "@/lib/api/useApiCall";
import { formatInteger } from "@/lib/format/integer";
import { formatCatalogueName, formatDsp, formatExternalPair, leavesTheOpenQueue, RESOLVE_ERROR_MESSAGES, RESOLVE_FAILED_MESSAGE, TYPE_LABELS } from "./labels";
import { ResolveDialog } from "./ResolveDialog";

const HEADER_STYLE = { textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" } as const;
const CELL_STYLE = { padding: "0.5rem 1rem" } as const;

/** The two failures that replace the whole page: the session is gone, or the user lacks the role. */
export type { FatalKind };

/** One tab of the queue: loads its own list, and resolves open exceptions without reloading it. */
export function ExceptionList({ status, onFatal }: { status: ExceptionStatus; onFatal: (kind: FatalKind) => void }) {
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
  if (state.status === "loading") return <div role="status">Cargando excepciones…</div>;
  if (state.status === "error") {
    return <div role="alert" style={{ backgroundColor: "#fee2e2", padding: "1rem" }}>No se pudo cargar la cola de excepciones. Inténtalo de nuevo más tarde.</div>;
  }

  const rows = state.data;
  const without = (id: number) => rows.filter((row) => row.id !== id);

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
        <div key={warning} role="alert" style={{ backgroundColor: "#fef3c7", padding: "1rem", marginBottom: "1rem" }}>{warning}</div>
      ))}
      {notice && <div role="status" style={{ backgroundColor: "#dcfce7", padding: "1rem", marginBottom: "1rem" }}>{notice}</div>}
      {problem && <div role="alert" style={{ backgroundColor: "#fee2e2", padding: "1rem", marginBottom: "1rem" }}>{problem}</div>}
      {rows.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", backgroundColor: "#f3f4f6" }}>
          <p>{status === "open" ? "No hay excepciones abiertas" : "No hay excepciones resueltas"}</p>
        </div>
      ) : (
        <table aria-label="Cola de excepciones" style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ backgroundColor: "#f3f4f6", borderBottom: "2px solid #d1d5db" }}>
              <th scope="col" style={HEADER_STYLE}>Tipo</th>
              <th scope="col" style={HEADER_STYLE}>DSP</th>
              <th scope="col" style={HEADER_STYLE}>Pareja externa</th>
              <th scope="col" style={HEADER_STYLE}>Campaña Adform</th>
              <th scope="col" style={HEADER_STYLE}>Línea Adform</th>
              <th scope="col" style={HEADER_STYLE}>Primera fecha</th>
              <th scope="col" style={HEADER_STYLE}>Última fecha</th>
              <th scope="col" style={HEADER_STYLE}>Días</th>
              <th scope="col" style={HEADER_STYLE}>Impresiones</th>
              <th scope="col" style={HEADER_STYLE}>Clics</th>
              <th scope="col" style={HEADER_STYLE}>{status === "open" ? "Acciones" : "Nota"}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} style={{ borderBottom: "1px solid #e5e7eb" }}>
                <td style={CELL_STYLE}>{TYPE_LABELS[row.exception_type]}</td>
                <td style={CELL_STYLE}>{formatDsp(row.dsp_id)}</td>
                <td style={CELL_STYLE}>{formatExternalPair(row)}</td>
                <td style={CELL_STYLE}>{formatCatalogueName(row, row.campaign_name)}</td>
                <td style={CELL_STYLE}>{formatCatalogueName(row, row.line_item_name)}</td>
                <td style={CELL_STYLE}>{row.first_date ?? "—"}</td>
                <td style={CELL_STYLE}>{row.last_date ?? "—"}</td>
                <td style={CELL_STYLE}>{row.days}</td>
                <td style={CELL_STYLE}>{formatInteger(row.impressions_total)}</td>
                <td style={CELL_STYLE}>{formatInteger(row.clicks_total)}</td>
                <td style={CELL_STYLE}>
                  {status === "open" ? (
                    <span style={{ display: "flex", gap: "0.5rem" }}>
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
