import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { headers } from "next/headers";
import { connection } from "next/server";
import { THEME_COLOR, THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-jb", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Fixify — Find bugs. Understand them. Fix them.", template: "%s · Fixify" },
  description:
    "An intelligent website testing platform that detects real-world issues, explains what went wrong, and helps your team generate human-reviewed fixes.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: THEME_COLOR.light },
    { media: "(prefers-color-scheme: dark)", color: THEME_COLOR.dark },
  ],
  colorScheme: "light dark",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Render every page per request so it carries this request's CSP nonce (see proxy.ts).
  // Statically prerendered HTML has no nonce and would be blocked by the strict script policy.
  await connection();
  // Same nonce proxy.ts put on the response's CSP header, forwarded via this request header, so
  // the inline theme script below is allowed to run under the strict script-src.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    // suppressHydrationWarning: the inline script sets data-theme/data-theme-pref on the client
    // before React hydrates, which the server-rendered markup never had — an expected, one-time
    // mismatch on this element only, not a real one.
    <html lang="en" className={`${inter.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-screen">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
