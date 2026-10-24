// Applying a theme: UI tokens become CSS variables on <html>; charts read the chart tokens.
// "system" follows the OS light/dark setting with the clinical themes.
import { DEFAULT_DARK, DEFAULT_LIGHT, findTheme, THEMES } from "./index";
import type { ThemeDef, UiTokens } from "./types";

export const STORAGE_KEY = "ctx-theme";
export const CHANGE_EVENT = "ctx-theme-change";
export type Selection = "system" | string;

const CSS_VARS: Record<keyof UiTokens, string> = {
  bg: "--bg", surface: "--surface", surface2: "--surface-2", ink: "--ink", ink2: "--ink-2",
  muted: "--muted", line: "--line", lineStrong: "--line-strong", action: "--action",
  actionHover: "--action-hover", actionInk: "--action-ink", actionSoft: "--action-soft",
  mark: "--mark", markInk: "--mark-ink", danger: "--danger", dangerSoft: "--danger-soft",
  warn: "--warn", warnSoft: "--warn-soft", shadow: "--shadow",
};

export function resolve(selection: Selection, prefersDark: boolean): ThemeDef {
  const chosen = selection !== "system" ? findTheme(selection) : undefined;
  return chosen ?? findTheme(prefersDark ? DEFAULT_DARK : DEFAULT_LIGHT)!;
}

export function readSelection(): Selection {
  try { return localStorage.getItem(STORAGE_KEY) ?? "system"; } catch { return "system"; }
}

export function prefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function applyTheme(theme: ThemeDef): void {
  const root = document.documentElement;
  for (const [key, cssVar] of Object.entries(CSS_VARS)) root.style.setProperty(cssVar, theme.ui[key as keyof UiTokens]);
  root.style.colorScheme = theme.mode;
  root.dataset.mode = theme.mode;
  root.dataset.theme = theme.id;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme.ui.bg);
}

export function saveSelection(selection: Selection): void {
  try {
    if (selection === "system") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, selection);
  } catch { /* storage unavailable: the choice lasts for this visit */ }
  applyTheme(resolve(selection, prefersDark()));
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: selection }));
}

/** Inline script that applies the saved theme before first paint (no flash of the wrong theme). */
export function themeScript(): string {
  const vars = Object.fromEntries(THEMES.map((t) => [t.id, {
    mode: t.mode,
    vars: Object.fromEntries(Object.entries(CSS_VARS).map(([k, v]) => [v, t.ui[k as keyof UiTokens]])),
  }]));
  return `(function(){try{var T=${JSON.stringify(vars)};var s=localStorage.getItem(${JSON.stringify(STORAGE_KEY)});` +
    `var d=window.matchMedia("(prefers-color-scheme: dark)").matches;` +
    `var t=T[s]||T[d?${JSON.stringify(DEFAULT_DARK)}:${JSON.stringify(DEFAULT_LIGHT)}];var r=document.documentElement;` +
    `for(var k in t.vars)r.style.setProperty(k,t.vars[k]);r.style.colorScheme=t.mode;r.dataset.mode=t.mode;}catch(e){}})();`;
}
