"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { homeFor, useAuth } from "./Auth";
import { useI18n } from "@/lib/i18n";
import { LOCALES, type Locale } from "@/lib/messages";

export function Nav() {
  const path = usePathname();
  const router = useRouter();
  const { user, logout, savePreferredLanguage } = useAuth();
  const { t, locale, setLocale } = useI18n();
  const links = user
    ? [
        { href: "/coach", label: t("nav.coach"), show: true },
        { href: "/progress", label: t("nav.progress"), show: user.role === "learner" },
        { href: "/translate", label: t("nav.translate"), show: true },
        { href: "/educator", label: t("nav.educator"), show: user.role !== "learner" },
        { href: "/evaluation", label: t("nav.evaluation"), show: user.role !== "learner" },
      ].filter((l) => l.show)
    : [];
  return (
    <header className="nav">
      <div className="nav-inner">
        <Link href={user ? homeFor(user.role) : "/"} className="brand"><span className="logo">文A</span> {t("app.name")}</Link>
        <nav>{links.map((l) => <Link key={l.href} href={l.href} className={path === l.href ? "active" : ""}>{l.label}</Link>)}</nav>
        <div className="who">
          <select aria-label={t("common.uiLang")} title={t("common.uiLang")} value={locale} onChange={(e) => { setLocale(e.target.value as Locale); savePreferredLanguage(e.target.value); }} style={{ width: "auto" }}>
            {LOCALES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
          {user ? (
            <>
              <span className="pill" title={user.username}>{t(`role.${user.role}`)}</span>
              <span>{user.display_name || user.username}</span>
              <button className="link" onClick={async () => { await logout(); router.replace("/signin"); }}>{t("nav.signout")}</button>
            </>
          ) : (
            <>
              <Link href="/signin" className={path === "/signin" ? "active" : ""}>{t("nav.signin")}</Link>
              <Link href="/signup" className={path === "/signup" ? "active" : ""}>{t("nav.signup")}</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
