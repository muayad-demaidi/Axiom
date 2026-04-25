"use client";

const TOKEN_KEY = "axiom_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(t: string | null) {
  if (typeof window === "undefined") return;
  if (t) window.localStorage.setItem(TOKEN_KEY, t);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export type ApiBody = Record<string, unknown> | unknown[] | null;

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: ApiBody } = {}
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined = init.body as BodyInit | undefined;
  if (init.json !== undefined) {
    body = JSON.stringify(init.json);
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...init, headers, body });
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail =
      typeof data === "object" && data !== null
        ? ((data as Record<string, unknown>).detail ?? (data as Record<string, unknown>).message)
        : null;
    throw new ApiError(res.status, typeof detail === "string" ? detail : res.statusText, data);
  }
  return data as T;
}

export async function streamPost(
  path: string,
  body: ApiBody,
  onChunk: (s: string) => void
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text || res.statusText);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

/**
 * Stream NDJSON from a POST endpoint. Each newline-delimited JSON object
 * is parsed and forwarded through `onEvent`. Used by the chat endpoint
 * which interleaves text deltas and tool-call lifecycle events on the
 * same channel so the UI can show skeleton loaders the moment a tool
 * fires.
 */
export async function streamPostNDJSON(
  path: string,
  body: ApiBody,
  onEvent: (ev: Record<string, unknown>) => void,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text || res.statusText);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl = buf.indexOf("\n");
    while (nl !== -1) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) {
        try {
          onEvent(JSON.parse(line) as Record<string, unknown>);
        } catch {
          onEvent({ type: "text", data: line });
        }
      }
      nl = buf.indexOf("\n");
    }
  }
  if (buf.trim()) {
    try {
      onEvent(JSON.parse(buf.trim()) as Record<string, unknown>);
    } catch {
      onEvent({ type: "text", data: buf });
    }
  }
}
