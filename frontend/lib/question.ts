// Keyboard shortcut for editing the asked question from anywhere on the answer page.

export type KeyInfo = { key: string; tag: string; editable: boolean; modifier: boolean };

const FIELDS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function isEditShortcut({ key, tag, editable, modifier }: KeyInfo): boolean {
  if (modifier || editable || FIELDS.has(tag)) return false;
  return key === "/" || key === "e";
}
