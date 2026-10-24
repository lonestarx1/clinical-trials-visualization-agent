import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { themeScript } from "@/lib/themes/runtime";
import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Clinical Trials Explorer",
  description: "Ask questions about ClinicalTrials.gov and get charts where every number links back to the trials behind it.",
};

export const viewport: Viewport = { themeColor: "#eef2f8" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript() }} /></head>
      <body>{children}</body>
    </html>
  );
}
