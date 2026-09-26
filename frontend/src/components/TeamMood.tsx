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
import { api, errorText, reportSaveError } from "../api";
import { useI18n } from "../i18n";

export const MOODS = ["good", "mixed", "bad"] as const;
export type Mood = (typeof MOODS)[number];

// Un nuage dessine plutot qu'un emoji. Un emoji depend de la police installee: il
// change de style d'un poste a l'autre et sort en carre la ou le jeu couleur
// manque, y compris dans les documents exportes. Les memes trois teintes et la
// meme geometrie qu'en HTML et en PPTX (voir backend/app/reportcommon.py), pour
// que le moral se reconnaisse d'un support a l'autre.
const CLOUD: Record<Mood, { ink: string; fill: string; mouth: string }> = {
  good: { ink: "#027A48", fill: "#7EE2B8", mouth: "M24 27 Q32 35 40 27" },
  mixed: { ink: "#B54708", fill: "#FBD96B", mouth: "M25 29 L39 29" },
  bad: { ink: "#B42318", fill: "#F9A8A0", mouth: "M24 33 Q32 25 40 33" },
};

/** Le nuage d'un niveau de moral. La couleur porte le niveau, la bouche le redit
 *  pour qui imprime en noir et blanc, ou ne distingue pas les teintes. */
export function MoodCloud({ mood, size = 30 }: { mood: Mood; size?: number }) {
  const c = CLOUD[mood];
  return (
    <svg className="mood-cloud" width={size} height={Math.round(size * 0.72)}
         viewBox="0 0 64 46" role="img" aria-hidden="true" focusable="false">
      <path d="M18 40 A11 11 0 0 1 18 18 A13 13 0 0 1 43 14 A11 11 0 0 1 47 40 Z"
            fill={c.fill} stroke={c.ink} strokeWidth="3" strokeLinejoin="round" />
      <circle cx="26" cy="23" r="2.8" fill={c.ink} />
      <circle cx="39" cy="23" r="2.8" fill={c.ink} />
      <path d={c.mouth} fill="none" stroke={c.ink} strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/** Au-dela de ce delai, le moral affiche est signale comme ancien. */
const STALE_DAYS = 45;
/** Dans la saisie hebdomadaire, un moral d'une autre semaine est a rafraichir. */
export const WEEKLY_STALE_DAYS = 6;

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
  // In the weekly reporting (big), last week's mood is already one to refresh.
  const stale = age !== null && age > (big ? WEEKLY_STALE_DAYS : STALE_DAYS);

  // Clicking a level declares it for this week, the current one included: on a
  // Monday "same as last week" is the most common answer, and re-clicking used to
  // withdraw the mood instead. Withdrawing has its own small button.
  async function send(next: Mood | null) {
    if (!canEdit || busy) return;
    setBusy(true); setErr(null);
    try {
      await api.put(`/api/squads/${squadId}/mood`, { mood: next });
      onChange?.();
    } catch (e) {
      setErr(errorText(e));
    } finally { setBusy(false); }
  }
  const pick = (next: Mood) => send(next);

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
            <MoodCloud mood={m} size={big ? 54 : 30} />
          </button>
        ))}
      </div>
      {mood && moodAt && (
        <div className="small muted" style={{ color: stale ? "var(--orange)" : undefined }}>
          {stale ? t("mood.stale", { date: formatDate(moodAt) }) : formatDate(moodAt)}
        </div>
      )}
      {!mood && canEdit && <div className="small muted">{t("mood.empty")}</div>}
      {mood && canEdit && big && (
        <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={() => send(null)}>
          {t("mood.withdraw")}
        </button>
      )}
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
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setDraft(comment ?? ""); }, [comment]);

  async function save() {
    if (draft === (comment ?? "")) return;
    setBusy(true); setErr(null);
    try {
      // The comment alone: the level and its date stay as they are.
      await api.put(`/api/squads/${squadId}/mood`, mood ? { comment: draft || null } : { mood: null, comment: draft || null });
      onChange?.();
    } catch (e) {
      // Put the saved note back and say why, rather than an unhandled promise.
      setDraft(comment ?? "");
      setErr(errorText(e)); reportSaveError(errorText(e));
    } finally { setBusy(false); }
  }

  return (
    <>
      <input className="mood-note" value={draft} maxLength={300} disabled={busy}
             placeholder={t("mood.note_ph")} aria-label={t("mood.note_ph")}
             onChange={(e) => setDraft(e.target.value)} onBlur={save} />
      {err && <div className="small" style={{ color: "var(--red)" }}>{err}</div>}
    </>
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
          title={`${t("mood.title")}${t("common.colon")}${t(`mood.${mood}`)}${moodAt ? `, ${formatDate(moodAt)}` : ""}`}>
      <MoodCloud mood={mood} size={22} />
    </span>
  );
}
