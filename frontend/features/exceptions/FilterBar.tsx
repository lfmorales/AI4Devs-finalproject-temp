import { useId } from "react";

import { hasActiveFilter, NO_FILTER, type ExceptionFilter, type TypeFilter } from "./filter";

interface FilterBarProps {
  filter: ExceptionFilter;
  shown: number;
  total: number;
  onChange: (filter: ExceptionFilter) => void;
}

/** The search box and the type selector of the queue, with the counter and the button that clears them. */
export function FilterBar({ filter, shown, total, onChange }: FilterBarProps) {
  const searchId = useId();
  const typeId = useId();

  return (
    <>
      <div className="filters">
        <div>
          <label htmlFor={searchId}>Buscar excepciones</label>
          <input id={searchId} type="search" value={filter.text} onChange={(event) => onChange({ ...filter, text: event.target.value })} />
        </div>
        <div>
          <label htmlFor={typeId}>Tipo</label>
          <select id={typeId} value={filter.type} onChange={(event) => onChange({ ...filter, type: event.target.value as TypeFilter })}>
            <option value="">Todas</option>
            <option value="unmatched_delivery">Entrega sin casar</option>
            <option value="missing_delivery">Ausencia</option>
          </select>
        </div>
        <button type="button" disabled={!hasActiveFilter(filter)} onClick={() => onChange(NO_FILTER)}>Limpiar filtros</button>
      </div>
      <p className="hint">Mostrando {shown} de {total}</p>
    </>
  );
}
