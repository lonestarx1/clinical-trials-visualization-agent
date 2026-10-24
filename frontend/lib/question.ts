// Keyboard shortcuts on the answer page: edit the asked question, or stop it while it runs.

export type KeyInfo = { key: string; tag: string; editable: boolean; modifier: boolean };

const FIELDS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function isEditShortcut({ key, tag, editable, modifier }: KeyInfo): boolean {
  if (modifier || editable || FIELDS.has(tag)) return false;
  return key === "/" || key === "e";
}

/** Esc stops the question being answered, unless a field has focus (Esc closes the editor there). */
export function isStopShortcut({ key, tag, editable, modifier }: KeyInfo): boolean {
  if (modifier || editable || FIELDS.has(tag)) return false;
  return key === "Escape";
}
