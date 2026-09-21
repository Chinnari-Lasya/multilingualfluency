"use client";
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, ApiError, post, tokenStore, UNAUTH_EVENT, type Role, type User } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { LOCALES, type Locale } from "@/lib/messages";

export interface RegisterForm { name: string; username: string; password: string; confirm_password: string; role: Role; preferred_language: string; invite_code?: string }

export const homeFor = (role: Role) => (role === "educator" ? "/educator" : role === "admin" ? "/evaluation" : "/coach");

interface AuthCtx {
  user: User | null; ready: boolean;
  login: (u: string, p: string) => Promise<User>;
  register: (f: RegisterForm) => Promise<User>;
  savePreferredLanguage: (code: string) => void;
  logout: () => Promise<void>;
}
const Ctx = createContext<AuthCtx>({ user: null, ready: false, login: async () => { throw new Error("no provider"); }, register: async () => { throw new Error("no provider"); }, logout: async () => {}, savePreferredLanguage: () => {} });
export const useAuth = () => useContext(Ctx);

/** Translate any error into a user-facing message in the current UI language. */
export function useErrText() {
  const { t, tx } = useI18n();
  return (e: unknown) => {
    if (e instanceof ApiError) return tx(`err.${e.code}`, t("err.generic"));
    return t("err.generic");
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const { setLocale } = useI18n();

  // Restore the session from the stored token by asking the BACKEND who we are (no client-side trust).
  useEffect(() => {
    if (!tokenStore.get()) { setReady(true); return; }
    api<User>("/api/v1/me").then((u) => { setUser(u); applyLocale(u); }).catch(() => { tokenStore.set(null); setUser(null); }).finally(() => setReady(true));
  }, []);
  // Any 401 from the API (expired/revoked token) drops the session everywhere.
  useEffect(() => {
    const h = () => setUser(null);
    window.addEventListener(UNAUTH_EVENT, h);
    return () => window.removeEventListener(UNAUTH_EVENT, h);
  }, []);

  // the user's saved language preference becomes the UI language (and is what they see after refresh/sign-in)
  const applyLocale = (u: User) => { if (LOCALES.some((l) => l.code === u.preferred_language)) setLocale(u.preferred_language as Locale); };
  const finish = (r: { token: string; user: User }) => { tokenStore.set(r.token); setUser(r.user); applyLocale(r.user); return r.user; };
  const login = useCallback(async (username: string, password: string) => finish(await post("/api/v1/auth/login", { username, password })), []);
  const register = useCallback(async (f: RegisterForm) => finish(await post("/api/v1/auth/register", f)), []);
  const savePreferredLanguage = useCallback((code: string) => {
    if (!tokenStore.get()) return;
    api<User>("/api/v1/me/preferences", { method: "PATCH", body: JSON.stringify({ preferred_language: code }) }).then((u) => setUser((cur) => (cur ? { ...cur, preferred_language: u.preferred_language } : cur))).catch(() => {});
  }, []);
  const logout = useCallback(async () => {
    try { await post("/api/v1/auth/logout", {}); } catch { /* token may already be invalid: still sign out locally */ }
    tokenStore.set(null);
    setUser(null);
  }, []);
  return <Ctx.Provider value={{ user, ready, login, register, logout, savePreferredLanguage }}>{children}</Ctx.Provider>;
}

/** Protects a page: redirects to /signin when signed out, and to the role's home when the role is not allowed. */
export function Gate({ roles, children }: { roles?: Role[]; children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const path = usePathname();
  const denied = !!user && !!roles && !roles.includes(user.role);
  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace(`/signin?next=${encodeURIComponent(path)}`);
    else if (denied) router.replace(homeFor(user.role));
  }, [ready, user, denied, router, path]);
  if (!ready || !user || denied) return <p className="muted">{denied ? t("auth.wrongRole", { role: user!.role }) : t("common.loading")}</p>;
  return <>{children}</>;
}
