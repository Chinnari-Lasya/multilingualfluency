"use client";
import { useI18n } from "@/lib/i18n";
export function Footer() { const { t } = useI18n(); return <footer className="footer">{t("app.footer")}</footer>; }
