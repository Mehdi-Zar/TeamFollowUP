// Two reporting sections that the API carried but no screen ever showed.
//
// The quarterly progress was the stranger case: the entry screen's own submit
// checklist tested it ("has progress"), the print views and the dashboard showed
// it, and the only way to set it was a PUT nobody could reach from the app. A
// number displayed everywhere and editable nowhere.
//
// Review actions (the decisions taken in a squad's COPIL) had a complete CRUD, a
// TypeScript type, and a module toggle. No component ever called it.
import { useState } from "react";
import { api, errorText, reportSaveError } from "../api";
import { SquadDetail } from "../types";
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
  // Only a quarter without jalons can say it does not concern the squad.
  const planned = (q: number) => squad.roadmap_items.some((r) => r.year === year && r.quarter === q);

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
      setErr(errorText(e));
      reportSaveError(errorText(e));
    } finally { setBusy(null); }
  }

  // Le meme drapeau que la case de la colonne du trimestre dans la roadmap : on le
  // cherchait ici, a cote du pourcentage qu'il remplace.
  async function setNa(q: number, v: boolean) {
    setBusy(q); setErr(null);
    try {
      await api.put(`/api/squads/${squad.id}/quarter-progress`, { year, quarter: q, not_applicable: v });
      onChange();
    } catch (e) {
      setErr(errorText(e));
      reportSaveError(errorText(e));
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
            <th style={{ width: 130 }} title={t("entry.q_na_hint")}>{t("entry.q_na_box")}</th>
            <th>{t("entry.progress_comment")}</th>
          </tr>
        </thead>
        <tbody>
          {QUARTERS.map((q) => (
            <tr key={q}>
              <td className="strong">Q{q}</td>
              <td className="strong" title={t("entry.progress_derived_hint")}>
                {planned(q) ? `${current(q).progress_pct ?? 0}%`
                  : current(q).not_applicable ? t("entry.q_na_short")
                    : <span className="muted">{t("entry.q_nothing")}</span>}
              </td>
              <td title={planned(q) ? t("entry.q_na_planned") : t("entry.q_na_hint")}>
                <input type="checkbox" aria-label={`${t("entry.q_na_box")} Q${q}`}
                       disabled={readonly || busy === q || planned(q)}
                       checked={!planned(q) && !!current(q).not_applicable}
                       onChange={(e) => setNa(q, e.target.checked)} />
              </td>
              <td>
                <input disabled={readonly || busy === q} placeholder={t("entry.progress_comment_ph")}
                       aria-label={t("entry.progress_comment") + ` Q${q}`}
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
