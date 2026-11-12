import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AuthenticatedLayout from "@/app/(authenticated)/layout";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";

vi.mock("@/lib/auth/user-manager", () => ({ getUserManager: () => ({ getUser: vi.fn(), removeUser: vi.fn() }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/status" }));

const ALL_PAGES = ["/campaigns", "/status", "/margin", "/exceptions", "/dsp-catalog"] as const;
const LABELS: Record<(typeof ALL_PAGES)[number], string> = {
  "/campaigns": "Campañas",
  "/status": "Estado",
  "/margin": "Margen",
  "/exceptions": "Excepciones",
  "/dsp-catalog": "Catálogo Adform",
};

/** The pages the access matrix opens to each role; the backend answers 403 for every other one. */
const ROLE_PAGES = {
  operations: ALL_PAGES,
  finance: ["/campaigns", "/status", "/margin"],
  business: ["/campaigns", "/status"],
  trading: ["/status"],
} as const;
type Role = keyof typeof ROLE_PAGES;

/** The pages a user holding these roles may open: the union of what each role opens. */
function pagesOf(roles: Role[]): string[] {
  return ALL_PAGES.filter((page) => roles.some((role) => (ROLE_PAGES[role] as readonly string[]).includes(page)));
}

function Refused({ path }: { path: string }) {
  useReportForbidden(path, true);
  return null;
}

function renderAs(roles: Role[]) {
  const allowed = pagesOf(roles);
  const value: AuthContextValue = {
    session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
    signIn: vi.fn(),
    signOut: vi.fn(),
  };
  render(
    <AuthContext.Provider value={value}>
      <AuthenticatedLayout>
        {ALL_PAGES.filter((page) => !allowed.includes(page)).map((page) => <Refused key={page} path={page} />)}
      </AuthenticatedLayout>
    </AuthContext.Provider>,
  );
  return within(screen.getByRole("navigation", { name: "Principal" }));
}

describe("the navigation once the backend has refused the pages a profile may not open", () => {
  it.each([
    [["operations"], ["Campañas", "Estado", "Margen", "Excepciones", "Catálogo Adform"]],
    [["finance"], ["Campañas", "Estado", "Margen"]],
    [["business"], ["Campañas", "Estado"]],
    [["trading"], ["Estado"]],
    [["finance", "trading"], ["Campañas", "Estado", "Margen"]],
    [["business", "trading"], ["Campañas", "Estado"]],
    [["business", "finance"], ["Campañas", "Estado", "Margen"]],
  ] as [Role[], string[]][])("for %s shows %j", (roles, expected) => {
    const nav = renderAs(roles);

    expect(nav.getAllByRole("link").map((link) => link.textContent)).toEqual(expected);
    for (const page of ALL_PAGES) {
      const shown = nav.queryByRole("link", { name: LABELS[page] }) !== null;
      expect(shown).toBe(expected.includes(LABELS[page]));
    }
  });
});
