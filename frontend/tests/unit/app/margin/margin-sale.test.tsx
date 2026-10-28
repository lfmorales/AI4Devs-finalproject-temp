import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";

import MarginPage from "@/app/(authenticated)/margin/page";
import { createApiClient } from "@/lib/api/client";
import { getMargin } from "@/lib/api/margin";
import { installRoutes, plain, renderAuthenticated, reply } from "../../../helpers/api-pages";
import { campaign, flight, line, margin, totals } from "../../../helpers/margin-data";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const SPACE = " ";
const HELP = "Ingreso proporcional a los días transcurridos del flight; en un flight cerrado es igual a la venta contratada.";

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

function figure(container: HTMLElement, label: string): string {
  const labelElement = within(container).getAllByText(label, { selector: ".figure-label" })[0]!;
  return plain(labelElement.nextElementSibling);
}

const RUNNING = flight({
  flight_id: 7, period_month: 8, state: "running", provisional: true, flight_start: "2026-08-01", flight_end: "2026-08-14",
  revenue: "1000.00", contracted_revenue: "1400.00", accrued_days: 10, window_days: 14,
  delivered_impressions: 250000, contracted_impressions: 400000,
});
const CLOSED = flight({
  flight_id: 6, period_month: 7, state: "closed", flight_start: "2026-07-01", flight_end: "2026-07-31",
  revenue: "3000.00", contracted_revenue: "3000.00", accrued_days: 31, window_days: 31,
  delivered_impressions: 1234567, contracted_impressions: 1500000,
});
const PENDING = flight({
  flight_id: 5, period_month: 6, state: "pending_close", flight_start: "2026-06-01", flight_end: "2026-06-30",
  revenue: "2000.00", contracted_revenue: "2000.00", accrued_days: 30, window_days: 30,
});

const WORLD = margin({
  campaigns: [campaign({
    campaign_id: 1, name: "Alfa",
    totals: totals({ revenue: "6000.00", contracted_revenue: "6400.00", delivered_impressions: 2000000, contracted_impressions: 2900000 }),
    lines: [line({
      campaign_line_id: 10, line_number: 1,
      totals: totals({ revenue: "6000.00", contracted_revenue: "6400.00", delivered_impressions: 1484567, contracted_impressions: 1900000 }),
      flights: [CLOSED, RUNNING, PENDING],
    })],
  })],
  totals: totals({ revenue: "6000.00", contracted_revenue: "6400.00", delivered_impressions: 2000000, contracted_impressions: 2900000 }),
});

async function renderWorld(body = WORLD) {
  installRoutes({ "GET /margin": () => reply(200, body) });
  renderAuthenticated(<MarginPage />);
  return screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
}

function rowOf(table: HTMLElement, period: string): HTMLElement {
  return within(table).getAllByRole("row").find((row) => within(row).queryByText(period) !== null)!;
}

describe("the fields of the API, through the real client", () => {
  it("keeps the new fields as received", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(WORLD), { status: 200, headers: { "Content-Type": "application/json" } })));

    const result = await getMargin(createApiClient({ baseUrl: "http://api" }), {});

    const running = result.campaigns[0]!.lines[0]!.flights[1]!;
    expect(running).toMatchObject({ contracted_revenue: "1400.00", accrued_days: 10, window_days: 14, delivered_impressions: 250000, contracted_impressions: 400000 });
    expect(result.totals).toMatchObject({ contracted_revenue: "6400.00", delivered_impressions: 2000000, contracted_impressions: 2900000 });
    expect(result.campaigns[0]!.totals.contracted_revenue).toBe("6400.00");
    expect(result.campaigns[0]!.lines[0]!.totals.contracted_revenue).toBe("6400.00");
  });
});

describe("the contracted sale and the accrued revenue", () => {
  it("puts «Venta contratada» immediately to the left of «Devengado» in the flights table", async () => {
    const table = await renderWorld();

    const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
    expect(headers.indexOf("Venta contratada")).toBeGreaterThan(-1);
    expect(headers.indexOf("Devengado")).toBe(headers.indexOf("Venta contratada") + 1);
    expect(headers).not.toContain("Ingreso");
  });

  it("shows the contracted sale of every flight, formatted, beside its accrued revenue", async () => {
    const table = await renderWorld();

    const cells = within(rowOf(table, "08/2026")).getAllByRole("cell").map((cell) => plain(cell));
    expect(cells.slice(3, 5)).toEqual([`1.400,00${SPACE}€`, `1.000,00${SPACE}€`]);
  });

  it("shows the contracted sale among the figures of the line, the campaign and the period", async () => {
    await renderWorld();

    const period = screen.getByRole("region", { name: "Totales del periodo" });
    const group = screen.getByRole("group", { name: "Campaña Alfa" });
    const lineGroup = screen.getByRole("group", { name: "Línea 1 de Alfa" });
    for (const container of [period, group, lineGroup]) {
      expect(figure(container, "Venta contratada")).toBe(`6.400,00${SPACE}€`);
      expect(figure(container, "Devengado")).toBe(`6.000,00${SPACE}€`);
    }
    expect(screen.queryByText("Ingreso", { selector: ".figure-label" })).not.toBeInTheDocument();
  });

  it("explains «Devengado» in the column header with an accessible description", async () => {
    const table = await renderWorld();

    const header = within(table).getByRole("columnheader", { name: "Devengado" });
    expect(header).toHaveAccessibleDescription(HELP);
  });

  it("explains «Devengado» among the figures too", async () => {
    await renderWorld();

    const period = screen.getByRole("region", { name: "Totales del periodo" });
    const label = within(period).getByText("Devengado", { selector: ".figure-label" });
    expect(label).toHaveAccessibleDescription(HELP);
  });

  it("shows a contracted sale of long precision whole, at every level", async () => {
    const long = "12345678901234.56";
    const body = margin({
      campaigns: [campaign({
        name: "Alfa", totals: totals({ contracted_revenue: long }),
        lines: [line({ line_number: 1, totals: totals({ contracted_revenue: long }), flights: [flight({ contracted_revenue: long })] })],
      })],
      totals: totals({ contracted_revenue: long }),
    });
    const table = await renderWorld(body);

    const expected = `12.345.678.901.234,56${SPACE}€`;
    expect(figure(screen.getByRole("region", { name: "Totales del periodo" }), "Venta contratada")).toBe(expected);
    expect(figure(screen.getByRole("group", { name: "Campaña Alfa" }), "Venta contratada")).toBe(expected);
    expect(figure(screen.getByRole("group", { name: "Línea 1 de Alfa" }), "Venta contratada")).toBe(expected);
    expect(plain(within(within(table).getAllByRole("row")[1]!).getAllByRole("cell")[3]!)).toBe(expected);
  });

  it("shows «0,00 €» for a line without a price", async () => {
    const free = flight({ zero_sale: true, revenue: "0.00", contracted_revenue: "0.00", margin_pct: null });
    const body = margin({
      campaigns: [campaign({
        name: "Alfa", totals: totals({ revenue: "0.00", contracted_revenue: "0.00" }),
        lines: [line({ line_number: 1, zero_sale: true, totals: totals({ revenue: "0.00", contracted_revenue: "0.00" }), flights: [free] })],
      })],
      totals: totals({ revenue: "0.00", contracted_revenue: "0.00" }),
    });
    const table = await renderWorld(body);

    const cells = within(within(table).getAllByRole("row")[1]!).getAllByRole("cell").map((cell) => plain(cell));
    expect(cells.slice(3, 5)).toEqual([`0,00${SPACE}€`, `0,00${SPACE}€`]);
    expect(figure(screen.getByRole("group", { name: "Línea 1 de Alfa" }), "Venta contratada")).toBe(`0,00${SPACE}€`);
  });
});

describe("the legends of days and delivery", () => {
  it("says «10 de 14 días» on a running flight, with the days as received", async () => {
    const table = await renderWorld();

    expect(within(rowOf(table, "08/2026")).getByText("10 de 14 días")).toBeInTheDocument();
  });

  it("omits the days on a closed flight and on one pending close", async () => {
    const table = await renderWorld();

    expect(within(rowOf(table, "07/2026")).queryByText(/días/)).not.toBeInTheDocument();
    expect(within(rowOf(table, "06/2026")).queryByText(/días/)).not.toBeInTheDocument();
    expect(within(table).getAllByText(/ de \d+ días/)).toHaveLength(1);
  });

  it("says how much was delivered of the contracted impressions on every flight", async () => {
    const table = await renderWorld();

    expect(within(rowOf(table, "08/2026")).getByText("Entregado 250.000 de 400.000 impresiones")).toBeInTheDocument();
    expect(within(rowOf(table, "07/2026")).getByText("Entregado 1.234.567 de 1.500.000 impresiones")).toBeInTheDocument();
    expect(within(rowOf(table, "06/2026")).getByText("Entregado 700.000 de 726.202 impresiones")).toBeInTheDocument();
  });

  it("says it also on the line, the campaign and the period, with the sums as received", async () => {
    await renderWorld();

    const period = screen.getByRole("region", { name: "Totales del periodo" });
    const group = screen.getByRole("group", { name: "Campaña Alfa" });
    const lineGroup = screen.getByRole("group", { name: "Línea 1 de Alfa" });
    expect(within(period).getByText("Entregado 2.000.000 de 2.900.000 impresiones")).toBeInTheDocument();
    expect(within(group).getAllByText("Entregado 2.000.000 de 2.900.000 impresiones")).not.toHaveLength(0);
    expect(within(lineGroup).getAllByText("Entregado 1.484.567 de 1.900.000 impresiones")).not.toHaveLength(0);
  });
});
