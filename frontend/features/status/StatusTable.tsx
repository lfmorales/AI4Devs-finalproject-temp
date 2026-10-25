"use client";

import { useState } from "react";

import type { CampaignStatusRow } from "@/lib/api/status";
import { formatFraction, formatImpressions, formatPeriod, NOT_AVAILABLE } from "./format";
import { nextSort, sortRows, type SortColumn, type SortState } from "./sorting";

const HEADER_STYLE = { textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" } as const;
const CELL_STYLE = { padding: "0.5rem 1rem" } as const;

function SortableHeader({ column, label, sort, onSort }: {
  column: SortColumn;
  label: string;
  sort: SortState | null;
  onSort: (column: SortColumn) => void;
}) {
  const active = sort?.column === column ? sort.direction : "none";
  return (
    <th scope="col" aria-sort={active} style={HEADER_STYLE}>
      <button type="button" onClick={() => onSort(column)}>{label}</button>
    </th>
  );
}

function Flags({ row }: { row: CampaignStatusRow }) {
  if (!row.missing_data_flag && !row.pacing_flag) return <>{NOT_AVAILABLE}</>;
  return (
    <ul style={{ margin: 0, paddingLeft: "1rem" }}>
      {row.missing_data_flag && <li>Sin datos recibidos</li>}
      {row.pacing_flag && <li>Desviación de ritmo</li>}
    </ul>
  );
}

export function StatusTable({ rows }: { rows: CampaignStatusRow[] }) {
  const [sort, setSort] = useState<SortState | null>(null);
  const onSort = (column: SortColumn) => setSort((current) => nextSort(current, column));

  return (
    <table aria-label="Estado de las campañas" style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ backgroundColor: "#f3f4f6", borderBottom: "2px solid #d1d5db" }}>
          <th scope="col" style={HEADER_STYLE}>Campaña</th>
          <SortableHeader column="agency" label="Agencia" sort={sort} onSort={onSort} />
          <th scope="col" style={HEADER_STYLE}>Línea</th>
          <SortableHeader column="period" label="Periodo" sort={sort} onSort={onSort} />
          <th scope="col" style={HEADER_STYLE}>Ventana</th>
          <th scope="col" style={HEADER_STYLE}>Contratado</th>
          <th scope="col" style={HEADER_STYLE}>Entregado</th>
          <th scope="col" style={HEADER_STYLE}>Ratio</th>
          <th scope="col" style={HEADER_STYLE}>Esperado</th>
          <th scope="col" style={HEADER_STYLE}>Desviación</th>
          <th scope="col" style={HEADER_STYLE}>Días restantes</th>
          <th scope="col" style={HEADER_STYLE}>Avisos</th>
        </tr>
      </thead>
      <tbody>
        {sortRows(rows, sort).map((row) => (
          <tr key={`${row.campaign.id}-${row.line_number}-${row.flight.campaign_period_id}`} style={{ borderBottom: "1px solid #e5e7eb" }}>
            <td style={CELL_STYLE}>{row.campaign.name}</td>
            <td style={CELL_STYLE}>{row.agency.name}</td>
            <td style={CELL_STYLE}>{row.line_number}</td>
            <td style={CELL_STYLE}>{formatPeriod(row.flight.year, row.flight.month)}</td>
            <td style={CELL_STYLE}>{row.flight.start} – {row.flight.end}</td>
            <td style={CELL_STYLE}>{formatImpressions(row.contracted_impressions)}</td>
            <td style={CELL_STYLE}>{formatImpressions(row.delivered_impressions)}</td>
            <td style={CELL_STYLE}>{formatFraction(row.delivery_ratio)}</td>
            <td style={CELL_STYLE}>{formatImpressions(row.pacing.expected_impressions)}</td>
            <td style={CELL_STYLE}>{formatFraction(row.pacing.deviation)}</td>
            <td style={CELL_STYLE}>{row.pacing.days_remaining}</td>
            <td style={CELL_STYLE}><Flags row={row} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
