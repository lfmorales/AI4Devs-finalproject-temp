import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import MarginPage from "@/app/(authenticated)/margin/page";
import { installRoutes, plain, renderAuthenticated, reply } from "../../../helpers/api-pages";
import { campaign, flight, line, margin, totals } from "../../../helpers/margin-data";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

// plain() turns every kind of space, the no-break one included, into a plain space.
const SPACE = " ";
const NOTICE = "Las cifras provisionales pueden cambiar hasta el cierre del mes";

beforeEach(() => vi.clearAllMocks());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

/** The value shown next to a figure's label inside a summary or a region. */
function figure(container: HTMLElement, label: string): string {
  // A group also holds the levels below it: its own summary comes first.
  const labelElement = within(container).getAllByText(label, { selector: ".figure-label" })[0]!;
  return plain(labelElement.nextElementSibling);
}

function cellsOf(row: HTMLElement): string[] {
  return within(row).getAllByRole("cell").map((cell) => plain(cell));
}

const TWO_LINES = margin({
  campaigns: [
    campaign({
      campaign_id: 1,
      name: "Alfa",
      totals: totals({ revenue: "9000.00", media_cost: "3000.00", rebate: "1500.00", platform_cost: "1000.00", margin: "3500.00", margin_pct: "38.89", flights_counted: 3 }),
      lines: [
        line({
          campaign_line_id: 10,
          line_number: 1,
          channel: "Directo",
          scope: "national",
          totals: totals({ revenue: "6000.00", media_cost: "2000.00", rebate: "1000.00", platform_cost: "700.00", margin: "2300.00", margin_pct: "38.33", flights_counted: 2 }),
          flights: [
            flight({ flight_id: 100, period_month: 7, flight_start: "2026-07-01", flight_end: "2026-07-31", revenue: "3000.00", media_cost: "1000.00", rebate: "500.00", platform_cost: "350.00", margin: "1150.00", margin_pct: "38.33" }),
            flight({ flight_id: 101, period_month: 8, flight_start: "2026-08-01", flight_end: "2026-08-31", revenue: "3000.00", media_cost: "1000.00", rebate: "500.00", platform_cost: "350.00", margin: "1150.00", margin_pct: "38.33" }),
          ],
        }),
        line({
          campaign_line_id: 11,
          line_number: 2,
          channel: "Deal",
          scope: "international",
          totals: totals({ revenue: "3000.00", media_cost: "1000.00", rebate: "500.00", platform_cost: "300.00", margin: "1200.00", margin_pct: "40.00", flights_counted: 1 }),
          flights: [flight({ flight_id: 102, revenue: "3000.00", media_cost: "1000.00", rebate: "500.00", platform_cost: "300.00", margin: "1200.00", margin_pct: "40.00" })],
        }),
      ],
    }),
  ],
  totals: totals({ revenue: "9000.00", media_cost: "3000.00", rebate: "1500.00", platform_cost: "1000.00", margin: "3500.00", margin_pct: "38.89", flights_counted: 3 }),
});

describe("the margin page: hierarchy and totals", () => {
  it("shows the totals of the period, then each campaign with its totals", async () => {
    installRoutes({ "GET /margin": () => reply(200, TWO_LINES) });

    renderAuthenticated(<MarginPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Margen" })).toBeInTheDocument();
    const period = await screen.findByRole("region", { name: "Totales del periodo" });
    expect(figure(period, "Ingreso")).toBe(`9.000,00${SPACE}€`);
    expect(figure(period, "Coste de medios")).toBe(`3.000,00${SPACE}€`);
    expect(figure(period, "Rebate")).toBe(`1.500,00${SPACE}€`);
    expect(figure(period, "Coste de plataforma")).toBe(`1.000,00${SPACE}€`);
    expect(figure(period, "Margen")).toBe(`3.500,00${SPACE}€`);
    expect(figure(period, "% de margen")).toBe(`38,89${SPACE}%`);
    const group = screen.getByRole("group", { name: "Campaña Alfa" });
    expect(figure(group, "Ingreso")).toBe(`9.000,00${SPACE}€`);
  });

  it("shows each line of the campaign with its own totals", async () => {
    installRoutes({ "GET /margin": () => reply(200, TWO_LINES) });

    renderAuthenticated(<MarginPage />);

    const first = await screen.findByRole("group", { name: "Línea 1 de Alfa" });
    const second = screen.getByRole("group", { name: "Línea 2 de Alfa" });
    expect(figure(first, "Ingreso")).toBe(`6.000,00${SPACE}€`);
    expect(figure(first, "Margen")).toBe(`2.300,00${SPACE}€`);
    expect(figure(first, "% de margen")).toBe(`38,33${SPACE}%`);
    expect(figure(second, "Ingreso")).toBe(`3.000,00${SPACE}€`);
    expect(within(first).getByText(/Directo/)).toBeInTheDocument();
    expect(within(second).getByText(/Deal/)).toBeInTheDocument();
  });

  it("lists the flights of a line in a table with the six figures, the period, the window and the state", async () => {
    installRoutes({ "GET /margin": () => reply(200, TWO_LINES) });

    renderAuthenticated(<MarginPage />);

    const table = await screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
    const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
    expect(headers).toEqual([
      "Periodo", "Ventana", "Estado", "Ingreso", "Coste de medios", "Rebate", "Coste de plataforma", "Margen", "% de margen", "Avisos",
    ]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(cellsOf(rows[0]!).slice(0, 9)).toEqual([
      "07/2026", "2026-07-01 – 2026-07-31", "Cerrado",
      `3.000,00${SPACE}€`, `1.000,00${SPACE}€`, `500,00${SPACE}€`, `350,00${SPACE}€`, `1.150,00${SPACE}€`, `38,33${SPACE}%`,
    ]);
  });

  it("opens and closes the campaigns and the lines with the native details elements, without libraries", async () => {
    installRoutes({ "GET /margin": () => reply(200, TWO_LINES) });
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);

    const group = await screen.findByRole("group", { name: "Campaña Alfa" });
    expect(group.tagName).toBe("DETAILS");
    expect(within(group).getAllByText("Alfa")[0]!.closest("summary")).not.toBeNull();
    expect(group).not.toHaveAttribute("open");
    await user.click(group.querySelector("summary")!);
    expect(group).toHaveAttribute("open");
    await user.click(group.querySelector("summary")!);
    expect(group).not.toHaveAttribute("open");
  });

  it("shows the campaigns in the order the server gave them", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin({
      campaigns: [campaign({ campaign_id: 2, name: "Zeta" }), campaign({ campaign_id: 1, name: "Alfa" })],
    })) });

    renderAuthenticated(<MarginPage />);

    await screen.findByRole("group", { name: "Campaña Zeta" });
    const names = screen.getAllByRole("group", { name: /^Campaña / }).map((g) => g.getAttribute("aria-label"));
    expect(names).toEqual(["Campaña Zeta", "Campaña Alfa"]);
  });
});

describe("the state of each flight and the provisional notice", () => {
  const STATES = margin({
    campaigns: [campaign({ name: "Alfa", lines: [line({
      line_number: 1,
      totals: totals({ provisional: true }),
      flights: [
        flight({ flight_id: 1, state: "closed", provisional: false }),
        flight({ flight_id: 2, state: "pending_close", provisional: true }),
        flight({ flight_id: 3, state: "running", provisional: true }),
      ],
    })] })],
  });

  it("tags each flight with the text of its state", async () => {
    installRoutes({ "GET /margin": () => reply(200, STATES) });

    renderAuthenticated(<MarginPage />);

    const table = await screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
    const states = within(table).getAllByRole("row").slice(1).map((row) => cellsOf(row)[2]);
    expect(states).toEqual(["Cerrado", "Pendiente de cierre", "En curso (provisional)"]);
  });

  it("always shows the notice that provisional figures can change until the month is closed", async () => {
    installRoutes({ "GET /margin": () => reply(200, STATES) });

    renderAuthenticated(<MarginPage />);

    expect(await screen.findByText(NOTICE)).toBeInTheDocument();
  });

  it("shows the notice even when every flight is closed", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin()) });

    renderAuthenticated(<MarginPage />);

    expect(await screen.findByText(NOTICE)).toBeInTheDocument();
  });

  it("marks the line, the campaign and the period when their totals include provisional figures", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin({
      campaigns: [campaign({ name: "Alfa", totals: totals({ provisional: true }), lines: [line({ totals: totals({ provisional: true }) })] })],
      totals: totals({ provisional: true }),
    })) });

    renderAuthenticated(<MarginPage />);

    const campaignGroup = await screen.findByRole("group", { name: "Campaña Alfa" });
    const lineGroup = screen.getByRole("group", { name: "Línea 1 de Alfa" });
    const period = screen.getByRole("region", { name: "Totales del periodo" });
    for (const element of [campaignGroup, lineGroup, period]) {
      expect(within(element).getAllByText("Incluye cifras provisionales").length).toBeGreaterThan(0);
    }
  });

  it("does not mark a level whose figures are all closed", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin()) });

    renderAuthenticated(<MarginPage />);

    await screen.findByRole("group", { name: "Campaña Campaña A" });
    expect(screen.queryByText("Incluye cifras provisionales")).not.toBeInTheDocument();
  });
});

describe("negative margin and zero sale", () => {
  const FLAGGED = margin({
    campaigns: [campaign({
      name: "Alfa",
      zero_sale: true,
      totals: totals({ below_cost_count: 2, zero_sale_count: 1, margin: "-120.00", margin_pct: null, revenue: "0.00" }),
      lines: [line({
        line_number: 1,
        zero_sale: true,
        totals: totals({ below_cost_count: 2, zero_sale_count: 1, margin: "-120.00", margin_pct: null, revenue: "0.00" }),
        flights: [
          flight({ flight_id: 1, below_cost: true, margin: "-70.00", margin_pct: "-7.00" }),
          flight({ flight_id: 2, below_cost: true, zero_sale: true, revenue: "0.00", margin: "-50.00", margin_pct: null }),
          flight({ flight_id: 3 }),
        ],
      })],
    })],
    totals: totals({ below_cost_count: 2, zero_sale_count: 1, margin: "-120.00", margin_pct: null, revenue: "0.00" }),
  });

  it("labels a flight with a negative margin 'Margen negativo' and a flight without a price 'Sin venta'", async () => {
    installRoutes({ "GET /margin": () => reply(200, FLAGGED) });

    renderAuthenticated(<MarginPage />);

    const table = await screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
    const flags = within(table).getAllByRole("row").slice(1).map((row) => cellsOf(row)[9]);
    expect(flags).toEqual(["Margen negativo", "Margen negativo Sin venta", ""]);
  });

  it("shows how many flights are in each case on the line, the campaign and the period", async () => {
    installRoutes({ "GET /margin": () => reply(200, FLAGGED) });

    renderAuthenticated(<MarginPage />);

    const campaignGroup = await screen.findByRole("group", { name: "Campaña Alfa" });
    const lineGroup = screen.getByRole("group", { name: "Línea 1 de Alfa" });
    const period = screen.getByRole("region", { name: "Totales del periodo" });
    for (const element of [campaignGroup, lineGroup, period]) {
      expect(within(element).getAllByText("Margen negativo: 2 flights").length).toBeGreaterThan(0);
      expect(within(element).getAllByText("Sin venta: 1 flight").length).toBeGreaterThan(0);
    }
  });

  it("keeps their true value in the totals: nothing is left out or added in the browser", async () => {
    installRoutes({ "GET /margin": () => reply(200, FLAGGED) });

    renderAuthenticated(<MarginPage />);

    const period = await screen.findByRole("region", { name: "Totales del periodo" });
    expect(figure(period, "Margen")).toBe(`-120,00${SPACE}€`);
  });

  it("shows no count where there is none", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin()) });

    renderAuthenticated(<MarginPage />);

    await screen.findByRole("group", { name: "Campaña Campaña A" });
    expect(screen.queryByText(/Margen negativo:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sin venta:/)).not.toBeInTheDocument();
  });
});

describe("amounts and percentages", () => {
  it("shows an amount a floating-point number cannot hold exactly, whole", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin({
      totals: totals({ revenue: "12345678901234.56", margin: "-9007199254740993.01" }),
    })) });

    renderAuthenticated(<MarginPage />);

    const period = await screen.findByRole("region", { name: "Totales del periodo" });
    expect(figure(period, "Ingreso")).toBe(`12.345.678.901.234,56${SPACE}€`);
    expect(figure(period, "Margen")).toBe(`-9.007.199.254.740.993,01${SPACE}€`);
  });

  it("shows a dash for a margin percentage that is null, at the flight and at the totals", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin({
      campaigns: [campaign({ name: "Alfa", totals: totals({ margin_pct: null }), lines: [line({
        totals: totals({ margin_pct: null }), flights: [flight({ margin_pct: null })],
      })] })],
      totals: totals({ margin_pct: null }),
    })) });

    renderAuthenticated(<MarginPage />);

    const period = await screen.findByRole("region", { name: "Totales del periodo" });
    expect(figure(period, "% de margen")).toBe("—");
    expect(figure(screen.getByRole("group", { name: "Campaña Alfa" }), "% de margen")).toBe("—");
    const table = screen.getByRole("table", { name: "Flights de la línea 1 de Alfa" });
    expect(cellsOf(within(table).getAllByRole("row")[1]!)[8]).toBe("—");
  });

  it("shows the percentage exactly as the server computed it, with its sign", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin({ totals: totals({ margin_pct: "-5.00" }) })) });

    renderAuthenticated(<MarginPage />);

    const period = await screen.findByRole("region", { name: "Totales del periodo" });
    expect(figure(period, "% de margen")).toBe(`-5,00${SPACE}%`);
  });

  it("never asks the browser to compute anything with an amount", async () => {
    const number = vi.spyOn(globalThis, "Number");
    installRoutes({ "GET /margin": () => reply(200, TWO_LINES) });

    renderAuthenticated(<MarginPage />);

    await screen.findByRole("region", { name: "Totales del periodo" });
    const amounts = new Set(["3631.01", "1200.00", "907.75", "700.00", "823.26", "9000.00", "6000.00", "3000.00"]);
    const calledWithAnAmount = number.mock.calls.filter(([argument]) => typeof argument === "string" && amounts.has(argument));
    expect(calledWithAnAmount).toEqual([]);
    number.mockRestore();
  });
});

describe("masked names", () => {
  it("blurs a campaign name when NEXT_PUBLIC_MASK_NAMES is true, as the rest of the application does", async () => {
    vi.stubEnv("NEXT_PUBLIC_MASK_NAMES", "true");
    installRoutes({ "GET /margin": () => reply(200, TWO_LINES) });

    renderAuthenticated(<MarginPage />);

    const group = await screen.findByRole("group", { name: "Campaña Alfa" });
    const name = group.querySelector("summary [data-adform-name]") as HTMLElement;
    expect(name).toHaveTextContent("Alfa");
    expect(name).toHaveStyle({ filter: "blur(6px)", userSelect: "none", pointerEvents: "none" });
  });

  it("does not blur it otherwise", async () => {
    installRoutes({ "GET /margin": () => reply(200, TWO_LINES) });

    renderAuthenticated(<MarginPage />);

    const group = await screen.findByRole("group", { name: "Campaña Alfa" });
    expect(group.querySelector("summary [data-adform-name]")).not.toHaveStyle({ filter: "blur(6px)" });
  });
});

describe("waiting for the data", () => {
  it("waits for the request before showing anything of the margin", async () => {
    installRoutes({ "GET /margin": () => new Promise(() => {}) });

    renderAuthenticated(<MarginPage />);

    await waitFor(() => expect(screen.getByText("Cargando margen…")).toBeInTheDocument());
    expect(screen.queryByRole("region", { name: "Totales del periodo" })).not.toBeInTheDocument();
  });
});
