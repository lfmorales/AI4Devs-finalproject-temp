"use client";

import { useState } from "react";

import type { CampaignStatusRow } from "@/lib/api/status";
import { formatQuantity } from "@/lib/format/decimal";
import { metricLabel } from "@/lib/format/delivery-metric";
import { formatFraction, formatImpressions, formatPeriod, NOT_AVAILABLE } from "./format";
import { nextSort, sortRows, type SortColumn, type SortState } from "./sorting";

/** A target line's volume is an objective, not a commitment: it is named so in its own cell. */
const TARGET_VOLUME_LABEL = "Objetivo";

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
    <ul className="tags">
      {row.missing_data_flag && <li className="tag tag-info">Sin datos recibidos</li>}
      {row.pacing_flag && <li className="tag tag-warning">Desviación de ritmo</li>}
    </ul>
  );
}

/** `onCarry` is given to a user who may write a carry-over (operations or trading): each row then offers it. */
export function StatusTable({ rows, onCarry }: { rows: CampaignStatusRow[]; onCarry?: (row: CampaignStatusRow) => void }) {
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
          <th scope="col">Unidad</th>
          <th scope="col" className="num">Contratado</th>
          <th scope="col" className="num">Arrastre</th>
          <th scope="col" className="num">Objetivo de entrega</th>
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
            <td>{metricLabel(row.delivery_metric)}</td>
            <td className="num">
              {row.volume_commitment === "target" && <span className="figure-label">{TARGET_VOLUME_LABEL} </span>}
              {formatImpressions(row.contracted_impressions)}
            </td>
            <td className="num">
              {formatImpressions(row.carryover)}
              {onCarry !== undefined && (
                <>
                  {" "}
                  <button type="button" className="cell-action" onClick={() => onCarry(row)}>Registrar arrastre</button>
                </>
              )}
            </td>
            <td className="num">{formatImpressions(row.delivery_target)}</td>
            <td className="num">{formatQuantity(row.delivered)}</td>
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
