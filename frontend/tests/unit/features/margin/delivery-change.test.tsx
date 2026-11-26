import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarginTree } from "@/features/margin/MarginTree";
import type { DeliveryChange } from "@/lib/api/margin";
import { campaign, deliveryChange, flight, line, margin, totals } from "../../../helpers/margin-data";
import { plain } from "../../../helpers/api-pages";

const SPACE = " "; // plain() turns the no-break space of the euro amounts into a plain one
const HELP =
  "La entrega guardada de este flight cambió después del cierre del mes: el DSP reexpresó sus cifras o se desvinculó "
  + "la línea. El margen cerrado no cambia. El margen informativo usa la extraprima y las tarifas del cierre con la "
  + "entrega de hoy. Revisa con el DSP si la nueva entrega es correcta. Si lo es, la diferencia se regulariza fuera de "
  + "la aplicación: el mes cerrado no se reabre.";
const NOTE = "Margen informativo con la extraprima y las tarifas del cierre: solo cambia la entrega y no suma en ningún total.";

// The committed example of the specification as the API sends it: closed at 1,850.00 €, restated on 28 November.
const COMMITTED_CHANGE: DeliveryChange = deliveryChange({
  delivered_difference: "500000.0000", delivered_impressions_difference: 500000, media_cost_difference: "1800.00",
  current_margin: "-450.00", margin_difference: "-2300.00",
});
const COMMITTED_FLIGHT = flight({
  flight_id: 31, revenue: "5000.00", contracted_revenue: "5000.00", media_cost: "1200.00", rebate: "1250.00",
  platform_cost: "700.00", margin: "1850.00", margin_pct: "37.00", delivery_changed: true,
  delivery_change: COMMITTED_CHANGE,
});
// The Deal example: a target flight whose DSP restated its revenue and spend.
const TARGET_FLIGHT = flight({
  flight_id: 32, revenue: "4400.00", gross_revenue: "5500.00", margin: "2750.00", volume_commitment: "target",
  delivery_changed: true,
  delivery_change: deliveryChange({
    delivered_difference: "200000.0000", delivered_impressions_difference: 200000,
    reported_revenue_difference: "800.00", buyer_spend_difference: "1000.00", current_margin: "3350.00",
    margin_difference: "600.00",
  }),
});
const UNCHANGED_FLIGHT = flight({ flight_id: 33, delivery_changed: false, delivery_change: deliveryChange() });
const CHANGED_TOTALS = totals({ delivery_changed_count: 1 });

function tree(...flights: ReturnType<typeof flight>[]) {
  const counted = totals({ delivery_changed_count: flights.filter((f) => f.delivery_changed).length });
  return margin({
    campaigns: [campaign({ name: "Alfa", lines: [line({ flights, totals: counted })], totals: counted })],
    totals: counted,
  });
}

function warningsOf(flightIndex = 0): HTMLElement {
  const table = screen.getByRole("table", { name: "Flights de la línea 1 de Alfa" });
  const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
  const row = within(table).getAllByRole("row")[flightIndex + 1]!;
  return within(row).getAllByRole("cell")[headers.indexOf("Avisos")]!;
}

function detail(container: HTMLElement, label: string): string | null {
  const labels = within(container).queryAllByText(label, { selector: ".change-label" });
  if (labels.length === 0) return null;
  return plain(labels[0]!.parentElement!.querySelector(".change-value"));
}

describe("a closed flight whose delivery changed after closing", () => {
  it("is tagged «Cambió tras el cierre», saying that the closed margin does not move and what to check", () => {
    render(<MarginTree margin={tree(COMMITTED_FLIGHT)} />);

    const tag = within(warningsOf()).getByText("Cambió tras el cierre");
    expect(tag).toHaveAccessibleDescription(HELP);
    expect(tag).toHaveAttribute("title", HELP);
  });

  it("shows its current margin and its differences as the API sent them, with the note on the closing's rates", () => {
    render(<MarginTree margin={tree(COMMITTED_FLIGHT)} />);
    const warnings = warningsOf();

    expect(detail(warnings, "Margen informativo")).toBe(`-450,00${SPACE}€`);
    expect(detail(warnings, "Diferencia de margen")).toBe(`-2.300,00${SPACE}€`);
    expect(detail(warnings, "Diferencia de entrega")).toBe("500.000 impresiones");
    expect(detail(warnings, "Diferencia de impresiones")).toBe("500.000");
    expect(detail(warnings, "Diferencia de coste de medios")).toBe(`1.800,00${SPACE}€`);
    expect(within(warnings).getByText(NOTE)).toBeInTheDocument();
  });

  it("keeps showing the closed figures, not the current ones", () => {
    render(<MarginTree margin={tree(COMMITTED_FLIGHT)} />);

    const row = warningsOf().closest("tr")!;
    expect(plain(row)).toContain(`1.850,00${SPACE}€`);
    expect(within(row).getAllByText(`-450,00${SPACE}€`)).toHaveLength(1);
  });

  it("shows the revenue and spend differences of a target flight only", () => {
    render(<MarginTree margin={tree(TARGET_FLIGHT, COMMITTED_FLIGHT)} />);

    expect(detail(warningsOf(0), "Diferencia de ingreso comunicado")).toBe(`800,00${SPACE}€`);
    expect(detail(warningsOf(0), "Diferencia de gasto del comprador")).toBe(`1.000,00${SPACE}€`);
    expect(detail(warningsOf(0), "Margen informativo")).toBe(`3.350,00${SPACE}€`);
    expect(detail(warningsOf(1), "Diferencia de ingreso comunicado")).toBeNull();
    expect(detail(warningsOf(1), "Diferencia de gasto del comprador")).toBeNull();
  });

  it("shows OTS in the unit of the flight", () => {
    const dooh = flight({
      delivery_metric: "ots", delivery_changed: true,
      delivery_change: deliveryChange({ delivered_difference: "3000.5000", current_margin: "823.26" }),
    });
    render(<MarginTree margin={tree(dooh)} />);

    expect(detail(warningsOf(), "Diferencia de entrega")).toBe("3.000,5 OTS");
  });
});

describe("a flight whose delivery did not change", () => {
  it("shows no label and no differences, closed or not", () => {
    render(<MarginTree margin={tree(UNCHANGED_FLIGHT, flight({ flight_id: 34, state: "running" }))} />);

    for (const index of [0, 1]) {
      expect(within(warningsOf(index)).queryByText("Cambió tras el cierre")).not.toBeInTheDocument();
      expect(detail(warningsOf(index), "Margen informativo")).toBeNull();
    }
    expect(screen.queryByText(/Cambió tras el cierre/)).not.toBeInTheDocument();
  });
});

describe("the count of changed flights", () => {
  it("reaches the line, the campaign and the period like the other warnings", () => {
    render(<MarginTree margin={margin({
      campaigns: [campaign({ name: "Alfa", lines: [line({ flights: [COMMITTED_FLIGHT], totals: CHANGED_TOTALS })], totals: CHANGED_TOTALS })],
      totals: totals({ delivery_changed_count: 2 }),
    })} />);

    const period = screen.getByRole("region", { name: "Totales del periodo" });
    expect(within(period).getByText("Cambió tras el cierre: 2 flights")).toBeInTheDocument();
    const campaignLevel = screen.getByRole("group", { name: "Campaña Alfa" });
    const lineLevel = screen.getByRole("group", { name: "Línea 1 de Alfa" });
    expect(within(lineLevel.querySelector("summary")!).getByText("Cambió tras el cierre: 1 flight")).toBeInTheDocument();
    expect(within(campaignLevel.querySelector("summary")!).getByText("Cambió tras el cierre: 1 flight")).toBeInTheDocument();
  });
});
