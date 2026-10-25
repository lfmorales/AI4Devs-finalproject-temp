import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import StatusPage from "@/app/(authenticated)/status/page";
import { installRoutes, renderAuthenticated, reply, type FakeReply } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const LOADING = "Cargando estado…";
const EMPTY = "No hay campañas en curso";
const ERROR = "No se pudo cargar el estado de las campañas. Inténtalo de nuevo más tarde.";

function expectOnly(visible: string | null) {
  for (const text of [LOADING, EMPTY, ERROR]) {
    if (text === visible) expect(screen.getByText(text)).toBeInTheDocument();
    else expect(screen.queryByText(text)).not.toBeInTheDocument();
  }
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the states of the status page", () => {
  it("shows only the loading state while the request is pending", async () => {
    installRoutes({ "GET /campaign-status": () => new Promise<FakeReply>(() => {}) });

    renderAuthenticated(<StatusPage />);

    expect(await screen.findByText(LOADING)).toBeInTheDocument();
    expectOnly(LOADING);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows only the empty state when the list loaded with no rows", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, []) });

    renderAuthenticated(<StatusPage />);

    await waitFor(() => expect(screen.getByText(EMPTY)).toBeInTheDocument());
    expectOnly(EMPTY);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows only the error state when the request fails", async () => {
    installRoutes({ "GET /campaign-status": () => reply(500, { code: "internal_error", message: "x" }) });

    renderAuthenticated(<StatusPage />);

    await waitFor(() => expect(screen.getByText(ERROR)).toBeInTheDocument());
    expectOnly(ERROR);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows neither the empty nor the error state once there are rows", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, [{
      campaign: { id: 1, name: "Campaña A" }, agency: { id: 1, name: "Agencia A" }, line_number: 1,
      flight: { campaign_period_id: 7, year: 2026, month: 8, start: "2026-08-01", end: "2026-08-31" },
      contracted_impressions: 10, delivered_impressions: 5, delivery_ratio: 0.5,
      pacing: { expected_impressions: 5, deviation: 0, days_remaining: 1, status: "on_pace" },
      pacing_flag: false, missing_data_flag: false,
    }]) });

    renderAuthenticated(<StatusPage />);

    expect(await screen.findByRole("table", { name: "Estado de las campañas" })).toBeInTheDocument();
    expectOnly(null);
  });
});
