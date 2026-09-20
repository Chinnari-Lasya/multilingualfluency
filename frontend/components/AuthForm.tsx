"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { homeFor, useAuth, useErrText } from "./Auth";
import { useI18n } from "@/lib/i18n";
import { LOCALES } from "@/lib/messages";
import type { Role } from "@/lib/api";

const ROLES: Role[] = ["learner", "educator", "admin"];
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const USERNAME = /^[A-Za-z0-9_]{3,32}$/;

function Form({ mode }: { mode: "signin" | "signup" }) {
  const { user, ready, login, register } = useAuth();
  const { t, locale } = useI18n();
  const errText = useErrText();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [identifier, setId] = useState("");
  const [password, setP] = useState("");
  const [confirm, setC] = useState("");
  const [name, setN] = useState("");
  const [role, setRole] = useState<Role>("learner");
  const [lang, setLang] = useState<string>(locale);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // the preferred-language field follows the interface language until the user changes it explicitly
  const [langTouched, setLangTouched] = useState(false);
  useEffect(() => { if (!langTouched) setLang(locale); }, [locale, langTouched]);
  // already signed in -> go to the role dashboard
  useEffect(() => { if (ready && user) router.replace(next && next.startsWith("/") ? next : homeFor(user.role)); }, [ready, user, router, next]);

  function validate(): string | null {
    if (!identifier.trim() || !password || (mode === "signup" && (!name.trim() || !confirm))) return t("err.required");
    if (mode === "signup") {
      const id = identifier.trim();
      if (id.includes("@") ? !EMAIL.test(id) : !USERNAME.test(id)) return id.includes("@") ? t("err.invalid_email") : t("err.invalid_username");
      if (password.length < 8) return t("err.weak_password");
      if (password !== confirm) return t("err.password_mismatch");
    }
    return null;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const v = validate();
    if (v) { setErr(v); return; }
    setBusy(true); setErr(null);
    try {
      const u = mode === "signin"
        ? await login(identifier, password)
        : await register({ name, username: identifier, password, confirm_password: confirm, role, preferred_language: lang });
      router.replace(mode === "signin" && next && next.startsWith("/") ? next : homeFor(u.role));
    } catch (x) { setErr(errText(x)); } finally { setBusy(false); }
  }
  async function demo(u: string) {
    setBusy(true); setErr(null);
    try { const r = await login(u, "demo"); router.replace(homeFor(r.role)); } catch (x) { setErr(errText(x)); } finally { setBusy(false); }
  }

  return (
    <div className="card narrow">
      <h2>{mode === "signin" ? t("auth.signin.title") : t("auth.signup.title")}</h2>
      <form onSubmit={submit} noValidate>
        {mode === "signup" && (<><label htmlFor="n">{t("auth.name")}</label><input id="n" autoComplete="name" value={name} onChange={(e) => setN(e.target.value)} maxLength={64} /></>)}
        <label htmlFor="u">{mode === "signup" ? t("auth.identifier") : t("auth.identifier")}</label>
        <input id="u" autoComplete="username" value={identifier} onChange={(e) => setId(e.target.value)} maxLength={64} />
        {mode === "signup" && <p className="muted small">{t("auth.hint.identifier")}</p>}
        <label htmlFor="p">{t("auth.password")}</label>
        <input id="p" type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} value={password} onChange={(e) => setP(e.target.value)} />
        {mode === "signup" && (
          <>
            <p className="muted small">{t("auth.hint.password")}</p>
            <label htmlFor="c">{t("auth.confirm")}</label>
            <input id="c" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setC(e.target.value)} />
            <div className="grid2">
              <div><label htmlFor="r">{t("auth.role")}</label>
                <select id="r" value={role} onChange={(e) => setRole(e.target.value as Role)}>{ROLES.map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}</select></div>
              <div><label htmlFor="l">{t("auth.prefLang")}</label>
                <select id="l" value={lang} onChange={(e) => { setLang(e.target.value); setLangTouched(true); }}>{LOCALES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}</select></div>
            </div>
            <p className="muted small">{t("auth.protoRole")}</p>
          </>
        )}
        <div className="row">
          <button type="submit" disabled={busy}>{busy ? t("auth.working") : mode === "signin" ? t("auth.submit.signin") : t("auth.submit.signup")}</button>
          <span className="muted small">{mode === "signin" ? t("auth.noAccount") : t("auth.haveAccount")} <Link href={mode === "signin" ? "/signup" : "/signin"}>{mode === "signin" ? t("nav.signup") : t("nav.signin")}</Link></span>
        </div>
      </form>
      {err && <p className="error" role="alert">{err}</p>}
      {mode === "signin" && (
        <>
          <hr style={{ border: 0, borderTop: "1px solid var(--line)", margin: "18px 0" }} />
          <p className="muted small">{t("auth.demoAs")}</p>
          <div className="row tight">
            {["learner", "educator", "admin"].map((r) => <button key={r} type="button" className="secondary" disabled={busy} onClick={() => demo(r)}>{t(`role.${r}`)}</button>)}
          </div>
        </>
      )}
    </div>
  );
}

export function AuthForm({ mode }: { mode: "signin" | "signup" }) {
  return <Suspense fallback={null}><Form mode={mode} /></Suspense>;
}
