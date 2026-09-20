"use client";
import { useEffect, useState } from "react";
import { Gate, useAuth, useErrText } from "@/components/Auth";
import { api, post, type Lang } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface Info { provider: string; model: string | null; license: string | null; note: string }
interface Result { translation: string; source_language: string; target_language: string; provider: string; model: string | null }

const FALLBACK: Lang[] = ["te", "or", "hi", "en", "ja", "ko"].map((c) => ({ code: c, name: c, native_name: c, capability: {} as Lang["capability"] }));

function Translate() {
  const { t } = useI18n();
  const { user } = useAuth();
  const errText = useErrText();
  const [langs, setLangs] = useState<Lang[]>(FALLBACK);
  const [src, setSrc] = useState("en");
  const [tgt, setTgt] = useState("hi");
  const [text, setText] = useState("");
  const [out, setOut] = useState<Result | null>(null);
  const [info, setInfo] = useState<Info | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Lang[]>("/api/v1/languages").then(setLangs).catch(() => {});
    api<Info>("/api/v1/translate/info").then(setInfo).catch(() => {});
  }, []);
  useEffect(() => { // default target = the user's preferred language when it differs from the source
    if (user?.preferred_language && user.preferred_language !== "en") setTgt(user.preferred_language);
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run() {
    setBusy(true); setErr(null); setOut(null);
    try { setOut(await post<Result>("/api/v1/translate", { text, source_language: src, target_language: tgt })); }
    catch (e) { setErr(errText(e)); }
    finally { setBusy(false); }
  }
  function swap() { setSrc(tgt); setTgt(src); if (out) { setText(out.translation); setOut(null); } }

  const opts = langs.map((l) => <option key={l.code} value={l.code}>{l.native_name} — {l.name}</option>);
  return (
    <section className="card">
      <h2>{t("tr.title")}</h2>
      <p className="muted">{t("tr.subtitle")}</p>
      <div className="row" style={{ alignItems: "end" }}>
        <label className="grow">{t("tr.source")}<select value={src} onChange={(e) => setSrc(e.target.value)}>{opts}</select></label>
        <button type="button" className="secondary" onClick={swap} title={t("tr.swap")} aria-label={t("tr.swap")}>⇄</button>
        <label className="grow">{t("tr.target")}<select value={tgt} onChange={(e) => setTgt(e.target.value)}>{opts}</select></label>
      </div>
      <label htmlFor="trin">{t("tr.input")}</label>
      <textarea id="trin" className="lang-text" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("tr.placeholder")} />
      <div className="row"><button onClick={run} disabled={busy || !text.trim()}>{busy ? t("tr.working") : t("tr.button")}</button></div>
      {err && <p className="error" role="alert">{err}</p>}
      {out && (
        <>
          <h4>{t("tr.output")}</h4>
          <p className="text lang-text corrected">{out.translation}</p>
          <p className="muted small">{t("tr.provider", { p: out.provider, m: out.model ?? "—" })}</p>
        </>
      )}
      <p className="notice">{t("tr.note")}{info?.license && <> {t("tr.license", { l: info.license })}</>}</p>
    </section>
  );
}
export default function Page() { return <Gate><Translate /></Gate>; }
