import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { CLASS_LIST, FEASIBILITY_META } from "../classes";

/** WCAG 2.x relative luminance / contrast ratio. */
function lum(hex: string): number {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}
export function contrast(a: string, b: string): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

const css = fs.readFileSync(path.resolve(__dirname, "../../app/globals.css"), "utf-8");
function scope(name: string): Record<string, string> {
  const m = new RegExp(`\\.${name}\\s*\\{([^}]*)\\}`).exec(css);
  if (!m) throw new Error(`scope .${name} not found`);
  const vars: Record<string, string> = {};
  for (const [, k, v] of (m[1] as string).matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) vars[k as string] = v as string;
  return vars;
}

describe.each(["theme-dark", "theme-paper", "theme-forest"])("%s tokens meet WCAG 2.2 AA", (name) => {
  const t = scope(name);
  const surfaces = ["canvas", "surface", "raised", "sunken"] as const;

  it("text roles on every surface", () => {
    for (const s of surfaces) {
      expect(contrast(t.ink!, t[s]!), `ink on ${s}`).toBeGreaterThanOrEqual(7);
      expect(contrast(t["ink-2"]!, t[s]!), `ink-2 on ${s}`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t["ink-3"]!, t[s]!), `ink-3 on ${s}`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t.accent!, t[s]!), `accent as text on ${s}`).toBeGreaterThanOrEqual(name === "theme-paper" ? 4.5 : 4.5);
    }
  });
  it("filled primary action and hover", () => {
    expect(contrast(t["on-accent"]!, t.accent!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["on-accent"]!, t["accent-hover"]!)).toBeGreaterThanOrEqual(4.5);
  });
  it("control borders and focus ring reach 3:1 (WCAG 1.4.11)", () => {
    for (const s of ["canvas", "surface", "sunken"] as const) {
      expect(contrast(t["line-strong"]!, t[s]!), `line-strong on ${s}`).toBeGreaterThanOrEqual(3);
      expect(contrast(t.focus!, t[s]!), `focus on ${s}`).toBeGreaterThanOrEqual(3);
    }
  });
  it("state text colours", () => {
    for (const k of ["danger", "warn", "ok"]) {
      for (const s of ["canvas", "surface", "raised"] as const) expect(contrast(t[k]!, t[s]!), `${k} on ${s}`).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("map class colours", () => {
  it("the class number printed on each swatch is readable", () => {
    for (const c of CLASS_LIST) expect(contrast(c.onColor, c.color), `class ${c.code}`).toBeGreaterThanOrEqual(4.5);
  });
  it("feasibility chips are readable", () => {
    for (const [k, m] of Object.entries(FEASIBILITY_META)) expect(contrast(m.onColor, m.color), k).toBeGreaterThanOrEqual(4.5);
  });
  it("every class swatch is distinguishable from the dark app canvas (3:1)", () => {
    for (const c of CLASS_LIST) expect(contrast(c.color, "#171c19"), `class ${c.code} on surface`).toBeGreaterThanOrEqual(3);
  });
});

describe("persistent demonstration bar", () => {
  it("amber bar with dark ink is readable", () => {
    expect(contrast("#1a1405", "#ecd48c")).toBeGreaterThanOrEqual(7);
  });
});
