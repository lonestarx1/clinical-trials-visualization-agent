// Every theme must stay readable: these gates run in CI, so a new theme can't regress contrast.
import { describe, expect, it } from "vitest";
import { THEMES } from "@/lib/themes";
import { DEFAULT_SELECTION, resolve, themeScript } from "@/lib/themes/runtime";

const lum = (hex: string) => {
  const [r, g, b] = (hex.replace("#", "").match(/../g) ?? []).map((h) => parseInt(h, 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

describe("theme registry", () => {
  it("has 10 themes with unique ids, 5 light and 5 dark", () => {
    expect(THEMES).toHaveLength(10);
    expect(new Set(THEMES.map((t) => t.id)).size).toBe(10);
    expect(THEMES.filter((t) => t.mode === "light")).toHaveLength(5);
  });

  it.each(THEMES.map((t) => [t.id, t] as const))("%s keeps text readable", (_, t) => {
    for (const bg of [t.ui.bg, t.ui.surface, t.ui.surface2]) {
      expect(contrast(t.ui.ink, bg)).toBeGreaterThanOrEqual(12);
      expect(contrast(t.ui.ink2, bg)).toBeGreaterThanOrEqual(7);
      expect(contrast(t.ui.muted, bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t.ui.action, bg)).toBeGreaterThanOrEqual(4.5);
    }
    expect(contrast(t.ui.markInk, t.ui.mark)).toBeGreaterThanOrEqual(7);
    expect(contrast(t.ui.actionInk, t.ui.action)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.chart.muted, t.chart.surface)).toBeGreaterThanOrEqual(7);
  });

  it.each(THEMES.map((t) => [t.id, t] as const))("%s draws charts on its own surface with 8 fixed colours", (_, t) => {
    expect(t.chart.surface).toBe(t.ui.surface);
    expect(t.chart.palette).toHaveLength(8);
    for (const hex of [...Object.values(t.ui).filter((v) => v.startsWith("#")), ...t.chart.palette]) {
      expect(hex).toMatch(/^#[0-9a-f]{6}$/);
    }
  });
});

describe("default theme", () => {
  it("is Clinical light, even on a device in dark mode", () => {
    expect(DEFAULT_SELECTION).toBe("clinical-light");
    expect(resolve(DEFAULT_SELECTION, true).id).toBe("clinical-light");
  });

  it("follows the device only when the user picks Automatic", () => {
    expect(resolve("system", true).id).toBe("clinical-dark");
    expect(resolve("system", false).id).toBe("clinical-light");
  });

  it("falls back to the default for an unknown saved theme", () => {
    expect(resolve("retired-theme", true).id).toBe("clinical-light");
  });

  it("applies the default before first paint when nothing is saved", () => {
    expect(themeScript()).toContain('T[s==="system"?');
    expect(themeScript()).toContain('"clinical-light"');
  });
});
