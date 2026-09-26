// Les messages cles d'une squad: un succes, une alerte, un risque.
//
// C'est ce que le comite lit en premier, et ce qui part en toutes lettres dans
// les documents. Le panneau est employe a deux endroits, la page de la squad et
// l'ecran de saisie: la page pour les lire, la saisie pour les ecrire au moment
// ou l'on rend compte. Un composant plutot qu'une copie, pour qu'une correction
// vaille des deux cotes.
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { KeyMessageKind, SquadDetail } from "../types";
import { Collapsible, ErrorBanner } from "./ui";

/** Map a key-message kind to its badge colour class (success/risk/alert). */
function kmKindClass(k: KeyMessageKind): string {
  return k === "success" ? "badge-green" : k === "risk" ? "badge-red" : "badge-orange";
}

/**
 * Key messages panel: the squad's highlights (success / alert / risk) for the
 * year. Visible to everyone who can see the squad; editable only by the squad
 * leader or admin (`canEdit`, from `leadsThisSquad`). Supports inline add / edit
 * / delete and calls onChange (reload) after each mutation.
 */
export default function KeyMessagesPanel({ squad, canEdit, onChange, editTo, editLabel }:
  { squad: SquadDetail; canEdit: boolean; onChange: () => void;
    /** Where the messages are edited, when not here (the squad page). */
    editTo?: string; editLabel?: string }) {
  const { t, formatDateTime } = useI18n();
  // The message whose deletion waits for a second click (the same gesture everywhere).
  const [deleting, setDeleting] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<KeyMessageKind>("success");
  const [text, setText] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editKind, setEditKind] = useState<KeyMessageKind>("success");
  const [editText, setEditText] = useState("");

  // A refused write (403, 422) is said here; it used to be swallowed.
  const [err, setErr] = useState<string | null>(null);
  const fail = (e: unknown) => setErr(errorText(e));
  const kinds: KeyMessageKind[] = ["success", "alert", "risk"];
  const add = () => {
    if (!text.trim()) return;
    setErr(null);
    api.post(`/api/squads/${squad.id}/key-messages?year=${squad.year}`,
      { kind, text: text.trim(), display_order: squad.key_messages.length })
      .then(() => { setText(""); setKind("success"); setAdding(false); onChange(); })
      .catch(fail);
  };
  const startEdit = (m: { id: number; kind: KeyMessageKind; text: string }) => {
    setEditId(m.id); setEditKind(m.kind); setEditText(m.text);
  };
  const saveEdit = (id: number) => {
    if (!editText.trim()) return;
    setErr(null);
    api.put(`/api/squads/${squad.id}/key-messages/${id}`, { kind: editKind, text: editText.trim() })
      .then(() => { setEditId(null); onChange(); }).catch(fail);
  };
  const remove = (id: number) =>
    (setErr(null), api.del(`/api/squads/${squad.id}/key-messages/${id}`).then(onChange).catch(fail));

  return (
    <Collapsible title={t("km.title")} defaultOpen
                 subtitle={t("km.collapsed_hint", { n: squad.key_messages.length })}
                 right={!canEdit && editTo ? <Link to={editTo} className="btn btn-secondary btn-sm">{editLabel}</Link> : undefined}>
      <div className="small muted" style={{ marginBottom: 8 }}>{t("km.hint")}</div>
      {err && <ErrorBanner message={err} />}
      {squad.key_messages.length === 0 && <div className="small muted">{t("km.none")}</div>}
      {squad.key_messages.map((m) => (
        <div key={m.id} className="item-row">
          {editId === m.id ? (
            <div className="grow stack" style={{ gap: 6 }}>
              <select value={editKind} onChange={(e) => setEditKind(e.target.value as KeyMessageKind)}>
                {kinds.map((k) => <option key={k} value={k}>{t(`km.kind.${k}`)}</option>)}
              </select>
              <textarea rows={2} value={editText} onChange={(e) => setEditText(e.target.value)} />
              <div className="inline" style={{ gap: 8 }}>
                <button className="btn-sm" onClick={() => saveEdit(m.id)}>{t("action.save")}</button>
                <button className="btn-secondary btn-sm" onClick={() => setEditId(null)}>{t("action.cancel")}</button>
              </div>
            </div>
          ) : (
            <>
              <span className={`badge ${kmKindClass(m.kind)}`}>{t(`km.kind.${m.kind}`)}</span>
              <div className="grow">
                <div className="small">{m.text}</div>
                <div className="small muted">{formatDateTime(m.created_at)}</div>
              </div>
              {canEdit && (
                <span className="inline" style={{ gap: 6 }}>
                  <button className="btn-secondary btn-sm" onClick={() => startEdit(m)}>{t("action.edit")}</button>
                  {deleting === m.id ? (
                    <>
                      <button className="btn-danger btn-sm" onClick={() => { setDeleting(null); remove(m.id); }}>{t("action.delete")}</button>
                      <button className="btn-ghost btn-sm" onClick={() => setDeleting(null)}>{t("action.cancel")}</button>
                    </>
                  ) : (
                    <button className="btn-danger btn-sm" onClick={() => setDeleting(m.id)} aria-label={t("action.delete")}>✕</button>
                  )}
                </span>
              )}
            </>
          )}
        </div>
      ))}
      {canEdit && (adding ? (
        <div className="stack" style={{ gap: 6, marginTop: 10 }}>
          <select value={kind} onChange={(e) => setKind(e.target.value as KeyMessageKind)}>
            {kinds.map((k) => <option key={k} value={k}>{t(`km.kind.${k}`)}</option>)}
          </select>
          <textarea rows={2} value={text} placeholder={t("km.text_ph")} onChange={(e) => setText(e.target.value)} />
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-sm" onClick={add}>{t("action.add")}</button>
            <button className="btn-secondary btn-sm" onClick={() => setAdding(false)}>{t("action.cancel")}</button>
          </div>
        </div>
      ) : (
        <button className="btn-secondary btn-sm" style={{ marginTop: 10 }} onClick={() => setAdding(true)}>
          + {t("km.add")}
        </button>
      ))}
    </Collapsible>
  );
}
