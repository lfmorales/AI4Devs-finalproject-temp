import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AuthenticatedLayout from "@/app/(authenticated)/layout";
import StatusPage from "@/app/(authenticated)/status/page";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { installRoutes, reply } from "../../helpers/api-pages";

// A stand-in for oidc-client-ts that behaves like the real one where it matters here: removeUser raises userUnloaded.
const manager = vi.hoisted(() => {
  const unloaded: (() => void)[] = [];
  const state = { user: null as unknown };
  return {
    unloaded,
    state,
    api: {
      getUser: async () => state.user,
      removeUser: async () => {
        state.user = null;
        unloaded.forEach((handler) => handler());
      },
      signinRedirect: async () => {},
      events: {
        addUserLoaded: () => {},
        removeUserLoaded: () => {},
        addUserUnloaded: (handler: () => void) => unloaded.push(handler),
        removeUserUnloaded: (handler: () => void) => unloaded.splice(unloaded.indexOf(handler), 1),
        addSilentRenewError: () => {},
        removeSilentRenewError: () => {},
      },
    },
  };
});

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => manager.api,
  getLogoutUrl: () => "http://cognito.example/logout",
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/status" }));

const assign = vi.fn();

function renderApp() {
  return render(
    <AuthProvider>
      <AuthenticatedLayout>
        <StatusPage />
      </AuthenticatedLayout>
    </AuthProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  manager.unloaded.length = 0;
  manager.state.user = { id_token: "token", expired: false, profile: { email: "user@example.com" } };
  Object.defineProperty(window, "location", { value: { assign }, configurable: true });
});
afterEach(() => vi.unstubAllGlobals());

describe("signing out", () => {
  it("is a voluntary exit: no session-expired page, and the sign-in button is offered", async () => {
    const user = userEvent.setup();
    installRoutes({ "GET /campaign-status": () => reply(200, []) });
    renderApp();
    await screen.findByText("No hay campañas en curso");

    await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => expect(screen.getByText("Por favor, inicia sesión")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Iniciar sesión" })).toBeInTheDocument();
    expect(screen.queryByText("Sesión caducada")).not.toBeInTheDocument();
    expect(assign).toHaveBeenCalledWith("http://cognito.example/logout");
  });
});

describe("losing the session without signing out", () => {
  it("still shows the session-expired page when the API answers 401", async () => {
    installRoutes({ "GET /campaign-status": () => reply(401, { code: "invalid_token", message: "x" }) });

    renderApp();

    await waitFor(() => expect(screen.getByText("Sesión caducada")).toBeInTheDocument());
    expect(screen.queryByText("Por favor, inicia sesión")).not.toBeInTheDocument();
  });

  it("still shows the session-expired page when the user is unloaded by the library", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, []) });
    renderApp();
    await screen.findByText("No hay campañas en curso");

    await act(async () => manager.unloaded.forEach((handler) => handler()));

    expect(screen.getByText("Sesión caducada")).toBeInTheDocument();
  });
});
