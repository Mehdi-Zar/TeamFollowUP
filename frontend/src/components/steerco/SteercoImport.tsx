// Fill a platform's figures from Excel, the alternative to the in-app assistant
// when the figures are collected offline. Three steps: download the platform's file
// (its name and rows already in), fill it in, drop it back. The import adds and
// updates, never deletes, and leaves a validated month as the committee saw it.
import { useEffect, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { ErrorBanner, Modal } from "../ui";
import { Platform } from "../../steerco";

export type SteercoImportSummary = {
  platform: string; period: string; months: number; kpis: number; services: number; events: number;
  /** KPIs already reported that the file did not cover: kept, not deleted. */
  kept_kpis: string[];
  /** Validated months the file named: left untouched. */
  skipped_validated?: string[];
};

export function SteercoImportModal({ tribeId, onClose, onDone }: {
  tribeId: number | null; onClose: () => void; onDone?: () => void;
}) {
  const { t } = useI18n();
  const [platforms, setPlatforms] = useState<Platform[] | null>(null);
  const [platformId, setPlatformId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SteercoImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = tribeId ? `?tribe_id=${tribeId}` : "";
    api.get<Platform[]>(`/api/steerco/platforms${q}`)
      .then((ps) => {
        const mine = ps.filter((p) => p.can_run && p.steerco_enabled);
        setPlatforms(mine);
        if (mine.length) setPlatformId(String(mine[0].id));
      })
      .catch((e) => { setError(errorText(e)); setPlatforms([]); });
  }, [tribeId]);

  async function submit() {
    if (!file) return;
    setResult(null); setError(null); setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      setResult(await api.postForm<SteercoImportSummary>("/api/steerco/import", form));
      onDone?.();
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }

  return (
    <Modal width={680} title={t("import.steerco.title")} onClose={onClose}
           footer={<button className="btn-secondary btn-sm" onClick={onClose}>{t("action.close")}</button>}>
      <div className="stack" style={{ gap: 14 }}>
        {error && <ErrorBanner message={error} />}
        <div className="small muted">{t("import.steerco.intro")}</div>

        <div className="sc-istep">
          <span className="sc-step-n">1</span>
          <div className="stack" style={{ gap: 6, flex: 1 }}>
            <span className="strong">{t("import.steerco.step_pick")}</span>
            <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
              <select aria-label={t("a11y.template_platform")} value={platformId} disabled={!platforms?.length}
                      onChange={(e) => setPlatformId(e.target.value)} style={{ minWidth: 200 }}>
                {(platforms ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              <a className={`btn-secondary btn-sm${platformId ? "" : " disabled"}`} aria-disabled={!platformId}
                 href={platformId ? `/api/steerco/import/template?platform_id=${platformId}` : undefined}>
                ⬇ {t("import.download")}
              </a>
            </div>
            <span className="small muted">{t("import.steerco.prefilled_hint")}</span>
          </div>
        </div>

        <div className="sc-istep">
          <span className="sc-step-n">2</span>
          <div className="stack" style={{ gap: 4, flex: 1 }}>
            <span className="strong">{t("import.steerco.step_fill")}</span>
            <span className="small muted">{t("import.steerco.step_fill_hint")}</span>
          </div>
        </div>

        <div className="sc-istep">
          <span className="sc-step-n">3</span>
          <div className="stack" style={{ gap: 6, flex: 1 }}>
            <span className="strong">{t("import.steerco.step_upload")}</span>
            <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
              <input type="file" accept=".xlsx,.xlsm" aria-label={t("a11y.choose_file")}
                     onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }} />
              <button className="btn-sm" onClick={submit} disabled={!file || busy}>
                {busy ? t("import.importing") : t("import.import")}
              </button>
            </div>
            <span className="small muted">{t("import.steerco.idempotent")}</span>
          </div>
        </div>

        {result && (
          <div className="card stack" style={{ gap: 6, borderLeft: "4px solid var(--green)" }}>
            <div className="strong">{t("import.steerco.done", { platform: result.platform })}</div>
            <div className="small">
              {t("import.steerco.result_counts", {
                months: String(result.months), kpis: String(result.kpis),
                services: String(result.services), events: String(result.events),
              })}
            </div>
            {result.kept_kpis?.length > 0 && (
              <div className="small" style={{ color: "var(--orange)" }}>
                {t("import.steerco.kept_kpis", { list: result.kept_kpis.join(", ") })}
              </div>
            )}
            {!!result.skipped_validated?.length && (
              <div className="small" style={{ color: "var(--orange)" }}>
                {t("import.steerco.skipped_validated", { list: result.skipped_validated.join(", ") })}
              </div>
            )}
            <div className="small muted">{t("import.steerco.done_next")}</div>
          </div>
        )}
      </div>
    </Modal>
  );
}
