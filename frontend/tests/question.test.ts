import { describe, expect, it } from "vitest";
import { isEditShortcut } from "@/lib/question";

const key = (k: string, extra: Partial<Parameters<typeof isEditShortcut>[0]> = {}) =>
  ({ key: k, tag: "BODY", editable: false, modifier: false, ...extra });

describe("isEditShortcut", () => {
  it("opens the question editor on / or e", () => {
    expect(isEditShortcut(key("/"))).toBe(true);
    expect(isEditShortcut(key("e"))).toBe(true);
  });

  it("ignores other keys", () => {
    expect(isEditShortcut(key("x"))).toBe(false);
    expect(isEditShortcut(key("Enter"))).toBe(false);
  });

  it("never steals a key from a field the user is typing in", () => {
    for (const tag of ["INPUT", "TEXTAREA", "SELECT"]) expect(isEditShortcut(key("/", { tag }))).toBe(false);
    expect(isEditShortcut(key("e", { editable: true }))).toBe(false);
  });

  it("leaves browser and system shortcuts alone", () => {
    expect(isEditShortcut(key("e", { modifier: true }))).toBe(false);
  });
});
