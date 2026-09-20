"use client";
import { useEffect, useState } from "react";
import { Gate, useAuth, useErrText } from "@/components/Auth";
import { RunCard } from "@/components/RunCard";
import { api, post, type Compare, type Lang } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

// Example INPUTS (learner sentences containing errors), several per language. They are sent to the real pipeline;
// no result is pre-baked. "Insert sample" cycles through them.
const SAMPLES: Record<string, string[]> = {
  en: ["I likes to swimming in the pool. She don't know nothing.", "He go to school yesterday and buy a apple.", "We was very happy to see the the teacher ."],
  hi: ["मैं स्कूल जाती है। राम ने ने खाना खाया|", "वे किताबें पढ़ता है।", "लड़कियाँ खेल रहा है।"],
  ko: ["나는 학교을 갑니다. 한국어는어렵다.", "저는 어제 친구를 만나요.", "저는 커피을 좋아합니다."],
  ja: ["私は学校を行きます,  昨日友達をを会いました.", "私は日本語が勉強します。", "彼は先生がです。"],
  te: ["నేను నేను ఇంటికి వెళ్తాను.  ఈ రోజు వాతావరణం బాగుంది.", "వారు పుస్తకం చదివాడు.", "అతను పాఠశాలకు వెళ్ళింది."],
  or: ["ମୁଁ ମୁଁ ଘରକୁ ଯାଉଛି |", "ସେମାନେ ବହି ପଢ଼େ ।", "ପିଲାମାନେ ଖେଳୁଛି ।"],
};
const CODES = Object.keys(SAMPLES);
const TEXT_LANG_KEY = "gec_text_lang";

function Coach() {
  const { t, tx } = useI18n();
  const errText = useErrText();
  const [langs, setLangs] = useState<Lang[]>([]);
  const { user } = useAuth();
  const [lang, setLangState] = useState("en");
  const [text, setText] = useState(SAMPLES.en[0]);
  const [sampleIdx, setSampleIdx] = useState(0);
  const [mode, setMode] = useState<"minimal" | "fluency">("minimal");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<Compare | null>(null);

  // text language: last used, else the user's saved preference, else English (independent of the UI language)
  useEffect(() => {
    let saved: string | null = null;
    try { saved = window.localStorage.getItem(TEXT_LANG_KEY); } catch { /* ignore */ }
    const initial = [saved, user?.preferred_language, "en"].find((c) => c && CODES.includes(c)) as string;
    setLangState(initial); setText(SAMPLES[initial][0]); setSampleIdx(1);
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  function changeLang(code: string) {
    setLangState(code); setText(SAMPLES[code][0]); setSampleIdx(1); setRes(null); setErr(null);
    try { window.localStorage.setItem(TEXT_LANG_KEY, code); } catch { /* ignore */ }
  }
  function insertSample() { const list = SAMPLES[lang] ?? SAMPLES.en; setText(list[sampleIdx % list.length]); setSampleIdx((i) => i + 1); setErr(null); }

  useEffect(() => { api<Lang[]>("/api/v1/languages").then(setLangs).catch((e) => setErr(errText(e))); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  const cap = langs.find((l) => l.code === lang)?.capability;

  async function submit() {
    setBusy(true); setErr(null);
    try { setRes(await post<Compare>("/api/v1/corrections/compare", { text, language: lang, o3_mode: mode, explain: true })); }
    catch (e) { setErr(errText(e)); setRes(null); }
    finally { setBusy(false); }
  }
  async function refresh() {
    if (!res) return;
    try {
      const [o2, o3] = await Promise.all([api<Compare["o2"]>(`/api/v1/corrections/${res.o2.run_id}`), api<Compare["o3"]>(`/api/v1/corrections/${res.o3.run_id}`)]);
      setRes({ ...res, o2, o3 });
    } catch { /* keep the current view */ }
  }

  return (
    <>
      <section className="card">
        <h2>{t("coach.title")}</h2>
        <div className="grid2">
          <label>{t("coach.language")}
            <select value={lang} onChange={(e) => changeLang(e.target.value)}>
              {langs.map((l) => <option key={l.code} value={l.code}>{l.native_name} — {l.name}</option>)}
            </select>
          </label>
          <label>{t("coach.mode")}
            <select value={mode} onChange={(e) => setMode(e.target.value as "minimal" | "fluency")}>
              <option value="minimal">{t("coach.mode.minimal")}</option>
              <option value="fluency">{t("coach.mode.fluency")}</option>
            </select>
          </label>
        </div>
        <p className="muted small">{t("coach.textLangNote")}</p>
        {cap && (
          <div className={`notice ${cap.level === "rules_and_detection" ? "warn" : ""}`}>
            <b>{tx(`cap.${cap.level}`, cap.level)}</b> — {cap.summary}
            <details><summary className="small">{t("coach.limitations")}</summary><ul>{cap.limitations.map((l, i) => <li key={i} className="small">{l}</li>)}</ul>{cap.license_note && <p className="small">{cap.license_note}</p>}</details>
          </div>
        )}
        <label htmlFor="txt">{t("coach.yourText")}</label>
        <textarea id="txt" className="lang-text" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("coach.placeholder")} />
        <div className="row">
          <button onClick={submit} disabled={busy || !text.trim()}>{busy ? t("coach.correcting") : t("coach.correct")}</button>
          <button type="button" className="secondary" onClick={insertSample}>{t("coach.sample")}</button>
        </div>
        {err && <p className="error" role="alert">{err}</p>}
      </section>

      {res && (
        <>
          <section className="card">
            <h3>{t("coach.original")}</h3>
            <p className="text lang-text">{res.source}</p>
            <p className="muted small">{t("coach.saved", { lang: res.language, id: res.submission_id })}</p>
          </section>
          <div className="grid2 top">
            <RunCard run={res.o2} title={t("run.o2.title")} subtitle={t("run.o2.sub")} onChanged={refresh} />
            <RunCard run={res.o3} title={t("run.o3.title", { mode: res.o3.mode })} subtitle={t("run.o3.sub")} onChanged={refresh} />
          </div>
        </>
      )}
    </>
  );
}

export default function Page() { return <Gate><Coach /></Gate>; }
