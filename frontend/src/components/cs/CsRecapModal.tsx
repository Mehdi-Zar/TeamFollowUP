// The recap mail (docs/37, section 5): built by the server, shown here as it will
// read, then copied for Outlook.
//
// The copy goes through a selection of the rendered HTML (execCommand "copy"),
// not the async clipboard API: the app is served over plain HTTP behind the
// company's TLS, and that API only exists in a secure context. A selection copy
// carries the formatting (table, bold, lists) into Outlook either way.
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { CsSettings, Project, fmtDate } from "../../cs";
import { Chip, ErrorBanner, Modal, Spinner } from "../ui";

export default function CsRecapModal({ tribeId, settings, projects, canRun, onClose, onSaved }: {
  tribeId: number; settings: CsSettings; projects: Project[]; canRun: boolean;
  onClose: () => void; onSaved: () => void;
}) {
  const { t, lang } = useI18n();
  const [offer, setOffer] = useState("");
  // Every stage but the last (Closed by default): a closed project has left the recap.
  const [stages, setStages] = useState<string[]>(settings.stages.slice(0, -1).map((s) => s.key));
  const [mailLang, setMailLang] = useState<"fr" | "en">(lang === "en" ? "en" : "fr");
  const [intro, setIntro] = useState(settings.recap_intro);
  const [introDirty, setIntroDirty] = useState(false);
  const [html, setHtml] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [marked, setMarked] = useState(settings.recap_marked_at);
  const box = useRef<HTMLDivElement>(null);
  const offers = Array.from(new Set(projects.map((p) => p.offer).filter((o): o is string => !!o))).sort();

  const query = () => {
    const q = new URLSearchParams({ tribe_id: String(tribeId), lang: mailLang });
    if (offer) q.set("offer", offer);
    if (stages.length) q.set("stages", stages.join(","));
    return q.toString();
  };
  const refresh = () => {
    setErr(null);
    api.get<string>(`/api/cs/recap.html?${query()}`).then((h) => setHtml(String(h ?? ""))).catch((e) => setErr(errorText(e)));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(refresh, [offer, stages.join(","), mailLang, tribeId]);

  async function saveIntro() {
    setErr(null);
    try {
      await api.put(`/api/cs/settings?tribe_id=${tribeId}`, { recap_intro: intro });
      setIntroDirty(false); onSaved(); refresh();
    } catch (e) { setErr(errorText(e)); }
  }

  function copy() {
    const el = box.current;
    if (!el) return;
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    sel?.removeAllRanges();
    sel?.addRange(range);
    let done = false;
    try { done = document.execCommand("copy"); } catch { done = false; }
    sel?.removeAllRanges();
    setNote(done ? t("cs.recap.copied") : t("cs.recap.copy_failed"));
  }

  async function mark() {
    if (!window.confirm(t("cs.recap.mark_confirm"))) return;
    try {
      const r = await api.post<{ recap_marked_at: string }>(`/api/cs/recap/mark?tribe_id=${tribeId}`);
      setMarked(r.recap_marked_at); setNote(t("cs.recap.marked")); onSaved(); refresh();
    } catch (e) { setErr(errorText(e)); }
  }

  const toggleStage = (k: string) => setStages(stages.includes(k) ? stages.filter((x) => x !== k) : [...stages, k]);

  return (
    <Modal width={1040} title={t("cs.recap.title")} onClose={onClose} dirty={introDirty}
           footer={
             <div className="between" style={{ width: "100%", alignItems: "center", gap: 8 }}>
               <span className="small muted">
                 {marked ? t("cs.recap.last_marked", { date: fmtDate(marked.slice(0, 10), lang) }) : t("cs.recap.never_marked")}
               </span>
               <div className="inline" style={{ gap: 8, alignItems: "center" }}>
                 {note && <span className="small">{note}</span>}
                 {canRun && <button className="btn-secondary btn-sm" onClick={mark}>{t("cs.recap.mark")}</button>}
                 <button className="btn-sm" disabled={!html} onClick={copy}>{t("cs.recap.copy")}</button>
               </div>
             </div>
           }>
      <div className="stack" style={{ gap: 12 }}>
        {err && <ErrorBanner message={err} />}
        <div className="inline" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          {offers.length > 0 && (
            <select className="w-auto" aria-label={t("cs.f.offer")} value={offer} onChange={(e) => setOffer(e.target.value)}>
              <option value="">{t("cs.all_offers")}</option>
              {offers.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          )}
          <select className="w-auto" aria-label={t("cs.recap.lang")} value={mailLang} onChange={(e) => setMailLang(e.target.value as "fr" | "en")}>
            <option value="fr">Français</option>
            <option value="en">English</option>
          </select>
        </div>
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          {settings.stages.map((s) => <Chip key={s.key} on={stages.includes(s.key)} onToggle={() => toggleStage(s.key)}>{s.label}</Chip>)}
        </div>
        {canRun && (
          <div className="stack" style={{ gap: 4 }}>
            <label className="small strong" htmlFor="cs-recap-intro">{t("cs.recap.intro")}</label>
            <textarea id="cs-recap-intro" rows={4} value={intro} placeholder={t("cs.recap.intro_hint")}
                      onChange={(e) => { setIntro(e.target.value); setIntroDirty(true); }} />
            {introDirty && <div><button className="btn-secondary btn-sm" onClick={saveIntro}>{t("cs.recap.save_intro")}</button></div>}
          </div>
        )}
        <div className="small muted">{t("cs.recap.hint")}</div>
        {html === null ? (!err && <Spinner />)
          // The server escapes every typed text (routers/cs.py, recap_html).
          : <div ref={box} className="cs-recap" dangerouslySetInnerHTML={{ __html: html }} />}
      </div>
    </Modal>
  );
}
