import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import HomePage from "@/app/page";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import { firstPageFor } from "@/lib/auth/navigation";
import { installRoutes, reply } from "../../helpers/api-pages";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace }) }));
vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({ getUser: vi.fn().mockResolvedValue({ access_token: "token", expired: false }), removeUser: vi.fn() }),
}));

const value: AuthContextValue = {
  session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
  signIn: vi.fn(),
  signOut: vi.fn(),
};

function renderHome() {
  return render(<AuthContext.Provider value={value}><HomePage /></AuthContext.Provider>);
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the page after signing in leads to the first screen the user can see", () => {
  it.each([
    [["operations"], "/campaigns"],
    [["business"], "/campaigns"],
    [["finance"], "/campaigns"],
    [["trading"], "/status"],
    [["trading", "finance"], "/campaigns"],
  ])("for %j goes to %s", async (roles, expected) => {
    installRoutes({ "GET /users/me": () => reply(200, { roles }) });

    renderHome();

    await waitFor(() => expect(replace).toHaveBeenCalledWith(expected));
    expect(replace).toHaveBeenCalledTimes(1);
  });

  it("goes nowhere while the roles load", () => {
    installRoutes({ "GET /users/me": () => new Promise(() => {}) });

    renderHome();

    expect(replace).not.toHaveBeenCalled();
  });

  it("goes nowhere and explains when the user has no profile", async () => {
    installRoutes({ "GET /users/me": () => reply(200, { roles: [] }) });

    renderHome();

    expect(await screen.findByText("Tu usuario no tiene ningún perfil asignado")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("goes nowhere and offers a retry when the permissions cannot be loaded", async () => {
    installRoutes({ "GET /users/me": () => reply(500, { code: "x", message: "x" }) });

    renderHome();

    expect(await screen.findByText("No se han podido cargar tus permisos")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("has no first page for no roles", () => {
    expect(firstPageFor([])).toBeNull();
  });
});
