"use client";

const PROJECT_KEY = "axiom_active_project";
const DATASET_KEY = "axiom_active_dataset";
const MODE_KEY = "axiom_project_mode_";
// Per-chat-session dataset selection. Scoped per session so a brand-new
// chat doesn't auto-inherit the dataset the user happened to have
// selected in some other chat / project — see the "+ New" sidebar task.
const SESSION_DATASET_KEY_PREFIX = "axiom_chat_dataset_";

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

/** Per-chat-session dataset selection.
 *
 * Returns the dataset the user explicitly bound to a given chat session,
 * or `null` if no choice has been made yet. Used by the project
 * workspace so a freshly created chat starts with the empty-state
 * preview instead of auto-attaching whatever the user happened to have
 * selected somewhere else. */
export function getChatSessionDatasetId(
  sessionId: number | null | undefined
): number | null {
  if (typeof window === "undefined" || sessionId == null) return null;
  const v = window.localStorage.getItem(SESSION_DATASET_KEY_PREFIX + sessionId);
  return v ? Number(v) : null;
}
export function setChatSessionDatasetId(
  sessionId: number | null | undefined,
  id: number | null
) {
  if (typeof window === "undefined" || sessionId == null) return;
  const key = SESSION_DATASET_KEY_PREFIX + sessionId;
  if (id == null) window.localStorage.removeItem(key);
  else window.localStorage.setItem(key, String(id));
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
