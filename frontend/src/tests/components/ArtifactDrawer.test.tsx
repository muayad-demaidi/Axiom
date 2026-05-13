import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArtifactDrawer } from "@/components/product/ArtifactDrawer";

// Tab labels live in a component-internal `TABS` constant in
// ArtifactDrawer.tsx; the assertions below use position + role/aria
// instead of text so the spec is locale-agnostic.

const baseProps = {
  open: true,
  onClose: vi.fn(),
  sessionId: 1,
  refreshKey: 0,
  pending: [],
};

describe("ArtifactDrawer", () => {
  it("renders five tabs and switches selection on click", async () => {
    const user = userEvent.setup();
    render(<ArtifactDrawer {...baseProps} />);
    const tabs = await screen.findAllByRole("tab");
    expect(tabs).toHaveLength(5);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    await user.click(tabs[1]);
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(tabs[0]).toHaveAttribute("aria-selected", "false");
  });

  it("hides the data-model tab when showDataModelTab=false", async () => {
    render(<ArtifactDrawer {...baseProps} showDataModelTab={false} />);
    const tabs = await screen.findAllByRole("tab");
    expect(tabs).toHaveLength(4);
  });

  it("renders a pending tool skeleton for in-flight tools", async () => {
    render(
      <ArtifactDrawer
        {...baseProps}
        pending={[{ id: "abc", tool: "profile_dataset" }]}
      />,
    );
    const skels = await screen.findAllByRole("status");
    expect(skels.length).toBeGreaterThan(0);
  });

  it("switches to the Data-model tab and renders the model body", async () => {
    const user = userEvent.setup();
    render(<ArtifactDrawer {...baseProps} />);
    const tabs = await screen.findAllByRole("tab");
    await user.click(tabs[tabs.length - 1]);
    await waitFor(
      () => {
        const txt = document.body.textContent || "";
        expect(/Tables|Relationships|sales|customers/.test(txt)).toBe(true);
      },
      { timeout: 3000 },
    );
  });
});
