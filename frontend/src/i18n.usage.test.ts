import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve, join } from "node:path";

/**
 * The dictionary and the code must agree in both directions.
 *
 * The parity test proves FR and EN carry the same keys. It says nothing about
 * whether those keys mean anything, and 142 of them meant nothing: leftovers
 * from an OTD screen, an older dashboard, a reporting and subscription UI and an
 * export menu that had all been redesigned. Dead labels are not harmless. They
 * are read as an inventory of what the product does, they get translated, and
 * they make the real ones harder to find.
 *
 * The other direction matters more: a key used but absent renders as the raw key
 * on screen, because `t()` deliberately falls back to it rather than to a blank.
 *
 * Keys reached through a template literal (`t(`leaves.status.${s}`)`) are found by
 * discovering those prefixes IN THE SOURCE rather than from a list here. Adding a
 * new family protects it automatically; a list would need someone to remember.
 */
const SRC = resolve(process.cwd(), "src");
const I18N = join(SRC, "i18n.tsx");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(p);
  }
  return out;
}

/** The body of a named dictionary in i18n.tsx, by brace matching. */
function dictionary(text: string, anchor: string): string {
  const at = text.search(new RegExp(anchor + "\\s*:\\s*\\{"));
  const start = text.indexOf("{", at);
  let depth = 0;
  for (let i = start; i < text.length; i++) {
    if (text[i] === "{") depth++;
    else if (text[i] === "}" && --depth === 0) return text.slice(start, i + 1);
  }
  return "";
}

const i18nText = readFileSync(I18N, "utf8");
const fr = dictionary(i18nText, "\\n  fr");
const en = dictionary(i18nText, "\\n  en");
const keysOf = (s: string) => new Set([...s.matchAll(/"([\w.]+)":/g)].map((m) => m[1]));
const frKeys = keysOf(fr);
const enKeys = keysOf(en);

// Everything the code says, with the dictionaries themselves cut out so a key
// does not count as a reference to itself.
const code = [
  i18nText.replace(fr, "").replace(en, ""),
  ...walk(SRC).filter((p) => p !== I18N).map((p) => readFileSync(p, "utf8")),
].join("\n");

/** Keys named outright, anywhere: in `t("x")`, in a route table, in a map. */
const named = new Set([...code.matchAll(/["'`]([\w.]+)["'`]/g)].map((m) => m[1]));
/** Keys passed to t() explicitly, which must exist or the screen shows the key. */
const called = new Set([...code.matchAll(/\bt\(\s*"([\w.]+)"/g)].map((m) => m[1]));
/** Prefixes a template literal can build: `leaves.status.`, `access.history_`.
 *  A family is not always dot-terminated, hence the two separators. Any other
 *  template literal in the source widens reachability a little, which is the
 *  conservative direction: this test must never say "delete" about a live key. */
const prefixes = [...new Set([...code.matchAll(/`([\w.]+[._])\$\{/g)].map((m) => m[1]))];

const reachable = (k: string) => named.has(k) || prefixes.some((p) => k.startsWith(p));

describe("the dictionary and the code agree", () => {
  it("every key the code asks for exists in both languages", () => {
    const missing = [...called].filter((k) => !frKeys.has(k) || !enKeys.has(k)).sort();
    expect(missing, "these render as the raw key on screen").toEqual([]);
  });

  it("every key in the dictionary is reachable from the code", () => {
    const dead = [...frKeys].filter((k) => !reachable(k)).sort();
    expect(
      dead,
      "unreachable labels: use them, or delete them from BOTH dictionaries. If one is " +
        "built dynamically, the prefix is discovered from a template literal in the source",
    ).toEqual([]);
  });

  it("looks at something, in both directions", () => {
    // Every filter here is easy to over-tighten into a permanently green test.
    expect(frKeys.size).toBeGreaterThan(900);
    expect(called.size).toBeGreaterThan(700);
    expect(prefixes.length).toBeGreaterThan(10);
    expect(prefixes).toContain("leaves.status.");
  });
});
