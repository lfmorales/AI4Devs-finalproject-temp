import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import CampaignsPage from "@/app/(authenticated)/campaigns/page";
import MarginPage from "@/app/(authenticated)/margin/page";
import { installRoutes, renderAuthenticated, reply } from "../../helpers/api-pages";
import { margin } from "../../helpers/margin-data";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({ getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }), removeUser: vi.fn() }),
}));

type Role = "operations" | "business" | "finance" | "trading";

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("'Nueva campaña'", () => {
  it.each([
    [["operations"], true],
    [["business"], false],
    [["finance"], false],
    [["business", "finance"], false],
    [["operations", "finance"], true],
  ] as [Role[], boolean][])("for %j is shown: %s", async (roles, shown) => {
    installRoutes({ "GET /campaigns": () => reply(200, []) });

    renderAuthenticated(<CampaignsPage />, { roles });

    await screen.findByRole("heading", { name: "Campañas" });
    await waitFor(() => expect(screen.queryByText("Todavía no hay campañas registradas.")).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: "Nueva campaña" }) !== null).toBe(shown);
  });

  it("is hidden while the roles are not known", async () => {
    installRoutes({ "GET /campaigns": () => reply(200, []) });

    renderAuthenticated(<CampaignsPage />, { roles: null });

    await screen.findByRole("heading", { name: "Campañas" });
    expect(screen.queryByRole("link", { name: "Nueva campaña" })).not.toBeInTheDocument();
  });
});

describe("'Cerrar mes'", () => {
  it.each([
    [["operations"], true],
    [["finance"], true],
    [["operations", "finance"], true],
    [["business"], false],
    [["trading"], false],
    [["business", "trading"], false],
  ] as [Role[], boolean][])("for %j is shown: %s", async (roles, shown) => {
    installRoutes({ "GET /margin": () => reply(200, margin()) });

    renderAuthenticated(<MarginPage />, { roles });

    await screen.findByRole("region", { name: "Totales del periodo" });
    expect(screen.queryByRole("button", { name: "Cerrar mes" }) !== null).toBe(shown);
  });
});
