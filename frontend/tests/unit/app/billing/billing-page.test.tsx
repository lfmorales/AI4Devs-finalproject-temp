import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import BillingPage from "@/app/(authenticated)/billing/page";
import { installRoutes, plain, renderAuthenticated, reply, type Route } from "../../../helpers/api-pages";
import { adjustmentInForce, billing, billingCampaign, billingFlight, billingLine } from "../../../helpers/billing-data";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ access_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const SPACE = " "; // plain() turns the no-break space of the euro amounts into a plain one
const OCTOBER = "GET /billing?year=2026&month=10";

// Today is 26 November 2026 in Madrid: the screen opens on October 2026. Only the clock is faked, not the timers.
const TODAY = new Date("2026-11-26T10:00:00+01:00");

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(TODAY);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** The screen as it opens on 26 November 2026: on October, read with these routes. */
async function renderOctober(routes: Record<string, Route>) {
  const requests = installRoutes(routes);
  const user = userEvent.setup();
  renderAuthenticated(<BillingPage />);
  return { requests, user };
}

function campaignSection(name: string): HTMLElement {
  return screen.getByRole("region", { name: `Campaña ${name}` });
}

function flightsTable(name: string, lineNumber = 1): HTMLElement {
  return screen.getByRole("table", { name: `Flights de la línea ${lineNumber} de ${name}` });
}

function headersOf(table: HTMLElement): string[] {
  return within(table).getAllByRole("columnheader").map((header) => plain(header));
}

function cellOf(table: HTMLElement, header: string, row = 0): HTMLElement {
  const index = headersOf(table).indexOf(header);
  expect(index, header).toBeGreaterThan(-1);
  return within(within(table).getAllByRole("row")[row + 1]!).getAllByRole("cell")[index]!;
}

// ---------------------------------------------------------------- the month and its campaigns

describe("the billing screen", () => {
  it("opens on the month before today's and reads it", async () => {
    const requests = installRoutes({ [OCTOBER]: () => reply(200, billing()) });

    renderAuthenticated(<BillingPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Facturación" })).toBeInTheDocument();
    expect(screen.getByLabelText("Año")).toHaveValue("2026");
    expect(screen.getByLabelText("Mes")).toHaveDisplayValue("octubre");
    await screen.findByRole("region", { name: "Campaña Alfa" });
    expect(requests.map((request) => `${request.method} ${request.path}`)).toEqual([OCTOBER]);
  });

  it("opens on December of the year before in January", async () => {
    vi.setSystemTime(new Date("2027-01-10T10:00:00+01:00"));
    const requests = installRoutes({ "GET /billing?year=2026&month=12": () => reply(200, billing({ month: 12 })) });

    renderAuthenticated(<BillingPage />);

    await screen.findByRole("region", { name: "Campaña Alfa" });
    expect(screen.getByLabelText("Año")).toHaveValue("2026");
    expect(screen.getByLabelText("Mes")).toHaveDisplayValue("diciembre");
    expect(requests.map((request) => request.path)).toEqual(["/billing?year=2026&month=12"]);
  });

  it("reads another month once it is chosen", async () => {
    const requests = installRoutes({
      [OCTOBER]: () => reply(200, billing()),
      "GET /billing?year=2026&month=9": () => reply(200, billing({ month: 9, campaigns: [billingCampaign({ name: "Septiembre" })] })),
    });
    const user = userEvent.setup();
    renderAuthenticated(<BillingPage />);
    await screen.findByRole("region", { name: "Campaña Alfa" });

    await user.selectOptions(screen.getByLabelText("Mes"), "septiembre");

    expect(await screen.findByRole("region", { name: "Campaña Septiembre" })).toBeInTheDocument();
    expect(requests.map((request) => request.path)).toEqual(["/billing?year=2026&month=10", "/billing?year=2026&month=9"]);
  });

  it("asks for a year and a month again when the year is cleared, and reads nothing more", async () => {
    const requests = installRoutes({ [OCTOBER]: () => reply(200, billing()) });
    const user = userEvent.setup();
    renderAuthenticated(<BillingPage />);
    await screen.findByRole("region", { name: "Campaña Alfa" });

    await user.clear(screen.getByLabelText("Año"));

    expect(screen.getByText("Elige año y mes para ver la facturación")).toBeInTheDocument();
    expect(requests).toHaveLength(1);
  });

  it("shows each campaign with its agency, its advertiser and its review state", async () => {
    await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [
        billingCampaign({ campaign_id: 1, name: "Alfa", review_state: "in_progress" }),
        billingCampaign({ campaign_id: 2, name: "Beta", review_state: "pending_review" }),
        billingCampaign({ campaign_id: 3, name: "Gamma", review_state: "reviewed", review_set_by: 7, review_set_by_name: "Ana Pérez", review_set_at: "2026-11-02T10:15:30.123456" }),
        billingCampaign({ campaign_id: 4, name: "Delta", review_state: "closed" }),
      ] })),
    });

    await screen.findByRole("region", { name: "Campaña Alfa" });
    expect(plain(campaignSection("Alfa"))).toContain("Agencia Uno · Anunciante Uno");
    expect(within(campaignSection("Alfa")).getByText("En curso")).toBeInTheDocument();
    expect(within(campaignSection("Beta")).getByText("Pendiente de revisión")).toBeInTheDocument();
    expect(within(campaignSection("Gamma")).getByText("Revisada")).toBeInTheDocument();
    expect(within(campaignSection("Delta")).getByText("Cerrada")).toBeInTheDocument();
    expect(plain(campaignSection("Gamma"))).toContain("por Ana Pérez el 02/11/2026 10:15");
    expect(plain(document.body)).not.toMatch(/usuario \d/);
  });

  it("shows each flight's volumes and billing as the server sent them", async () => {
    await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [billingCampaign({ lines: [billingLine({ flights: [billingFlight({
        contracted_impressions: 500000, carryover: 100000, carryover_billable: true, delivery_target: 600000,
        delivered: "580000.0000", billable: "580000.0000", billing: "2900.00",
      })] })] })] })),
    });

    const table = await screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
    expect(plain(cellOf(table, "Contratado"))).toBe("500.000 impresiones");
    expect(plain(cellOf(table, "Arrastre"))).toContain("100.000");
    expect(plain(cellOf(table, "Objetivo de entrega"))).toBe("600.000");
    expect(plain(cellOf(table, "Entregado"))).toBe("580.000");
    expect(plain(cellOf(table, "Volumen facturable"))).toBe("580.000");
    expect(plain(cellOf(table, "CPM"))).toBe(`5,00${SPACE}€`);
    expect(plain(cellOf(table, "Facturable"))).toBe(`2.900,00${SPACE}€`);
  });

  it("labels the billing of a line with a running flight «Facturable a la fecha»", async () => {
    await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [billingCampaign({ review_state: "in_progress", lines: [
        billingLine({ flights: [billingFlight({ state: "running", billing: "900.00" })] }),
      ] })] })),
    });

    const table = await screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
    expect(headersOf(table)).toContain("Facturable a la fecha");
    expect(plain(cellOf(table, "Facturable a la fecha"))).toBe(`900,00${SPACE}€`);
  });

  it("shows a flight that has not started without a billing", async () => {
    await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [billingCampaign({ review_state: "in_progress", lines: [billingLine({ flights: [
        billingFlight({ state: "not_started", delivered: null, billable: null, billing: null, billing_basis: null }),
      ] })] })] })),
    });

    const table = await screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
    expect(plain(cellOf(table, "Estado"))).toBe("Sin empezar");
    expect(plain(cellOf(table, "Facturable a la fecha"))).toBe("—");
  });

  it("shows the adjustment in force with its basis, reason, author and moment", async () => {
    await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [billingCampaign({ lines: [billingLine({ flights: [billingFlight({
        billing: "4200.00", billable: null, billing_basis: "custom", adjustment: adjustmentInForce(),
      })] })] })] })),
    });

    const table = await screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
    expect(plain(cellOf(table, "Ajuste"))).toBe(
      "Ajustado: importe fijo · Acuerdo con la agencia · Ana Pérez · 02/11/2026 10:15",
    );
    expect(plain(cellOf(table, "Volumen facturable"))).toBe("—");
  });
});

// ---------------------------------------------------------------- the review

describe("the review of a campaign", () => {
  it("marks a campaign pending review as reviewed and reads the month again", async () => {
    let state = "pending_review";
    const { requests, user } = await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [billingCampaign({ campaign_id: 5, review_state: state as "pending_review" })] })),
      "POST /billing/reviews": () => {
        state = "reviewed";
        return reply(201, { campaign_id: 5, year: 2026, month: 10, state: "reviewed", set_by: 7, set_at: "2026-11-02T10:15:00" });
      },
    });

    await user.click(await screen.findByRole("button", { name: "Marcar como revisada" }));

    await waitFor(() => expect(within(campaignSection("Alfa")).getByText("Revisada")).toBeInTheDocument());
    expect(requests.find((request) => request.method === "POST")?.body).toEqual({ campaign_id: 5, year: 2026, month: 10 });
    expect(screen.getByRole("button", { name: "Quitar revisión" })).toBeInTheDocument();
  });

  it("withdraws the review of a reviewed campaign", async () => {
    const { requests, user } = await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [billingCampaign({ campaign_id: 5, review_state: "reviewed", review_set_by: 7, review_set_by_name: "Ana Pérez", review_set_at: "2026-11-02T10:15:00" })] })),
      "POST /billing/reviews/withdrawals": () => reply(201, { campaign_id: 5, year: 2026, month: 10, state: "pending_review", set_by: 7, set_at: "2026-11-02T11:00:00" }),
    });

    await user.click(await screen.findByRole("button", { name: "Quitar revisión" }));

    await waitFor(() => expect(requests.some((request) => request.path === "/billing/reviews/withdrawals")).toBe(true));
    expect(screen.queryByRole("button", { name: "Marcar como revisada" })).not.toBeInTheDocument(); // still the read's state
  });

  it("offers no review button to a campaign in progress or closed", async () => {
    await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [
        billingCampaign({ campaign_id: 1, name: "Alfa", review_state: "in_progress" }),
        billingCampaign({ campaign_id: 2, name: "Beta", review_state: "closed" }),
      ] })),
    });

    await screen.findByRole("region", { name: "Campaña Alfa" });
    expect(screen.queryByRole("button", { name: "Marcar como revisada" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Quitar revisión" })).not.toBeInTheDocument();
  });

  it("explains in Spanish why a review is refused while the DSP has not loaded the month's last day", async () => {
    const { user } = await renderOctober({
      [OCTOBER]: () => reply(200, billing()),
      "POST /billing/reviews": () => reply(409, {
        code: "month_delivery_not_loaded",
        message: "The delivery of 2026-10 from Adform is not loaded up to its last day. Load it, then review the campaign.",
      }),
    });

    await user.click(await screen.findByRole("button", { name: "Marcar como revisada" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No se puede revisar Alfa: Adform aún no ha cargado la entrega del último día de octubre de 2026. "
      + "Espera a la ingesta de ese día y vuelve a marcarla como revisada.",
    );
  });
});

// ---------------------------------------------------------------- the adjustment

describe("the adjustment of a flight", () => {
  const MONTH = { [OCTOBER]: () => reply(200, billing()) };

  it("is offered on an ended, unfrozen committed flight only", async () => {
    await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [billingCampaign({ lines: [billingLine({ flights: [
        billingFlight({ flight_id: 1, state: "pending_close" }),
        billingFlight({ flight_id: 2, state: "running", flight_start: "2026-10-05" }),
        billingFlight({ flight_id: 3, state: "closed", flight_start: "2026-10-06" }),
        billingFlight({ flight_id: 4, state: "pending_close", billing_basis: "reported", billable: null, flight_start: "2026-10-07" }),
      ] })] })] })),
    });

    const table = await screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
    expect(within(table).getAllByRole("button", { name: "Ajustar" })).toHaveLength(1);
    expect(within(cellOf(table, "Acciones", 0)).getByRole("button", { name: "Ajustar" })).toBeInTheDocument();
  });

  it("asks for an amount only with the custom basis and requires a reason", async () => {
    const { user } = await renderOctober(MONTH);
    await user.click(await screen.findByRole("button", { name: "Ajustar" }));
    const dialog = screen.getByRole("dialog", { name: "Ajustar la facturación" });

    expect(within(dialog).queryByLabelText("Importe")).not.toBeInTheDocument();
    const save = within(dialog).getByRole("button", { name: "Guardar ajuste" });
    expect(save).toBeDisabled();
    await user.selectOptions(within(dialog).getByLabelText("Base"), "Importe fijo");
    expect(within(dialog).getByLabelText("Importe")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Motivo"), "Acuerdo");
    expect(save).toBeDisabled(); // a custom billing needs its amount
    await user.type(within(dialog).getByLabelText("Importe"), "4200,5");
    expect(save).toBeEnabled();
    await user.clear(within(dialog).getByLabelText("Motivo"));
    await user.type(within(dialog).getByLabelText("Motivo"), "   ");
    expect(save).toBeDisabled();
  });

  it("sends the basis, the amount with a decimal point and the reason, then reads the month again", async () => {
    let adjusted = false;
    const { requests, user } = await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [billingCampaign({ lines: [billingLine({ flights: [adjusted
        ? billingFlight({ billing: "4200.50", billing_basis: "custom", billable: null, adjustment: adjustmentInForce({ amount: "4200.50", reason: "Acuerdo" }) })
        : billingFlight()] })] })] })),
      "POST /billing/flights/31/adjustments": () => {
        adjusted = true;
        return reply(201, { id: 9, flight_id: 31, basis: "custom", amount: "4200.50", reason: "Acuerdo", created_by: 7, created_at: "2026-11-02T10:15:00", billing: "4200.50" });
      },
    });
    await user.click(await screen.findByRole("button", { name: "Ajustar" }));
    const dialog = screen.getByRole("dialog", { name: "Ajustar la facturación" });

    await user.selectOptions(within(dialog).getByLabelText("Base"), "Importe fijo");
    await user.type(within(dialog).getByLabelText("Importe"), "4200,50");
    await user.type(within(dialog).getByLabelText("Motivo"), "Acuerdo");
    await user.click(within(dialog).getByRole("button", { name: "Guardar ajuste" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(requests.find((request) => request.method === "POST")?.body).toEqual({ basis: "custom", amount: "4200.50", reason: "Acuerdo" });
    const table = screen.getByRole("table", { name: "Flights de la línea 1 de Alfa" });
    await waitFor(() => expect(plain(cellOf(table, "Facturable"))).toBe(`4.200,50${SPACE}€`));
  });

  it("sends no amount with a basis other than custom", async () => {
    const { requests, user } = await renderOctober({
      ...MONTH,
      "POST /billing/flights/31/adjustments": () => reply(201, { id: 9, flight_id: 31, basis: "contracted", amount: null, reason: "OC", created_by: 7, created_at: "2026-11-02T10:15:00", billing: "5000.00" }),
    });
    await user.click(await screen.findByRole("button", { name: "Ajustar" }));
    const dialog = screen.getByRole("dialog", { name: "Ajustar la facturación" });

    await user.selectOptions(within(dialog).getByLabelText("Base"), "Lo contratado (el tope)");
    await user.type(within(dialog).getByLabelText("Motivo"), "OC");
    await user.click(within(dialog).getByRole("button", { name: "Guardar ajuste" }));

    await waitFor(() => expect(requests.some((request) => request.method === "POST")).toBe(true));
    expect(requests.find((request) => request.method === "POST")?.body).toEqual({ basis: "contracted", amount: null, reason: "OC" });
  });

  it("explains a refusal in Spanish inside the dialog, with what to do", async () => {
    const { user } = await renderOctober({
      ...MONTH,
      "POST /billing/flights/31/adjustments": () => reply(409, { code: "flight_closed", message: "the month is closed" }),
    });
    await user.click(await screen.findByRole("button", { name: "Ajustar" }));
    const dialog = screen.getByRole("dialog", { name: "Ajustar la facturación" });
    await user.type(within(dialog).getByLabelText("Motivo"), "OC");

    await user.click(within(dialog).getByRole("button", { name: "Guardar ajuste" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "El mes de este flight ya está cerrado: su facturación no se puede ajustar. Recarga la página para ver lo que se congeló.",
    );
  });

  // The dialog never sends a blank reason, but the server can refuse it two ways: its request validation answers a
  // missing reason with `validation_error`, the adjustment's rules a blank one with `invalid_adjustment`.
  it.each(["validation_error", "invalid_adjustment"])("explains a 422 %s of the adjustment with the same message", async (code) => {
    const { user } = await renderOctober({
      ...MONTH,
      "POST /billing/flights/31/adjustments": () => reply(422, { code, message: "the reason is missing" }),
    });
    await user.click(await screen.findByRole("button", { name: "Ajustar" }));
    const dialog = screen.getByRole("dialog", { name: "Ajustar la facturación" });
    await user.type(within(dialog).getByLabelText("Motivo"), "OC");

    await user.click(within(dialog).getByRole("button", { name: "Guardar ajuste" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "El ajuste no es válido: elige una base, escribe el motivo y, solo con un importe fijo, un importe de cero o más con dos decimales como máximo.",
    );
  });

  it("lists the adjustments of a flight, latest first, with the one in force", async () => {
    const { user } = await renderOctober({
      ...MONTH,
      "GET /billing/flights/31/adjustments": () => reply(200, { adjustments: [
        { id: 2, flight_id: 31, basis: "custom", amount: "4200.00", reason: "Acuerdo", created_by: 7, created_by_name: "Ana Pérez",
          created_at: "2026-11-02T11:00:00", in_force: true },
        { id: 1, flight_id: 31, basis: "delivered", amount: null, reason: "Primero", created_by: 8,
          created_by_name: "luis@example.com", created_at: "2026-11-02T10:00:00", in_force: false },
      ] }),
    });

    await user.click(await screen.findByRole("button", { name: "Historial" }));

    const dialog = await screen.findByRole("dialog", { name: "Historial de ajustes" });
    const items = within(dialog).getAllByRole("listitem").map((item) => plain(item));
    expect(items).toEqual([
      `Importe fijo 4.200,00${SPACE}€ · Acuerdo · Ana Pérez · 02/11/2026 11:00 · En vigor`,
      "Todo lo entregado · Primero · luis@example.com · 02/11/2026 10:00",
    ]);
  });
});

// ---------------------------------------------------------------- the billable flag of a carry-over

describe("the billable flag of a carry-over", () => {
  function carried(billable: boolean, state: "pending_close" | "closed" = "pending_close") {
    return billing({ campaigns: [billingCampaign({ lines: [billingLine({ flights: [billingFlight({
      state, carryover: 100000, carryover_billable: billable, delivery_target: 1100000,
    })] })] })] });
  }

  it("is set from the flight's row and the month is read again", async () => {
    let billable = false;
    const { requests, user } = await renderOctober({
      [OCTOBER]: () => reply(200, carried(billable)),
      "PUT /billing/flights/31/carryover/billable": (request) => {
        billable = (request.body as { billable: boolean }).billable;
        return reply(200, { flight_id: 31, carryover: 100000, billable, set_by: 7, set_at: "2026-11-02T10:15:00" });
      },
    });

    const box = await screen.findByRole("checkbox", { name: "Arrastre facturable" });
    expect(box).not.toBeChecked();
    await user.click(box);

    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Arrastre facturable" })).toBeChecked());
    expect(requests.find((request) => request.method === "PUT")?.body).toEqual({ billable: true });
  });

  it("is offered on no flight without a carry-over, and is read only on a closed flight", async () => {
    await renderOctober({
      [OCTOBER]: () => reply(200, billing({ campaigns: [billingCampaign({ lines: [billingLine({ flights: [
        billingFlight({ flight_id: 1 }),
        billingFlight({ flight_id: 2, state: "closed", carryover: 100000, carryover_billable: true, flight_start: "2026-10-02" }),
      ] })] })] })),
    });

    const table = await screen.findByRole("table", { name: "Flights de la línea 1 de Alfa" });
    expect(within(cellOf(table, "Arrastre", 0)).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(cellOf(table, "Arrastre", 1)).getByRole("checkbox", { name: "Arrastre facturable" })).toBeDisabled();
  });

  it("explains a refusal in Spanish", async () => {
    const { user } = await renderOctober({
      [OCTOBER]: () => reply(200, carried(false)),
      "PUT /billing/flights/31/carryover/billable": () => reply(409, { code: "month_closed", message: "closed" }),
    });

    await user.click(await screen.findByRole("checkbox", { name: "Arrastre facturable" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El mes de este flight ya está cerrado: la marca del arrastre no se puede cambiar.",
    );
  });
});

// ---------------------------------------------------------------- the CSV

describe("the CSV of a closed month", () => {
  function closedMonth() {
    return billing({ campaigns: [billingCampaign({ review_state: "closed", lines: [billingLine({ flights: [billingFlight({ state: "closed" })] })] })] });
  }

  it("is off while no flight of the month is closed, and says why", async () => {
    await renderOctober({ [OCTOBER]: () => reply(200, billing()) });

    const button = await screen.findByRole("button", { name: "Descargar CSV" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("El CSV está disponible cuando el mes está cerrado");
  });

  it("downloads facturacion-YYYY-MM.csv from the export of the month", async () => {
    const createObjectURL = vi.fn(() => "blob:csv");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { requests, user } = await renderOctober({
      [OCTOBER]: () => reply(200, closedMonth()),
      "GET /billing/export?year=2026&month=10": () => reply(200, "cliente;agencia"),
    });

    await user.click(await screen.findByRole("button", { name: "Descargar CSV" }));

    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    const anchor = click.mock.instances[0] as unknown as HTMLAnchorElement;
    expect(anchor.download).toBe("facturacion-2026-10.csv");
    expect(anchor.href).toBe("blob:csv");
    expect(requests.some((request) => request.path === "/billing/export?year=2026&month=10")).toBe(true);
    click.mockRestore();
  });

  it("explains in Spanish that an open month has no CSV", async () => {
    const { user } = await renderOctober({
      [OCTOBER]: () => reply(200, closedMonth()),
      "GET /billing/export?year=2026&month=10": () => reply(409, { code: "month_not_closed", message: "2026-10 is not closed" }),
    });

    await user.click(await screen.findByRole("button", { name: "Descargar CSV" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "octubre de 2026 no está cerrado: el CSV se puede descargar cuando se cierre el mes.",
    );
  });
});

// ---------------------------------------------------------------- access

describe("the access to the billing screen", () => {
  it("shows 'Acceso denegado' when the read answers 403", async () => {
    await renderOctober({ [OCTOBER]: () => reply(403, { code: "forbidden", message: "x" }) });

    expect(await screen.findByRole("heading", { name: "Acceso denegado" })).toBeInTheDocument();
    expect(screen.getByText("No tienes permiso para ver la facturación.")).toBeInTheDocument();
  });

  it("shows 'Sesión caducada' when the read answers 401", async () => {
    await renderOctober({ [OCTOBER]: () => reply(401, { code: "unauthenticated", message: "x" }) });

    expect(await screen.findByRole("heading", { name: /Sesión caducada/ })).toBeInTheDocument();
  });
});

describe("the billing screen and the roles", () => {
  it.each([[["trading"]], [["business"]], [["business", "trading"]]] as [("trading" | "business")[]][])(
    "is refused to %j without asking the server, as the navigation hides it",
    async (roles) => {
      const requests = installRoutes({});

      renderAuthenticated(<BillingPage />, { roles });

      expect(await screen.findByRole("heading", { name: "Acceso denegado" })).toBeInTheDocument();
      expect(screen.getByText("No tienes permiso para ver la facturación.")).toBeInTheDocument();
      expect(requests).toHaveLength(0);
    },
  );

  it.each([[["finance"]], [["operations"]], [["finance", "trading"]]] as [("finance" | "operations" | "trading")[]][])(
    "is open to %j",
    async (roles) => {
      installRoutes({});

      renderAuthenticated(<BillingPage />, { roles });

      expect(await screen.findByRole("heading", { level: 1, name: "Facturación" })).toBeInTheDocument();
    },
  );
});
