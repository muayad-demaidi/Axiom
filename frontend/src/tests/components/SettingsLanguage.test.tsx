// Settings → language selector (Task #275).
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import SettingsPage from "@/app/[locale]/app/settings/page";
import { server } from "@/tests/mocks/server";
import { setToken } from "@/lib/api";
import { t } from "@/tests/utils/i18n";
import { LOCALE_COOKIE } from "@/i18n/config";

const replaceMock = vi.fn();
const refreshMock = vi.fn();
vi.mock("next/navigation", async () => {
  const React = await import("react");
  void React;
  return {
    useRouter: () => ({
      push: vi.fn(),
      replace: replaceMock,
      refresh: refreshMock,
      back: vi.fn(),
      forward: vi.fn(),
      prefetch: vi.fn(),
    }),
    useSearchParams: () => new URLSearchParams(""),
    usePathname: () => "/app/settings",
    useParams: () => ({ locale: "en" }),
    redirect: vi.fn(),
    notFound: vi.fn(),
  };
});

beforeEach(() => {
  setToken("test-token");
  document.cookie = `${LOCALE_COOKIE}=; Path=/; Max-Age=0`;
  replaceMock.mockClear();
  refreshMock.mockClear();
});

describe("Settings → language selector", () => {
  it("renders the language section title from the EN catalogue", async () => {
    render(<SettingsPage />);
    expect(
      await screen.findByText(t("en", "settings.languageSection")),
    ).toBeInTheDocument();
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

  it("PATCHes /api/users/me/locale, writes the cookie, and navigates to /ar", async () => {
    const patched = vi.fn<(body: unknown) => void>();
    let calledPath = "";
    server.use(
      http.patch("/api/users/me/locale", async ({ request }) => {
        calledPath = new URL(request.url).pathname;
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
    await screen.findByText(t("en", "settings.languageSection"));

    const arRadio = document.getElementById("locale-ar") as HTMLInputElement;
    await user.click(arRadio);

    const save = screen.getByRole("button", { name: t("en", "common.save") });
    await user.click(save);

    await waitFor(() => expect(patched).toHaveBeenCalled());
    expect(calledPath).toBe("/api/users/me/locale");
    expect(patched.mock.calls[0][0]).toEqual({ locale: "ar" });
    expect(document.cookie).toContain(`${LOCALE_COOKIE}=ar`);

    await waitFor(() => expect(replaceMock).toHaveBeenCalled());
    expect(replaceMock.mock.calls[0][0]).toMatch(/^\/ar(\/|$)/);
    expect(refreshMock).toHaveBeenCalled();
  });
});
