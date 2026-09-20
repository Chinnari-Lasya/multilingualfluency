"use client";
import React, { useState } from "react";
import { post, type Edit, type Run } from "@/lib/api";
import { segments } from "@/lib/text";
import { useI18n } from "@/lib/i18n";
import { useAuth, useErrText } from "./Auth";

function Chip({ tone, children, title }: { tone: string; children: React.ReactNode; title?: string }) {
  return <span className={`chip ${tone}`} title={title}>{children}</span>;
}

function Marked({ run }: { run: Run }) {
  return (
    <p className="text lang-text">
      {segments(run.source, run.edits).map((s, i) => {
        if (s.kind === "plain") return <span key={i}>{s.text}</span>;
        const e = s.edit!;
        return (
          <span key={i} className={`mark ${e.gate_status === "rejected" ? "rejected" : "applied"}`} title={`${e.error_type}${e.gate_reason ? " — " + e.gate_reason : ""}`}>
            {s.text && <del>{s.text}</del>}
            {e.replacement && <ins>{e.replacement}</ins>}
          </span>
        );
      })}
    </p>
  );
}

function EditRow({ e, onChanged }: { e: Edit; onChanged: () => void }) {
  const { user } = useAuth();
  const { t, tx } = useI18n();
  const errText = useErrText();
  const [modify, setModify] = useState(false);
  const [text, setText] = useState(e.replacement);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const isReviewer = user?.role === "educator" || user?.role === "admin";
  const conf = e.confidence == null ? null : Math.round(e.confidence * 100);
  const label = tx(`et.${e.error_type}`, e.error_type.replace(/_/g, " ").toLowerCase());

  async function act(kind: "accept" | "reject" | "revise") {
    if (e.id == null) return;
    setBusy(true); setMsg(null);
    try {
      if (isReviewer) await post(`/api/v1/edits/${e.id}/adjudications`, { verdict: kind, revised_replacement: kind === "revise" ? text : null });
      else await post(`/api/v1/edits/${e.id}/decision`, { decision: kind });
      setMsg(isReviewer ? t("run.recorded", { v: kind === "revise" ? t("run.modify") : kind === "accept" ? t("run.accept") : t("run.reject") }) : kind === "accept" ? t("run.youAccepted") : t("run.youRejected"));
      setModify(false);
      onChanged();
    } catch (err) { setMsg(errText(err)); } finally { setBusy(false); }
  }

  return (
    <li className={`edit ${e.gate_status === "rejected" ? "blocked" : ""}`}>
      <div className="edit-head">
        <span className="chg">{e.original ? <del>{e.original}</del> : <em className="muted">{t("run.insert")}</em>} <span className="arrow">→</span> {e.replacement ? <ins>{e.replacement}</ins> : <em className="muted">{t("run.delete")}</em>}</span>
        <Chip tone="cat" title={e.rule_id ?? ""}>{label}</Chip>
        <Chip tone="src">{e.source.startsWith("rule:") ? t("run.src.rule") : e.source.startsWith("model:") ? t("run.src.model") : e.source}</Chip>
        {e.gate_status === "accepted" && <Chip tone="ok">{t("run.gate.passed")}</Chip>}
        {e.gate_status === "rejected" && <Chip tone="bad">{t("run.gate.blocked")}</Chip>}
      </div>
      {conf != null && (
        <div className="conf">
          <div className="bar"><div style={{ width: `${conf}%` }} /></div>
          <span>{t("run.confidence", { n: conf })} {!e.confidence_calibrated && <em className="muted">{t("run.uncalibrated")}</em>}</span>
        </div>
      )}
      {e.gate_reason && <p className="gate-reason">{t("run.blocked", { reason: e.gate_reason })}</p>}
      {e.explanation && (
        <p className="explain">
          {e.explanation.text}
          <span className="muted small"> · {e.explanation.source === "llm" ? t("run.expl.llm") : t("run.expl.template")} · {t("run.expl.unreviewed")} · {t("run.expl.english")}</span>
        </p>
      )}
      {e.id != null && e.gate_status !== "rejected" && (
        <div className="row tight">
          <button className="small" disabled={busy} onClick={() => act("accept")}>{isReviewer ? t("run.accept") : t("run.acceptSuggestion")}</button>
          <button className="small secondary" disabled={busy} onClick={() => act("reject")}>{t("run.reject")}</button>
          {isReviewer && <button className="small secondary" disabled={busy} onClick={() => setModify((m) => !m)}>{t("run.modify")}</button>}
          {(e.adjudications ?? []).map((a, i) => <Chip key={i} tone="src">{a.verdict}{a.reviewer_independent ? "" : " (demo)"}</Chip>)}
        </div>
      )}
      {modify && (
        <div className="row tight">
          <input value={text} onChange={(ev) => setText(ev.target.value)} className="grow lang-text" />
          <button className="small" disabled={busy || !text} onClick={() => act("revise")}>{t("run.saveMod")}</button>
        </div>
      )}
      {msg && <p className="muted small">{msg}</p>}
    </li>
  );
}

export function RunCard({ run, title, subtitle, onChanged }: { run: Run; title: string; subtitle: string; onChanged: () => void }) {
  const { t } = useI18n();
  const mp = run.assessment?.meaning_preservation;
  const oc = run.assessment?.over_correction;
  const applied = run.edits.filter((e) => e.gate_status !== "rejected").length;
  const mpTone = mp?.status === "preserved" ? "ok" : mp?.status === "violated" ? "bad" : "warn";
  const ocTone = oc?.risk === "low" ? "ok" : oc?.risk === "high" ? "bad" : "warn";
  return (
    <section className="card run">
      <div className="run-head"><div><h3>{title}</h3><p className="muted small">{subtitle}</p></div><span className="muted small">{Math.round(run.latency_ms)} ms</span></div>
      <div className="chips">
        <Chip tone={mpTone} title={mp?.hard_check_failures?.join(", ") || mp?.note}>{t("run.meaning")}: {mp ? t(`run.status.${mp.status}`) : t("common.na")}{mp?.similarity != null ? ` (${mp.similarity.toFixed(2)})` : ""}</Chip>
        <Chip tone={ocTone} title={oc?.note}>{t("run.overcorrection")}: {oc ? t(`run.risk.${oc.risk}`) : t("common.na")}</Chip>
        <Chip tone="src">{t("run.applied", { n: applied })}</Chip>
        {run.abstained && <Chip tone="warn">{t("run.abstained")}</Chip>}
        {run.degraded && <Chip tone="bad">{t("run.degraded")}</Chip>}
      </div>
      {run.abstained && <p className="notice warn">{t("run.abstainedNote", { reason: run.abstain_reason ?? "" })}</p>}
      <h4>{t("run.corrected")}</h4>
      <p className="text lang-text corrected">{run.corrected}</p>
      <h4>{t("run.edits")} <span className="muted small">{t("run.edits.legend")}</span></h4>
      <Marked run={run} />
      {run.edits.length === 0 ? <p className="muted">{t("run.noEdits")}</p> : <ul className="edits">{run.edits.map((e, i) => <EditRow key={e.id ?? i} e={e} onChanged={onChanged} />)}</ul>}
      {!!run.flags?.length && (
        <div className="flags">
          <h4>{t("run.flags")} <span className="muted small">{t("run.flags.sub")}</span></h4>
          <ul>{run.flags.map((f, i) => <li key={i}><span className="lang-text">{f.text}</span> <span className="muted small">{f.reason}</span></li>)}</ul>
        </div>
      )}
      {!!oc?.edits_blocked_by_gates.length && <div className="notice"><b>{t("run.blockedOver")}</b> {oc.edits_blocked_by_gates.map((b, i) => <span key={i} className="lang-text"> {b.original || "∅"}→{b.replacement || "∅"} </span>)}</div>}
      {!!run.warnings?.length && <details><summary className="muted small">{t("run.warnings", { n: run.warnings.length })}</summary><ul>{run.warnings.map((w, i) => <li key={i} className="small">{w}</li>)}</ul></details>}
      <details><summary className="muted small">{t("run.repro")}</summary><pre className="small">{JSON.stringify({ models: run.model_ids, trace: run.trace }, null, 2)}</pre></details>
    </section>
  );
}
