import { PALETTE_DARK } from "./clinical";
import type { ThemeDef } from "./types";

// Four dark themes with distinct personalities. All share the validated dark chart palette.
export const DARK_SET: ThemeDef[] = [
  {
    id: "midnight",
    name: "Midnight",
    mode: "dark",
    ui: {
      bg: "#060b1a", surface: "#111a2e", surface2: "#18233b", ink: "#f4f8ff", ink2: "#d3ddef", muted: "#a3b2cc",
      line: "#243251", lineStrong: "#34466b", action: "#38bdf8", actionHover: "#7dd3fc", actionInk: "#04121c",
      actionSoft: "#0c2a3f", mark: "#facc15", markInk: "#1a1400", danger: "#ff8a80", dangerSoft: "#2c1517",
      warn: "#fbbf5e", warnSoft: "#2a2112",
      shadow: "0 1px 2px rgba(0, 0, 0, 0.4), 0 10px 28px rgba(0, 0, 0, 0.45)",
    },
    chart: { palette: PALETTE_DARK, other: "#64708a", surface: "#111a2e", ink: "#f4f8ff", muted: "#c0cce0",
      faint: "#6a7a99", grid: "#22304d", highlight: "#facc15" },
  },
  {
    id: "graphite",
    name: "Graphite",
    mode: "dark",
    ui: {
      bg: "#121212", surface: "#1f1f1f", surface2: "#292929", ink: "#f5f5f5", ink2: "#d6d6d6", muted: "#ababab",
      line: "#363636", lineStrong: "#4d4d4d", action: "#fbbf24", actionHover: "#fcd34d", actionInk: "#1a1200",
      actionSoft: "#352a10", mark: "#bef264", markInk: "#141a00", danger: "#ff8a80", dangerSoft: "#2e1816",
      warn: "#fdba74", warnSoft: "#2e2216",
      shadow: "0 1px 2px rgba(0, 0, 0, 0.4), 0 10px 28px rgba(0, 0, 0, 0.45)",
    },
    chart: { palette: PALETTE_DARK, other: "#6e6e6e", surface: "#1f1f1f", ink: "#f5f5f5", muted: "#cccccc",
      faint: "#7a7a7a", grid: "#333333", highlight: "#bef264" },
  },
  {
    id: "forest-night",
    name: "Forest night",
    mode: "dark",
    ui: {
      bg: "#07110d", surface: "#10201a", surface2: "#172a22", ink: "#f1faf5", ink2: "#cfe3d8", muted: "#9fb8ab",
      line: "#21392f", lineStrong: "#305242", action: "#6ee7b7", actionHover: "#a7f3d0", actionInk: "#04150e",
      actionSoft: "#12352a", mark: "#fde047", markInk: "#1a1600", danger: "#ff8f85", dangerSoft: "#2b1615",
      warn: "#f5c86e", warnSoft: "#2a2313",
      shadow: "0 1px 2px rgba(0, 0, 0, 0.4), 0 10px 28px rgba(0, 0, 0, 0.45)",
    },
    chart: { palette: PALETTE_DARK, other: "#5f7369", surface: "#10201a", ink: "#f1faf5", muted: "#c0d6ca",
      faint: "#6b8a7b", grid: "#21392f", highlight: "#fde047" },
  },
  {
    id: "high-contrast-dark",
    name: "High contrast (dark)",
    mode: "dark",
    ui: {
      bg: "#000000", surface: "#121212", surface2: "#1e1e1e", ink: "#ffffff", ink2: "#f0f0f0", muted: "#d4d4d4",
      line: "#8a8a8a", lineStrong: "#c4c4c4", action: "#ffe500", actionHover: "#fff176", actionInk: "#000000",
      actionSoft: "#3a3400", mark: "#67e8f9", markInk: "#000000", danger: "#ff9b94", dangerSoft: "#3a0f0c",
      warn: "#ffd166", warnSoft: "#332600",
      shadow: "0 0 0 1px rgba(255, 255, 255, 0.25), 0 10px 28px rgba(0, 0, 0, 0.6)",
    },
    chart: { palette: PALETTE_DARK, other: "#9a9a9a", surface: "#121212", ink: "#ffffff", muted: "#e6e6e6",
      faint: "#9e9e9e", grid: "#3d3d3d", highlight: "#67e8f9" },
  },
];
