import { expect, planTrip, stopNames, test, type Page } from "./fixtures";

/** Fills in the sign-up form on screen and sends it. */
async function signUp(page: Page, name: string) {
  const email = `${name.toLowerCase()}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  // By role: the page left behind stays in the document, hidden, with fields of its own.
  await page.getByRole("textbox", { name: "Name" }).fill(name);
  await page.getByRole("textbox", { name: "Email" }).fill(email);
  await page.getByRole("textbox", { name: "Password" }).fill("correct horse battery");
  await page.getByRole("button", { name: "Sign up" }).click();
}

test("signs up, saves a plan to my trips and ticks a stop visited", async ({ page }) => {
  await page.goto("/signup");
  await signUp(page, "Ana");
  const account = page.getByRole("navigation", { name: "Account" });
  await expect(account).toContainText("Ana");

  const plan = await planTrip(page, "A day in Lisbon");
  const [first] = await stopNames(plan).allTextContents();
  await plan.getByRole("button", { name: "Save to my trips" }).click();
  await expect(plan.getByRole("link", { name: "In My trips" })).toBeVisible();
  await expect(page).toHaveURL(/\?trip=\d+/);

  const firstCard = plan
    .getByRole("listitem")
    .filter({ has: page.getByRole("heading", { name: first }) });
  await firstCard.getByRole("button", { name: "Mark visited" }).click();
  await expect(firstCard.getByRole("button", { name: "Visited", exact: true })).toBeVisible();

  // My trips lists it; it opens with its visit.
  await account.getByRole("link", { name: "My trips" }).click();
  await page.getByRole("link", { name: "1 day in Lisbon" }).click();
  const saved = page.getByRole("region", { name: "Trip plan" });
  await expect(stopNames(saved).first()).toHaveText(first);
  await expect(saved.getByRole("button", { name: "Visited", exact: true })).toHaveCount(1);
});

test("adds a place to eat as the next stop after the one searched around", async ({ page }) => {
  await page.goto("/signup");
  await signUp(page, "Cai");
  await expect(page.getByRole("navigation", { name: "Account" })).toContainText("Cai");
  // Tomorrow's day: the search is around its first stop, before the trip begins.
  const plan = await planTrip(page, "A day in Lisbon");
  await plan.getByRole("button", { name: "Save to my trips" }).click();
  await expect(page).toHaveURL(/\?trip=\d+/);
  const [first] = await stopNames(plan).allTextContents();

  await plan.getByRole("button", { name: "Find places to eat", exact: true }).click();
  const search = page.getByRole("region", { name: "Places to eat and drink" });
  await expect(search.getByText(`Near ${first}, the first stop`)).toBeVisible();
  // Open or closed when the traveller leaves it tomorrow, not now.
  await expect(search.getByText(`, when you leave ${first}.`)).toBeVisible();
  await expect(search.getByRole("checkbox", { name: /^Open at \d\d:\d\d$/ })).toBeVisible();
  await search.getByLabel("Within").selectOption("2000");
  const card = search.getByRole("article").first();
  const venue = (await card.getByRole("heading").textContent()) ?? "";
  await card.getByRole("button", { name: "Add to route" }).click();
  await expect(card.getByLabel("Visit").locator("option:checked")).toContainText(`After ${first}`);
  await card.getByRole("button", { name: "Add to day 1" }).click();

  // The draft has it right after the first stop, not at the end of the day.
  await expect(page.getByText(`Day 1: added ${venue} (after ${first}).`)).toBeVisible();
  await expect(stopNames(plan).nth(1)).toHaveText(venue);
  await expect(stopNames(plan).first()).toHaveText(first);
  expect(await stopNames(plan).count()).toBeGreaterThan(2);
});

test("asks to log in before saving, then saves", async ({ page }) => {
  const plan = await planTrip(page, "A day in Lisbon");
  await plan.getByRole("button", { name: "Save to my trips" }).click();
  await expect(page).toHaveURL(/\/login\?/);
  await page.getByRole("main").getByRole("link", { name: "Sign up" }).click();
  await signUp(page, "Bo");
  await expect(page).toHaveURL(/\?trip=\d+/, { timeout: 30_000 });
  await expect(page.getByRole("link", { name: "In My trips" })).toBeVisible();
});
