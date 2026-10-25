"use client";

import { manualSplitProblem, monthLabel, volumesSum, type LinePreview } from "./line-flights";

interface FlightEditorProps {
  canCalculate: boolean;
  calculating: boolean;
  /** The current preview, or null when there is none or it is stale. */
  preview: LinePreview | null;
  /** A preview was made but the dates or the volume changed since. */
  stale: boolean;
  error?: string | null;
  onCalculate: () => void;
  onEditVolume: (index: number, value: string) => void;
  onReset: () => void;
}

const errorStyle = { color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" } as const;
const cell = { padding: "0.25rem 0.5rem", textAlign: "left" } as const;

/** The monthly split of a line: calculated by the backend, editable by the user. */
export function FlightEditor({
  canCalculate,
  calculating,
  preview,
  stale,
  error,
  onCalculate,
  onEditVolume,
  onReset,
}: FlightEditorProps) {
  const problem = preview?.manual ? manualSplitProblem(preview) : null;

  return (
    <div style={{ gridColumn: "1 / -1" }}>
      <button
        type="button"
        onClick={onCalculate}
        disabled={!canCalculate || calculating}
        style={{
          padding: "0.5rem 1rem",
          backgroundColor: !canCalculate || calculating ? "#9ca3af" : "#3b82f6",
          color: "white",
          borderRadius: "0.375rem",
          border: "none",
          cursor: !canCalculate || calculating ? "not-allowed" : "pointer",
        }}
      >
        {calculating ? "Calculando…" : "Calcular reparto"}
      </button>

      {stale && (
        <p style={{ marginTop: "0.5rem", color: "#92400e" }}>
          Las fechas o el volumen han cambiado: vuelve a calcular el reparto.
        </p>
      )}
      {error && <p style={errorStyle}>{error}</p>}

      {preview && (
        <div style={{ marginTop: "0.75rem" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={cell}>Mes</th>
                <th style={cell}>Ventana</th>
                <th style={cell}>Volumen</th>
              </tr>
            </thead>
            <tbody>
              {preview.flights.map((flight, index) => (
                <tr key={`${flight.period_year}-${flight.period_month}`}>
                  <td style={cell}>{monthLabel(flight)}</td>
                  <td style={cell}>{`${flight.flight_start} – ${flight.flight_end}`}</td>
                  <td style={cell}>
                    <input
                      type="number"
                      aria-label={`Volumen ${monthLabel(flight)}`}
                      value={preview.volumes[index] ?? ""}
                      onChange={(e) => onEditVolume(index, e.target.value)}
                      style={{ width: "10rem", padding: "0.25rem", border: "1px solid #d1d5db", borderRadius: "0.375rem" }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <p style={{ marginTop: "0.5rem", fontWeight: "500" }}>
            {`Suma ${volumesSum(preview)} de ${preview.request.contracted_impressions}`}
          </p>

          {preview.manual && (
            <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginTop: "0.5rem" }}>
              <span>Reparto manual</span>
              <button type="button" onClick={onReset} style={{ padding: "0.25rem 0.75rem" }}>
                Restablecer reparto proporcional
              </button>
            </div>
          )}
          {problem && <p style={errorStyle}>{problem}</p>}
        </div>
      )}
    </div>
  );
}
