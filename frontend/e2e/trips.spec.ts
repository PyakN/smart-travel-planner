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

test("asks to log in before saving, then saves", async ({ page }) => {
  const plan = await planTrip(page, "A day in Lisbon");
  await plan.getByRole("button", { name: "Save to my trips" }).click();
  await expect(page).toHaveURL(/\/login\?/);
  await page.getByRole("main").getByRole("link", { name: "Sign up" }).click();
  await signUp(page, "Bo");
  await expect(page).toHaveURL(/\?trip=\d+/, { timeout: 30_000 });
  await expect(page.getByRole("link", { name: "In My trips" })).toBeVisible();
});
