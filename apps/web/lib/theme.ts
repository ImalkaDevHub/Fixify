export const THEME_STORAGE_KEY = "fixify-theme";

export type Theme = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark" || value === "system";
}

export function resolveTheme(theme: Theme, systemPrefersDark: boolean): ResolvedTheme {
  return theme === "system" ? (systemPrefersDark ? "dark" : "light") : theme;
}

export const THEME_COLOR: Record<ResolvedTheme, string> = { light: "#F8F7F5", dark: "#111114" };

/**
 * Runs synchronously in <head>, before first paint, so the correct theme is already on <html>
 * by the time anything renders — no flash of the wrong theme while React hydrates. Kept as a
 * plain string (not a function) because it has to be inlined into a <script> tag before any app
 * JS, including this module, has loaded.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var k="${THEME_STORAGE_KEY}";var s=localStorage.getItem(k);var t=s==="light"||s==="dark"||s==="system"?s:"system";var r=t==="system"?(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):t;var e=document.documentElement;e.setAttribute("data-theme",r);e.setAttribute("data-theme-pref",t);e.style.colorScheme=r;}catch(err){}})();`;
