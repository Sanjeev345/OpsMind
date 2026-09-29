import type {
  FeedbackForm, FeedbackResult, Health, Incident, IncidentSummary, MemoryStats, StreamEvent,
} from "./types";

// Only the backend URL is public. API keys live exclusively in the FastAPI backend.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "backend_unreachable", `OpsMind backend unreachable at ${API_BASE}`);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = body?.error;
    throw new ApiError(res.status, err?.code ?? "error", err?.message ?? `Request failed (${res.status})`);
  }
  return body as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  incidents: () => request<{ incidents: IncidentSummary[] }>("/api/incidents").then((r) => r.incidents),
  incident: (id: string) =>
    request<{ kind: string; incident: Incident }>(`/api/incidents/${encodeURIComponent(id)}`).then((r) => r.incident),
  stats: () => request<MemoryStats>("/api/memory/stats"),
  feedback: (incident_id: string, f: FeedbackForm) =>
    request<FeedbackResult>("/api/feedback", {
      method: "POST",
      body: JSON.stringify({ incident_id, correct: f.correct, actual_root_cause: f.actual_root_cause,
        actual_resolution: f.actual_resolution, engineer_note: f.engineer_note }),
    }),
  reset: () => request<{ deleted_learned_memories: number }>("/api/demo/reset", {
    method: "POST", body: JSON.stringify({ reseed: false }),
  }),
};

/** Stream an investigation. Calls onEvent for every NDJSON event as the backend emits it. */
export async function streamInvestigation(incidentId: string, onEvent: (e: StreamEvent) => void, signal?: AbortSignal) {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/investigate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ incident_id: incidentId }),
      signal,
    });
  } catch {
    throw new ApiError(0, "backend_unreachable", `OpsMind backend unreachable at ${API_BASE}`);
  }
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.error?.code ?? "error", body?.error?.message ?? `Investigation failed (${res.status})`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) onEvent(JSON.parse(line) as StreamEvent);
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf) as StreamEvent);
}
