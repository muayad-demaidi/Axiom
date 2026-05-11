import { test, expect } from "@playwright/test";
import { localeOf, tFor } from "./_i18n";

function signupPath(locale: "en" | "ar") {
  return locale === "ar" ? "/ar/signup" : "/signup";
}

test.describe("signup error reporting", () => {
  test("409 Conflict (User exists) shows specific backend message", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(signupPath(locale));

    // Intercept register call
    await page.route("**/api/auth/register", async (route) => {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "User with this email or username already exists" }),
      });
    });

    await page.getByPlaceholder(tFor(locale, "auth.email")).first().fill("existing@example.com");
    await page.getByPlaceholder(tFor(locale, "auth.username")).fill("existinguser");
    await page.getByPlaceholder(tFor(locale, "auth.passwordPlaceholder")).fill("password123");
    await page.getByRole("button", { name: tFor(locale, "auth.createAccountCta") }).click();

    // The frontend should show the specific detail from backend
    await expect(page.getByText("User with this email or username already exists")).toBeVisible();
  });

  test("422 Validation (Short password) shows specific validation message", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(signupPath(locale));

    // Bypass browser-level validation
    await page.evaluate(() => {
      const el = document.querySelector('input[type="password"]');
      if (el) {
        el.removeAttribute('minLength');
        (el as HTMLInputElement).required = false;
      }
    });

    await page.route("**/api/auth/register", async (route) => {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          detail: [{ loc: ["body", "password"], msg: "ensure this value has at least 6 characters", type: "value_error" }]
        }),
      });
    });

    await page.getByPlaceholder(tFor(locale, "auth.email")).first().fill("new@example.com");
    await page.getByPlaceholder(tFor(locale, "auth.username")).fill("newuser");
    await page.getByPlaceholder(tFor(locale, "auth.passwordPlaceholder")).fill("123");
    await page.getByRole("button", { name: tFor(locale, "auth.createAccountCta") }).click();

    // In 422 case, we map the detail array.
    await expect(page.getByText("ensure this value has at least 6 characters")).toBeVisible();
  });

  test("500 Server Error shows specific backend detail", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(signupPath(locale));

    await page.route("**/api/auth/register", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Registration failed: database connection issue" }),
      });
    });

    await page.getByPlaceholder(tFor(locale, "auth.email")).first().fill("fail@example.com");
    await page.getByPlaceholder(tFor(locale, "auth.username")).fill("failuser");
    await page.getByPlaceholder(tFor(locale, "auth.passwordPlaceholder")).fill("password123");
    await page.getByRole("button", { name: tFor(locale, "auth.createAccountCta") }).click();

    await expect(page.getByText("Registration failed: database connection issue")).toBeVisible();
  });

  test("500 Server Error with generic text shows status code in UI", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(signupPath(locale));

    await page.route("**/api/auth/register", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "text/plain",
        body: "Internal Server Error",
      });
    });

    await page.getByPlaceholder(tFor(locale, "auth.email")).first().fill("fail2@example.com");
    await page.getByPlaceholder(tFor(locale, "auth.username")).fill("failuser2");
    await page.getByPlaceholder(tFor(locale, "auth.passwordPlaceholder")).fill("password123");
    await page.getByRole("button", { name: tFor(locale, "auth.createAccountCta") }).click();

    // Should fallback to localized "Sign-up failed" + status code
    const fallbackBase = tFor(locale, "auth.signUpFailed");
    await expect(page.getByText(`${fallbackBase} (500)`)).toBeVisible();
  });

  test("404 Not Found shows descriptive configuration error", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(signupPath(locale));

    await page.route("**/api/auth/register", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "text/plain",
        body: "Not Found",
      });
    });

    await page.getByPlaceholder(tFor(locale, "auth.email")).first().fill("404@example.com");
    await page.getByPlaceholder(tFor(locale, "auth.username")).fill("404user");
    await page.getByPlaceholder(tFor(locale, "auth.passwordPlaceholder")).fill("password123");
    await page.getByRole("button", { name: tFor(locale, "auth.createAccountCta") }).click();

    await expect(page.getByText(/404: Not Found/).first()).toBeVisible();
    await expect(page.getByText(tFor(locale, "auth.signUpDiagnostic"))).toBeVisible();
  });

  test("Successful signup redirects to /app", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(signupPath(locale));

    await page.route("**/api/auth/register", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          token: "fake-jwt-token",
          user: { id: 1, email: "success@example.com", username: "successuser", assistant_mode: "guided" }
        }),
      });
    });

    await page.getByPlaceholder(tFor(locale, "auth.email")).first().fill("success@example.com");
    await page.getByPlaceholder(tFor(locale, "auth.username")).fill("successuser");
    await page.getByPlaceholder(tFor(locale, "auth.passwordPlaceholder")).fill("password123");
    await page.getByRole("button", { name: tFor(locale, "auth.createAccountCta") }).click();

    await expect(page).toHaveURL(/\/app(\?|$)/);
  });
});
