"use client";

import { useEffect, useState } from "react";
import { type Theme, toChartTheme } from "./theme";
import { CHANGE_EVENT, DEFAULT_SELECTION, applyTheme, prefersDark, readSelection, resolve, saveSelection, type Selection } from "./themes/runtime";

/** The chosen theme ("system" or a theme id) and its chart colours. */
export function useTheme(): { theme: Theme; selection: Selection; choose: (s: Selection) => void } {
  const [selection, setSelection] = useState<Selection>(DEFAULT_SELECTION);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setSelection(readSelection());
    setDark(prefersDark());
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onMedia = () => {
      setDark(media.matches);
      if (readSelection() === "system") applyTheme(resolve("system", media.matches));
    };
    const onChange = (e: Event) => setSelection((e as CustomEvent<Selection>).detail);
    media.addEventListener("change", onMedia);
    window.addEventListener(CHANGE_EVENT, onChange);
    return () => {
      media.removeEventListener("change", onMedia);
      window.removeEventListener(CHANGE_EVENT, onChange);
    };
  }, []);

  return { theme: toChartTheme(resolve(selection, dark)), selection, choose: saveSelection };
}
