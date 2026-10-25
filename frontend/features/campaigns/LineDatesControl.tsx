"use client";

interface LineDatesControlProps {
  /** Unique within the page, to tie each label to its input. */
  idPrefix: string;
  inherit: boolean;
  startDate: string;
  endDate: string;
  startError?: string;
  endError?: string;
  onInheritChange: (inherit: boolean) => void;
  onDateChange: (field: "start_date" | "end_date", value: string) => void;
}

const inputStyle = (hasError: boolean) => ({
  width: "100%",
  padding: "0.5rem",
  border: hasError ? "2px solid #dc2626" : "1px solid #d1d5db",
  borderRadius: "0.375rem",
});

const errorStyle = { color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" } as const;

/** The line's dates: inherited from the campaign unless the box is cleared. */
export function LineDatesControl({
  idPrefix,
  inherit,
  startDate,
  endDate,
  startError,
  endError,
  onInheritChange,
  onDateChange,
}: LineDatesControlProps) {
  return (
    <div style={{ gridColumn: "1 / -1" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <input
          id={`${idPrefix}-inherit`}
          type="checkbox"
          checked={inherit}
          onChange={(e) => onInheritChange(e.target.checked)}
        />
        <label htmlFor={`${idPrefix}-inherit`}>Heredar las fechas de la campaña</label>
      </div>

      {!inherit && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "1.5rem", marginTop: "0.75rem" }}>
          <div>
            <label htmlFor={`${idPrefix}-start`} style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Inicio de la línea
            </label>
            <input
              id={`${idPrefix}-start`}
              type="date"
              value={startDate}
              onChange={(e) => onDateChange("start_date", e.target.value)}
              style={inputStyle(Boolean(startError))}
            />
            {startError && <p style={errorStyle}>{startError}</p>}
          </div>
          <div>
            <label htmlFor={`${idPrefix}-end`} style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Fin de la línea
            </label>
            <input
              id={`${idPrefix}-end`}
              type="date"
              value={endDate}
              onChange={(e) => onDateChange("end_date", e.target.value)}
              style={inputStyle(Boolean(endError))}
            />
            {endError && <p style={errorStyle}>{endError}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
