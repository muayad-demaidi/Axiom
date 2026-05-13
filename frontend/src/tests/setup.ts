import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import React from "react";
import { server } from "./mocks/server";
import enMessages from "../../messages/en.json";

// Resolve translations from messages/en.json; missing keys throw.
function resolveKey(scope: string | undefined, key: string): string {
  const path = scope ? `${scope}.${key}` : key;
  const parts = path.split(".");
  let cur: unknown = enMessages;
  for (const p of parts) {
    if (cur && typeof cur === "object" && p in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[p];
    } else {
      throw new Error(`[i18n test mock] missing key "${path}" in en.json`);
    }
  }
  if (typeof cur !== "string") {
    throw new Error(`[i18n test mock] key "${path}" is not a string`);
  }
  return cur;
}
function interpolate(template: string, values?: Record<string, unknown>): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) => {
    const v = values[k];
    return v == null ? `{${k}}` : String(v);
  });
}
vi.mock("next-intl", () => ({
  useTranslations:
    (scope?: string) => (key: string, values?: Record<string, unknown>) =>
      interpolate(resolveKey(scope, key), values),
  useLocale: () => "en",
  NextIntlClientProvider: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
}));

// next/navigation mocks ------------------------------------------------------
const pushMock = vi.fn();
const replaceMock = vi.fn();
const refreshMock = vi.fn();
const backMock = vi.fn();
const forwardMock = vi.fn();
const prefetchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    refresh: refreshMock,
    back: backMock,
    forward: forwardMock,
    prefetch: prefetchMock,
  }),
  useSearchParams: () => new URLSearchParams(""),
  usePathname: () => "/",
  // useParams is consumed by locale-aware pages (e.g. Settings) to read the
  // active `[locale]` segment. Returning the default keeps client components
  // in sync with the `useLocale()` mock above.
  useParams: () => ({ locale: "en" }),
  redirect: vi.fn(),
  notFound: vi.fn(),
}));

// next/image mock — render a plain <img>
vi.mock("next/image", () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) =>
    React.createElement("img", { ...props, alt: (props.alt as string) || "" }),
}));

// next/dynamic mock — return component synchronously, no SSR fallback
vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: (loader: () => Promise<{ default?: unknown } | unknown>) => {
    const Lazy = React.lazy(async () => {
      const mod: any = await loader();
      if (mod && typeof mod === "object" && "default" in mod) return mod;
      return { default: mod };
    });
    function DynamicShim(props: Record<string, unknown>) {
      return React.createElement(
        React.Suspense,
        { fallback: null },
        React.createElement(Lazy as any, props),
      );
    }
    return DynamicShim;
  },
}));

// Do not pre-stub globalThis.fetch — MSW must own the fetch wrapper.
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  server.resetHandlers();
  pushMock.mockClear();
  replaceMock.mockClear();
});
afterAll(() => server.close());

// jsdom doesn't implement scrollIntoView on Element refs (used by ChatPanel
// auto-scroll). Stub it on the prototype so any attached ref is callable.
if (typeof Element !== "undefined" && !(Element.prototype as unknown as { scrollIntoView?: unknown }).scrollIntoView) {
  (Element.prototype as unknown as { scrollIntoView: () => void }).scrollIntoView = () => {};
}

// jsdom/happy-dom doesn't ship matchMedia
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}
