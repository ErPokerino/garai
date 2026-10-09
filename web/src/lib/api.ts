import type {
  Assignment,
  CostSummary,
  Estimate,
  LLMCall,
  PersonContent,
  PriceRow,
  Provider,
  Run,
  RunSummary,
  SettingsView,
  Status,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public retryAfter?: number) {
    super(message);
  }
}

/** Evento globale: la sessione non è (più) valida -> l'app mostra la schermata di accesso. */
export const UNAUTHORIZED_EVENT = "garai:unauthorized";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin", ...init });
  if (!res.ok) {
    let msg = res.statusText;
    let retry: number | undefined;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
      retry = body.retry_after ?? undefined;
    } catch {
      /* risposta non JSON */
    }
    if (res.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    throw new ApiError(res.status, msg, retry);
  }
  return res.json() as Promise<T>;
}

export interface Me {
  user: string;
  initial_password: boolean;
  expires?: number;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  me: () => req<Me>("/api/auth/me"),
  login: (username: string, password: string) => req<Me>("/api/auth/login", json("POST", { username, password })),
  logout: () => req<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  changePassword: (current: string, next: string) => req<{ ok: boolean }>("/api/auth/password", json("POST", { current, new: next })),

  status: () => req<Status>("/api/status"),

  settings: () => req<SettingsView>("/api/settings"),
  saveSettings: (patch: Record<string, unknown>) => req<SettingsView>("/api/settings", json("PUT", patch)),
  testProvider: (provider: Provider) =>
    req<{ ok: boolean; provider: string; error?: string; tiers?: Record<string, { model: string; latency_ms: number }> }>(
      "/api/settings/test",
      json("POST", { provider }),
    ),

  pricing: () => req<PriceRow[]>("/api/pricing"),

  costs: (days: number) => req<CostSummary>(`/api/costs/summary?days=${days}`),
  calls: (runId?: string, limit = 200) =>
    req<LLMCall[]>(`/api/costs/calls?limit=${limit}${runId ? `&run_id=${runId}` : ""}`),

  runs: () => req<RunSummary[]>("/api/runs"),
  run: (id: string) => req<Run>(`/api/runs/${id}`),
  createRun: (form: FormData) => req<Run>("/api/runs", { method: "POST", body: form }),
  reanalyze: (id: string) => req<Run>(`/api/runs/${id}/analyze`, { method: "POST" }),
  deleteRun: (id: string) => req<{ ok: boolean }>(`/api/runs/${id}`, { method: "DELETE" }),
  /** names: nome file CV -> nome e cognome inserito/corretto in revisione ("" = assente, verrà inventato) */
  setAssignments: (id: string, assignments: Record<string, Assignment>, names?: Record<string, string>) =>
    req<Run>(`/api/runs/${id}/assignments`, json("PUT", { assignments, names })),
  estimate: (id: string, visualCritic: boolean) =>
    req<Estimate>(`/api/runs/${id}/estimate?visual_critic=${visualCritic}`),
  generate: (id: string, visualCritic: boolean) =>
    req<Run>(`/api/runs/${id}/generate`, json("POST", { visual_critic: visualCritic })),
  updatePerson: (id: string, content: PersonContent) =>
    req<Run>(`/api/runs/${id}/people/${encodeURIComponent(content.source_file)}`, json("PUT", content)),
  rebuild: (id: string) => req<Run>(`/api/runs/${id}/rebuild`, { method: "POST" }),
};

export const fileUrl = (runId: string, path: string, download = false) =>
  `/api/runs/${runId}/files/${path.split("/").map(encodeURIComponent).join("/")}${download ? "?download=true" : ""}`;
