import { useState } from "react";
import { useI18n } from "../i18n";
import { Modal } from "./ui";

/** In-app window that shows an HTML export instead of redirecting to a browser
 *  tab. The export is rendered in an iframe (cookie auth flows through), with a
 *  download action kept for those who want the file. Used everywhere an export
 *  HTML link existed, so the experience stays coherent across the app. */
export function HtmlPreviewModal({ url, title, onClose }: { url: string; title: string; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <Modal
      width={1120}
      title={title}
      onClose={onClose}
      footer={
        <div className="between" style={{ width: "100%", alignItems: "center" }}>
          <span className="small muted">{t("export.preview_hint")}</span>
          <div className="inline" style={{ gap: 8 }}>
            <a className="btn-secondary btn-sm" href={url} download>{t("export.download")}</a>
            <button className="btn btn-secondary btn-sm" onClick={onClose}>{t("action.close")}</button>
          </div>
        </div>
      }
    >
      <iframe
        src={url}
        title={title}
        style={{ width: "100%", height: "76vh", border: "1px solid var(--line)", borderRadius: 8, background: "#F5F7FA" }}
      />
    </Modal>
  );
}

/** Drop-in replacement for an `<a href=… target="_blank">HTML</a>` export link:
 *  opens the HTML in the in-app window instead of a new tab. */
export function HtmlPreviewButton({ url, title, label = "HTML", className = "btn btn-secondary", disabled = false, onOpen }:
  { url: string; title: string; label?: string; className?: string; disabled?: boolean; onOpen?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className={className} disabled={disabled} onClick={() => { if (disabled) return; onOpen?.(); setOpen(true); }}>
        {label}
      </button>
      {open && <HtmlPreviewModal url={url} title={title} onClose={() => setOpen(false)} />}
    </>
  );
}
