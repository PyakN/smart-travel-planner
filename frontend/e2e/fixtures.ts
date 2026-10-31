import { expect, test as base, type Page } from "@playwright/test";

/** Pages that never reach the internet: map tiles and photos are left out. */
export const test = base.extend<{ page: Page }>({
  page: async ({ page }, provide) => {
    await page.route(
      (url) => !["localhost", "127.0.0.1"].includes(url.hostname),
      (route) => route.abort(),
    );
    await provide(page);
  },
});

export { expect, type Page };

/** Describes the trip on the planner (Lisbon) and plans it; resolves to the plan. */
export async function planTrip(page: Page, text: string) {
  await page.goto("/?city=lisbon");
  await page.getByLabel("Describe your trip").fill(text);
  await page.getByRole("button", { name: "Plan my trip" }).click();
  const plan = page.getByRole("region", { name: "Trip plan" });
  await expect(plan).toBeVisible({ timeout: 30_000 });
  await expect(page).toHaveURL(/[?&](plan|trip)=\d+/);
  return plan;
}

/** The names of the active day's stops, in visiting order. */
export function stopNames(plan: ReturnType<Page["getByRole"]>) {
  return plan.getByRole("tabpanel").getByRole("heading", { level: 3 });
}
