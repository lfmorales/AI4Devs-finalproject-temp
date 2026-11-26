import type { RoleName } from "../support/e2e-users";
import { type E2eUserName, expect, signInAs, test } from "../support/fixtures";

// Each profile is its own E2E user, seeded with exactly its roles by the global setup: no case changes any user's
// roles, so the cases are independent of each other and of their order.
const PAGES = [
  { link: "Campañas", path: "/campaigns", api: /\/api\/campaigns(\?|$)/ },
  { link: "Estado", path: "/status", api: /\/api\/campaign-status(\?|$)/ },
  { link: "Margen", path: "/margin", api: /\/api\/margin(\?|$)/ },
  // The billing reads nothing until a month is chosen: the screen itself is what answers.
  { link: "Facturación", path: "/billing", api: null },
  { link: "Excepciones", path: "/exceptions", api: /\/api\/ingestion-exceptions(\?|$)/ },
  { link: "Catálogo Adform", path: "/dsp-catalog", api: /\/api\/dsp-catalog(\?|$)/ },
] as const;
type Page = (typeof PAGES)[number];

/** The access matrix, page by page: the pages each role may open. */
const OPENS: Record<RoleName, readonly string[]> = {
  operations: PAGES.map((page) => page.path),
  finance: ["/campaigns", "/status", "/margin", "/billing"],
  business: ["/campaigns", "/status"],
  trading: ["/status"],
};

const PROFILES: { name: string; user: E2eUserName; roles: RoleName[] }[] = [
  { name: "operations", user: "operations", roles: ["operations"] },
  { name: "finance", user: "finance", roles: ["finance"] },
  { name: "business", user: "business", roles: ["business"] },
  { name: "trading", user: "trading", roles: ["trading"] },
  { name: "finance and trading, the union of both", user: "finance-trading", roles: ["finance", "trading"] },
  { name: "business and trading, the union of both", user: "business-trading", roles: ["business", "trading"] },
];

const allowedFor = (roles: RoleName[]): Page[] => PAGES.filter((page) => roles.some((role) => OPENS[role].includes(page.path)));

test.describe("the pages each profile may open, each with its own E2E user and the roles held in the database", () => {
  for (const profile of PROFILES) {
    test(`${profile.name}: the links shown on sign-in, 'Acceso denegado' on the rest by direct URL`, async ({ page }) => {
      const allowed = allowedFor(profile.roles);
      const refused = PAGES.filter((candidate) => !allowed.includes(candidate));
      await signInAs(page, profile.user);

      const navigation = page.getByRole("navigation", { name: "Principal" });

      // The daily status is open to every role: it is where every profile starts.
      const start = page.waitForResponse(PAGES[1].api);
      await page.goto("/status");
      expect((await start).status()).toBe(200);
      await expect(navigation).toBeVisible();

      // The navigation shows, as soon as the session starts, exactly the links the roles of the profile open.
      await expect(navigation.getByRole("link")).toHaveCount(allowed.length);
      for (const target of PAGES) {
        await expect(navigation.getByRole("link", { name: target.link })).toHaveCount(allowed.includes(target) ? 1 : 0);
      }

      // Each page the profile may open is reached through its link and the backend serves it.
      for (const target of allowed.filter((candidate) => candidate.path !== "/status")) {
        if (target.api === null) {
          await navigation.getByRole("link", { name: target.link }).click();
          await expect(page.getByRole("heading", { level: 1, name: target.link })).toBeVisible();
          continue;
        }
        const response = page.waitForResponse(target.api);
        await navigation.getByRole("link", { name: target.link }).click();
        expect((await response).status(), `${target.path} for ${profile.name}`).toBe(200);
      }

      // A page the profile may not open has no link, so it is reached by direct URL only: the backend still refuses it.
      for (const target of refused) {
        await page.goto(target.path);
        await expect(page.getByRole("heading", { name: "Acceso denegado" })).toBeVisible();
      }
    });
  }
});
