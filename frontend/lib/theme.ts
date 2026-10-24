// Chart colours. Categorical slots are the validated colour-blind-safe palette (fixed order,
// never cycled), with separate steps for light and dark surfaces. Validated with the dataviz
// checker against these surfaces: light passes with a contrast warning (relief: table view and
// tooltips), dark passes all checks.

export interface Theme {
  name: "light" | "dark";
  palette: readonly string[];
  other: string; // everything past the eighth series ("Other"), never a generated hue
  surface: string;
  ink: string;
  muted: string;
  faint: string;
  grid: string;
  highlight: string;
}

export const LIGHT: Theme = {
  name: "light",
  palette: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
  other: "#a3abb8",
  surface: "#ffffff",
  ink: "#16233d",
  muted: "#5a6478",
  faint: "#8c95a6",
  grid: "#e9edf3",
  highlight: "#fde68a",
};

export const DARK: Theme = {
  name: "dark",
  palette: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
  other: "#5f697b",
  surface: "#141a24",
  ink: "#e7ecf4",
  muted: "#a6afbf",
  faint: "#6f7a8d",
  grid: "#242d3c",
  highlight: "#7c5e10",
};

export function seriesColor(theme: Theme, index: number): string {
  return index < theme.palette.length ? theme.palette[index] : theme.other;
}

export function currentTheme(): Theme {
  if (typeof document === "undefined") return LIGHT;
  const forced = document.documentElement.dataset.theme;
  if (forced === "dark") return DARK;
  if (forced === "light") return LIGHT;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? DARK : LIGHT;
}
