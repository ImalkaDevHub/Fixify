"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { isTheme, resolveTheme, THEME_COLOR, THEME_STORAGE_KEY, type ResolvedTheme, type Theme } from "@/lib/theme";

type ThemeContextValue = {
  /** The user's stored preference: "light" | "dark" | "system". */
  theme: Theme;
  /** What "system" currently resolves to, or the explicit choice. What components should render by. */
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Server-safe defaults: the server has nothing to read, so the client's first render must
  // match them exactly or React fails to hydrate. The real value — already on <html>, set by the
  // inline script in <head> before paint — is read client-only in the effect below, right after
  // hydration; the page's actual colors are already correct by then (that's the script's job),
  // so this is a same-frame state correction, not a visible flash.
  const [theme, setThemeState] = useState<Theme>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");

  const applyTheme = useCallback((next: Theme, transition = true) => {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const resolved = resolveTheme(next, prefersDark);
    const root = document.documentElement;

    if (transition) {
      // A brief, opt-in transition only while actively switching — not a permanent global one,
      // so it never animates the very first paint or fights other motion on the page.
      root.classList.add("theme-transition");
      window.setTimeout(() => root.classList.remove("theme-transition"), 200);
    }

    root.setAttribute("data-theme", resolved);
    root.setAttribute("data-theme-pref", next);
    root.style.colorScheme = resolved;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[resolved]);
    setResolvedTheme(resolved);
  }, []);

  // Client-only: adopt whatever the inline init script already applied to <html>. No transition —
  // this reflects the current state, it isn't a change the user asked for.
  useEffect(() => {
    const pref = document.documentElement.getAttribute("data-theme-pref");
    const initial = isTheme(pref) ? pref : "system";
    setThemeState(initial);
    applyTheme(initial, false);
  }, [applyTheme]);

  const setTheme = useCallback(
    (next: Theme) => {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
      setThemeState(next);
      applyTheme(next);
    },
    [applyTheme],
  );

  // Live-update while on "system" if the OS preference changes without a page reload.
  useEffect(() => {
    if (theme !== "system") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [theme, applyTheme]);

  const value = useMemo(() => ({ theme, resolvedTheme, setTheme }), [theme, resolvedTheme, setTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
