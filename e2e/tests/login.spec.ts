import { expect, test } from "@playwright/test";

const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;

test.describe("the real sign-in with Cognito", () => {
  test.skip(!email || !password, "E2E_EMAIL and E2E_PASSWORD are not set in the environment.");

  test("signs in through the hosted UI and lands on the campaigns", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Iniciar sesión" }).click();

    await page.getByRole("textbox", { name: /email|correo|username/i }).and(page.locator(":visible")).first().fill(email ?? "");
    await page.getByPlaceholder("Password").and(page.locator(":visible")).first().fill(password ?? "");
    await page.getByRole("button", { name: /sign in|iniciar sesión/i }).and(page.locator(":visible")).first().click();

    await expect(page).toHaveURL(/\/campaigns/);
    await expect(page.getByRole("navigation", { name: "Principal" })).toBeVisible();
  });
});
