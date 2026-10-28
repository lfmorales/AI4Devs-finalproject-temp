import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AuthenticatedLayout from "@/app/(authenticated)/layout";
import MarginPage from "@/app/(authenticated)/margin/page";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import { installRoutes, reply } from "../../../helpers/api-pages";
import { campaign, flight, line, margin } from "../../../helpers/margin-data";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/margin" }));

function renderLayout(children: React.ReactNode) {
  const value: AuthContextValue = {
    session: { status: "authenticated", email: "user@example.com", idToken: "token" },
    signIn: vi.fn(),
    signOut: vi.fn(),
  };
  return render(<AuthContext.Provider value={value}><AuthenticatedLayout>{children}</AuthenticatedLayout></AuthContext.Provider>);
}

const forbidden = () => reply(403, { code: "missing_role", message: "x" });
const unauthenticated = () => reply(401, { code: "unauthenticated", message: "x" });

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the margin link", () => {
  it("is in the navigation of the authenticated layout, pointing to the margin page", () => {
    installRoutes({ "GET /margin": () => reply(200, margin()) });

    renderLayout(<div>content</div>);

    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).getByRole("link", { name: "Margen" })).toHaveAttribute("href", "/margin");
  });

  it("is shown while the page has not been refused: roles are not decoded in the browser", async () => {
    installRoutes({ "GET /margin": () => reply(200, margin()) });

    renderLayout(<MarginPage />);

    await screen.findByRole("region", { name: "Totales del periodo" });
    expect(within(screen.getByRole("navigation", { name: "Principal" })).getByRole("link", { name: "Margen" })).toBeInTheDocument();
  });

  it("disappears once the backend answers 403, and the other links stay", async () => {
    installRoutes({ "GET /margin": forbidden });

    renderLayout(<MarginPage />);

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
    const nav = screen.getByRole("navigation", { name: "Principal" });
    await waitFor(() => expect(within(nav).queryByRole("link", { name: "Margen" })).not.toBeInTheDocument());
    expect(within(nav).getByRole("link", { name: "Campañas" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Estado" })).toBeInTheDocument();
  });
});

describe("a user without the finance role", () => {
  it("sees 'Acceso denegado' with a message about the margin, and no figure", async () => {
    installRoutes({ "GET /margin": forbidden });

    renderLayout(<MarginPage />);

    expect(await screen.findByText("Acceso denegado")).toBeInTheDocument();
    expect(screen.getByText("No tienes permiso para ver el margen.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Totales del periodo" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cerrar mes" })).not.toBeInTheDocument();
  });
});

describe("an expired session", () => {
  it("leads to 'Sesión caducada' when the page answers 401", async () => {
    installRoutes({ "GET /margin": unauthenticated });

    renderLayout(<MarginPage />);

    expect(await screen.findByText("Sesión caducada")).toBeInTheDocument();
    expect(screen.queryByText("Acceso denegado")).not.toBeInTheDocument();
  });
});

describe("the closing and the access", () => {
  async function closeAugust() {
    const user = userEvent.setup();
    await screen.findByRole("region", { name: "Totales del periodo" });
    await user.type(screen.getByLabelText("Año"), "2026");
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
    await user.click(screen.getByRole("button", { name: "Cerrar mes" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirmar cierre" }));
  }

  const pendingClose = () =>
    margin({ campaigns: [campaign({ lines: [line({ flights: [flight({ state: "pending_close" })] })] })] });

  function routesWithClosing(closing: () => ReturnType<typeof reply>) {
    return {
      "GET /margin": () => reply(200, margin()),
      "GET /margin?year=2026&month=8": () => reply(200, pendingClose()),
      "POST /margin/closings": closing,
    };
  }

  it("leads to 'Acceso denegado' and hides the link when the closing answers 403", async () => {
    installRoutes(routesWithClosing(forbidden));

    renderLayout(<MarginPage />);
    await closeAugust();

    expect(await screen.findByText("Acceso denegado")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Principal" });
    await waitFor(() => expect(within(nav).queryByRole("link", { name: "Margen" })).not.toBeInTheDocument());
  });

  it("leads to 'Sesión caducada' when the closing answers 401", async () => {
    installRoutes(routesWithClosing(unauthenticated));

    renderLayout(<MarginPage />);
    await closeAugust();

    expect(await screen.findByText("Sesión caducada")).toBeInTheDocument();
  });
});
