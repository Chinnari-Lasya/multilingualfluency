export const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type Role = "learner" | "educator" | "admin";
export interface User { id: number; username: string; role: Role; display_name: string; is_independent_educator: boolean; preferred_language: string }

export interface Explanation { text: string; rule_id: string; source: string; verified: boolean; fallback_reason?: string | null; native_educator_reviewed?: boolean }
export interface Adjudication { verdict: string; reviewer_independent: boolean; notes: string; meaning_changed: boolean }
export interface Edit {
  id: number | null; start: number; end: number; original: string; replacement: string; op: string; language: string;
  error_type: string; rule_id: string | null; source: string; confidence: number | null; confidence_calibrated: boolean;
  gate_status: "accepted" | "rejected" | "not_applicable"; gate_reason: string | null; scores: Record<string, number>;
  explanation: Explanation | null; learner_decision?: string | null; adjudications?: Adjudication[];
}
export interface Flag { start: number; end: number; text: string; score: number; reason: string; suggestion: string | null }
export interface Assessment {
  meaning_preservation?: { status: "preserved" | "uncertain" | "violated" | "not_checked"; similarity?: number; threshold?: number; hard_check_failures?: string[]; note?: string };
  over_correction?: { risk: "low" | "medium" | "high"; edit_ratio: number; applied_edits: number; lexical_rewrites_applied: number; edits_blocked_by_gates: { original: string; replacement: string; reason: string }[]; note: string };
}
export interface Capability { language: string; level: string; model_id: string | null; summary: string; limitations: string[]; license_note?: string | null }
export interface Run {
  run_id: number | null; submission_id?: number; pipeline: "o2" | "o3"; mode: string; language: string; source: string; corrected: string;
  degraded: boolean; abstained: boolean; abstain_reason?: string | null; latency_ms: number; edits: Edit[]; flags?: Flag[];
  assessment?: Assessment; capability?: Capability; warnings?: string[]; model_ids?: Record<string, string>;
  trace?: { stage: string; status: string; ms: number; detail?: string | null }[];
}
export interface Compare { submission_id: number; language: string; source: string; o2: Run; o3: Run }
export interface Lang { code: string; name: string; native_name: string; capability: Capability }

/** `code` is a stable machine code from the backend (e.g. "username_taken"); the UI translates it. */
export class ApiError extends Error {
  status: number; code: string;
  constructor(status: number, code: string, msg: string) { super(msg); this.status = status; this.code = code; }
}

export const tokenStore = {
  get: () => { try { return typeof window === "undefined" ? null : window.localStorage.getItem("gec_token"); } catch { return null; } },
  set: (t: string | null) => { try { if (typeof window !== "undefined") { if (t) window.localStorage.setItem("gec_token", t); else window.localStorage.removeItem("gec_token"); } } catch { /* ignore */ } },
};

export const UNAUTH_EVENT = "gec-unauth";
const PUBLIC_PATHS = ["/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/languages"];

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get();
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init.headers as Record<string, string> | undefined) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let res: Response;
  try { res = await fetch(`${API}${path}`, { ...init, headers }); }
  catch { throw new ApiError(0, "network", `Cannot reach the backend at ${API}.`); }
  if (!res.ok) {
    let code = "generic"; let msg = res.statusText;
    try {
      const j = await res.json();
      code = j.error || (res.status === 401 ? "unauthorized" : res.status === 403 ? "forbidden" : "generic");
      msg = j.message || (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j)) || msg;
    } catch { /* keep defaults */ }
    if (res.status === 401 && !PUBLIC_PATHS.includes(path) && typeof window !== "undefined") {
      tokenStore.set(null);
      window.dispatchEvent(new Event(UNAUTH_EVENT));
    }
    throw new ApiError(res.status, code, msg);
  }
  return res.json() as Promise<T>;
}

export const post = <T,>(path: string, body: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(body) });
