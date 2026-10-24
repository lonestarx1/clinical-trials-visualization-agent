"use client";

import { useEffect, useState } from "react";

/** A code sample with a label and a copy button. Long lines scroll inside the block, not the page. */
export function CodeBlock({ code, label }: { code: string; label: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(t);
  }, [copied]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch { /* clipboard unavailable (e.g. insecure context): the text can still be selected */ }
  };

  return (
    <figure className="code">
      <figcaption className="code-head">
        <span>{label}</span>
        <button type="button" className="ghost code-copy" onClick={copy} aria-label={`Copy ${label}`}>
          {copied ? "Copied" : "Copy"}
        </button>
      </figcaption>
      <pre tabIndex={0}><code>{code}</code></pre>
      <span className="sr-only" aria-live="polite">{copied ? "Copied to the clipboard" : ""}</span>
    </figure>
  );
}
