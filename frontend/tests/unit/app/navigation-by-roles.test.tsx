import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AuthenticatedLayout from "@/app/(authenticated)/layout";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";
import { NAVIGATION_LINKS } from "@/lib/auth/navigation";
import { installRoutes, reply, type FakeReply } from "../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ access_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/status" }));

type Role = "operations" | "business" | "finance" | "trading";

/** The one table of the specification: which roles open which link. */
const LINKS_BY_ROLE: Record<string, Role[]> = {
  Campañas: ["operations", "business", "finance"],
  Estado: ["operations", "business", "finance", "trading"],
  Excepciones: ["operations"],
  "Catálogo Adform": ["operations"],
  Margen: ["operations", "finance"],
};
const ORDER = ["Campañas", "Estado", "Margen", "Excepciones", "Catálogo Adform"];

function expectedFor(roles: Role[]): string[] {
  return ORDER.filter((label) => LINKS_BY_ROLE[label]!.some((role) => roles.includes(role)));
}

const SESSION: AuthContextValue["session"] = { status: "authenticated", email: "user@example.com", bearerToken: "token" };

function layoutAs(session: AuthContextValue["session"], children: React.ReactNode = <div>content</div>) {
  const value: AuthContextValue = { session, signIn: vi.fn(), signOut: vi.fn() };
  return (
    <AuthContext.Provider value={value}>
      <AuthenticatedLayout>{children}</AuthenticatedLayout>
    </AuthContext.Provider>
  );
}

const rolesRoute = (roles: Role[]) => () => reply(200, { roles });
const navigation = () => within(screen.getByRole("navigation", { name: "Principal" }));
const linkTexts = () => navigation().queryAllByRole("link").map((link) => link.textContent);

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the table of links by role", () => {
  it("is the table of the specification", () => {
    const table = Object.fromEntries(NAVIGATION_LINKS.map((link) => [link.label, [...link.roles].sort()]));

    expect(table).toEqual(Object.fromEntries(Object.entries(LINKS_BY_ROLE).map(([label, roles]) => [label, [...roles].sort()])));
    expect(NAVIGATION_LINKS.map((link) => link.label)).toEqual(ORDER);
  });
});

describe("the navigation driven by GET /users/me", () => {
  it.each([
    [["operations"]],
    [["business"]],
    [["finance"]],
    [["trading"]],
    [["finance", "trading"]],
    [["business", "finance"]],
    [["business", "trading"]],
    [["operations", "trading"]],
  ] as [Role[]][])("for %j shows exactly the links of the table", async (roles) => {
    installRoutes({ "GET /users/me": rolesRoute(roles) });

    render(layoutAs(SESSION));

    await waitFor(() => expect(linkTexts()).toEqual(expectedFor(roles)));
  });

  it("asks for the roles once, as soon as there is a valid session", async () => {
    const requests = installRoutes({ "GET /users/me": rolesRoute(["operations"]) });

    render(layoutAs(SESSION));
    await waitFor(() => expect(linkTexts()).toHaveLength(5));

    expect(requests.filter((request) => request.path === "/users/me")).toHaveLength(1);
  });

  it("shows no link while the roles load", async () => {
    let release: (answer: FakeReply) => void = () => {};
    const requests = installRoutes({ "GET /users/me": () => new Promise<FakeReply>((resolve) => (release = resolve)) });

    render(layoutAs(SESSION));
    await waitFor(() => expect(requests).toHaveLength(1));

    expect(navigation().queryAllByRole("link")).toHaveLength(0);
    release(reply(200, { roles: ["trading"] }));
    await waitFor(() => expect(linkTexts()).toEqual(["Estado"]));
  });

  it("says the permissions could not be loaded when the call fails, and shows nothing else", async () => {
    installRoutes({ "GET /users/me": () => reply(500, { code: "internal_error", message: "x" }) });

    render(layoutAs(SESSION));

    expect(await screen.findByText("No se han podido cargar tus permisos")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(screen.queryByText("content")).not.toBeInTheDocument();
    expect(navigation().queryAllByRole("link")).toHaveLength(0);
  });

  it("retries the call when 'Reintentar' is pressed", async () => {
    const user = userEvent.setup();
    const answers = [reply(503, { code: "x", message: "x" }), reply(200, { roles: ["finance"] })];
    const requests = installRoutes({ "GET /users/me": () => answers.shift()! });

    render(layoutAs(SESSION));
    await user.click(await screen.findByRole("button", { name: "Reintentar" }));

    await waitFor(() => expect(linkTexts()).toEqual(["Campañas", "Estado", "Margen"]));
    expect(screen.getByText("content")).toBeInTheDocument();
    expect(requests.filter((request) => request.path === "/users/me")).toHaveLength(2);
  });

  it.each([
    ["an empty list", () => reply(200, { roles: [] })],
    ["a 403", () => reply(403, { code: "missing_role", message: "x" })],
  ])("says the user has no profile for %s, with no link", async (_name, answer) => {
    installRoutes({ "GET /users/me": answer });

    render(layoutAs(SESSION));

    expect(await screen.findByText("Tu usuario no tiene ningún perfil asignado")).toBeInTheDocument();
    expect(navigation().queryAllByRole("link")).toHaveLength(0);
    expect(screen.queryByText("content")).not.toBeInTheDocument();
    expect(screen.queryByText("No se han podido cargar tus permisos")).not.toBeInTheDocument();
  });

  it("hides the link of a page refused with a 403 even though the role allows it", async () => {
    installRoutes({ "GET /users/me": rolesRoute(["operations"]) });
    function Refused() {
      useReportForbidden("/margin", true);
      return null;
    }

    render(layoutAs(SESSION, <Refused />));

    await waitFor(() => expect(linkTexts()).toEqual(["Campañas", "Estado", "Excepciones", "Catálogo Adform"]));
  });

  it("keeps the roles out of every browser storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    installRoutes({ "GET /users/me": rolesRoute(["operations", "finance"]) });

    render(layoutAs(SESSION));
    await waitFor(() => expect(linkTexts()).toHaveLength(5));

    expect(setItem).not.toHaveBeenCalled();
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    setItem.mockRestore();
  });

  it("forgets the roles when the session ends and asks again for the next one", async () => {
    const answers = [reply(200, { roles: ["operations"] }), reply(200, { roles: ["trading"] })];
    const requests = installRoutes({ "GET /users/me": () => answers.shift()! });

    const { rerender } = render(layoutAs(SESSION));
    await waitFor(() => expect(linkTexts()).toHaveLength(5));

    rerender(layoutAs({ status: "unauthenticated" }));
    expect(screen.queryByRole("navigation", { name: "Principal" })).not.toBeInTheDocument();

    rerender(layoutAs(SESSION));
    expect(navigation().queryAllByRole("link")).toHaveLength(0);
    await waitFor(() => expect(linkTexts()).toEqual(["Estado"]));
    expect(requests.filter((request) => request.path === "/users/me")).toHaveLength(2);
  });

  it("forgets the roles when the session expires", async () => {
    installRoutes({ "GET /users/me": rolesRoute(["operations"]) });

    const { rerender } = render(layoutAs(SESSION));
    await waitFor(() => expect(linkTexts()).toHaveLength(5));

    rerender(layoutAs({ status: "session_expired" }));

    expect(screen.getByText("Sesión caducada")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Principal" })).not.toBeInTheDocument();
  });
});
