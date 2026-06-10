import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Notif, NotificationsResponse } from "../types";

function BellIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

export default function NotificationBell() {
  const { t, formatDateTime } = useI18n();
  const navigate = useNavigate();
  const [data, setData] = useState<NotificationsResponse>({ unread_count: 0, items: [] });
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  function load() {
    api.get<NotificationsResponse>("/api/notifications").then(setData).catch(() => {});
  }
  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  async function readAll() {
    await api.post("/api/notifications/read-all");
    load();
  }
  function openItem(n: Notif) {
    if (!n.is_read) api.post(`/api/notifications/${n.id}/read`).catch(() => {});
    setOpen(false);
    if (n.link) navigate(n.link);
    setTimeout(load, 300);
  }
  const label = (n: Notif) =>
    n.kind === "reply" ? t("notif.reply", { actor: n.actor_name || "?" }) : t("notif.tweet", { actor: n.actor_name || "?" });

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        className="btn-ghost"
        style={{ color: "#fff", borderColor: "rgba(255,255,255,.3)", position: "relative", padding: "8px 10px" }}
        onClick={() => setOpen((o) => !o)}
        title={t("notif.title")}
      >
        <BellIcon />
        {data.unread_count > 0 && <span className="notif-badge">{data.unread_count}</span>}
      </button>
      {open && (
        <div className="notif-panel">
          <div className="between" style={{ padding: "2px 4px 8px" }}>
            <span className="strong">{t("notif.title")}</span>
            {data.unread_count > 0 && (
              <button className="btn-ghost btn-sm" onClick={readAll}>
                {t("notif.read_all")}
              </button>
            )}
          </div>
          {data.items.length === 0 && <div className="small muted" style={{ padding: 8 }}>{t("notif.none")}</div>}
          {data.items.map((n) => (
            <button key={n.id} className={`notif-item ${n.is_read ? "" : "unread"}`} onClick={() => openItem(n)}>
              <div className="small strong">{label(n)}</div>
              {n.excerpt && (
                <div className="small muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {n.excerpt}
                </div>
              )}
              <div className="small muted">{formatDateTime(n.created_at)}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
