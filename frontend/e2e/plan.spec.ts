import { expect, planTrip, stopNames, test } from "./fixtures";

test("plans a trip from a request, by day, and reopens it from its link", async ({ page }) => {
  const plan = await planTrip(page, "2 days in Lisbon: viewpoints and museums");

  await expect(plan.getByRole("tab")).toHaveCount(2);
  await expect(plan.getByRole("tab", { name: /Day 1/ })).toHaveAttribute("aria-selected", "true");
  const firstDay = await stopNames(plan).allTextContents();
  expect(firstDay.length).toBeGreaterThanOrEqual(3);
  // Every stop has the LLM's note on why it suits the traveller.
  await expect(plan.getByText("Chosen by the test LLM.")).toHaveCount(firstDay.length);
  // The map numbers the day's stops.
  await expect(page.locator(".stop-marker").first()).toBeVisible();

  await plan.getByRole("tab", { name: /Day 2/ }).click();
  await expect(plan.getByRole("tab", { name: /Day 2/ })).toHaveAttribute("aria-selected", "true");
  const secondDay = await stopNames(plan).allTextContents();
  expect(secondDay.length).toBeGreaterThanOrEqual(3);
  expect(secondDay.filter((name) => firstDay.includes(name))).toEqual([]);

  // The share link opens the same plan.
  await page.goto(page.url());
  const shared = page.getByRole("region", { name: "Trip plan" });
  await expect(stopNames(shared)).toHaveText(firstDay);
});

test("says when the plan was made without the AI", async ({ page }) => {
  // The scripted LLM fails on this word, as in an outage.
  const plan = await planTrip(page, "A day of sightseeing in Lisbon llm-outage");

  const notice = plan.getByRole("status").filter({ hasText: "Planned without the AI" });
  await expect(notice).toContainText("The AI planner is unavailable right now");
  await expect(notice).toContainText("best-known places in Lisbon");
  expect(await stopNames(plan).count()).toBeGreaterThanOrEqual(3);
  await expect(plan.getByText("Chosen by the test LLM.")).toHaveCount(0);
});

test("warns before planning when the request names another city", async ({ page }) => {
  await page.goto("/?city=lisbon");
  await page.getByLabel("Describe your trip").fill("2 days in Berlin");
  await expect(page.getByText("Your request names Berlin, but Lisbon is chosen.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Plan in Berlin instead" })).toBeVisible();
});

test("replaces a stop with another place, and undoes it", async ({ page }) => {
  const plan = await planTrip(page, "A day in Lisbon");
  const before = await stopNames(plan).allTextContents();
  const planUrl = page.url();

  await plan.getByRole("checkbox", { name: `Select ${before[0]} to replace` }).check();
  await plan.getByRole("button", { name: "Replace 1 stop" }).click();

  await expect(plan.getByText(new RegExp(`^Day 1: replaced ${before[0]} with `))).toBeVisible();
  // A new version, without the stop (a shorter day may also get a filler).
  expect(await stopNames(plan).allTextContents()).not.toContain(before[0]);
  expect(page.url()).not.toBe(planUrl);

  await plan.getByRole("button", { name: "Undo" }).click();
  await expect(stopNames(plan)).toHaveText(before);
  expect(page.url()).toBe(planUrl);
});
