"use client";

import { useEffect, useState } from "react";

import { createApiClient, type ApiError } from "@/lib/api/client";
import { listIngestionExceptions, resolveIngestionException, type ExceptionStatus } from "@/lib/api/exceptions";
import { useApiCall } from "@/lib/api/useApiCall";
import { formatInteger } from "@/lib/format/integer";
import { formatDsp, formatExternalPair, leavesTheOpenQueue, RESOLVE_ERROR_MESSAGES, RESOLVE_FAILED_MESSAGE, TYPE_LABELS } from "./labels";
import { ResolveDialog } from "./ResolveDialog";

const HEADER_STYLE = { textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" } as const;
const CELL_STYLE = { padding: "0.5rem 1rem" } as const;

/** The two failures that replace the whole page: the session is gone, or the user lacks the role. */
export type FatalKind = "unauthenticated" | "forbidden";

/** One tab of the queue: loads its own list, and resolves open exceptions without reloading it. */
export function ExceptionList({ status, onFatal }: { status: ExceptionStatus; onFatal: (kind: FatalKind) => void }) {
  const { state, setData } = useApiCall(`exceptions-${status}`, (client) => listIngestionExceptions(client, status));
  const [resolvingId, setResolvingId] = useState<number | null>(null);
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

  return (
    <div>
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
                <td style={CELL_STYLE}>{row.first_date ?? "—"}</td>
                <td style={CELL_STYLE}>{row.last_date ?? "—"}</td>
                <td style={CELL_STYLE}>{row.days}</td>
                <td style={CELL_STYLE}>{formatInteger(row.impressions_total)}</td>
                <td style={CELL_STYLE}>{formatInteger(row.clicks_total)}</td>
                <td style={CELL_STYLE}>
                  {status === "open" ? (
                    <button type="button" aria-label={`Resolver excepción ${row.id}`} onClick={() => setResolvingId(row.id)}>
                      Resolver
                    </button>
                  ) : (
                    row.note ?? "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
