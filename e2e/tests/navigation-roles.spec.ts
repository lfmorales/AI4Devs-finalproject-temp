import { expect, failApiCalls, test } from "../support/fixtures";

const LINKS = ["Campañas", "Estado", "Margen", "Facturación", "Excepciones", "Catálogo Adform"];

// The session is the E2E operations user's (see roles-matrix.spec.ts for the other profiles): under the access matrix
// operations sees the six links.
test.describe("the navigation of the operations user", () => {
  test("has the six links", async ({ operationsSession: page }) => {
    await page.goto("/status");

    const navigation = page.getByRole("navigation", { name: "Principal" });
    await expect(navigation.getByRole("link")).toHaveCount(LINKS.length);
    for (const name of LINKS) await expect(navigation.getByRole("link", { name })).toBeVisible();
  });

  test("shows 'Acceso denegado' and drops the Margen link when the margin answers 403", async ({ operationsSession: page }) => {
    await failApiCalls(page, "/margin", 403);

    await page.goto("/margin");

    await expect(page.getByRole("heading", { name: "Acceso denegado" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Margen" })).toHaveCount(0);
  });

  test("shows 'Sesión caducada' when the margin answers 401", async ({ operationsSession: page }) => {
    await failApiCalls(page, "/margin", 401);

    await page.goto("/margin");

    await expect(page.getByRole("heading", { name: "Sesión caducada" })).toBeVisible();
  });
});
