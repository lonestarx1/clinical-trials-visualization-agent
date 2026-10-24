const KEY = "ctx-recent";
const MAX = 8;

export function readRecent(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((v) => typeof v === "string").slice(0, MAX) : [];
  } catch {
    return [];
  }
}

export function rememberQuestion(question: string): string[] {
  const next = [question, ...readRecent().filter((q) => q !== question)].slice(0, MAX);
  try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
  return next;
}
