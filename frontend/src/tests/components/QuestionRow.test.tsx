import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuestionRow } from "@/components/product/ArtifactDrawer";
import { t } from "@/tests/utils/i18n";

const baseQ = { id: 1, kind: "join_clarification", prompt: "هل العمود معرف فريد؟", status: "open" };

describe("QuestionRow", () => {
  it("renders the prompt text", () => {
    render(<QuestionRow q={baseQ} projectId={1} busy={false} onAnswer={vi.fn()} />);
    expect(screen.getByText(baseQ.prompt)).toBeInTheDocument();
  });

  it("renders option buttons and answers with the option payload", async () => {
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    const yesLabel = t("ar", "common.yes");
    const noLabel = t("ar", "common.no");
    const q = {
      ...baseQ,
      options: [
        { value: "yes", label: yesLabel },
        { value: "no", label: noLabel },
      ],
    };
    render(<QuestionRow q={q} projectId={1} busy={false} onAnswer={onAnswer} />);
    await userEvent.setup().click(screen.getByRole("button", { name: yesLabel }));
    expect(onAnswer).toHaveBeenCalledWith({
      status: "answered",
      answer: { value: "yes", label: yesLabel },
    });
  });

  it("dismisses with the right payload", async () => {
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(<QuestionRow q={baseQ} projectId={1} busy={false} onAnswer={onAnswer} />);
    await userEvent.setup().click(screen.getByTestId("qr-dismiss"));
    expect(onAnswer).toHaveBeenCalledWith({ status: "dismissed" });
  });

  it("'Write an answer' opens textarea; submit disabled while empty", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(<QuestionRow q={baseQ} projectId={1} busy={false} onAnswer={onAnswer} />);
    await user.click(screen.getByTestId("qr-write-answer"));
    const submit = screen.getByTestId("qr-submit");
    expect(submit).toBeDisabled();
    await user.type(screen.getByTestId("qr-free-text"), "answer body");
    expect(submit).toBeEnabled();
    await user.click(submit);
    expect(onAnswer).toHaveBeenCalledWith({
      status: "answered",
      answer: { text: "answer body" },
    });
  });

  it("'Discuss in chat' dispatches axiom:chat:prefill window event", async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    window.addEventListener("axiom:chat:prefill", handler as EventListener);
    render(<QuestionRow q={baseQ} projectId={1} busy={false} onAnswer={vi.fn()} />);
    await user.click(screen.getByTestId("qr-discuss"));
    expect(handler).toHaveBeenCalled();
    const ev = handler.mock.calls[0][0] as CustomEvent;
    expect(ev.detail).toEqual({ text: baseQ.prompt, send: false });
    window.removeEventListener("axiom:chat:prefill", handler as EventListener);
  });
});
