import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import AuthenticatedLayout from "@/app/(authenticated)/layout";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import { installRoutes, rolesRoutes } from "../../helpers/api-pages";

const pathname = vi.fn<() => string | null>();

vi.mock("next/navigation", () => ({ usePathname: () => pathname() }));
vi.mock("@/lib/auth/user-manager", () => ({ getUserManager: () => ({ getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }), removeUser: vi.fn() }) }));

/** The navigation of an operations user, once its roles have loaded. */
async function renderAt(path: string | null) {
  pathname.mockReturnValue(path);
  installRoutes(rolesRoutes(["operations"]));
  const value: AuthContextValue = {
    session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
    signIn: vi.fn(), signOut: vi.fn(),
  };
  render(<AuthContext.Provider value={value}><AuthenticatedLayout><div>content</div></AuthenticatedLayout></AuthContext.Provider>);
  const nav = screen.getByRole("navigation", { name: "Principal" });
  await within(nav).findByRole("link", { name: "Estado" });
  return nav;
}

afterEach(() => vi.unstubAllGlobals());

describe("the current page in the navigation", () => {
  it("marks the link of the current page with aria-current=page and no other", async () => {
    const nav = await renderAt("/exceptions");

    expect(within(nav).getByRole("link", { name: "Excepciones" })).toHaveAttribute("aria-current", "page");
    for (const name of ["Campañas", "Estado", "Catálogo Adform"]) {
      expect(within(nav).getByRole("link", { name })).not.toHaveAttribute("aria-current");
    }
  });

  it("keeps the section marked on a sub-page", async () => {
    const nav = await renderAt("/campaigns/new");

    expect(within(nav).getByRole("link", { name: "Campañas" })).toHaveAttribute("aria-current", "page");
  });

  it("does not mark a section whose name only starts the same way", async () => {
    const nav = await renderAt("/campaigns-archive");

    expect(within(nav).queryByRole("link", { current: "page" })).not.toBeInTheDocument();
  });

  it("marks nothing when the path is unknown", async () => {
    const nav = await renderAt(null);

    expect(within(nav).queryByRole("link", { current: "page" })).not.toBeInTheDocument();
  });
});
