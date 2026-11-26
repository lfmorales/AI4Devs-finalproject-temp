import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarginTree } from "@/features/margin/MarginTree";
import { campaign, flight, line, margin, totals } from "../../../helpers/margin-data";
import { plain } from "../../../helpers/api-pages";

const SPACE = " "; // plain() turns the no-break space of the euro amounts into a plain one

// The worked example as the API sends it: a target Deal line that served 1,100,000 impressions at 5.00 €.
const TARGET_FLIGHT = flight({
  flight_id: 21, contracted_revenue: "5000.00", revenue: "4400.00", gross_revenue: "5500.00", media_cost: "0.00",
  rebate: "550.00", platform_cost: "1100.00", margin: "2750.00", margin_pct: "62.50", volume_commitment: "target",
  gross_differs_from_buyer_spend: true, data_cost_reported: true,
});
const TARGET_TOTALS = totals({
  contracted_revenue: "5000.00", revenue: "4400.00", gross_revenue: "5500.00", volume_commitment: "target",
  gross_differs_count: 1, data_cost_count: 1,
});
const TARGET_LINE = line({ campaign_line_id: 20, line_number: 2, channel: "Deal", flights: [TARGET_FLIGHT], totals: TARGET_TOTALS });
const COMMITTED_LINE = line({ campaign_line_id: 10, line_number: 1 });
const MIXED_TOTALS = totals({ volume_commitment: null, gross_revenue: "5500.00", gross_differs_count: 1, data_cost_count: 1 });
const RESPONSE = margin({
  campaigns: [campaign({ name: "Alfa", lines: [COMMITTED_LINE, TARGET_LINE], totals: MIXED_TOTALS })],
  totals: MIXED_TOTALS,
});

function flightsTable(lineNumber: number) {
  return screen.getByRole("table", { name: `Flights de la línea ${lineNumber} de Alfa` });
}

function headersOf(table: HTMLElement): string[] {
  return within(table).getAllByRole("columnheader").map((h) => plain(h));
}

function cellOf(table: HTMLElement, header: string): HTMLElement {
  const index = headersOf(table).indexOf(header);
  expect(index, header).toBeGreaterThan(-1);
  return within(within(table).getAllByRole("row")[1]!).getAllByRole("cell")[index]!;
}

function figure(container: HTMLElement, label: string): string | null {
  const labels = within(container).queryAllByText(label, { selector: ".figure-label" });
  if (labels.length === 0) return null;
  return plain(labels[0]!.parentElement!.querySelector(".figure-value"));
}

describe("a target flight in the margin", () => {
  it("names its sale «Venta objetivo» and shows its gross, labelled «Bruto», next to its revenue", () => {
    render(<MarginTree margin={RESPONSE} />);

    const table = flightsTable(2);
    const headers = headersOf(table);
    expect(headers).toContain("Venta objetivo");
    expect(headers).not.toContain("Venta contratada");
    expect(headers.indexOf("Bruto")).toBe(headers.indexOf("Facturable") + 1);
    expect(plain(cellOf(table, "Venta objetivo"))).toBe(`5.000,00${SPACE}€`);
    expect(plain(cellOf(table, "Facturable"))).toBe(`4.400,00${SPACE}€`);
    expect(plain(cellOf(table, "Bruto"))).toBe(`5.500,00${SPACE}€`);
    expect(plain(cellOf(table, "% de margen"))).toContain("62,50");
  });

  it("tags the two warnings where raised, each saying in Spanish what to check", () => {
    render(<MarginTree margin={RESPONSE} />);

    const warnings = cellOf(flightsTable(2), "Avisos");
    const gross = within(warnings).getByText("Bruto distinto del gasto");
    const dataCost = within(warnings).getByText("Coste de datos");
    expect(gross).toHaveAccessibleDescription(
      "El bruto (impresiones servidas por el CPM de la línea) se aleja más de un 1 % del gasto del comprador que "
      + "comunica el DSP. Revisa el CPM de la línea y el paquete vinculado.",
    );
    expect(dataCost).toHaveAccessibleDescription(
      "El DSP comunica costes de datos de terceros o de audiencia en este flight. No se restan del margen: revisa "
      + "con el comprador si deben repercutirse.",
    );
  });

  it("says «Venta objetivo» and shows «Bruto» among the figures of its line", () => {
    render(<MarginTree margin={RESPONSE} />);

    const lineGroup = screen.getByRole("group", { name: "Línea 2 de Alfa" });
    expect(figure(lineGroup, "Venta objetivo")).toBe(`5.000,00${SPACE}€`);
    expect(figure(lineGroup, "Bruto")).toBe(`5.500,00${SPACE}€`);
    expect(figure(lineGroup, "Venta contratada")).toBeNull();
  });

  it("counts the two warnings in the totals of the line, the campaign and the period", () => {
    render(<MarginTree margin={RESPONSE} />);

    for (const container of [
      screen.getByRole("group", { name: "Línea 2 de Alfa" }).querySelector("summary")!,
      screen.getByRole("group", { name: "Campaña Alfa" }).querySelector("summary")!,
      screen.getByRole("region", { name: "Totales del periodo" }),
    ]) {
      expect(within(container as HTMLElement).getByText("Bruto distinto del gasto: 1 flight")).toBeInTheDocument();
      expect(within(container as HTMLElement).getByText("Coste de datos: 1 flight")).toBeInTheDocument();
    }
  });
});

describe("a committed flight in the margin", () => {
  it("keeps «Venta contratada» and shows no gross", () => {
    render(<MarginTree margin={RESPONSE} />);

    const table = flightsTable(1);
    expect(headersOf(table)).toContain("Venta contratada");
    expect(headersOf(table)).not.toContain("Bruto");
    expect(headersOf(table)).not.toContain("Venta objetivo");
    const lineGroup = screen.getByRole("group", { name: "Línea 1 de Alfa" });
    expect(figure(lineGroup, "Venta contratada")).toBe(`3.631,01${SPACE}€`);
    expect(figure(lineGroup, "Bruto")).toBeNull();
    expect(within(cellOf(table, "Avisos")).queryByText("Bruto distinto del gasto")).not.toBeInTheDocument();
  });

  it("shows the gross of the target line among the figures of a campaign of both commitments", () => {
    render(<MarginTree margin={RESPONSE} />);

    const campaignSummary = screen.getByRole("group", { name: "Campaña Alfa" }).querySelector("summary") as HTMLElement;
    expect(figure(campaignSummary, "Bruto")).toBe(`5.500,00${SPACE}€`);
    expect(figure(campaignSummary, "Venta contratada")).toBe(`3.631,01${SPACE}€`);
  });
});
