import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarginTree } from "@/features/margin/MarginTree";
import type { FlightMargin } from "@/lib/api/margin";
import { campaign, deliveryChange, flight, line, margin, totals } from "../../../helpers/margin-data";
import { plain } from "../../../helpers/api-pages";

const SPACE = " "; // plain() turns the no-break space of the euro amounts into a plain one

function figureLabels(container: HTMLElement): string[] {
  return within(container).queryAllByText(/Facturable|Devengado/, { selector: ".figure-label" }).map((label) => plain(label));
}

function headers(lineNumber: number, campaignName = "Alfa"): string[] {
  const table = screen.getByRole("table", { name: `Flights de la línea ${lineNumber} de ${campaignName}` });
  return within(table).getAllByRole("columnheader").map((header) => plain(header));
}

function treeOf(...lines: ReturnType<typeof line>[]) {
  return margin({ campaigns: [campaign({ name: "Alfa", lines })] });
}

describe("the billing labels of the margin (committed-billing-and-review)", () => {
  it("labels an ended flight «Facturable», and its line, campaign and period too", () => {
    const { container } = render(<MarginTree margin={treeOf(line({ flights: [flight({ state: "pending_close" })] }))} />);

    expect(headers(1)).toContain("Facturable");
    expect(headers(1)).not.toContain("Facturable a la fecha");
    expect(figureLabels(screen.getByRole("region", { name: "Totales del periodo" }))).toEqual(["Facturable"]);
    expect(figureLabels(screen.getByRole("group", { name: "Campaña Alfa" })).every((label) => label === "Facturable")).toBe(true);
    expect(container.textContent).not.toContain("Devengado");
  });

  it("labels a running flight «Facturable a la fecha», and every level that includes it", () => {
    const { container } = render(<MarginTree margin={treeOf(line({ flights: [flight({ state: "running" })] }))} />);

    expect(headers(1)).toContain("Facturable a la fecha");
    expect(figureLabels(screen.getByRole("region", { name: "Totales del periodo" }))).toEqual(["Facturable a la fecha"]);
    const levels = figureLabels(screen.getByRole("group", { name: "Campaña Alfa" }));
    expect(levels.length).toBeGreaterThanOrEqual(2);
    expect(levels.every((label) => label === "Facturable a la fecha")).toBe(true);
    expect(container.textContent).not.toContain("Devengado");
  });

  it("labels each line by its own flights, and the campaign and the period by any running flight below", () => {
    const ended = line({ campaign_line_id: 10, line_number: 1, flights: [flight({ flight_id: 1, state: "closed" })] });
    const running = line({ campaign_line_id: 20, line_number: 2, flights: [flight({ flight_id: 2, state: "running" })] });

    render(<MarginTree margin={treeOf(ended, running)} />);

    expect(headers(1)).toContain("Facturable");
    expect(headers(2)).toContain("Facturable a la fecha");
    expect(figureLabels(screen.getByRole("group", { name: "Línea 1 de Alfa" }))[0]).toBe("Facturable");
    expect(figureLabels(screen.getByRole("group", { name: "Línea 2 de Alfa" }))[0]).toBe("Facturable a la fecha");
    expect(figureLabels(screen.getByRole("region", { name: "Totales del periodo" }))).toEqual(["Facturable a la fecha"]);
  });

  it("shows the billing of a flight as the server sent it", () => {
    render(<MarginTree margin={treeOf(line({ flights: [flight({ state: "closed", revenue: "3500.00" })], totals: totals({ revenue: "3500.00" }) }))} />);

    const table = screen.getByRole("table", { name: "Flights de la línea 1 de Alfa" });
    const index = headers(1).indexOf("Facturable");
    expect(plain(within(within(table).getAllByRole("row")[1]!).getAllByRole("cell")[index]!)).toBe(`3.500,00${SPACE}€`);
  });

  it.each([
    ["custom", true], ["contracted", true], ["delivered", true], ["minimum", false], ["reported", false], [null, false],
  ] as [FlightMargin["billing_basis"], boolean][])("labels a flight with the basis %s «Ajustado»: %s", (basis, adjusted) => {
    render(<MarginTree margin={treeOf(line({ flights: [flight({ billing_basis: basis })] }))} />);

    const table = screen.getByRole("table", { name: "Flights de la línea 1 de Alfa" });
    expect(within(table).queryByText("Ajustado") !== null).toBe(adjusted);
  });

  it("shows the billable volume and billing differences of a changed closed flight, as sent", () => {
    const changed = flight({
      delivery_changed: true,
      delivery_change: deliveryChange({
        delivered_difference: "500000.0000", delivered_impressions_difference: 500000, media_cost_difference: "1800.00",
        billable_difference: "300000.0000", billing_difference: "1500.00", current_margin: "-75.00", margin_difference: "-800.00",
      }),
    });

    render(<MarginTree margin={treeOf(line({ flights: [changed] }))} />);

    const table = screen.getByRole("table", { name: "Flights de la línea 1 de Alfa" });
    expect(plain(within(table).getByText("Diferencia de volumen facturable").parentElement)).toBe(
      "Diferencia de volumen facturable 300.000 impresiones",
    );
    expect(plain(within(table).getByText("Diferencia de facturación").parentElement)).toBe(
      `Diferencia de facturación 1.500,00${SPACE}€`,
    );
  });

  it("leaves out the billing differences a target flight or an old closing does not have", () => {
    const changed = flight({
      delivery_changed: true,
      delivery_change: deliveryChange({ billable_difference: null, billing_difference: null, margin_difference: "5.00" }),
    });

    render(<MarginTree margin={treeOf(line({ flights: [changed] }))} />);

    expect(screen.queryByText("Diferencia de volumen facturable")).not.toBeInTheDocument();
    expect(screen.queryByText("Diferencia de facturación")).not.toBeInTheDocument();
  });
});
