import { CLINICAL } from "./clinical";
import { DARK_SET } from "./dark-set";
import { LIGHT_SET } from "./light-set";
import type { ThemeDef } from "./types";

export type { ThemeDef } from "./types";

/** Every theme users can pick, in dropdown order: light themes, then dark themes. */
export const THEMES: ThemeDef[] = [...CLINICAL, ...LIGHT_SET, ...DARK_SET].sort((a, b) => (a.mode === b.mode ? 0 : a.mode === "light" ? -1 : 1));

export const DEFAULT_LIGHT = "clinical-light";
export const DEFAULT_DARK = "clinical-dark";

export function findTheme(id: string): ThemeDef | undefined {
  return THEMES.find((t) => t.id === id);
}
