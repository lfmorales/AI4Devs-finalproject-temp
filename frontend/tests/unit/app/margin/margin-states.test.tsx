import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import MarginPage from "@/app/(authenticated)/margin/page";
import { installRoutes, renderAuthenticated, reply, type FakeReply } from "../../../helpers/api-pages";
import { margin } from "../../../helpers/margin-data";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const LOADING = "Cargando margen…";
const EMPTY = "No hay margen para el periodo elegido";
const ERROR = "No se pudo cargar el margen. Inténtalo de nuevo más tarde.";

function expectOnly(visible: string | null) {
  for (const text of [LOADING, EMPTY, ERROR]) {
    if (text === visible) expect(screen.getByText(text)).toBeInTheDocument();
    else expect(screen.queryByText(text)).not.toBeInTheDocument();
  }
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the states of the margin page", () => {
  it("shows only the loading state while the request is pending", async () => {
    installRoutes({ "GET /margin": () => new Promise<FakeReply>(() => {}) });

    renderAuthenticated(<MarginPage />);

    expect(await screen.findByText(LOADING)).toBeInTheDocument();
    expectOnly(LOADING);
    expect(screen.getByRole("status")).toHaveTextContent(LOADING);
  });

  it("shows only the empty state when there is no margin for the period", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin({ campaigns: [] })) });

    renderAuthenticated(<MarginPage />);

    await waitFor(() => expect(screen.getByText(EMPTY)).toBeInTheDocument());
    expectOnly(EMPTY);
    expect(screen.queryByRole("region", { name: "Totales del periodo" })).not.toBeInTheDocument();
  });

  it("shows only the error state, as an alert, when the request fails", async () => {
    installRoutes({ "GET /margin": () => reply(500, { code: "internal_error", message: "x" }) });

    renderAuthenticated(<MarginPage />);

    await waitFor(() => expect(screen.getByText(ERROR)).toBeInTheDocument());
    expectOnly(ERROR);
    expect(screen.getByRole("alert")).toHaveTextContent(ERROR);
  });

  it("shows neither the empty nor the error state once there is margin", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin()) });

    renderAuthenticated(<MarginPage />);

    expect(await screen.findByRole("region", { name: "Totales del periodo" })).toBeInTheDocument();
    expectOnly(null);
  });

  it("keeps the filters on screen in every state so that the period can be changed", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin({ campaigns: [] })) });

    renderAuthenticated(<MarginPage />);

    await screen.findByText(EMPTY);
    expect(screen.getByLabelText("Año")).toBeInTheDocument();
    expect(screen.getByLabelText("Mes")).toBeInTheDocument();
    expect(screen.getByLabelText("Campaña")).toBeInTheDocument();
  });

  it("asks nothing of the server before the session is authenticated", async () => {
    const requests = installRoutes({ "GET /margin": () => reply(200, margin()) });

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("region", { name: "Totales del periodo" });

    expect(requests.map((request) => `${request.method} ${request.path}`)).toEqual(["GET /margin"]);
  });
});
