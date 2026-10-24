"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Logo } from "@/components/Logo";
import { ThemePicker } from "@/components/ThemePicker";
import { useTheme } from "@/lib/useTheme";

/** The top bar for pages other than the question page: the brand links home, the other pages, and the theme picker. */
export function DocsTopbar() {
  const { selection, choose } = useTheme();
  const here = usePathname();
  const link = (href: string, label: ReactNode) => (
    <Link className="ghost docs-link" href={href} aria-current={here === href ? "page" : undefined}>{label}</Link>
  );
  return (
    <header className="topbar">
      <Link className="brand" href="/" aria-label="Clinical Trials Explorer, ask a question">
        <Logo /><span className="brand-name">Clinical Trials Explorer</span>
      </Link>
      <div className="topbar-actions">
        <Link className="ghost new-question" href="/">New<span className="wide-only"> question</span></Link>
        {link("/docs", <>API<span className="wide-only"> docs</span></>)}
        {link("/examples", "Examples")}
        <ThemePicker selection={selection} onChoose={choose} />
      </div>
    </header>
  );
}
