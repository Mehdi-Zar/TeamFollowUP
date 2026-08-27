/**
 * Helpers shared by more than one administration panel.
 *
 * `useErr` is the small load-or-show-the-error wrapper nearly every panel uses;
 * `useAppRestart` drives the restart flow, needed by both the TLS panel (the
 * listener binds at boot) and the Ops panel.
 */
import { useState } from "react";
import { api, ApiError } from "../../api";
import { useI18n } from "../../i18n";


/** Shared error helper for the admin panels: exposes an `error` string and a
 *  `wrap` that runs an async action, clearing then capturing any ApiError message
 *  and returning undefined on failure (so callers can guard on the result). */
export function useErr() {
  const [error, setError] = useState<string | null>(null);
  const wrap = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
      return undefined;
    }
  };
  return { error, wrap };
}


/** Shared self-restart action, used by the Ops panel and the TLS "restart pending"
 *  banner. Triggers POST /api/admin/restart, then (when a supervisor will bring the
 *  process back) polls the health probe until the app is down-then-up and reloads.
 *  Exposes a `restarting` overlay so callers render a consistent waiting state. */
export function useAppRestart() {
  const { t } = useI18n();
  const [restarting, setRestarting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function waitForBack() {
    const start = Date.now();
    let sawDown = false;
    const tick = async () => {
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        if (res.ok && sawDown) { window.location.reload(); return; }
        if (!res.ok) sawDown = true;
      } catch { sawDown = true; }
      if (Date.now() - start < 120000) setTimeout(tick, 1500);
      else window.location.reload();
    };
    setTimeout(tick, 1500);
  }

  async function restart(): Promise<any> {
    setErr(null);
    try {
      const r = await api.post<any>("/api/admin/restart", {});
      if (r.scheduled !== false) {
        setRestarting(true);
        if (r.auto_restart) waitForBack();
      }
      return r;
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Erreur");
      return null;
    }
  }

  const overlay = restarting ? (
    <div className="modal-overlay">
      <div className="modal stack" style={{ alignItems: "center", gap: 12 }}>
        <div className="spinner" />
        <div className="strong">{t("ops.restarting")}</div>
        <div className="small muted" style={{ textAlign: "center" }}>{t("ops.restarting_hint")}</div>
      </div>
    </div>
  ) : null;

  return { restart, restarting, overlay, err };
}
