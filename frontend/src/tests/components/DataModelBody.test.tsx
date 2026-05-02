import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { DataModelBody, type Artifact } from "@/components/product/ArtifactDrawer";
import { server } from "@/tests/mocks/server";
import { dataModelFixture } from "@/tests/mocks/handlers";

function makeArtifact(): Artifact {
  return {
    id: 5,
    session_id: 1,
    project_id: 1,
    dataset_id: null,
    kind: "data_model",
    title: "Data model",
    params: {},
    result: dataModelFixture as unknown as Record<string, unknown>,
    pinned: false,
    created_at: "2026-05-01T10:04:00Z",
  };
}

describe("DataModelBody", () => {
  it("shows role labels (Fact/Dimension)", async () => {
    render(<DataModelBody artifact={makeArtifact()} />);
    await waitFor(() => {
      const selects = screen.getAllByLabelText(/Override table role/i);
      expect(selects.length).toBeGreaterThan(0);
    });
    const selects = screen.getAllByLabelText(/Override table role/i) as HTMLSelectElement[];
    expect(selects[0].value).toBe("fact");
    expect(selects[1].value).toBe("dimension");
  });

  it("PATCHes role on dropdown change", async () => {
    const user = userEvent.setup();
    const seenBodies: unknown[] = [];
    server.use(
      http.patch(
        "/api/projects/1/data-model/tables/:datasetId",
        async ({ request }) => {
          seenBodies.push(await request.json());
          return HttpResponse.json({ ok: true });
        },
      ),
    );
    render(<DataModelBody artifact={makeArtifact()} />);
    const selects = await screen.findAllByLabelText(/Override table role/i);
    await user.selectOptions(selects[0], "summary");
    await waitFor(() =>
      expect(seenBodies).toContainEqual({ role: "summary", confirmed: true }),
    );
  });

  it("renders Confirm/Reject/Reset buttons; Reset disabled while proposed", async () => {
    render(<DataModelBody artifact={makeArtifact()} />);
    const confirmBtn = await screen.findByRole("button", { name: "تأكيد" });
    const rejectBtn = screen.getByRole("button", { name: "رفض" });
    const resetBtn = screen.getByRole("button", { name: "إعادة ضبط" });
    expect(confirmBtn).toBeEnabled();
    expect(rejectBtn).toBeEnabled();
    expect(resetBtn).toBeDisabled();
  });

  it("PATCHes the right body when Confirm is clicked", async () => {
    const user = userEvent.setup();
    const seen: unknown[] = [];
    server.use(
      http.patch(
        "/api/projects/1/data-model/relationships/:id",
        async ({ request }) => {
          seen.push(await request.json());
          return HttpResponse.json({ ok: true });
        },
      ),
    );
    render(<DataModelBody artifact={makeArtifact()} />);
    const confirmBtn = await screen.findByRole("button", { name: "تأكيد" });
    await user.click(confirmBtn);
    await waitFor(() => expect(seen).toContainEqual({ status: "confirmed" }));
  });

  it("renders a suspicious-column warning chip", async () => {
    render(<DataModelBody artifact={makeArtifact()} />);
    expect(await screen.findByText(/⚠/)).toBeInTheDocument();
  });

  it("POSTs when Refresh is clicked", async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.post("/api/projects/1/data-model/refresh", async () => {
        calls += 1;
        return HttpResponse.json({ ok: true });
      }),
    );
    render(<DataModelBody artifact={makeArtifact()} />);
    const btn = await screen.findByRole("button", { name: /Refresh/i });
    await user.click(btn);
    await waitFor(() => expect(calls).toBeGreaterThan(0));
  });
});
