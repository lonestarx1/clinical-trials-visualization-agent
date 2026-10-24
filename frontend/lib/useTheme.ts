"use client";

import { useEffect, useState } from "react";
import { currentTheme, type Theme } from "./theme";

const KEY = "ctx-theme";

/** The chart theme, following the page theme (system setting unless the user picked one). */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  useEffect(() => {
    const update = () => setTheme(currentTheme());
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", update);
    window.addEventListener("ctx-theme-change", update);
    update();
    return () => {
      media.removeEventListener("change", update);
      window.removeEventListener("ctx-theme-change", update);
    };
  }, []);
  const toggle = () => {
    const next = currentTheme().name === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(KEY, next); } catch { /* private mode: keep it for this visit */ }
    window.dispatchEvent(new Event("ctx-theme-change"));
  };
  return [theme, toggle];
}

/** Runs before paint so a saved theme never flashes the other one. */
export const THEME_SCRIPT = `try{var t=localStorage.getItem("${KEY}");if(t)document.documentElement.dataset.theme=t}catch(e){}`;
