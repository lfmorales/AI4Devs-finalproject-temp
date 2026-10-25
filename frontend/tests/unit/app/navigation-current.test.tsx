import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import AuthenticatedLayout from "@/app/(authenticated)/layout";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";

const pathname = vi.fn<() => string | null>();

vi.mock("next/navigation", () => ({ usePathname: () => pathname() }));

function renderAt(path: string | null) {
  pathname.mockReturnValue(path);
  const value: AuthContextValue = {
    session: { status: "authenticated", email: "user@example.com", idToken: "token" },
    signIn: vi.fn(), signOut: vi.fn(),
  };
  render(<AuthContext.Provider value={value}><AuthenticatedLayout><div>content</div></AuthenticatedLayout></AuthContext.Provider>);
  return screen.getByRole("navigation", { name: "Principal" });
}

describe("the current page in the navigation", () => {
  it("marks the link of the current page with aria-current=page and no other", () => {
    const nav = renderAt("/exceptions");

    expect(within(nav).getByRole("link", { name: "Excepciones" })).toHaveAttribute("aria-current", "page");
    for (const name of ["Campañas", "Estado", "Catálogo Adform"]) {
      expect(within(nav).getByRole("link", { name })).not.toHaveAttribute("aria-current");
    }
  });

  it("keeps the section marked on a sub-page", () => {
    const nav = renderAt("/campaigns/new");

    expect(within(nav).getByRole("link", { name: "Campañas" })).toHaveAttribute("aria-current", "page");
  });

  it("does not mark a section whose name only starts the same way", () => {
    const nav = renderAt("/campaigns-archive");

    expect(within(nav).queryByRole("link", { current: "page" })).not.toBeInTheDocument();
  });

  it("marks nothing when the path is unknown", () => {
    const nav = renderAt(null);

    expect(within(nav).queryByRole("link", { current: "page" })).not.toBeInTheDocument();
  });
});
