// Moral de l'equipe, en trois niveaux.
//
// Trois et pas cinq: une echelle fine invite a la nuance, or ce qu'on cherche ici
// est un signal. Trois choix se decident en une seconde, ce qui est la condition
// pour que la case soit remplie chaque semaine plutot qu'une fois en janvier.
//
// La date compte autant que le niveau: un moral de mars affiche en septembre ment
// plus surement qu'une case vide, donc l'age est toujours dit, et un moral trop
// vieux se signale de lui-meme.
import { useEffect, useState } from "react";
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
export default function TeamMood({ squadId, mood, moodAt, comment, canEdit, onChange, big }: {
  squadId: number; mood?: Mood | null; moodAt?: string | null; comment?: string | null;
  canEdit?: boolean; onChange?: () => void;
  /** Au centre d'une etape de reporting: les trois visages prennent la place
   *  qu'ils meritent quand la question est la seule posee a l'ecran. */
  big?: boolean;
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
    // Cale a droite dans un coin d'entete, centre quand il occupe l'ecran.
    <div className="stack" style={{ gap: 2, alignItems: big ? "center" : "flex-end" }}>
      <div className="small muted">{t("mood.title")}</div>
      <div className={big ? "mood mood-big" : "mood"} role={canEdit ? "group" : undefined} aria-label={t("mood.title")}>
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
      {/* Le mot qui explique le visage. Il ne s'ecrit que la ou la question est
          posee en grand: dans un coin d'entete, un champ de texte n'aurait ni la
          place ni le sens. */}
      {big && canEdit ? (
        <MoodNote squadId={squadId} mood={mood} comment={comment} onChange={onChange} />
      ) : (
        comment && <div className="small muted" style={{ maxWidth: 220, textAlign: big ? "center" : "right" }}>{comment}</div>
      )}
      {err && <div className="small" style={{ color: "var(--red)" }}>{err}</div>}
    </div>
  );
}

/**
 * Le commentaire du moral: une phrase, enregistree en quittant le champ.
 *
 * Il accompagne le niveau sans le remplacer. Le serveur le coupe a 300
 * caracteres, la meme borne est posee ici pour que la coupe ne soit pas une
 * surprise a la relecture.
 */
function MoodNote({ squadId, mood, comment, onChange }: {
  squadId: number; mood?: Mood | null; comment?: string | null; onChange?: () => void;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState(comment ?? "");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setDraft(comment ?? ""); }, [comment]);

  async function save() {
    if (draft === (comment ?? "")) return;
    setBusy(true);
    try {
      await api.put(`/api/squads/${squadId}/mood`, { mood: mood ?? null, comment: draft || null });
      onChange?.();
    } finally { setBusy(false); }
  }

  return (
    <input className="mood-note" value={draft} maxLength={300} disabled={busy}
           placeholder={t("mood.note_ph")} aria-label={t("mood.note_ph")}
           onChange={(e) => setDraft(e.target.value)} onBlur={save} />
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
