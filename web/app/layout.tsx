import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import EngineProvider from "@/components/EngineProvider";
import Header from "@/components/Header";
import "./globals.css";

const jakarta = Plus_Jakarta_Sans({ subsets: ["latin", "latin-ext"], weight: ["600", "700"], variable: "--font-jakarta", display: "swap" });
const inter = Inter({ subsets: ["latin", "latin-ext"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["500"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: "CBJ Studio",
  description:
    "Text, image or video in, a 30-60 second CBJ ad out: a deterministic game pipeline with an agentic planner and controlled, proven edits.",
  applicationName: "CBJ Studio",
};

export const viewport: Viewport = {
  themeColor: "#f9f9ff",
  colorScheme: "light",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${jakarta.variable} ${inter.variable} ${mono.variable}`}>
      <body className="min-h-dvh bg-background font-sans text-body-md text-on-surface antialiased">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface-container-lowest focus:px-3 focus:py-2">
          Skip to content
        </a>
        <EngineProvider>
          <Header />
          <main id="main" className="mx-auto w-full max-w-[1560px] px-4 py-6 sm:px-6">
            {children}
          </main>
        </EngineProvider>
        <Analytics />
      </body>
    </html>
  );
}
