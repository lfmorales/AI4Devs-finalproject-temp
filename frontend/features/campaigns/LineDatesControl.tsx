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
    <div className="span-all">
      <div className="check">
        <input
          id={`${idPrefix}-inherit`}
          type="checkbox"
          checked={inherit}
          onChange={(e) => onInheritChange(e.target.checked)}
        />
        <label htmlFor={`${idPrefix}-inherit`}>Heredar las fechas de la campaña</label>
      </div>

      {!inherit && (
        <div className="form-grid">
          <div>
            <label htmlFor={`${idPrefix}-start`}>
              Inicio de la línea
            </label>
            <input
              id={`${idPrefix}-start`}
              type="date"
              value={startDate}
              onChange={(e) => onDateChange("start_date", e.target.value)}
            />
            {startError && <p className="field-error">{startError}</p>}
          </div>
          <div>
            <label htmlFor={`${idPrefix}-end`}>
              Fin de la línea
            </label>
            <input
              id={`${idPrefix}-end`}
              type="date"
              value={endDate}
              onChange={(e) => onDateChange("end_date", e.target.value)}
            />
            {endError && <p className="field-error">{endError}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
