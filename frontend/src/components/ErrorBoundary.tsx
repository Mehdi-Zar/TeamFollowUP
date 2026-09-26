// ErrorBoundary: a page that fails to render shows a way out instead of a
// blank screen. Two causes are common:
// - after a deployment, an open tab asks for a page chunk that no longer
//   exists: one automatic reload fetches the new version;
// - any other exception while rendering: a translated message with a reload
//   button, the menu and the top bar stay in place.
import { Component, ReactNode } from "react";
import { useI18n } from "../i18n";

const RELOADED = "chunk-reloaded";

function isStaleChunk(error: unknown): boolean {
  const msg = String((error as any)?.message ?? error ?? "");
  return /dynamically imported module|Importing a module script failed|ChunkLoadError|Loading chunk/i.test(msg);
}

function CrashScreen() {
  const { t } = useI18n();
  return (
    <div className="card" role="alert" style={{ maxWidth: 520, margin: "40px auto", textAlign: "center" }}>
      <h2 style={{ marginTop: 0 }}>{t("crash.title")}</h2>
      <p className="muted">{t("crash.text")}</p>
      <button className="btn" onClick={() => window.location.reload()}>{t("crash.reload")}</button>
    </div>
  );
}

export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    // A new version was deployed: reload, at most once a minute (if the chunk
    // is really missing, the second failure shows the message instead of looping).
    if (isStaleChunk(error)) {
      let last = 0;
      try { last = Number(sessionStorage.getItem(RELOADED) || 0); sessionStorage.setItem(RELOADED, String(Date.now())); } catch { /* private mode */ }
      if (Date.now() - last > 60000) { window.location.reload(); return; }
    }
    console.error(error);
  }

  render() {
    return this.state.failed ? <CrashScreen /> : this.props.children;
  }
}
