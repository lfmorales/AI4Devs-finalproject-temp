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
    <div className="span-all">
      <button
        type="button"
        className="btn-primary"
        onClick={onCalculate}
        disabled={!canCalculate || calculating}
      >
        {calculating ? "Calculando…" : "Calcular reparto"}
      </button>

      {stale && (
        <p className="notice notice-warning">
          Las fechas o el volumen han cambiado: vuelve a calcular el reparto.
        </p>
      )}
      {error && <p className="field-error">{error}</p>}

      {preview && (
        <div className="flight-preview">
          <div className="table-scroll compact">
          <table>
            <thead>
              <tr>
                <th>Mes</th>
                <th>Ventana</th>
                <th>Volumen</th>
              </tr>
            </thead>
            <tbody>
              {preview.flights.map((flight, index) => (
                <tr key={`${flight.period_year}-${flight.period_month}`}>
                  <td>{monthLabel(flight)}</td>
                  <td>{`${flight.flight_start} – ${flight.flight_end}`}</td>
                  <td>
                    <input
                      type="number"
                      aria-label={`Volumen ${monthLabel(flight)}`}
                      value={preview.volumes[index] ?? ""}
                      onChange={(e) => onEditVolume(index, e.target.value)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>

          <p>
            {`Suma ${volumesSum(preview)} de ${preview.request.contracted_impressions}`}
          </p>

          {preview.manual && (
            <div className="inline-row">
              <span>Reparto manual</span>
              <button type="button" onClick={onReset}>
                Restablecer reparto proporcional
              </button>
            </div>
          )}
          {problem && <p className="field-error">{problem}</p>}
        </div>
      )}
    </div>
  );
}
