"use client";
import { useCallback, useEffect, useState } from "react";
import { Gate, useAuth, useErrText } from "@/components/Auth";
import { api, post, type Edit } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface QItem extends Edit { context: string; pipeline: string; mode: string }
interface Summary { status: string; n_independent_reviews: number; n_total_adjudications_incl_demo: number; acceptance_rate?: number; wilson_95?: number[] }

function Item({ e, onDone }: { e: QItem; onDone: () => void }) {
  const { t, tx } = useI18n();
  const errText = useErrText();
  const [mod, setMod] = useState(false);
  const [text, setText] = useState(e.replacement);
  const [notes, setNotes] = useState("");
  const [meaning, setMeaning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function act(v: "accept" | "reject" | "revise") {
    try { await post(`/api/v1/edits/${e.id}/adjudications`, { verdict: v, revised_replacement: v === "revise" ? text : null, notes, meaning_changed: meaning }); onDone(); }
    catch (x) { setErr(errText(x)); }
  }
  return (
    <li className="edit">
      <p className="small muted">{e.language.toUpperCase()} · {e.pipeline.toUpperCase()}{e.mode !== "reference" ? ` (${e.mode})` : ""} · {tx(`et.${e.error_type}`, e.error_type.toLowerCase())} · {e.confidence != null ? `${Math.round(e.confidence * 100)}% ${t("run.uncalibrated")}` : ""}{e.gate_status === "rejected" ? ` · ${t("edu.blocked")}` : ""}</p>
      <p className="lang-text">{e.context}</p>
      <p className="chg"><del>{e.original || "∅"}</del> <span className="arrow">→</span> <ins>{e.replacement || "∅"}</ins></p>
      {e.explanation && <p className="explain small">{e.explanation.text}</p>}
      {e.gate_reason && <p className="gate-reason">{e.gate_reason}</p>}
      <div className="row tight">
        <input placeholder={t("edu.notes")} value={notes} onChange={(x) => setNotes(x.target.value)} className="grow" />
        <label style={{ margin: 0 }}><input type="checkbox" style={{ width: "auto" }} checked={meaning} onChange={(x) => setMeaning(x.target.checked)} /> {t("edu.meaningChanged")}</label>
      </div>
      <div className="row tight">
        <button className="small" onClick={() => act("accept")}>{t("run.accept")}</button>
        <button className="small secondary" onClick={() => act("reject")}>{t("run.reject")}</button>
        <button className="small secondary" onClick={() => setMod(!mod)}>{t("run.modify")}</button>
      </div>
      {mod && <div className="row tight"><input className="grow lang-text" value={text} onChange={(x) => setText(x.target.value)} /><button className="small" disabled={!text} onClick={() => act("revise")}>{t("run.saveMod")}</button></div>}
      {err && <p className="error" role="alert">{err}</p>}
    </li>
  );
}

function View() {
  const { user } = useAuth();
  const { t } = useI18n();
  const errText = useErrText();
  const [q, setQ] = useState<QItem[]>([]);
  const [sum, setSum] = useState<Summary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => {
    Promise.all([api<QItem[]>("/api/v1/review/queue"), api<Summary>("/api/v1/review/summary")]).then(([a, b]) => { setQ(a); setSum(b); setErr(null); }).catch((e) => setErr(errText(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(load, [load]);
  return (
    <>
      <section className="card">
        <h2>{t("edu.acceptance")}</h2>
        {sum && sum.status === "not_performed_yet" ? (
          <p><b>{t("edu.notPerformed")}</b> {t("edu.notPerformedDetail")} {sum.n_total_adjudications_incl_demo > 0 && <span className="muted">{t("edu.demoExcluded", { n: sum.n_total_adjudications_incl_demo })}</span>}</p>
        ) : sum ? (
          <p>{t("edu.reviews", { n: sum.n_independent_reviews, rate: sum.acceptance_rate != null ? Math.round(sum.acceptance_rate * 100) + "%" : "—" })} {sum.wilson_95 && `(95% CI ${sum.wilson_95.map((x) => Math.round(x * 100)).join("–")}%)`}</p>
        ) : <p className="muted">{t("common.loading")}</p>}
        {user && !user.is_independent_educator && <p className="notice warn">{t("edu.demoNote")}</p>}
      </section>
      <section className="card">
        <h2>{t("edu.queue")} <span className="muted small">{t("edu.queueSub")}</span></h2>
        {err && <p className="error" role="alert">{err}</p>}
        {q.length === 0 ? <p className="muted">{t("edu.nothing")}</p> : <ul className="edits">{q.map((e) => <Item key={e.id} e={e} onDone={load} />)}</ul>}
      </section>
    </>
  );
}
export default function Page() { return <Gate roles={["educator", "admin"]}><View /></Gate>; }
