import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Guard: the FR and EN dictionaries in i18n.tsx must expose exactly the same keys.
function block(txt: string, anchor: string): string {
  const m = txt.search(new RegExp(anchor + "\\s*:\\s*\\{"));
  let i = txt.indexOf("{", m), depth = 0;
  for (let j = i; j < txt.length; j++) {
    if (txt[j] === "{") depth++;
    else if (txt[j] === "}") { depth--; if (depth === 0) return txt.slice(i, j + 1); }
  }
  return "";
}
const keys = (s: string) => new Set([...s.matchAll(/"([\w.]+)":/g)].map((m) => m[1]));

describe("i18n", () => {
  it("FR and EN have identical key sets", () => {
    const txt = readFileSync(resolve(process.cwd(), "src/i18n.tsx"), "utf8");
    const fr = keys(block(txt, "\\n  fr"));
    const en = keys(block(txt, "\\n  en"));
    const frOnly = [...fr].filter((k) => !en.has(k));
    const enOnly = [...en].filter((k) => !fr.has(k));
    expect({ frOnly, enOnly }).toEqual({ frOnly: [], enOnly: [] });
    expect(fr.size).toBeGreaterThan(400);
  });
});
