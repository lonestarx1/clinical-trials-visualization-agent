"use client";

import Link from "next/link";
import { Logo } from "@/components/Logo";
import { ThemePicker } from "@/components/ThemePicker";
import { useTheme } from "@/lib/useTheme";

/** The top bar for pages other than the question page: the brand links home, plus the theme picker. */
export function DocsTopbar() {
  const { selection, choose } = useTheme();
  return (
    <header className="topbar">
      <Link className="brand" href="/" aria-label="Clinical Trials Explorer, ask a question">
        <Logo />Clinical Trials Explorer
      </Link>
      <div className="topbar-actions">
        <ThemePicker selection={selection} onChoose={choose} />
      </div>
    </header>
  );
}
