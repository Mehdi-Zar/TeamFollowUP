import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve, join } from "node:path";

// Guard: the project convention (CLAUDE.md) bans the em dash and the middot from
// anything a user reads. Both read as machine-written, and the weekly report was
// shipping the middot as a separator throughout before it was cleaned up.
//
// Comment-only lines are skipped: developer prose is not the target, code that
// renders text is. A trailing comment on a code line is therefore still flagged,
// which errs on the side of noticing.
const BANNED: Array<[string, string]> = [
  ["—", "em dash"],
  ["·", "middot"],
];

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|css)$/.test(name)) out.push(p);
  }
  return out;
}

function offences(file: string): string[] {
  const found: string[] = [];
  readFileSync(file, "utf8").split("\n").forEach((line, i) => {
    const t = line.trim();
    if (t.startsWith("//") || t.startsWith("*") || t.startsWith("/*")) return;
    for (const [char, label] of BANNED) {
      if (line.includes(char)) found.push(`${file.split(/[\\/]/).pop()}:${i + 1}: ${label}`);
    }
  });
  return found;
}

describe("typography", () => {
  it("no em dash and no middot in anything a user reads", () => {
    const src = resolve(process.cwd(), "src");
    // Only this file is exempt, because it has to spell the characters out. Other
    // tests are scanned on purpose: one that asserts a user-facing label would
    // otherwise be free to assert a banned one.
    const all = walk(src).filter((f) => !f.endsWith("typography.test.ts")).flatMap(offences);
    expect(all).toEqual([]);
  });

  it("neither dictionary carries one, whichever language is served", () => {
    const txt = readFileSync(resolve(process.cwd(), "src/i18n.tsx"), "utf8");
    for (const [char, label] of BANNED) expect(txt.includes(char), label).toBe(false);
  });
});
