// Steerco > Parametres: every setting of the tribe's Steerco, in one place and in
// the order they are done the first time. A "set up" checklist on top says what is
// done and what is left, each line leading to its section. The month's work (enter,
// validate, send) is never here: it is in "Le mois".
//
// What is set elsewhere is named here too, with the way there: who may READ the
// Steerco is a persona capability (Administration > Personas), and the slide's
// layout is designed in the export Studio.
import { ReactNode, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../i18n";
import { Platform } from "../../steerco";
import { LeadersSection, MailSettings } from "./SteercoLeaders";
import { PlatformList, TribeModelEditor } from "./SteercoPlatforms";

type Status = { leaders: number; model: boolean; platforms: number; recipients: number };

// At module level: declared inside the component, it would be a new component type
// on every render, and the forms inside would lose what is being typed.
function Section({ id, n, title, children }: { id: string; n: number; title: string; children: ReactNode }) {
  return (
    <section id={id} className="card stack" style={{ gap: 12, scrollMarginTop: "calc(var(--topbar-h, 64px) + 12px)" }}>
      <h2 style={{ margin: 0 }}><span className="sc-step-n">{n}</span> {title}</h2>
      {children}
    </section>
  );
}

export default function SteercoSettings({ tribeId, canRun, canDesignate }: {
  tribeId: number; canRun: boolean; canDesignate: boolean;
}) {
  const { t } = useI18n();
  const { adminTabs } = useAuth();
  const [st, setSt] = useState<Status | null>(null);

  const refresh = useCallback(() => {
    const leaders = api.get<{ leaders: { active: boolean }[] }>(`/api/steerco/leaders?tribe_id=${tribeId}`)
      .then((r) => r.leaders.filter((l) => l.active).length).catch(() => 0);
    const model = canRun ? api.get<{ kpis: unknown[]; sla: unknown[] }>(`/api/steerco/model?tribe_id=${tribeId}`)
      .then((m) => (m.kpis?.length ?? 0) + (m.sla?.length ?? 0) > 0).catch(() => false) : Promise.resolve(false);
    const platforms = canRun ? api.get<Platform[]>(`/api/steerco/platforms?tribe_id=${tribeId}`)
      .then((ps) => ps.filter((p) => p.steerco_enabled).length).catch(() => 0) : Promise.resolve(0);
    const recipients = canRun ? api.get<{ recipients: string[] }>(`/api/steerco/mail?tribe_id=${tribeId}`)
      .then((c) => c.recipients?.length ?? 0).catch(() => 0) : Promise.resolve(0);
    Promise.all([leaders, model, platforms, recipients])
      .then(([l, m, p, r]) => setSt({ leaders: l, model: m, platforms: p, recipients: r }));
  }, [tribeId, canRun]);
  useEffect(() => { setSt(null); refresh(); }, [refresh]);

  const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  // The set-up steps, in the order they are done the first time.
  const steps = [
    { id: "sc-leaders", show: true, done: !!st && st.leaders > 0,
      text: st ? t("steerco.setup.leaders_state", { n: st.leaders }) : "" },
    { id: "sc-model", show: canRun, done: !!st?.model,
      text: st?.model ? t("steerco.setup.model_done") : t("steerco.setup.model_todo") },
    { id: "sc-platforms", show: canRun, done: !!st && st.platforms > 0,
      text: st ? t("steerco.setup.platforms_state", { n: st.platforms }) : "" },
    { id: "sc-mail", show: canRun, done: !!st && st.recipients > 0,
      text: st ? t("steerco.setup.mail_state", { n: st.recipients }) : "" },
    { id: "sc-readers", show: true, done: true, optional: true, text: t("steerco.setup.readers_state") },
  ].filter((s) => s.show);
  const left = steps.filter((s) => !s.done).length;

  let n = 0;

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card stack" style={{ gap: 10 }}>
        <div className="stack" style={{ gap: 2 }}>
          <h2 style={{ margin: 0 }}>{t("steerco.setup.title")}</h2>
          <div className="small muted">{t("steerco.setup.hint")}</div>
        </div>
        <ol className="sc-checklist">
          {steps.map((s, i) => (
            <li key={s.id} className={s.done ? "done" : "todo"}>
              <span className="sc-check" aria-hidden>{s.done ? "✓" : i + 1}</span>
              <span className="stack" style={{ gap: 0, flex: 1 }}>
                <span className="strong">{t(`steerco.setup.step.${s.id}`)}</span>
                <span className="small muted">{s.text}</span>
              </span>
              <button type="button" className={s.done ? "btn-ghost btn-sm" : "btn-sm"} onClick={() => go(s.id)}>
                {s.done ? t("steerco.setup.see") : t("steerco.setup.do")}
              </button>
            </li>
          ))}
        </ol>
        {st && (left === 0
          ? <div className="small" style={{ color: "var(--green)" }}>{t("steerco.setup.ready")} <Link to="/steerco?tab=month">{t("steerco.tab.month")}</Link></div>
          : <div className="small muted">{t("steerco.setup.left", { n: left })}</div>)}
      </div>

      <Section id="sc-leaders" n={++n} title={t("steerco.setup.step.sc-leaders")}>
        {canDesignate || canRun ? <LeadersSection tribeId={tribeId} onChanged={refresh} /> : null}
      </Section>
      {canRun && (
        <>
          <Section id="sc-model" n={++n} title={t("steerco.setup.step.sc-model")}>
            <TribeModelEditor tribeId={tribeId} onSaved={refresh} />
          </Section>
          <Section id="sc-platforms" n={++n} title={t("steerco.setup.step.sc-platforms")}>
            <PlatformList tribeId={tribeId} onChanged={refresh} />
          </Section>
          <Section id="sc-mail" n={++n} title={t("steerco.setup.step.sc-mail")}>
            <MailSettings tribeId={tribeId} onSaved={refresh} />
          </Section>
        </>
      )}
      <Section id="sc-readers" n={++n} title={t("steerco.setup.step.sc-readers")}>
        <div className="small">{t("steerco.setup.readers_hint")}</div>
        {adminTabs.includes("personas")
          ? <div><Link className="btn-secondary btn-sm" to="/admin?section=personas">{t("steerco.setup.open_personas")}</Link></div>
          : <div className="small muted">{t("steerco.setup.readers_ask_admin")}</div>}
      </Section>
    </div>
  );
}
