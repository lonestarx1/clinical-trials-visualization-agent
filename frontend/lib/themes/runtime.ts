// Applying a theme: UI tokens become CSS variables on <html>; charts read the chart tokens.
// The default is Clinical light. "system" (Automatic) follows the device's light/dark setting
// with the clinical themes, only when the user picks it.
import { DEFAULT_DARK, DEFAULT_LIGHT, findTheme, THEMES } from "./index";
import type { ThemeDef, UiTokens } from "./types";

export const STORAGE_KEY = "ctx-theme";
export const CHANGE_EVENT = "ctx-theme-change";
export type Selection = "system" | string;
export const DEFAULT_SELECTION: Selection = DEFAULT_LIGHT;

const CSS_VARS: Record<keyof UiTokens, string> = {
  bg: "--bg", surface: "--surface", surface2: "--surface-2", ink: "--ink", ink2: "--ink-2",
  muted: "--muted", line: "--line", lineStrong: "--line-strong", action: "--action",
  actionHover: "--action-hover", actionInk: "--action-ink", actionSoft: "--action-soft",
  mark: "--mark", markInk: "--mark-ink", danger: "--danger", dangerSoft: "--danger-soft",
  warn: "--warn", warnSoft: "--warn-soft", shadow: "--shadow",
};

export function resolve(selection: Selection, prefersDark: boolean): ThemeDef {
  if (selection === "system") return findTheme(prefersDark ? DEFAULT_DARK : DEFAULT_LIGHT)!;
  return findTheme(selection) ?? findTheme(DEFAULT_SELECTION)!;
}

export function readSelection(): Selection {
  try { return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_SELECTION; } catch { return DEFAULT_SELECTION; }
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
    localStorage.setItem(STORAGE_KEY, selection);
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
    `var t=T[s==="system"?(d?${JSON.stringify(DEFAULT_DARK)}:${JSON.stringify(DEFAULT_LIGHT)}):s]||T[${JSON.stringify(DEFAULT_SELECTION)}];` +
    `var r=document.documentElement;` +
    `for(var k in t.vars)r.style.setProperty(k,t.vars[k]);r.style.colorScheme=t.mode;r.dataset.mode=t.mode;}catch(e){}})();`;
}
