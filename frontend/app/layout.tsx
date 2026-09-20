import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/Auth";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { I18nProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "Multilingual GEC Coach",
  description: "Grammatical error correction and fluency-aware learning coach for Telugu, Odia, Hindi, English, Japanese and Korean",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <I18nProvider>
          <AuthProvider>
            <Nav />
            <main className="container">{children}</main>
            <Footer />
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
