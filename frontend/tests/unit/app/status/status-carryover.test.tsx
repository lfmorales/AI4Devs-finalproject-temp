import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import StatusPage from "@/app/(authenticated)/status/page";
import type { Role } from "@/lib/auth/navigation";
import type { CampaignStatusRow } from "@/lib/api/status";
import { installRoutes, plain, renderAuthenticated, reply, type Route } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ access_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

function row(overrides: Partial<CampaignStatusRow> = {}): CampaignStatusRow {
  return {
    campaign: { id: 1, name: "Campaña A" },
    agency: { id: 1, name: "Agencia M" },
    line_number: 1,
    flight: { id: 70, campaign_period_id: 7, year: 2026, month: 11, start: "2026-11-01", end: "2026-11-30" },
    contracted_impressions: 500000,
    carryover: 100000,
    delivery_target: 600000,
    delivery_metric: "impressions",
    delivered: "120000.0000",
    delivered_impressions: 120000,
    delivery_ratio: 0.2,
    pacing: { expected_impressions: 180000, deviation: -0.33, days_remaining: 20, status: "under_delivering" },
    pacing_flag: false,
    missing_data_flag: false,
    volume_commitment: "committed",
    ...overrides,
  };
}

function cellOf(header: string, index = 0): HTMLElement {
  const table = screen.getByRole("table", { name: "Estado de las campañas" });
  const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
  const column = headers.indexOf(header);
  expect(column, header).toBeGreaterThan(-1);
  return within(within(table).getAllByRole("row")[index + 1]!).getAllByRole("cell")[column]!;
}

async function renderStatus(roles: Role[], routes: Record<string, Route> = {}) {
  const requests = installRoutes({ "GET /campaign-status": () => reply(200, [row()]), ...routes });
  const user = userEvent.setup();
  renderAuthenticated(<StatusPage />, { roles });
  await screen.findByRole("table", { name: "Estado de las campañas" });
  return { requests, user };
}

async function openForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(within(cellOf("Arrastre")).getByRole("button", { name: "Registrar arrastre" }));
  return screen.getByRole("dialog", { name: "Arrastre de Campaña A · línea 1" });
}

describe("the carry-over in the campaign status", () => {
  it("shows «Arrastre» and «Objetivo de entrega» on every row, as the server sent them", async () => {
    await renderStatus(["business"], {
      "GET /campaign-status": () => reply(200, [row(), row({ carryover: 0, delivery_target: 500000, line_number: 2 })]),
    });

    expect(plain(cellOf("Arrastre", 0))).toContain("100.000");
    expect(plain(cellOf("Objetivo de entrega", 0))).toBe("600.000");
    expect(plain(cellOf("Arrastre", 1))).toContain("0");
    expect(plain(cellOf("Objetivo de entrega", 1))).toBe("500.000");
  });

  it("keeps the carry-over figure apart from its button", async () => {
    await renderStatus(["trading"]);

    expect(plain(cellOf("Arrastre"))).toBe("100.000 Registrar arrastre");
  });

  it.each([[["operations"]], [["trading"]], [["finance", "trading"]]] as [Role[]][])(
    "offers the carry-over form to %j",
    async (roles) => {
      await renderStatus(roles);

      expect(within(cellOf("Arrastre")).getByRole("button", { name: "Registrar arrastre" })).toBeInTheDocument();
    },
  );

  it.each([[["business"]], [["finance"]], [["business", "finance"]]] as [Role[]][])(
    "offers no carry-over form to %j",
    async (roles) => {
      await renderStatus(roles);

      expect(screen.queryByRole("button", { name: "Registrar arrastre" })).not.toBeInTheDocument();
    },
  );

  it("shows no billable flag and no amount to anyone", async () => {
    const { user } = await renderStatus(["operations", "trading"]);
    const dialog = await openForm(user);

    for (const container of [screen.getByRole("table", { name: "Estado de las campañas" }), dialog]) {
      expect(within(container).queryByRole("checkbox")).not.toBeInTheDocument();
      expect(plain(container)).not.toMatch(/facturable|€/i);
    }
  });

  it("sends a whole volume and a reason, then reads the status again", async () => {
    let carried = 100000;
    const { requests, user } = await renderStatus(["trading"], {
      "GET /campaign-status": () => reply(200, [row({ carryover: carried, delivery_target: 500000 + carried })]),
      "PUT /flights/70/carryover": (request) => {
        carried = (request.body as { volume: number }).volume;
        return reply(200, { flight_id: 70, delivery_metric: "impressions", contracted_impressions: 500000, carryover: carried,
          delivery_target: 500000 + carried, reason: "Falta de octubre", set_by: 3, set_at: "2026-11-10T09:00:00" });
      },
    });
    const dialog = await openForm(user);

    await user.type(within(dialog).getByLabelText("Volumen"), "80000");
    await user.type(within(dialog).getByLabelText("Motivo"), "Falta de octubre");
    await user.click(within(dialog).getByRole("button", { name: "Guardar arrastre" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(requests.find((request) => request.method === "PUT")?.body).toEqual({ volume: 80000, reason: "Falta de octubre" });
    await waitFor(() => expect(plain(cellOf("Objetivo de entrega"))).toBe("580.000"));
  });

  it("accepts a volume of zero, which removes the carry-over, and refuses anything but a whole number", async () => {
    const { user } = await renderStatus(["operations"]);
    const dialog = await openForm(user);
    const save = within(dialog).getByRole("button", { name: "Guardar arrastre" });
    await user.type(within(dialog).getByLabelText("Motivo"), "Sin arrastre");

    for (const text of ["", "1,5", "-3", "1e3", "abc"]) {
      await user.clear(within(dialog).getByLabelText("Volumen"));
      if (text !== "") await user.type(within(dialog).getByLabelText("Volumen"), text);
      expect(save, text).toBeDisabled();
    }
    await user.clear(within(dialog).getByLabelText("Volumen"));
    await user.type(within(dialog).getByLabelText("Volumen"), "0");
    expect(save).toBeEnabled();
    await user.clear(within(dialog).getByLabelText("Motivo"));
    expect(save).toBeDisabled();
  });

  it("names the shortfall of the previous flight when the carry-over is above it", async () => {
    const { user } = await renderStatus(["trading"], {
      "PUT /flights/70/carryover": () => reply(409, {
        code: "carryover_exceeds_shortfall", message: "the previous flight fell short by 100000",
      }),
    });
    const dialog = await openForm(user);
    await user.type(within(dialog).getByLabelText("Volumen"), "150000");
    await user.type(within(dialog).getByLabelText("Motivo"), "Falta");

    await user.click(within(dialog).getByRole("button", { name: "Guardar arrastre" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "El arrastre supera lo que le faltó al flight anterior: como máximo 100.000. Indica un volumen menor.",
    );
  });

  it.each([
    ["no_previous_flight", "Es el primer flight de la línea: no tiene un flight anterior del que arrastrar."],
    ["previous_flight_not_ended", "El flight anterior de la línea aún no ha terminado: el arrastre se podrá registrar cuando acabe."],
    ["month_closed", "El mes de este flight ya está cerrado: su arrastre no se puede cambiar."],
  ])("explains %s in Spanish", async (code, text) => {
    const { user } = await renderStatus(["operations"], {
      "PUT /flights/70/carryover": () => reply(409, { code, message: "x" }),
    });
    const dialog = await openForm(user);
    await user.type(within(dialog).getByLabelText("Volumen"), "10");
    await user.type(within(dialog).getByLabelText("Motivo"), "Falta");

    await user.click(within(dialog).getByRole("button", { name: "Guardar arrastre" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(text);
  });
});
