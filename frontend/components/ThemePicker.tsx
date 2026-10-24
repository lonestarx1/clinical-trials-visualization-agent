"use client";

import { useEffect, useRef, useState } from "react";
import { THEMES } from "@/lib/themes";
import type { ThemeDef } from "@/lib/themes/types";
import type { Selection } from "@/lib/themes/runtime";

function Swatch({ theme }: { theme: ThemeDef }) {
  const { bg, surface, action, mark } = theme.ui;
  return (
    <span className="swatch" aria-hidden style={{ background: bg, borderColor: theme.ui.lineStrong }}>
      <span style={{ background: surface }} /><span style={{ background: action }} /><span style={{ background: mark }} />
    </span>
  );
}

export function ThemePicker({ selection, onChoose }: { selection: Selection; onChoose: (s: Selection) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const current = THEMES.find((t) => t.id === selection);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onClick); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const pick = (s: Selection) => { onChoose(s); setOpen(false); };
  const option = (s: Selection, label: string, theme?: ThemeDef) => (
    <li key={s}>
      <button role="menuitemradio" aria-checked={selection === s} className={selection === s ? "on" : ""} onClick={() => pick(s)}>
        {theme ? <Swatch theme={theme} /> : <span className="swatch swatch-auto" aria-hidden />}
        <span>{label}</span>
        {selection === s && <span className="tick" aria-hidden>✓</span>}
      </button>
    </li>
  );

  return (
    <div className="theme-picker" ref={box}>
      <button className="ghost theme-button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        {current ? <Swatch theme={current} /> : <span className="swatch swatch-auto" aria-hidden />}
        <span className="theme-name">{current?.name ?? "Automatic"}</span>
        <span aria-hidden>▾</span>
      </button>
      {open && (
        <div className="theme-menu" role="menu" aria-label="Colour theme">
          <ul>{option("system", "Automatic (follows your device)")}</ul>
          <p className="theme-group">Light</p>
          <ul>{THEMES.filter((t) => t.mode === "light").map((t) => option(t.id, t.name, t))}</ul>
          <p className="theme-group">Dark</p>
          <ul>{THEMES.filter((t) => t.mode === "dark").map((t) => option(t.id, t.name, t))}</ul>
        </div>
      )}
    </div>
  );
}
