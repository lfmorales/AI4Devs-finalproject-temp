"use client";

import { useState } from "react";

import type { CampaignStatusRow } from "@/lib/api/status";
import { formatFraction, formatImpressions, formatPeriod, NOT_AVAILABLE } from "./format";
import { nextSort, sortRows, type SortColumn, type SortState } from "./sorting";

function SortableHeader({ column, label, sort, onSort }: {
  column: SortColumn;
  label: string;
  sort: SortState | null;
  onSort: (column: SortColumn) => void;
}) {
  const active = sort?.column === column ? sort.direction : "none";
  return (
    <th scope="col" aria-sort={active}>
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
    <div className="table-scroll">
    <table aria-label="Estado de las campañas">
      <thead>
        <tr>
          <th scope="col">Campaña</th>
          <SortableHeader column="agency" label="Agencia" sort={sort} onSort={onSort} />
          <th scope="col">Línea</th>
          <SortableHeader column="period" label="Periodo" sort={sort} onSort={onSort} />
          <th scope="col">Ventana</th>
          <th scope="col" className="num">Contratado</th>
          <th scope="col" className="num">Entregado</th>
          <th scope="col" className="num">Ratio</th>
          <th scope="col" className="num">Esperado</th>
          <th scope="col" className="num">Desviación</th>
          <th scope="col" className="num">Días restantes</th>
          <th scope="col">Avisos</th>
        </tr>
      </thead>
      <tbody>
        {sortRows(rows, sort).map((row) => (
          <tr key={`${row.campaign.id}-${row.line_number}-${row.flight.campaign_period_id}`}>
            <td>{row.campaign.name}</td>
            <td>{row.agency.name}</td>
            <td>{row.line_number}</td>
            <td>{formatPeriod(row.flight.year, row.flight.month)}</td>
            <td>{row.flight.start} – {row.flight.end}</td>
            <td className="num">{formatImpressions(row.contracted_impressions)}</td>
            <td className="num">{formatImpressions(row.delivered_impressions)}</td>
            <td className="num">{formatFraction(row.delivery_ratio)}</td>
            <td className="num">{formatImpressions(row.pacing.expected_impressions)}</td>
            <td className="num">{formatFraction(row.pacing.deviation)}</td>
            <td className="num">{row.pacing.days_remaining}</td>
            <td><Flags row={row} /></td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}
