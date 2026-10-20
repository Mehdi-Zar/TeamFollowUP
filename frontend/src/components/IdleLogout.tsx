// IdleLogout: signs the user out after the inactivity the admin set
// (Administration > General settings, "idle_timeout_minutes"; 0 = never).
//
// Activity is what the person does (mouse, keyboard, scroll, touch), shared by
// every tab of the app through localStorage: working in one tab keeps the others
// signed in. A minute before the end a window says so, with a button to stay.
// While the person is active the page tells the server, at most every two
// minutes, so the server's own check (deps._check_idle) agrees with the page.
// The page's automatic refreshes are not activity (api.poll).
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useConfig } from "../config";
import { useI18n } from "../i18n";
import { Modal } from "./ui";

const KEY = "tfu.lastActivity";
const WARN_SECONDS = 60;
const PING_EVERY_MS = 120_000;
const EVENTS = ["mousedown", "mousemove", "keydown", "wheel", "scroll", "touchstart"] as const;

function readLast(): number {
  try { return Number(localStorage.getItem(KEY)) || Date.now(); } catch { return Date.now(); }
}

export function IdleLogout() {
  const { t } = useI18n();
  const { user, logout } = useAuth();
  const minutes = Number((useConfig() as any).idle_timeout_minutes) || 0;
  const [left, setLeft] = useState<number | null>(null);
  const lastWrite = useRef(0);
  const lastPing = useRef(Date.now());
  const local = useRef(Date.now());

  useEffect(() => {
    if (!user || minutes <= 0) return;
    const mark = () => {
      const now = Date.now();
      local.current = now;
      if (now - lastWrite.current > 5000) {
        lastWrite.current = now;
        try { localStorage.setItem(KEY, String(now)); } catch { /* this tab only */ }
      }
      if (now - lastPing.current > PING_EVERY_MS) {
        lastPing.current = now;
        api.get("/api/auth/me").catch(() => {});
      }
    };
    mark();
    EVENTS.forEach((e) => window.addEventListener(e, mark, { passive: true }));
    const tick = setInterval(() => {
      const last = Math.max(readLast(), local.current);
      const idle = (Date.now() - last) / 1000;
      const limit = minutes * 60;
      if (idle >= limit) {
        clearInterval(tick);
        logout().finally(() => window.location.assign(`/login?idle=${minutes}`));
      } else if (idle >= limit - WARN_SECONDS) {
        setLeft(Math.ceil(limit - idle));
      } else {
        setLeft(null);
      }
    }, 1000);
    return () => {
      clearInterval(tick);
      EVENTS.forEach((e) => window.removeEventListener(e, mark));
    };
  }, [user?.id, minutes]);

  if (left === null) return null;
  const stay = () => {
    const now = Date.now();
    local.current = now;
    try { localStorage.setItem(KEY, String(now)); } catch { /* this tab only */ }
    lastPing.current = now;
    api.get("/api/auth/me").catch(() => {});
    setLeft(null);
  };
  return (
    <Modal width={440} title={t("idle.title")} onClose={stay}
           footer={<>
             <button className="btn-secondary" onClick={() => logout().finally(() => window.location.assign("/login"))}>
               {t("action.logout")}
             </button>
             <button onClick={stay}>{t("idle.stay")}</button>
           </>}>
      <p style={{ margin: 0 }}>{t("idle.body", { n: left })}</p>
    </Modal>
  );
}
