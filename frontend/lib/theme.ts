// Chart colours for the current theme. Categorical slots are the validated colour-blind-safe
// palette (fixed order, never cycled); each theme validated it against its own surface.
import { CLINICAL } from "./themes/clinical";
import type { ChartTokens, ThemeDef } from "./themes/types";

export interface Theme extends ChartTokens {
  id: string;
  mode: "light" | "dark";
}

export const toChartTheme = (t: ThemeDef): Theme => ({ id: t.id, mode: t.mode, ...t.chart });

export const LIGHT: Theme = toChartTheme(CLINICAL[0]);
export const DARK: Theme = toChartTheme(CLINICAL[1]);

export function seriesColor(theme: Theme, index: number): string {
  return index < theme.palette.length ? theme.palette[index] : theme.other;
}
