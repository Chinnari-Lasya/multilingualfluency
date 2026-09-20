"use client";
import { useCallback, useEffect, useState } from "react";
import { Gate, useAuth, useErrText } from "@/components/Auth";
import { useI18n } from "@/lib/i18n";
import { api, post } from "@/lib/api";

interface RunRow { id: number; pipeline: string; mode: string; dataset: string; status: string; progress: string; created_at: string; error: string | null }
/* eslint-disable @typescript-eslint/no-explicit-any */
interface Report { system: string; dataset: any; manifest: any; metrics: { per_language: Record<string, any>; macro: any }; not_measured: Record<string, any>; warnings: string[] }
interface Detail { id: number; status: string; progress: string; error: string | null; report: Report | null }

const pct = (x: number | null | undefined) => (x == null ? <span className="na">—</span> : (x * 100).toFixed(1) + "%");
const num = (x: number | null | undefined) => (x == null ? <span className="na">—</span> : x.toFixed(3));

function View() {
  const { user } = useAuth();
  const { t } = useI18n();
  const errText = useErrText();
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [sel, setSel] = useState<Detail | null>(null);
  const [pipeline, setPipeline] = useState<"o2" | "o3">("o2");
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => { api<RunRow[]>("/api/v1/evaluations").then(setRuns).catch((e) => setErr(errText(e))); }, []);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);
  useEffect(() => { if (sel && sel.status === "running") { const t = setInterval(() => open(sel.id), 4000); return () => clearInterval(t); } }, [sel]);
  const open = (id: number) => api<Detail>(`/api/v1/evaluations/${id}`).then(setSel).catch((e) => setErr(errText(e)));
  async function start() {
    try { const r = await post<{ id: number }>("/api/v1/evaluations/run", { pipeline, mode: pipeline === "o3" ? "minimal" : "reference" }); load(); open(r.id); }
    catch (e) { setErr(errText(e)); }
  }
  const rep = sel?.report;
  return (
    <>
      <section className="card">
        <h2>{t("ev.title")}</h2>
        <p className="muted">{t("ev.intro")}</p>
        {user?.role === "admin" ? (
          <div className="row"><select value={pipeline} onChange={(e) => setPipeline(e.target.value as "o2" | "o3")} style={{ width: 220 }}><option value="o2">O2 reference</option><option value="o3">O3 controlled (minimal)</option></select><button onClick={start}>{t("ev.run")}</button></div>
        ) : <p className="muted small">{t("ev.adminOnly")}</p>}
        {err && <p className="error">{err}</p>}
        {runs.length === 0 ? <p><b>{t("ev.notEvaluated")}</b></p> : (
          <table><thead><tr><th>#</th><th>System</th><th>Dataset</th><th>Status</th><th>Started</th><th /></tr></thead>
            <tbody>{runs.map((r) => <tr key={r.id}><td>{r.id}</td><td>{r.pipeline.toUpperCase()} {r.mode}</td><td>{r.dataset}</td><td>{r.status} {r.progress}{r.error ? ` — ${r.error}` : ""}</td><td className="small">{new Date(r.created_at).toLocaleString()}</td><td><button className="small secondary" onClick={() => open(r.id)}>{t("ev.view")}</button></td></tr>)}</tbody></table>
        )}
      </section>

      {sel && (
        <section className="card">
          <h3>Run #{sel.id} — {sel.status} {sel.progress}</h3>
          {sel.error && <p className="error">{sel.error}</p>}
          {rep && (
            <>
              {rep.warnings.map((w, i) => <p key={i} className="notice warn">{w}</p>)}
              <div className="small muted">System: {rep.system} · dataset {rep.dataset.meta.name} (n={rep.dataset.n}, sha256 {String(rep.dataset.sha256).slice(0, 12)}…) · git {String(rep.manifest.git_sha).slice(0, 8)} · {rep.manifest.created_utc}</div>
              <table style={{ marginTop: 10 }}>
                <thead><tr><th>Lang</th><th>n</th><th>GLEU (vs identity)</th><th>F0.5 (P / R)</th><th>Over-correction: sentences / edits</th><th>Meaning preserved</th><th>Calibration</th><th>Latency p50 / p95 ms</th><th>Crash</th></tr></thead>
                <tbody>
                  {Object.entries(rep.metrics.per_language).map(([lang, m]: [string, any]) => (
                    <tr key={lang}>
                      <td><b>{lang}</b></td><td>{m.n_scored}/{m.n_examples}</td>
                      <td>{num(m.gleu?.value)} <span className="muted small">({num(m.gleu?.baseline_identity)})</span></td>
                      <td>{num(m["edit_f0.5"]?.["f0.5"])} <span className="muted small">({num(m["edit_f0.5"]?.precision)} / {num(m["edit_f0.5"]?.recall)})</span></td>
                      <td>{pct(m.over_correction?.sentence_level?.rate)} <span className="muted small">(n={m.over_correction?.sentence_level?.n_already_correct})</span> / {pct(m.over_correction?.edit_level?.rate)}</td>
                      <td>{pct(m.meaning_preservation?.rate_over_changed_outputs)} <span className="muted small">(n={m.meaning_preservation?.n_changed})</span></td>
                      <td>{m.calibration?.status === "ok" || m.calibration?.status === "insufficient_samples" ? <>ECE {num(m.calibration.ece)} <span className="muted small">n={m.calibration.n} ({m.calibration.status})</span></> : <span className="na">{t("ev.notEvaluated")}</span>}</td>
                      <td>{m.resource_cost?.latency_ms_p50 ?? "n/a"} / {m.resource_cost?.latency_ms_p95 ?? "n/a"}</td>
                      <td>{pct(m.crash_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h4>{t("ev.notMeasured")}</h4>
              <ul>
                <li>{t("ev.eduAcc", { s: rep.not_measured.educator_acceptance.status === "not_performed_yet" ? t("edu.notPerformed") : rep.not_measured.educator_acceptance.status })}</li>
                <li>{t("ev.heldOut")}</li>
                <li>{t("ev.human")}</li>
                <li>{t("ev.stress")}</li>
              </ul>
            </>
          )}
        </section>
      )}
    </>
  );
}
export default function Page() { return <Gate roles={["educator", "admin"]}><View /></Gate>; }
