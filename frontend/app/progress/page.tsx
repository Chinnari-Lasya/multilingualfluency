"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Gate, useErrText } from "@/components/Auth";
import { api, type Lang } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface Stats { attempts: number; corrected_sentences: number; errors_found: number; learner_accepted: number; learner_rejected: number; educator_verdicts: number; o3_abstained: number; o3_blocked_edits: number; avg_confidence: number | null; suggestion_acceptance_rate?: number | null }
interface ProgressRow { error_type: string; total: number; recent_per_100_tokens: number; earlier_per_100_tokens: number | null; trend: string }
interface Progress { languages: Record<string, { submissions: number; error_types: ProgressRow[]; focus: string[]; note: string | null; stats: Stats }>; totals: Stats; activity: { date: string; count: number }[]; min_submissions_for_trend: number }
interface HistoryItem { submission_id: number; language: string; text: string; created_at: string; runs: { run_id: number; pipeline: string; mode: string; corrected: string; n_edits: number; abstained: boolean }[] }

function Stat({ label, value }: { label: string; value: React.ReactNode }) { return <span className="stat"><b>{value}</b><span className="muted small">{label}</span></span>; }

/** Simple CSS bar chart: no chart library, values come straight from the API. */
function Bars({ data, label }: { data: { key: string; label: string; value: number }[]; label: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div role="img" aria-label={label} style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 110, marginTop: 8 }}>
      {data.map((d) => (
        <div key={d.key} title={`${d.label}: ${d.value}`} style={{ flex: 1, textAlign: "center", minWidth: 14 }}>
          <div style={{ height: `${(d.value / max) * 80}px`, minHeight: d.value ? 3 : 1, background: d.value ? "var(--brand)" : "var(--line)", borderRadius: 4 }} />
          <div className="small muted" style={{ fontSize: 10, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "clip" }}>{d.label}</div>
          <div className="small" style={{ fontSize: 11 }}>{d.value}</div>
        </div>
      ))}
    </div>
  );
}

function View() {
  const { t, tx } = useI18n();
  const errText = useErrText();
  const [p, setP] = useState<Progress | null>(null);
  const [h, setH] = useState<HistoryItem[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true); setErr(null);
    Promise.all([api<Progress>("/api/v1/learners/me/progress"), api<HistoryItem[]>("/api/v1/learners/me/history"), api<Lang[]>("/api/v1/languages")])
      .then(([a, b, l]) => { setP(a); setH(b); setNames(Object.fromEntries(l.map((x) => [x.code, x.native_name]))); })
      .catch((e) => setErr(errText(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    load();
    const onFocus = () => load(); // pick up corrections made in another tab
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  if (loading && !p) return <p className="muted">{t("common.loading")}</p>;
  if (err && !p) return <div className="card"><p className="error" role="alert">{t("prog.loadError")} {err}</p><button onClick={load}>{t("common.retry")}</button></div>;
  if (!p) return null;
  const langs = Object.entries(p.languages);
  const totals = p.totals;
  if (totals.attempts === 0) {
    return <section className="card"><h2>{t("prog.title")}</h2><p className="muted">{t("prog.empty")}</p><Link href="/coach"><button>{t("prog.goCoach")}</button></Link></section>;
  }
  const errTypes: Record<string, number> = {};
  langs.forEach(([, d]) => d.error_types.forEach((r) => { errTypes[r.error_type] = (errTypes[r.error_type] ?? 0) + r.total; }));
  const topErrors = Object.entries(errTypes).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([k, v]) => ({ key: k, label: tx(`et.${k}`, k.replace(/_/g, " ").toLowerCase()), value: v }));
  const pct = (x: number | null | undefined) => (x == null ? t("prog.none") : `${Math.round(x * 100)}%`);

  return (
    <>
      <section className="card">
        <h2>{t("prog.title")}</h2>
        <p className="muted small">{t("prog.note", { n: p.min_submissions_for_trend + 1 })}</p>
        <div>
          <Stat label={t("prog.corrections")} value={totals.attempts} />
          <Stat label={t("prog.corrected")} value={totals.corrected_sentences} />
          <Stat label={t("prog.errors")} value={totals.errors_found} />
          <Stat label={t("prog.avgConf")} value={pct(totals.avg_confidence)} />
          <Stat label={t("prog.acceptRate")} value={pct(totals.suggestion_acceptance_rate)} />
          <Stat label={t("prog.educator")} value={totals.educator_verdicts} />
          <Stat label={t("prog.abstained")} value={totals.o3_abstained} />
        </div>
      </section>

      <div className="grid2 top">
        <section className="card">
          <h3>{t("prog.activity")}</h3>
          <Bars label={t("prog.activity")} data={p.activity.map((a) => ({ key: a.date, label: a.date.slice(8), value: a.count }))} />
        </section>
        <section className="card">
          <h3>{t("prog.byLanguage")}</h3>
          <Bars label={t("prog.byLanguage")} data={langs.map(([c, d]) => ({ key: c, label: names[c] ?? c, value: d.stats.attempts }))} />
        </section>
      </div>

      {topErrors.length > 0 && (
        <section className="card"><h3>{t("prog.errorsByType")}</h3><Bars label={t("prog.errorsByType")} data={topErrors} /></section>
      )}

      {langs.filter(([, d]) => d.stats.attempts > 0).map(([code, d]) => (
        <section key={code} className="card">
          <h3>{names[code] ?? code} <span className="muted small">· {t("prog.attempts")}: {d.stats.attempts}</span></h3>
          <div>
            <Stat label={t("prog.corrected")} value={d.stats.corrected_sentences} /><Stat label={t("prog.errors")} value={d.stats.errors_found} />
            <Stat label={t("prog.avgConf")} value={pct(d.stats.avg_confidence)} /><Stat label={t("prog.accepted")} value={d.stats.learner_accepted} />
            <Stat label={t("prog.rejected")} value={d.stats.learner_rejected} /><Stat label={t("prog.blocked")} value={d.stats.o3_blocked_edits} />
          </div>
          {d.note && <p className="notice warn">{d.note}</p>}
          {d.focus.length > 0 && <p>{t("prog.focus")}: {d.focus.map((f) => <span key={f} className="chip warn" style={{ marginRight: 6 }}>{tx(`et.${f}`, f.toLowerCase())}</span>)}</p>}
          {d.error_types.length > 0 && (
            <table><thead><tr><th>{t("prog.errorType")}</th><th>{t("prog.total")}</th><th>{t("prog.recent")}</th><th>{t("prog.earlier")}</th><th>{t("prog.trend")}</th></tr></thead>
              <tbody>{d.error_types.map((r) => <tr key={r.error_type}><td>{tx(`et.${r.error_type}`, r.error_type.replace(/_/g, " ").toLowerCase())}</td><td>{r.total}</td><td>{r.recent_per_100_tokens}</td><td>{r.earlier_per_100_tokens ?? "—"}</td><td>{tx(`prog.trend.${r.trend}`, r.trend)}</td></tr>)}</tbody></table>
          )}
        </section>
      ))}

      <section className="card">
        <h2>{t("prog.recentHistory")}</h2>
        <table><thead><tr><th>{t("prog.when")}</th><th>{t("prog.lang")}</th><th>{t("prog.original")}</th><th>{t("prog.correctedText")}</th><th>{t("prog.runs")}</th></tr></thead>
          <tbody>{h.map((s) => {
            const o2 = s.runs.find((r) => r.pipeline === "o2");
            return (
              <tr key={s.submission_id}><td className="small">{new Date(s.created_at).toLocaleString()}</td><td>{names[s.language] ?? s.language}</td><td className="lang-text">{s.text}</td>
                <td className="lang-text">{o2?.corrected ?? "—"}</td>
                <td>{s.runs.map((r) => <div key={r.run_id} className="small"><b>{r.pipeline.toUpperCase()}</b>{r.mode !== "reference" ? ` (${r.mode})` : ""}: {t("prog.edits", { n: r.n_edits })}{r.abstained ? ` · ${t("run.abstained")}` : ""}</div>)}</td></tr>
            );
          })}</tbody></table>
      </section>
    </>
  );
}
export default function Page() { return <Gate roles={["learner"]}><View /></Gate>; }
