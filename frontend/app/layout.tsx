import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const mono = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "OpsMind — Incident memory",
  description: "An AI incident-response agent that learns from past incidents using Hindsight memory.",
  // The UI is natively dark: ask the Dark Reader extension not to rewrite it (its injected
  // attributes otherwise cause React hydration mismatches).
  other: { "darkreader-lock": "" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${mono.variable} antialiased`}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
