/**
 * Administration > Import: bulk-loading an organisation, Steerco data, and the
 * PowerPoint template.
 *
 * All three take a file from the administrator and hand it to the server. The org
 * importer is idempotent by natural key, so re-uploading an edited file updates
 * rather than duplicates (see docs/14).
 */
import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { useI18n } from "../../i18n";
import { useModule } from "../../config";
import { ErrorBanner } from "../../components/ui";

import { useErr } from "./shared";

export type ImportSummary = {
  tribe: string; year: number; squads: number; initiatives: number; otds: number;
  created: { users: number; squads: number; initiatives: number; otds: number };
};


/** Admin > Import: fill an Excel file with your real organisation (tribe, squads,
 *  leaders, initiatives, OTD), upload it here, and the app imports it directly.
 *  Idempotent and rebuild-free: works the same locally and in production (S3NS).
 *  Admin only. */
export function ImportOrgAdmin() {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportSummary | null>(null);
  const { error, wrap } = useErr();

  async function submit() {
    if (!file) return;
    setResult(null);
    setBusy(true);
    await wrap(async () => {
      const form = new FormData();
      form.append("file", file);
      setResult(await api.postForm<ImportSummary>("/api/admin/import-org", form));
    });
    setBusy(false);
  }

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      <div className="card stack" style={{ gap: 12 }}>
        <div>
          <h3 style={{ margin: 0 }}>{t("import.title")}</h3>
          <div className="small muted" style={{ marginTop: 4 }}>{t("import.intro")}</div>
        </div>
        <ol className="stack" style={{ gap: 6, margin: 0, paddingLeft: 18 }}>
          <li>
            {t("import.step_download")}{" "}
            <a className="btn-secondary btn-sm" href="/api/admin/import-org/template" style={{ marginLeft: 6 }}>
              {t("import.download")}
            </a>
          </li>
          <li>{t("import.step_fill")}</li>
          <li>{t("import.step_upload")}</li>
        </ol>
        <div className="row" style={{ alignItems: "center", gap: 10 }}>
          <input type="file" accept=".xlsx,.xlsm,.yaml,.yml" aria-label={t("a11y.choose_file")}
                 onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }} />
          <button onClick={submit} disabled={!file || busy}>
            {busy ? t("import.importing") : t("import.import")}
          </button>
        </div>
        <div className="small muted">{t("import.idempotent")}</div>
      </div>

      {result && (
        <div className="card stack" style={{ gap: 6 }}>
          <h3 style={{ margin: 0 }}>{t("import.done")}</h3>
          <div>{t("import.result_tribe")} <strong>{result.tribe}</strong> ({result.year})</div>
          <div className="small">
            {t("import.result_counts", {
              squads: String(result.squads),
              initiatives: String(result.initiatives),
              otds: String(result.otds),
            })}
          </div>
          <div className="small muted">
            {t("import.result_created", {
              users: String(result.created.users),
              squads: String(result.created.squads),
              initiatives: String(result.created.initiatives),
              otds: String(result.created.otds),
            })}
          </div>
        </div>
      )}
    </div>
  );
}


export type SteercoImportSummary = {
  squad: string; period: string; months: number; kpis: number; services: number; events: number;
  /** KPIs the squad already reported that the file did not cover: kept, not deleted. */
  kept_kpis: string[];
};


/** Admin > Import: collect a squad's Steerco data (KPI/SLA/incidents/events over 12
 *  months) in an Excel file, upload it here, and it is merged into the squad's monthly
 *  snapshots (history + current month). Idempotent per (squad, period). Admin only.
 *  Picking a squad before downloading yields a template pre-filled with its name and
 *  with the KPI / SLA rows it actually reports, instead of the standard structure. */
export function ImportSteercoAdmin() {
  const { t } = useI18n();
  const steercoOn = useModule()("steerco");
  const [squads, setSquads] = useState<{ id: number; name: string }[]>([]);
  const [squadId, setSquadId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SteercoImportSummary | null>(null);
  const { error, wrap } = useErr();

  useEffect(() => {
    if (!steercoOn) return;
    api.get<{ id: number; name: string }[]>("/api/squads").then(setSquads).catch(() => {});
  }, [steercoOn]);

  if (!steercoOn) return null;

  async function submit() {
    if (!file) return;
    setResult(null);
    setBusy(true);
    await wrap(async () => {
      const form = new FormData();
      form.append("file", file);
      setResult(await api.postForm<SteercoImportSummary>("/api/admin/import-steerco", form));
    });
    setBusy(false);
  }

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      <div className="card stack" style={{ gap: 12 }}>
        <div>
          <h3 style={{ margin: 0 }}>{t("import.steerco.title")}</h3>
          <div className="small muted" style={{ marginTop: 4 }}>{t("import.steerco.intro")}</div>
        </div>
        <ol className="stack" style={{ gap: 6, margin: 0, paddingLeft: 18 }}>
          <li>
            {t("import.steerco.step_pick")}{" "}
            <select aria-label={t("a11y.template_squad")} value={squadId} onChange={(e) => setSquadId(e.target.value)} style={{ minWidth: 190 }}>
              <option value="">{t("import.steerco.generic_template")}</option>
              {squads.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <a className="btn-secondary btn-sm" style={{ marginLeft: 8 }}
               href={`/api/admin/import-steerco/template${squadId ? `?squad_id=${squadId}` : ""}`}>
              {t("import.download")}
            </a>
            <div className="small muted" style={{ marginTop: 4 }}>{t("import.steerco.prefilled_hint")}</div>
          </li>
          <li>{t("import.steerco.step_fill")}</li>
          <li>{t("import.step_upload")}</li>
        </ol>
        <div className="row" style={{ alignItems: "center", gap: 10 }}>
          <input type="file" accept=".xlsx,.xlsm" aria-label={t("a11y.choose_file")}
                 onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }} />
          <button onClick={submit} disabled={!file || busy}>
            {busy ? t("import.importing") : t("import.import")}
          </button>
        </div>
        <div className="small muted">{t("import.steerco.idempotent")}</div>
      </div>

      {result && (
        <div className="card stack" style={{ gap: 6 }}>
          <h3 style={{ margin: 0 }}>{t("import.done")}</h3>
          <div>{t("import.steerco.result_squad")} <strong>{result.squad}</strong>, {result.period}</div>
          <div className="small">
            {t("import.steerco.result_counts", {
              months: String(result.months), kpis: String(result.kpis),
              services: String(result.services), events: String(result.events),
            })}
          </div>
          {result.kept_kpis?.length > 0 && (
            <div className="small" style={{ color: "var(--amber, #B54708)" }}>
              {t("import.steerco.kept_kpis", { list: result.kept_kpis.join(", ") })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


export type PptxTemplateMeta = { present: boolean; filename?: string; size?: number; uploaded_at?: string; uploaded_by?: string };


/** Admin > Import: upload a .pptx once; every PPTX export (reports, roadmap,
 *  dependencies, org, initiatives, steerco) is then built on it, so decks carry the
 *  organisation's master slides, theme and branding. Remove it to fall back to the
 *  plain default deck. */
export function PptxTemplateAdmin() {
  const { t, formatDateTime } = useI18n();
  const [meta, setMeta] = useState<PptxTemplateMeta | null>(null);
  const [busy, setBusy] = useState(false);
  const { error, wrap } = useErr();
  const inputRef = useRef<HTMLInputElement>(null);

  const load = () => api.get<PptxTemplateMeta>("/api/admin/pptx-template").then(setMeta).catch(() => setMeta({ present: false }));
  useEffect(() => { load(); }, []);

  async function upload(file: File) {
    setBusy(true);
    await wrap(async () => {
      const form = new FormData();
      form.append("file", file);
      setMeta(await api.postForm<PptxTemplateMeta>("/api/admin/pptx-template", form));
    });
    if (inputRef.current) inputRef.current.value = "";
    setBusy(false);
  }

  async function remove() {
    setBusy(true);
    await wrap(async () => { setMeta(await api.del<PptxTemplateMeta>("/api/admin/pptx-template")); });
    setBusy(false);
  }

  const kb = meta?.size ? Math.round(meta.size / 1024) : 0;

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div>
        <h3 style={{ margin: 0 }}>{t("set.pptx.title")}</h3>
        <div className="small muted" style={{ marginTop: 4 }}>{t("set.pptx.hint")}</div>
      </div>
      {error && <ErrorBanner message={error} />}

      {meta?.present ? (
        <div className="sc-status done" style={{ alignItems: "center" }}>
          <span className="sc-status-ic">✓</span>
          <div className="stack" style={{ gap: 2 }}>
            <div className="strong">{meta.filename}</div>
            <div className="small muted">
              {t("set.pptx.active", { kb: String(kb) })}
              {meta.uploaded_at ? `, ${formatDateTime(meta.uploaded_at)}` : ""}
              {meta.uploaded_by ? `, ${meta.uploaded_by}` : ""}
            </div>
          </div>
          <div className="inline" style={{ gap: 8, marginLeft: "auto" }}>
            <a className="btn-secondary btn-sm" href="/api/admin/pptx-template/download">{t("set.pptx.download")}</a>
            <button className="btn-ghost btn-sm" disabled={busy} onClick={remove}>{t("set.pptx.remove")}</button>
          </div>
        </div>
      ) : (
        <div className="small muted">{t("set.pptx.none")}</div>
      )}

      <div className="inline" style={{ gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <input ref={inputRef} type="file" accept=".pptx" aria-label={t("a11y.choose_file")}
               onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} />
        {busy && <span className="small muted">{t("common.loading")}</span>}
      </div>
    </div>
  );
}
