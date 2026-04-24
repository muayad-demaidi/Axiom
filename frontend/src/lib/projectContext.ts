"use client";

const PROJECT_KEY = "axiom_active_project";
const DATASET_KEY = "axiom_active_dataset";
const MODE_KEY = "axiom_project_mode_";

export function getActiveProjectId(): number | null {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(PROJECT_KEY);
  return v ? Number(v) : null;
}
export function setActiveProjectId(id: number | null) {
  if (typeof window === "undefined") return;
  if (id == null) window.localStorage.removeItem(PROJECT_KEY);
  else window.localStorage.setItem(PROJECT_KEY, String(id));
}

export function getActiveDatasetId(): number | null {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(DATASET_KEY);
  return v ? Number(v) : null;
}
export function setActiveDatasetId(id: number | null) {
  if (typeof window === "undefined") return;
  if (id == null) window.localStorage.removeItem(DATASET_KEY);
  else window.localStorage.setItem(DATASET_KEY, String(id));
}

export type Mode = "guided" | "expert";

export function getProjectMode(projectId: number | null): Mode {
  if (typeof window === "undefined" || projectId == null) return "guided";
  const v = window.localStorage.getItem(MODE_KEY + projectId);
  return v === "expert" ? "expert" : "guided";
}
export function setProjectMode(projectId: number, mode: Mode) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(MODE_KEY + projectId, mode);
}
