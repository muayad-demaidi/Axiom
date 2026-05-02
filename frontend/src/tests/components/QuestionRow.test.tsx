import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuestionRow } from "@/components/product/ArtifactDrawer";

const baseQ = {
  id: 1,
  kind: "join_clarification",
  prompt: "هل العمود معرف فريد؟",
  status: "open",
};

describe("QuestionRow", () => {
  it("renders the prompt text", () => {
    render(<QuestionRow q={baseQ} projectId={1} busy={false} onAnswer={vi.fn()} />);
    expect(screen.getByText("هل العمود معرف فريد؟")).toBeInTheDocument();
  });

  it("renders option buttons and answers with the option payload", async () => {
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    const q = {
      ...baseQ,
      options: [
        { value: "yes", label: "نعم" },
        { value: "no", label: "لا" },
      ],
    };
    render(<QuestionRow q={q} projectId={1} busy={false} onAnswer={onAnswer} />);
    const yes = screen.getByRole("button", { name: "نعم" });
    await userEvent.setup().click(yes);
    expect(onAnswer).toHaveBeenCalledWith({
      status: "answered",
      answer: { value: "yes", label: "نعم" },
    });
  });

  it("dismisses with the right payload", async () => {
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(
      <QuestionRow q={baseQ} projectId={1} busy={false} onAnswer={onAnswer} />,
    );
    const dismiss = screen.getByRole("button", { name: /Dismiss/i });
    await userEvent.setup().click(dismiss);
    expect(onAnswer).toHaveBeenCalledWith({ status: "dismissed" });
  });

  it("'Write an answer' opens textarea; submit disabled while empty", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(
      <QuestionRow q={baseQ} projectId={1} busy={false} onAnswer={onAnswer} />,
    );
    await user.click(screen.getByRole("button", { name: /Write an answer/i }));
    const submit = screen.getByRole("button", { name: /Submit/i });
    expect(submit).toBeDisabled();
    const ta = screen.getByPlaceholderText(/Your answer/i);
    await user.type(ta, "نعم بالضبط");
    expect(submit).toBeEnabled();
    await user.click(submit);
    expect(onAnswer).toHaveBeenCalledWith({
      status: "answered",
      answer: { text: "نعم بالضبط" },
    });
  });

  it("'Discuss in chat' dispatches axiom:chat:prefill window event", async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    window.addEventListener("axiom:chat:prefill", handler as EventListener);
    render(
      <QuestionRow q={baseQ} projectId={1} busy={false} onAnswer={vi.fn()} />,
    );
    await user.click(screen.getByRole("button", { name: /Discuss in chat/i }));
    expect(handler).toHaveBeenCalled();
    const ev = handler.mock.calls[0][0] as CustomEvent;
    expect(ev.detail).toEqual({ text: baseQ.prompt, send: false });
    window.removeEventListener("axiom:chat:prefill", handler as EventListener);
  });
});
