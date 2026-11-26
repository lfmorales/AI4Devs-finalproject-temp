import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AuthenticatedLayout from "@/app/(authenticated)/layout";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";
import { installRoutes, rolesRoutes } from "../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({ getUserManager: () => ({ getUser: vi.fn().mockResolvedValue({ access_token: "token", expired: false }), removeUser: vi.fn() }) }));

afterEach(() => vi.unstubAllGlobals());
vi.mock("next/navigation", () => ({ usePathname: () => "/status" }));

const ALL_PAGES = ["/campaigns", "/status", "/margin", "/billing", "/exceptions", "/dsp-catalog"] as const;
const LABELS: Record<(typeof ALL_PAGES)[number], string> = {
  "/campaigns": "Campañas",
  "/status": "Estado",
  "/margin": "Margen",
  "/billing": "Facturación",
  "/exceptions": "Excepciones",
  "/dsp-catalog": "Catálogo Adform",
};

/** The pages the access matrix opens to each role; the backend answers 403 for every other one. */
const ROLE_PAGES = {
  operations: ALL_PAGES,
  finance: ["/campaigns", "/status", "/margin", "/billing"],
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

/**
 * The safety net: a session whose roles open every link, as when the roles are stale, and a backend that refuses
 * the pages the profile may not open. The links of the refused pages must go.
 */
function renderAs(roles: Role[]) {
  const allowed = pagesOf(roles);
  installRoutes(rolesRoutes());
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

describe("the navigation, as a safety net, once the backend has refused the pages a profile may not open", () => {
  it.each([
    [["operations"], ["Campañas", "Estado", "Margen", "Facturación", "Excepciones", "Catálogo Adform"]],
    [["finance"], ["Campañas", "Estado", "Margen", "Facturación"]],
    [["business"], ["Campañas", "Estado"]],
    [["trading"], ["Estado"]],
    [["finance", "trading"], ["Campañas", "Estado", "Margen", "Facturación"]],
    [["business", "trading"], ["Campañas", "Estado"]],
    [["business", "finance"], ["Campañas", "Estado", "Margen", "Facturación"]],
  ] as [Role[], string[]][])("for %s shows %j", async (roles, expected) => {
    const nav = renderAs(roles);

    await waitFor(() => expect(nav.getAllByRole("link").map((link) => link.textContent)).toEqual(expected));
    for (const page of ALL_PAGES) {
      const shown = nav.queryByRole("link", { name: LABELS[page] }) !== null;
      expect(shown).toBe(expected.includes(LABELS[page]));
    }
  });
});
