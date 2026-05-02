import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { OpenQuestionsBar } from "@/components/product/OpenQuestionsBar";
import { server } from "@/tests/mocks/server";

describe("OpenQuestionsBar", () => {
  it("renders nothing when fewer than 2 datasets", async () => {
    server.use(
      http.get("/api/projects/1/data-model", () =>
        HttpResponse.json({
          tables: [{ dataset_name: "only" }],
          questions: [
            { id: 1, kind: "k", prompt: "Q?", status: "open" },
          ],
        }),
      ),
    );
    const { container } = render(
      <OpenQuestionsBar projectId={1} onAskQuestion={() => {}} />,
    );
    await new Promise((r) => setTimeout(r, 30));
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when there are no open questions", async () => {
    server.use(
      http.get("/api/projects/1/data-model", () =>
        HttpResponse.json({
          tables: [{ dataset_name: "a" }, { dataset_name: "b" }],
          questions: [],
        }),
      ),
    );
    const { container } = render(
      <OpenQuestionsBar projectId={1} onAskQuestion={() => {}} />,
    );
    await new Promise((r) => setTimeout(r, 30));
    expect(container.firstChild).toBeNull();
  });

  it("renders questions and clicking calls onAskQuestion; max 6 rendered", async () => {
    const qs = Array.from({ length: 9 }, (_, i) => ({
      id: i + 1,
      kind: "k",
      prompt: `Question ${i + 1}؟`,
      status: "open",
    }));
    server.use(
      http.get("/api/projects/1/data-model", () =>
        HttpResponse.json({
          tables: [{ dataset_name: "a" }, { dataset_name: "b" }],
          questions: qs,
        }),
      ),
    );
    const onAsk = vi.fn();
    render(<OpenQuestionsBar projectId={1} onAskQuestion={onAsk} />);
    const buttons = await screen.findAllByRole("button", undefined, {
      timeout: 3000,
    });
    expect(buttons.length).toBeGreaterThanOrEqual(6);
    const user = userEvent.setup();
    await user.click(buttons[0]);
    expect(onAsk).toHaveBeenCalledWith("Question 1؟");
  });
});
