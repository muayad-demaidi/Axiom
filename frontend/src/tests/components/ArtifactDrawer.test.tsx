import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArtifactDrawer } from "@/components/product/ArtifactDrawer";

const baseProps = {
  open: true,
  onClose: vi.fn(),
  sessionId: 1,
  refreshKey: 0,
  pending: [],
};

describe("ArtifactDrawer", () => {
  it("renders five tabs and switches between them", async () => {
    render(<ArtifactDrawer {...baseProps} />);
    const tabs = await screen.findAllByRole("tab");
    expect(tabs).toHaveLength(5);
    const labels = tabs.map((t) => t.textContent || "");
    expect(labels.some((l) => l.includes("ملف البيانات"))).toBe(true);
    expect(labels.some((l) => l.includes("الرسوم البيانية"))).toBe(true);
    expect(labels.some((l) => l.includes("التنبؤات"))).toBe(true);
    expect(labels.some((l) => l.includes("التجميع"))).toBe(true);
    expect(labels.some((l) => l.includes("نموذج البيانات"))).toBe(true);

    const user = userEvent.setup();
    const visTab = tabs.find((t) => (t.textContent || "").includes("الرسوم"))!;
    await user.click(visTab);
    expect(visTab).toHaveAttribute("aria-selected", "true");
  });

  it("hides the data-model tab when showDataModelTab=false", async () => {
    render(<ArtifactDrawer {...baseProps} showDataModelTab={false} />);
    const tabs = await screen.findAllByRole("tab");
    expect(tabs).toHaveLength(4);
    expect(tabs.some((t) => (t.textContent || "").includes("نموذج البيانات"))).toBe(false);
  });

  it("renders a pending tool skeleton with Arabic loading text", async () => {
    render(
      <ArtifactDrawer
        {...baseProps}
        pending={[{ id: "abc", tool: "profile_dataset" }]}
      />,
    );
    const skels = await screen.findAllByRole("status");
    expect(skels.length).toBeGreaterThan(0);
    expect(skels.some((s) => /جاري تجهيز ملف البيانات/.test(s.textContent || ""))).toBe(true);
  });

  it("switches to the Data-model tab and renders the model body", async () => {
    const user = userEvent.setup();
    render(<ArtifactDrawer {...baseProps} />);
    const tabs = await screen.findAllByRole("tab");
    const modelTab = tabs.find((t) => (t.textContent || "").includes("نموذج البيانات"))!;
    await user.click(modelTab);
    await waitFor(
      () => {
        const txt = document.body.textContent || "";
        expect(/Tables|Relationships|sales|customers/.test(txt)).toBe(true);
      },
      { timeout: 3000 },
    );
  });
});
