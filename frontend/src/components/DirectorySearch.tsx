/**
 * DirectorySearch: find a person in the corporate directory (Entra ID, LDAP /
 * Active Directory, Google Workspace) and hand them to the screen that adds them.
 *
 * Shown only when an administrator switched a source on (GET /api/directory/status,
 * cached for the page's lifetime): without a directory, the screens stay as they
 * were. The text is sent once the typing pauses (300 ms) and from two characters
 * on. A source that failed is named under the results, the others still answer.
 */
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";

/** A person as the directory describes them (backend app/directory.py). */
export interface DirectoryPerson {
  name: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  title: string | null;
  department: string | null;
  source: "entra" | "ldap" | "google";
  /** The account already existing for this email, if any. */
  user_id?: number | null;
}

interface SearchOut { results: DirectoryPerson[]; sources: Record<string, { ok: boolean; count?: number; error?: string }> }

let statusPromise: Promise<boolean> | null = null;

/** Forget the cached status (the admin just changed the directory settings). */
export function invalidateDirectoryStatus() { statusPromise = null; }

/** Whether a directory source is on. False while unknown and on error. */
export function useDirectoryEnabled(): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    let alive = true;
    statusPromise ??= api.get<{ enabled: boolean }>("/api/directory/status").then((s) => !!s.enabled).catch(() => false);
    statusPromise.then((v) => { if (alive) setOn(v); });
    return () => { alive = false; };
  }, []);
  return on;
}

/** First and last name, split from the display name when the directory gave none. */
export function splitName(p: DirectoryPerson): { first: string; last: string } {
  if (p.first_name || p.last_name) return { first: p.first_name ?? "", last: p.last_name ?? "" };
  const [first, ...rest] = (p.name || "").split(" ");
  return { first: first ?? "", last: rest.join(" ") };
}

export default function DirectorySearch({ onPick, placeholder }: {
  onPick: (p: DirectoryPerson) => void; placeholder?: string;
}) {
  const { t } = useI18n();
  const enabled = useDirectoryEnabled();
  const [q, setQ] = useState("");
  const [out, setOut] = useState<SearchOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const term = q.trim();
    if (!enabled || term.length < 2) { setOut(null); setErr(null); return; }
    const mine = ++seq.current;
    const timer = setTimeout(() => {
      setBusy(true);
      api.get<SearchOut>(`/api/directory/search?q=${encodeURIComponent(term)}`)
        .then((r) => { if (mine === seq.current) { setOut(r); setErr(null); } })
        .catch((e) => { if (mine === seq.current) { setOut(null); setErr(errorText(e)); } })
        .finally(() => { if (mine === seq.current) setBusy(false); });
    }, 300);
    return () => clearTimeout(timer);
  }, [q, enabled]);

  if (!enabled) return null;
  const failed = out ? Object.entries(out.sources).filter(([, s]) => !s.ok) : [];
  return (
    <div style={{ position: "relative" }}>
      <input type="search" autoComplete="off" value={q} aria-label={t("directory.search")}
             placeholder={placeholder ?? t("directory.search_ph")} onChange={(e) => setQ(e.target.value)} />
      {(out || err || busy) && q.trim().length >= 2 && (
        <div className="card" role="listbox"
             style={{ position: "absolute", zIndex: 6, left: 0, right: 0, marginTop: 2, padding: 4, maxHeight: 280, overflowY: "auto" }}>
          {busy && !out && <div className="small muted" style={{ padding: "2px 6px" }}>{t("directory.searching")}</div>}
          {err && <div className="small" style={{ padding: "2px 6px", color: "var(--red)" }}>{err}</div>}
          {out && out.results.length === 0 && <div className="small muted" style={{ padding: "2px 6px" }}>{t("directory.none")}</div>}
          {out?.results.map((p) => (
            <button type="button" role="option" key={p.email} className="btn-ghost btn-sm"
                    style={{ display: "block", width: "100%", textAlign: "left" }}
                    onClick={() => { onPick(p); setQ(""); setOut(null); }}>
              <span className="strong">{p.name}</span> <span className="muted">({p.email})</span>
              {(p.title || p.department) && (
                <span className="small muted">{t("common.colon")}{[p.title, p.department].filter(Boolean).join(", ")}</span>
              )}
              {p.user_id ? <span className="badge badge-grey" style={{ marginLeft: 6 }}>{t("directory.has_account")}</span> : null}
            </button>
          ))}
          {failed.map(([s, st]) => (
            <div key={s} className="small muted" style={{ padding: "2px 6px" }}>
              {t("directory.source_failed", { source: t(`directory.source.${s}`) })}{st.error ? ` (${st.error})` : ""}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
