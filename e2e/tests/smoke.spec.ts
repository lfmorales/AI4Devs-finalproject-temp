import { expect, test } from "@playwright/test";

test.describe("without a session", () => {
  test("the home page offers to sign in", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "AdOps360" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Iniciar sesión" })).toBeVisible();
  });

  test("a guarded page asks to sign in", async ({ page }) => {
    await page.goto("/status");

    await expect(page.getByRole("heading", { name: "Por favor, inicia sesión" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Iniciar sesión" })).toBeVisible();
  });
});
