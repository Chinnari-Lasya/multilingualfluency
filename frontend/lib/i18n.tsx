"use client";
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { LOCALES, MESSAGES, type Locale } from "./messages";

interface I18n {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  /** like t() but returns `fallback` when no translation exists (used for data-driven labels) */
  tx: (key: string, fallback: string) => string;
}
const Ctx = createContext<I18n>({ locale: "en", setLocale: () => {}, t: (k) => k, tx: (_k, f) => f });
export const useI18n = () => useContext(Ctx);

const STORE = "gec_locale";

function fmt(s: string, vars?: Record<string, string | number>) {
  return vars ? s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`)) : s;
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLoc] = useState<Locale>("en");
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORE) as Locale | null;
      if (saved && LOCALES.some((l) => l.code === saved)) setLoc(saved);
    } catch { /* storage unavailable: stay on English */ }
  }, []);
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  const setLocale = useCallback((l: Locale) => {
    setLoc(l);
    try { window.localStorage.setItem(STORE, l); } catch { /* ignore */ }
  }, []);
  const lookup = (key: string): string | undefined => MESSAGES[locale][key] ?? MESSAGES.en[key];
  const t = (key: string, vars?: Record<string, string | number>) => fmt(lookup(key) ?? key, vars);
  const tx = (key: string, fallback: string) => lookup(key) ?? fallback;
  return <Ctx.Provider value={{ locale, setLocale, t, tx }}>{children}</Ctx.Provider>;
}
