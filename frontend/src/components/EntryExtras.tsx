// Two reporting sections that the API carried but no screen ever showed.
//
// The quarterly progress was the stranger case: the entry screen's own submit
// checklist tested it ("has progress"), the print views and the dashboard showed
// it, and the only way to set it was a PUT nobody could reach from the app. A
// number displayed everywhere and editable nowhere.
//
// Review actions (the decisions taken in a squad's COPIL) had a complete CRUD, a
// TypeScript type, and a module toggle. No component ever called it.
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { ReviewAction, SquadDetail } from "../types";
import { SectionCard as Card } from "./ui";

const QUARTERS = [1, 2, 3, 4] as const;

/** The quarter's comment, next to the percentage the application computes.
 *
 *  The percentage is NOT typed in: it is the share of the quarter's milestones that
 *  are done, which is what the dashboard, the exports and the printed views all
 *  show. What was missing from every screen is the sentence that explains it, and
 *  it was reachable only through the API. Shown side by side on purpose: a figure
 *  and the reason for it belong together. */
export function QuarterProgressEditor({ squad, year, readonly, onChange, t }: {
  squad: SquadDetail; year: number; readonly?: boolean; onChange: () => void; t: (k: string, p?: any) => string;
}) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const current = (q: number) => squad.quarter_progress?.[String(q)] ?? { progress_pct: 0, comment: "" };
  const [draft, setDraft] = useState<Record<number, string>>(
    Object.fromEntries(QUARTERS.map((q) => [q, current(q).comment ?? ""])),
  );

  async function save(q: number) {
    if (readonly || draft[q] === (current(q).comment ?? "")) return;
    setBusy(q); setErr(null);
    try {
      await api.put(`/api/squads/${squad.id}/quarter-progress`, {
        year, quarter: q, comment: draft[q] || null,
      });
      onChange();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(null); }
  }

  return (
    <Card title={t("entry.progress_title", { year })} hint={t("entry.progress_hint")}>
      {err && <div className="banner banner-red" style={{ marginBottom: 8 }}>{err}</div>}
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 70 }}>{t("entry.quarter")}</th>
            <th style={{ width: 120 }}>{t("entry.progress_derived")}</th>
            <th>{t("entry.progress_comment")}</th>
          </tr>
        </thead>
        <tbody>
          {QUARTERS.map((q) => (
            <tr key={q}>
              <td className="strong">T{q}</td>
              <td className="strong" title={t("entry.progress_derived_hint")}>
                {current(q).progress_pct ?? 0} %
              </td>
              <td>
                <input disabled={readonly || busy === q} placeholder={t("entry.progress_comment_ph")}
                       aria-label={t("entry.progress_comment") + ` T${q}`}
                       value={draft[q]}
                       onChange={(e) => setDraft({ ...draft, [q]: e.target.value })}
                       onBlur={() => save(q)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

/** Review actions (COPIL): what was decided, who owns it, when it is due.
 *  Gated by the `review` module, like the API that serves it. */
export function ReviewActionsEditor({ squad, readonly, t }: {
  squad: SquadDetail; readonly?: boolean; t: (k: string, p?: any) => string;
}) {
  const [rows, setRows] = useState<ReviewAction[] | null>(null);
  const [text, setText] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try { setRows(await api.get<ReviewAction[]>(`/api/squads/${squad.id}/actions`)); }
    catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); setRows([]); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [squad.id]);

  async function wrap(fn: () => Promise<unknown>) {
    setErr(null);
    try { await fn(); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
  }

  const add = () => {
    if (!text.trim()) return;
    // La squad vient du chemin: l'envoyer aussi dans le corps laisserait croire
    // qu'elle est modifiable ici.
    wrap(() => api.post(`/api/squads/${squad.id}/actions`, {
      text: text.trim(), owner: owner.trim() || null, due_date: due || null,
    })).then(() => { setText(""); setOwner(""); setDue(""); });
  };

  return (
    <Card title={t("entry.actions_title")} hint={t("entry.actions_hint")}>
      {err && <div className="banner banner-red" style={{ marginBottom: 8 }}>{err}</div>}
      {rows === null ? <div className="small muted">{t("common.loading")}</div> : (
        <>
          {rows.length === 0 && <div className="small muted">{t("entry.actions_empty")}</div>}
          {rows.map((a) => (
            <div key={a.id} className="item-row">
              <input type="checkbox" checked={a.done} disabled={readonly}
                     aria-label={t("entry.actions_done")}
                     onChange={() => wrap(() => api.put(`/api/actions/${a.id}`, { done: !a.done }))} />
              <div className="grow">
                <div style={a.done ? { textDecoration: "line-through", opacity: 0.6 } : undefined}>{a.text}</div>
                <div className="small muted">
                  {a.owner || t("entry.actions_no_owner")}
                  {a.due_date ? `, ${t("entry.actions_due")} ${a.due_date.slice(0, 10)}` : ""}
                </div>
              </div>
              {!readonly && (
                <button className="icon-del" title={t("action.delete")} aria-label={t("action.delete")}
                        onClick={() => wrap(() => api.del(`/api/actions/${a.id}`))}>✕</button>
              )}
            </div>
          ))}
          {!readonly && (
            <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
              <input style={{ flex: 2, minWidth: 200 }} placeholder={t("entry.actions_text_ph")}
                     aria-label={t("entry.actions_text_ph")} value={text}
                     onChange={(e) => setText(e.target.value)} />
              <input style={{ flex: 1, minWidth: 130 }} placeholder={t("entry.actions_owner_ph")}
                     aria-label={t("entry.actions_owner_ph")} value={owner}
                     onChange={(e) => setOwner(e.target.value)} />
              <input type="date" style={{ width: 150 }} aria-label={t("entry.actions_due")}
                     value={due} onChange={(e) => setDue(e.target.value)} />
              <button className="btn-sm" disabled={!text.trim()} onClick={add}>{t("entry.actions_add")}</button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
