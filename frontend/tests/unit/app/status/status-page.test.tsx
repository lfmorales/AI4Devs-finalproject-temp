import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import StatusPage from "@/app/(authenticated)/status/page";
import type { CampaignStatusRow } from "@/lib/api/status";
import { installRoutes, plain, renderAuthenticated, reply } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

function row(overrides: Partial<CampaignStatusRow> = {}): CampaignStatusRow {
  return {
    campaign: { id: 1, name: "Campaña A" },
    agency: { id: 1, name: "Agencia M" },
    line_number: 1,
    flight: { campaign_period_id: 7, year: 2026, month: 8, start: "2026-08-01", end: "2026-08-31" },
    contracted_impressions: 31000,
    delivered_impressions: 12000,
    delivery_ratio: 0.387,
    pacing: { expected_impressions: 15000.4, deviation: -0.2, days_remaining: 20, status: "under_delivering" },
    pacing_flag: false,
    missing_data_flag: false,
    ...overrides,
  };
}

const ROWS_IN_SERVER_ORDER: CampaignStatusRow[] = [
  row({ campaign: { id: 1, name: "Campaña Z" }, agency: { id: 3, name: "Zeta" },
    flight: { campaign_period_id: 9, year: 2026, month: 9, start: "2026-09-01", end: "2026-09-30" } }),
  row({ campaign: { id: 2, name: "Campaña B" }, agency: { id: 1, name: "Alfa" },
    flight: { campaign_period_id: 8, year: 2026, month: 8, start: "2026-08-01", end: "2026-08-31" } }),
  row({ campaign: { id: 3, name: "Campaña C" }, agency: { id: 2, name: "Media" },
    flight: { campaign_period_id: 10, year: 2026, month: 10, start: "2026-10-01", end: "2026-10-31" } }),
];

function campaignOrder(): string[] {
  const table = screen.getByRole("table", { name: "Estado de las campañas" });
  return within(table).getAllByRole("row").slice(1).map((r) => plain(within(r).getAllByRole("cell")[0]!));
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the status page", () => {
  it("shows a row per flight with contracted and delivered in distinct columns", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, [row()]) });

    renderAuthenticated(<StatusPage />);

    const table = await screen.findByRole("table", { name: "Estado de las campañas" });
    const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
    for (const name of ["Campaña", "Agencia", "Línea", "Periodo", "Ventana", "Contratado", "Entregado", "Ratio",
      "Esperado", "Desviación", "Días restantes", "Avisos"]) {
      expect(headers).toContain(name);
    }
    const cells = within(within(table).getAllByRole("row")[1]!).getAllByRole("cell");
    const byHeader = (name: string) => plain(cells[headers.indexOf(name)]!);
    expect(byHeader("Campaña")).toBe("Campaña A");
    expect(byHeader("Agencia")).toBe("Agencia M");
    expect(byHeader("Línea")).toBe("1");
    expect(byHeader("Periodo")).toBe("08/2026");
    expect(byHeader("Ventana")).toBe("2026-08-01 – 2026-08-31");
    expect(byHeader("Contratado")).toBe("31.000");
    expect(byHeader("Entregado")).toBe("12.000");
    expect(byHeader("Días restantes")).toBe("20");
  });

  it("formats the ratio and the deviation as the API returns them, as percentages", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, [row()]) });

    renderAuthenticated(<StatusPage />);

    const table = await screen.findByRole("table", { name: "Estado de las campañas" });
    const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
    const cells = within(within(table).getAllByRole("row")[1]!).getAllByRole("cell");
    expect(plain(cells[headers.indexOf("Ratio")]!)).toBe("38,7 %");
    expect(plain(cells[headers.indexOf("Desviación")]!)).toBe("-20 %");
    expect(plain(cells[headers.indexOf("Esperado")]!)).toBe("15.000");
  });

  it("shows a dash, not zero, when the ratio or the deviation is null", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, [row({ delivery_ratio: null,
      pacing: { expected_impressions: 0, deviation: null, days_remaining: 20, status: "on_pace" } })]) });

    renderAuthenticated(<StatusPage />);

    const table = await screen.findByRole("table", { name: "Estado de las campañas" });
    const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
    const cells = within(within(table).getAllByRole("row")[1]!).getAllByRole("cell");
    expect(plain(cells[headers.indexOf("Ratio")]!)).toBe("—");
    expect(plain(cells[headers.indexOf("Desviación")]!)).toBe("—");
  });

  it("states the pacing flag in words", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, [row({ pacing_flag: true })]) });

    renderAuthenticated(<StatusPage />);

    expect(await screen.findByText("Desviación de ritmo")).toBeInTheDocument();
    expect(screen.queryByText("Sin datos recibidos")).not.toBeInTheDocument();
  });

  it("states the missing-data flag in words", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, [row({ missing_data_flag: true })]) });

    renderAuthenticated(<StatusPage />);

    expect(await screen.findByText("Sin datos recibidos")).toBeInTheDocument();
    expect(screen.queryByText("Desviación de ritmo")).not.toBeInTheDocument();
  });

  it("states both flags on the same row", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, [row({ pacing_flag: true, missing_data_flag: true })]) });

    renderAuthenticated(<StatusPage />);

    expect(await screen.findByText("Desviación de ritmo")).toBeInTheDocument();
    expect(screen.getByText("Sin datos recibidos")).toBeInTheDocument();
  });

  it("keeps the server order by default", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, ROWS_IN_SERVER_ORDER) });

    renderAuthenticated(<StatusPage />);

    await screen.findByRole("table", { name: "Estado de las campañas" });
    expect(campaignOrder()).toEqual(["Campaña Z", "Campaña B", "Campaña C"]);
  });

  it("sorts by period ascending, then descending, then back to the server order", async () => {
    const user = userEvent.setup();
    installRoutes({ "GET /campaign-status": () => reply(200, ROWS_IN_SERVER_ORDER) });
    renderAuthenticated(<StatusPage />);
    await screen.findByRole("table", { name: "Estado de las campañas" });
    const sortByPeriod = screen.getByRole("button", { name: "Periodo" });

    await user.click(sortByPeriod);
    expect(campaignOrder()).toEqual(["Campaña B", "Campaña Z", "Campaña C"]);
    expect(screen.getByRole("columnheader", { name: "Periodo" })).toHaveAttribute("aria-sort", "ascending");

    await user.click(sortByPeriod);
    expect(campaignOrder()).toEqual(["Campaña C", "Campaña Z", "Campaña B"]);
    expect(screen.getByRole("columnheader", { name: "Periodo" })).toHaveAttribute("aria-sort", "descending");

    await user.click(sortByPeriod);
    expect(campaignOrder()).toEqual(["Campaña Z", "Campaña B", "Campaña C"]);
  });

  it("sorts by agency, and only one column sorts at a time", async () => {
    const user = userEvent.setup();
    installRoutes({ "GET /campaign-status": () => reply(200, ROWS_IN_SERVER_ORDER) });
    renderAuthenticated(<StatusPage />);
    await screen.findByRole("table", { name: "Estado de las campañas" });

    await user.click(screen.getByRole("button", { name: "Agencia" }));
    expect(campaignOrder()).toEqual(["Campaña B", "Campaña C", "Campaña Z"]);

    await user.click(screen.getByRole("button", { name: "Periodo" }));
    expect(screen.getByRole("columnheader", { name: "Agencia" })).not.toHaveAttribute("aria-sort", "ascending");
    expect(campaignOrder()).toEqual(["Campaña B", "Campaña Z", "Campaña C"]);
  });

  it("does not call the backend again when sorting", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({ "GET /campaign-status": () => reply(200, ROWS_IN_SERVER_ORDER) });
    renderAuthenticated(<StatusPage />);
    await screen.findByRole("table", { name: "Estado de las campañas" });

    await user.click(screen.getByRole("button", { name: "Agencia" }));

    expect(requests).toHaveLength(1);
  });

  it("shows the session-expired page on a 401", async () => {
    installRoutes({ "GET /campaign-status": () => reply(401, { code: "invalid_token", message: "x" }) });

    renderAuthenticated(<StatusPage />);

    await waitFor(() => expect(screen.getByText("Sesión caducada")).toBeInTheDocument());
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the access-denied page on a 403", async () => {
    installRoutes({ "GET /campaign-status": () => reply(403, { code: "missing_role", message: "x" }) });

    renderAuthenticated(<StatusPage />);

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
