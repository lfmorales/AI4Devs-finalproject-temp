import type { Locator, Page } from "@playwright/test";

/**
 * The error notice of the application. Next.js inserts its own empty role="alert" (the route announcer) in every
 * page, so only an alert with text counts as the application's.
 */
export function appAlert(page: Page): Locator {
  return page.getByRole("alert").filter({ hasText: /\S/ });
}
