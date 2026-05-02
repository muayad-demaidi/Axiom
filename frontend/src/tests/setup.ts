import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import React from "react";
import { server } from "./mocks/server";

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

// Default global fetch mock — individual tests / MSW handlers override.
const defaultFetch = vi.fn(async () =>
  new Response(JSON.stringify({}), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }),
);
// Cast to any so callers can still set custom mocks.
(globalThis as unknown as { fetch: typeof fetch }).fetch = defaultFetch as unknown as typeof fetch;

// MSW lifecycle --------------------------------------------------------------
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  server.resetHandlers();
  pushMock.mockClear();
  replaceMock.mockClear();
});
afterAll(() => server.close());

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
