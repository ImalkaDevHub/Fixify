import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { connection } from "next/server";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-jb", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Fixify — Find bugs. Understand them. Fix them.", template: "%s · Fixify" },
  description:
    "An intelligent website testing platform that detects real-world issues, explains what went wrong, and helps your team generate human-reviewed fixes.",
};

export const viewport: Viewport = { themeColor: "#090D1A", colorScheme: "dark" };

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Render every page per request so it carries this request's CSP nonce (see proxy.ts).
  // Statically prerendered HTML has no nonce and would be blocked by the strict script policy.
  await connection();
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
