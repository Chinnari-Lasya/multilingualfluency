"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { homeFor, useAuth } from "@/components/Auth";
import { useI18n } from "@/lib/i18n";

export default function Home() {
  const { user, ready } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  useEffect(() => { if (ready && user) router.replace(homeFor(user.role)); }, [ready, user, router]);
  return (
    <section className="card narrow" style={{ textAlign: "center" }}>
      <h1 style={{ margin: "0 0 8px" }}>{t("home.title")}</h1>
      <p className="muted">{t("home.subtitle")}</p>
      <div className="row" style={{ justifyContent: "center" }}>
        <Link href="/signin"><button>{t("nav.signin")}</button></Link>
        <Link href="/signup"><button className="secondary">{t("nav.signup")}</button></Link>
      </div>
    </section>
  );
}
