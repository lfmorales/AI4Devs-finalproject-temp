import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AuthenticatedLayout from "@/app/(authenticated)/layout";
import CampaignsPage from "@/app/(authenticated)/campaigns/page";
import ExceptionsPage from "@/app/(authenticated)/exceptions/page";
import StatusPage from "@/app/(authenticated)/status/page";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import { installRoutes, reply } from "../../helpers/api-pages";

const removeUser = vi.fn();

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser,
  }),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/status" }));

function renderLayout(children: React.ReactNode, session: AuthContextValue["session"] = {
  status: "authenticated", email: "user@example.com", idToken: "token",
}) {
  const value: AuthContextValue = { session, signIn: vi.fn(), signOut: vi.fn() };
  return render(
    <AuthContext.Provider value={value}>
      <AuthenticatedLayout>{children}</AuthenticatedLayout>
    </AuthContext.Provider>,
  );
}

const forbidden = () => reply(403, { code: "missing_role", message: "x" });

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the navigation of the authenticated layout", () => {
  it("links campaigns, status and exceptions, and has the sign-out button", () => {
    renderLayout(<div>content</div>);

    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).getByRole("link", { name: "Campañas" })).toHaveAttribute("href", "/campaigns");
    expect(within(nav).getByRole("link", { name: "Estado" })).toHaveAttribute("href", "/status");
    expect(within(nav).getByRole("link", { name: "Excepciones" })).toHaveAttribute("href", "/exceptions");
    expect(within(nav).getByRole("button", { name: "Cerrar sesión" })).toBeInTheDocument();
  });

  it("signs out when the button is pressed", async () => {
    const user = userEvent.setup();
    renderLayout(<div>content</div>);

    await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(removeUser).toHaveBeenCalledTimes(1);
  });

  it("shows no navigation to someone who is not signed in", () => {
    renderLayout(<div>content</div>, { status: "unauthenticated" });

    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("shows every link until the backend says no, whatever the token holds", async () => {
    installRoutes({ "GET /campaign-status": () => reply(200, []) });

    renderLayout(<StatusPage />);

    await screen.findByText("No hay campañas en curso");
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).getAllByRole("link")).toHaveLength(3);
  });

  it("hides the exceptions link once the exception queue answers 403, and keeps the others", async () => {
    installRoutes({ "GET /ingestion-exceptions?status=open": forbidden });

    renderLayout(<ExceptionsPage />);

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).queryByRole("link", { name: "Excepciones" })).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Estado" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Campañas" })).toBeInTheDocument();
  });

  it("hides the status link once the status page answers 403", async () => {
    installRoutes({ "GET /campaign-status": forbidden });

    renderLayout(<StatusPage />);

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).queryByRole("link", { name: "Estado" })).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Excepciones" })).toBeInTheDocument();
  });

  it("hides the campaigns link once the campaigns page answers 403", async () => {
    installRoutes({ "GET /campaigns": forbidden });

    renderLayout(<CampaignsPage />);

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).queryByRole("link", { name: "Campañas" })).not.toBeInTheDocument();
  });

  it("does not hide a link after a 401, which is about the session and not about roles", async () => {
    installRoutes({ "GET /campaign-status": () => reply(401, { code: "invalid_token", message: "x" }) });

    renderLayout(<StatusPage />);

    await waitFor(() => expect(screen.getByText("Sesión caducada")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Estado" })).toBeInTheDocument();
  });

  it("leaves a single sign-out button on the campaigns page", async () => {
    installRoutes({ "GET /campaigns": () => reply(200, []) });

    renderLayout(<CampaignsPage />);

    await screen.findByText(/todavía no hay campañas/i);
    expect(screen.getAllByRole("button", { name: "Cerrar sesión" })).toHaveLength(1);
  });
});
