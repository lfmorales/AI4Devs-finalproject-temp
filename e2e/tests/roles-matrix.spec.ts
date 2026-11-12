import { expect, test } from "../support/fixtures";
import { restoreRolesIfBackedUp, type RoleName, withRoles } from "../support/roles";

// The development user keeps its token; only its roles in the database change, and they are read on every request.
// The roles are put back after each case, after the last one, and by the next run's setup if this one is killed.
// The cases change the same user's roles, so they run in this order, one at a time.
test.describe.configure({ mode: "serial" });
test.afterAll(() => {
  restoreRolesIfBackedUp();
});

const PAGES = [
  { link: "Campañas", path: "/campaigns", api: /\/api\/campaigns(\?|$)/ },
  { link: "Estado", path: "/status", api: /\/api\/campaign-status(\?|$)/ },
  { link: "Margen", path: "/margin", api: /\/api\/margin(\?|$)/ },
  { link: "Excepciones", path: "/exceptions", api: /\/api\/ingestion-exceptions(\?|$)/ },
  { link: "Catálogo Adform", path: "/dsp-catalog", api: /\/api\/dsp-catalog(\?|$)/ },
] as const;
type Page = (typeof PAGES)[number];

/** The access matrix, page by page: the pages each role may open. */
const OPENS: Record<RoleName, readonly string[]> = {
  operations: PAGES.map((page) => page.path),
  finance: ["/campaigns", "/status", "/margin"],
  business: ["/campaigns", "/status"],
  trading: ["/status"],
};

const PROFILES: { name: string; roles: RoleName[] }[] = [
  { name: "operations", roles: ["operations"] },
  { name: "finance", roles: ["finance"] },
  { name: "business", roles: ["business"] },
  { name: "trading", roles: ["trading"] },
  { name: "finance and trading, the union of both", roles: ["finance", "trading"] },
  { name: "business and trading, the union of both", roles: ["business", "trading"] },
];

const allowedFor = (roles: RoleName[]): Page[] => PAGES.filter((page) => roles.some((role) => OPENS[role].includes(page.path)));

test.describe("the pages each profile may open, with the roles held in the database", () => {
  for (const profile of PROFILES) {
    test(`${profile.name}: the links shown, 'Acceso denegado' on the rest, also by direct URL`, async ({ financeSession: page }) => {
      const allowed = allowedFor(profile.roles);
      const refused = PAGES.filter((candidate) => !allowed.includes(candidate));

      await withRoles(profile.roles, async () => {
        const navigation = page.getByRole("navigation", { name: "Principal" });

        // The daily status is open to every role: it is where every profile starts.
        const start = page.waitForResponse(PAGES[1].api);
        await page.goto("/status");
        expect((await start).status()).toBe(200);
        await expect(navigation).toBeVisible();

        // The navigation hides a page only after the backend has refused it, so each page is opened through its link.
        for (const target of PAGES.filter((candidate) => candidate.path !== "/status")) {
          const response = page.waitForResponse(target.api);
          await navigation.getByRole("link", { name: target.link }).click();
          expect((await response).status(), `${target.path} for ${profile.name}`).toBe(allowed.includes(target) ? 200 : 403);
          if (!allowed.includes(target)) await expect(page.getByRole("heading", { name: "Acceso denegado" })).toBeVisible();
        }

        await expect(navigation.getByRole("link")).toHaveCount(allowed.length);
        for (const target of PAGES) {
          await expect(navigation.getByRole("link", { name: target.link })).toHaveCount(allowed.includes(target) ? 1 : 0);
        }

        // A direct URL to a page the profile may not open shows the same refusal, in a fresh page load.
        for (const target of refused) {
          await page.goto(target.path);
          await expect(page.getByRole("heading", { name: "Acceso denegado" })).toBeVisible();
        }
      });
    });
  }
});
