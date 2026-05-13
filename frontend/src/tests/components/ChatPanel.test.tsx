import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatPanel } from "@/components/product/ChatPanel";
import { t } from "@/tests/utils/i18n";

const GREETING_PROBE = t("en", "chat.greetingNew").slice(0, 18);

function mockNDJSONStream(lines: string[]): Response {
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const l of lines) {
        controller.enqueue(enc.encode(l + "\n"));
        await new Promise((r) => setTimeout(r, 5));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "application/x-ndjson" },
  });
}

describe("ChatPanel", () => {
  it("renders the greeting and a disabled send while input is empty", async () => {
    render(<ChatPanel sessionId={null} hasData />);
    expect(await screen.findByText(new RegExp(GREETING_PROBE))).toBeInTheDocument();
    expect(screen.getByTestId("composer-send")).toBeDisabled();
  });

  it("Enter on the textarea sends the message", async () => {
    const fetchSpy = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes("/api/chat/stream")) {
        return mockNDJSONStream([
          JSON.stringify({ type: "text", data: "Hello" }),
          JSON.stringify({ type: "done" }),
        ]);
      }
      return new Response("{}", { status: 200 });
    });
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    render(<ChatPanel sessionId={null} hasData />);
    await screen.findByText(new RegExp(GREETING_PROBE));
    await user.type(screen.getByTestId("composer-textarea"), "test prompt{Enter}");
    await waitFor(() =>
      expect(
        fetchSpy.mock.calls.some((c) => String(c[0]).includes("/api/chat/stream")),
      ).toBe(true),
    );
    vi.unstubAllGlobals();
  });

  it("renders progressive tokens from a streamed response", async () => {
    const fetchSpy = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes("/api/chat/stream")) {
        return mockNDJSONStream([
          JSON.stringify({ type: "text", data: "Hel" }),
          JSON.stringify({ type: "text", data: "lo " }),
          JSON.stringify({ type: "text", data: "world" }),
          JSON.stringify({ type: "done" }),
        ]);
      }
      return new Response("{}", { status: 200 });
    });
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    render(<ChatPanel sessionId={null} hasData />);
    await screen.findByText(new RegExp(GREETING_PROBE));
    await user.type(screen.getByTestId("composer-textarea"), "stream test{Enter}");
    await waitFor(() => expect(screen.getByText(/Hello world/)).toBeInTheDocument());
    vi.unstubAllGlobals();
  });

  it("renders a tool skeleton when a tool starts streaming", async () => {
    const onToolStarted = vi.fn();
    const fetchSpy = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes("/api/chat/stream")) {
        return mockNDJSONStream([
          JSON.stringify({
            type: "tool_started",
            tool: "make_chart",
            call_id: "abc",
            params: {},
          }),
          JSON.stringify({ type: "done" }),
        ]);
      }
      return new Response("{}", { status: 200 });
    });
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    render(<ChatPanel sessionId={null} hasData onToolStarted={onToolStarted} />);
    await screen.findByText(new RegExp(GREETING_PROBE));
    await user.type(screen.getByTestId("composer-textarea"), "draw chart{Enter}");
    await waitFor(() => expect(onToolStarted).toHaveBeenCalled());
    vi.unstubAllGlobals();
  });
});
