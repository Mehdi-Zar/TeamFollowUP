// Moral de l'equipe, en trois niveaux.
//
// Trois et pas cinq: une echelle fine invite a la nuance, or ce qu'on cherche ici
// est un signal. Trois choix se decident en une seconde, ce qui est la condition
// pour que la case soit remplie chaque semaine plutot qu'une fois en janvier.
//
// La date compte autant que le niveau: un moral de mars affiche en septembre ment
// plus surement qu'une case vide, donc l'age est toujours dit, et un moral trop
// vieux se signale de lui-meme.
import { useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";

export const MOODS = ["good", "mixed", "bad"] as const;
export type Mood = (typeof MOODS)[number];
export const MOOD_EMOJI: Record<Mood, string> = { good: "😀", mixed: "😐", bad: "🙁" };

/** Au-dela de ce delai, le moral affiche est signale comme ancien. */
const STALE_DAYS = 45;

export function moodAge(at?: string | null): number | null {
  if (!at) return null;
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return null;
  return Math.floor((Date.now() - d.getTime()) / 86400000);
}

/** Les trois visages, cliquables pour qui peut editer la squad. */
export default function TeamMood({ squadId, mood, moodAt, comment, canEdit, onChange }: {
  squadId: number; mood?: Mood | null; moodAt?: string | null; comment?: string | null;
  canEdit?: boolean; onChange?: () => void;
}) {
  const { t, formatDate } = useI18n();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const age = moodAge(moodAt);
  const stale = age !== null && age > STALE_DAYS;

  async function pick(next: Mood) {
    if (!canEdit || busy) return;
    setBusy(true); setErr(null);
    try {
      // Recliquer sur le niveau courant retire la declaration: c'est la seule
      // facon de dire "je ne me prononce plus" sans inventer un quatrieme niveau.
      await api.put(`/api/squads/${squadId}/mood`, { mood: next === mood ? null : next });
      onChange?.();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(false); }
  }

  return (
    <div className="stack" style={{ gap: 2, alignItems: "flex-end" }}>
      <div className="small muted">{t("mood.title")}</div>
      <div className="mood" role={canEdit ? "group" : undefined} aria-label={t("mood.title")}>
        {MOODS.map((m) => (
          <button key={m} type="button" disabled={!canEdit || busy}
                  className={`mood-btn${mood === m ? " on" : ""}`}
                  aria-pressed={mood === m}
                  aria-label={t(`mood.${m}`)}
                  title={canEdit ? t(`mood.${m}`) : t(`mood.${m}`)}
                  onClick={() => pick(m)}>
            {MOOD_EMOJI[m]}
          </button>
        ))}
      </div>
      {mood && moodAt && (
        <div className="small muted" style={{ color: stale ? "var(--orange)" : undefined }}>
          {stale ? t("mood.stale", { date: formatDate(moodAt) }) : formatDate(moodAt)}
        </div>
      )}
      {!mood && canEdit && <div className="small muted">{t("mood.empty")}</div>}
      {comment && <div className="small muted" style={{ maxWidth: 220, textAlign: "right" }}>{comment}</div>}
      {err && <div className="small" style={{ color: "var(--red)" }}>{err}</div>}
    </div>
  );
}

/** Version compacte pour la grille du tableau de bord: le visage et rien d'autre. */
export function MoodBadge({ mood, moodAt }: { mood?: Mood | null; moodAt?: string | null }) {
  const { t, formatDate } = useI18n();
  if (!mood) return null;
  const age = moodAge(moodAt);
  const stale = age !== null && age > STALE_DAYS;
  return (
    <span className={`mood-card${stale ? "" : " on"}`}
          title={`${t("mood.title")} : ${t(`mood.${mood}`)}${moodAt ? `, ${formatDate(moodAt)}` : ""}`}>
      {MOOD_EMOJI[mood]}
    </span>
  );
}
