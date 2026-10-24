import { PALETTE_LIGHT } from "./clinical";
import type { ThemeDef } from "./types";

// Four light themes with distinct personalities. All share the validated light chart palette.
export const LIGHT_SET: ThemeDef[] = [
  {
    id: "glacier",
    name: "Glacier",
    mode: "light",
    ui: {
      bg: "#e3edf4", surface: "#fcfeff", surface2: "#eef5f9", ink: "#061923", ink2: "#1d3846", muted: "#46606f",
      line: "#d1dfe8", lineStrong: "#b2c6d3", action: "#0a6b75", actionHover: "#085862", actionInk: "#ffffff",
      actionSoft: "#d9f0f1", mark: "#fde047", markInk: "#1c1600", danger: "#b42318", dangerSoft: "#fef1f0",
      warn: "#7a4d00", warnSoft: "#fff4d6",
      shadow: "0 1px 2px rgba(6, 40, 58, 0.07), 0 10px 28px rgba(6, 40, 58, 0.09)",
    },
    chart: { palette: PALETTE_LIGHT, other: "#a2b0ba", surface: "#fcfeff", ink: "#061923", muted: "#32495a",
      faint: "#849eae", grid: "#dfe9f0", highlight: "#fde047" },
  },
  {
    id: "sage",
    name: "Sage",
    mode: "light",
    ui: {
      bg: "#e7eee8", surface: "#fdfefd", surface2: "#f0f5f1", ink: "#0e1c13", ink2: "#27392d", muted: "#4f6154",
      line: "#d4ded6", lineStrong: "#b6c5b9", action: "#1d6a38", actionHover: "#17572e", actionInk: "#ffffff",
      actionSoft: "#ddefe2", mark: "#ffe14d", markInk: "#1c1600", danger: "#b42318", dangerSoft: "#fef1f0",
      warn: "#7a4d00", warnSoft: "#fff4d6",
      shadow: "0 1px 2px rgba(20, 45, 28, 0.07), 0 10px 28px rgba(20, 45, 28, 0.08)",
    },
    chart: { palette: PALETTE_LIGHT, other: "#a5afa7", surface: "#fdfefd", ink: "#0e1c13", muted: "#37483c",
      faint: "#879a8b", grid: "#e0e8e2", highlight: "#ffe14d" },
  },
  {
    id: "ivory-ink",
    name: "Ivory & ink",
    mode: "light",
    ui: {
      bg: "#f2f0ed", surface: "#fffefc", surface2: "#f7f5f2", ink: "#1a1315", ink2: "#3a3034", muted: "#5f5459",
      line: "#e2ddd8", lineStrong: "#c8c0b9", action: "#8a1c3f", actionHover: "#721633", actionInk: "#ffffff",
      actionSoft: "#f6e3e9", mark: "#ffe45c", markInk: "#1c1600", danger: "#b42318", dangerSoft: "#fef1f0",
      warn: "#7a4d00", warnSoft: "#fff4d6",
      shadow: "0 1px 2px rgba(40, 24, 28, 0.06), 0 10px 28px rgba(40, 24, 28, 0.08)",
    },
    chart: { palette: PALETTE_LIGHT, other: "#aaa3a0", surface: "#fffefc", ink: "#1a1315", muted: "#463c40",
      faint: "#9a8f93", grid: "#ebe7e2", highlight: "#ffe45c" },
  },
  {
    id: "high-contrast-light",
    name: "High contrast (light)",
    mode: "light",
    ui: {
      bg: "#eef0f3", surface: "#ffffff", surface2: "#f2f4f7", ink: "#000000", ink2: "#141414", muted: "#333333",
      line: "#1a1a1a", lineStrong: "#000000", action: "#0040c1", actionHover: "#00319a", actionInk: "#ffffff",
      actionSoft: "#dbe6ff", mark: "#ffeb00", markInk: "#000000", danger: "#a30000", dangerSoft: "#ffecec",
      warn: "#5c3800", warnSoft: "#fff2c2",
      shadow: "0 1px 2px rgba(0, 0, 0, 0.12), 0 8px 20px rgba(0, 0, 0, 0.10)",
    },
    chart: { palette: PALETTE_LIGHT, other: "#808080", surface: "#ffffff", ink: "#000000", muted: "#1f1f1f",
      faint: "#6b6b6b", grid: "#cfcfcf", highlight: "#ffeb00" },
  },
];
