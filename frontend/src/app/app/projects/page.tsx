"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, getToken } from "@/lib/api";
import type { AxiomProject } from "@/lib/types";
import { errMessage } from "@/lib/types";
import {
  setActiveProjectId,
  getActiveProjectId,
  setProjectMode,
  getProjectMode,
  type Mode,
} from "@/lib/projectContext";
import { cacheKeys, patchCached, setCached } from "@/lib/workspaceCache";

export default function ProjectsIndex() {
  const router = useRouter();
  const [projects, setProjects] = useState<AxiomProject[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [modeTick, setModeTick] = useState(0);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    setActiveId(getActiveProjectId());
    api<AxiomProject[]>("/api/projects")
      .then((arr) => {
        // Keep the shared sidebar cache fresh too.
        setCached(cacheKeys.projects(), arr);
        // Hide the auto-managed Quick Chats project from the explicit
        // projects index — it's a system bucket for the home-screen
        // chat, not something the user manages here.
        setProjects(arr.filter((p) => p.name !== "Quick Chats"));
      })
      .catch((e: ApiError) => {
        if (e.status === 401) router.push("/login");
        else setError(e.message);
      });
  }, [router]);

  async function createProject(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const p = await api<AxiomProject>("/api/projects", {
        method: "POST",
        json: { name: newName.trim() },
      });
      setProjects((arr) => [p, ...(arr ?? [])]);
      // Mirror the new project into the shared cache so the unified
      // sidebar shows it immediately on next render.
      patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) => [
        p,
        ...((cur || []).filter((x) => x.id !== p.id)),
      ]);
      setNewName("");
      pick(p.id);
      router.push(`/app/project/${p.id}`);
    } catch (e: unknown) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function pick(id: number) {
    setActiveProjectId(id);
    setActiveId(id);
  }

  function chooseMode(id: number, m: Mode) {
    pick(id);
    setProjectMode(id, m);
    setModeTick((t) => t + 1);
  }

  function openProject(id: number) {
    pick(id);
    router.push(`/app/project/${id}`);
  }

  return (
    <div className="max-w-4xl">
      <span className="eyebrow">Workspace</span>
      <h1 className="text-2xl md:text-3xl font-bold mt-2">Your projects</h1>
      <p className="text-[var(--text-muted)] mt-2">
        Each project keeps its own datasets and chat history. AXIOM remembers everything in the project so it can answer across all your data.
      </p>

      <form onSubmit={createProject} className="mt-6 flex gap-2">
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New project name…"
          className="flex-1 px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
        />
        <button type="submit" className="btn btn-primary" disabled={busy || !newName.trim()}>
          Create
        </button>
      </form>

      {error && <div className="text-red-600 text-sm mt-4">{error}</div>}

      <section className="mt-8">
        {projects === null ? (
          <div className="card text-[var(--text-muted)] text-sm">Loading…</div>
        ) : projects.length === 0 ? (
          <div className="card text-[var(--text-muted)] text-sm">
            No projects yet. Create one above to get started.
          </div>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {projects.map((p) => {
              const mode = getProjectMode(p.id);
              const active = activeId === p.id;
              return (
                <li
                  key={`${p.id}-${modeTick}`}
                  className={`card ${active ? "ring-2 ring-[var(--accent)]" : ""}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3>{p.name}</h3>
                      <p className="text-xs">
                        {p.sheet_count ?? 0} dataset
                        {(p.sheet_count ?? 0) === 1 ? "" : "s"} ·
                        <span className="ml-1 font-mono">{mode}</span>
                      </p>
                    </div>
                    {active && (
                      <span className="text-[10px] font-mono text-[var(--accent)]">ACTIVE</span>
                    )}
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <span className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)] mr-1">
                      Mode
                    </span>
                    <button
                      type="button"
                      onClick={() => chooseMode(p.id, "guided")}
                      data-active={mode === "guided"}
                      className="mode-seg"
                      aria-pressed={mode === "guided"}
                    >
                      Guided
                    </button>
                    <button
                      type="button"
                      onClick={() => chooseMode(p.id, "expert")}
                      data-active={mode === "expert"}
                      className="mode-seg"
                      aria-pressed={mode === "expert"}
                    >
                      Expert
                    </button>
                  </div>

                  <div className="mt-4 flex gap-2">
                    <button
                      type="button"
                      onClick={() => openProject(p.id)}
                      className="btn btn-primary text-xs"
                    >
                      Open
                    </button>
                    <Link
                      href="/app/upload"
                      onClick={() => pick(p.id)}
                      className="btn btn-ghost text-xs"
                    >
                      Upload data
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
