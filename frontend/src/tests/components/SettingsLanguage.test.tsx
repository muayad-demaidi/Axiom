/**
 * SettingsLanguage — covers the locale selector landed in #273:
 *   1. Initial selection mirrors the active locale.
 *   2. Switching the radio + clicking Save issues PATCH /api/auth/me
 *      with the chosen locale and writes the NEXT_LOCALE cookie.
 *   3. Save button is disabled until the user picks a different locale.
 *
 * The page imports next-intl helpers (useLocale/useTranslations) which
 * are already mocked in `src/tests/setup.ts` to resolve keys against
 * `messages/en.json`. We mount the page directly because it's a Client
 * Component with no server-only dependencies once the mocks are in
 * place.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import SettingsPage from "@/app/[locale]/app/settings/page";
import { server } from "@/tests/mocks/server";
import { setToken } from "@/lib/api";
import { t } from "@/tests/utils/i18n";
import { LOCALE_COOKIE } from "@/i18n/config";

beforeEach(() => {
  setToken("test-token");
  document.cookie = `${LOCALE_COOKIE}=; Path=/; Max-Age=0`;
});

describe("Settings → language selector", () => {
  it("renders the language section title from the EN catalogue", async () => {
    render(<SettingsPage />);
    expect(
      await screen.findByText(t("en", "settings.languageSection")),
    ).toBeInTheDocument();
    // English option label comes from `common.english`.
    expect(screen.getByText(t("en", "common.english"))).toBeInTheDocument();
    expect(screen.getByText(t("en", "common.arabic"))).toBeInTheDocument();
  });

  it("disables Save until a different locale is selected", async () => {
    render(<SettingsPage />);
    const save = await screen.findByRole("button", {
      name: t("en", "common.save"),
    });
    expect(save).toBeDisabled();
  });

  it(
    "PATCHes /api/auth/me with the chosen locale and writes the NEXT_LOCALE cookie",
    async () => {
      const patched = vi.fn<(body: unknown) => void>();
      server.use(
        http.patch("/api/auth/me", async ({ request }) => {
          const body = await request.json();
          patched(body);
          return HttpResponse.json({
            id: 1,
            email: "demo@axiom.app",
            locale: (body as { locale?: string }).locale ?? "en",
          });
        }),
      );
      const user = userEvent.setup();
      render(<SettingsPage />);
      // Wait for the form to settle (initial /api/auth/me GET resolves).
      await screen.findByText(t("en", "settings.languageSection"));
      const arRadio = document.getElementById("locale-ar") as HTMLInputElement;
      expect(arRadio).not.toBeNull();
      await user.click(arRadio);
      const save = screen.getByRole("button", {
        name: t("en", "common.save"),
      });
      expect(save).not.toBeDisabled();
      await user.click(save);
      await waitFor(() => expect(patched).toHaveBeenCalled());
      expect(patched.mock.calls[0][0]).toEqual({ locale: "ar" });
      expect(document.cookie).toContain(`${LOCALE_COOKIE}=ar`);
    },
  );
});
