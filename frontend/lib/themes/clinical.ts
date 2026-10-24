import type { ThemeDef } from "./types";

// The reference categorical palette (validated light and dark steps).
export const PALETTE_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"] as const;
export const PALETTE_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"] as const;

export const CLINICAL: ThemeDef[] = [
  {
    id: "clinical-light",
    name: "Clinical light",
    mode: "light",
    ui: {
      bg: "#eef2f8", surface: "#ffffff", surface2: "#f3f6fb", ink: "#0b1324", ink2: "#26344b", muted: "#4f5d73",
      line: "#dde3ed", lineStrong: "#c3ccda", action: "#1d4ed8", actionHover: "#1a43b8", actionInk: "#ffffff",
      actionSoft: "#e3ebff", mark: "#fde047", markInk: "#1c1600", danger: "#b42318", dangerSoft: "#fef1f0",
      warn: "#7a4d00", warnSoft: "#fff4d6",
      shadow: "0 1px 2px rgba(15, 23, 42, 0.06), 0 10px 28px rgba(15, 23, 42, 0.08)",
    },
    chart: { palette: PALETTE_LIGHT, other: "#a3abb8", surface: "#ffffff", ink: "#0b1324", muted: "#3d4a60",
      faint: "#8794a8", grid: "#e3e8f0", highlight: "#fde047" },
  },
  {
    id: "clinical-dark",
    name: "Clinical dark",
    mode: "dark",
    ui: {
      bg: "#090e18", surface: "#141c2b", surface2: "#1b2537", ink: "#f5f8fc", ink2: "#d7deea", muted: "#a9b5c7",
      line: "#26324a", lineStrong: "#364563", action: "#86abff", actionHover: "#a3c0ff", actionInk: "#08101f",
      actionSoft: "#1a2a4d", mark: "#f5c518", markInk: "#161000", danger: "#ff8d82", dangerSoft: "#2c1615",
      warn: "#f5c86e", warnSoft: "#2b2312",
      shadow: "0 1px 2px rgba(0, 0, 0, 0.35), 0 10px 28px rgba(0, 0, 0, 0.4)",
    },
    chart: { palette: PALETTE_DARK, other: "#5f697b", surface: "#141c2b", ink: "#f5f8fc", muted: "#c3cddc",
      faint: "#6c7a91", grid: "#26324a", highlight: "#f5c518" },
  },
];
