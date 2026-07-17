// LeavesPage - team absence tracking (calendar, list, and personal views).
// Presents three tabs: a month calendar of everyone's absences, a filterable +
// CSV-exportable list, and "mine" (my absences plus, for leaders, the pending
// requests I can approve). Users file their own leave; leaders can file for their
// team members and approve/reject requests. All authorization (who can edit,
// decide, or file for others) is decided by the backend and reflected via flags
// like `can_edit` / `can_decide` on each Leave.
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { Modal, Spinner } from "../components/ui";
import { Leave, LeaveConfig, LeaveOverlapDay, LeaveStatus, LeaveType } from "../types";
import { leaveLabel, leaveTypeLabel } from "../leaves";

/* ---------- date helpers (local, no external dep) ---------- */
// Small pure date utilities kept in-file to avoid a date library dependency.
// iso: Date -> "YYYY-MM-DD" | parseISO: reverse | addDays: shift | sameDay: compare
// startOfMonth / mondayBefore: calendar-grid anchors | fmtShort: "DD/MM" display.
const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseISO = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const sameDay = (a: Date, b: Date) => iso(a) === iso(b);
const startOfMonth = (d: Date) => new Date(d.getFullYear(), d.getMonth(), 1);
const mondayBefore = (d: Date) => addDays(d, -((d.getDay() + 6) % 7));
const fmtShort = (s: string) => { const d = parseISO(s); return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`; };

/** Leave status -> badge CSS class, so status colour is consistent everywhere. */
const STATUS_CLASS: Record<LeaveStatus, string> = {
  pending: "badge-orange", approved: "badge-green", rejected: "badge-red", cancelled: "badge-grey",
};
const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
/** The three top-level tabs of the page. */
type View = "calendar" | "list" | "mine";

/**
 * Leaves page shell: owns the active tab, the shared reference data (types,
 * config, people), and the create/edit/detail modals.
 *
 * Business logic:
 * - Loads leave types, config (e.g. `require_approval`) and the list of people the
 *   user may file for, once on mount.
 * - `bump` is a monotonic counter: incrementing it via `reload()` forces the child
 *   views to re-fetch after any mutation, without lifting their data up here.
 * - `canFileForOthers` is true when the people list has more than just the current
 *   user, which only happens for leaders/managers per the backend.
 *
 * Access: any authenticated user; extra abilities depend on backend-provided scope.
 */
export default function LeavesPage() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const [view, setView] = useState<View>("calendar");
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [config, setConfig] = useState<LeaveConfig | null>(null);
  const [people, setPeople] = useState<{ user_id: number; name: string }[]>([]);
  const [editing, setEditing] = useState<Leave | "new" | null>(null);
  const [detail, setDetail] = useState<Leave | null>(null);

  useEffect(() => {
    api.get<LeaveType[]>("/api/leaves/types").then(setTypes).catch(() => {});
    api.get<LeaveConfig>("/api/leaves/config").then(setConfig).catch(() => setConfig(null));
    api.get<{ user_id: number; name: string }[]>("/api/leaves/people").then(setPeople).catch(() => {});
  }, []);

  // A single bump value forces children to re-fetch after a mutation.
  const [bump, setBump] = useState(0);
  const reload = () => setBump((b) => b + 1);
  const canFileForOthers = people.length > 1;

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="between" style={{ alignItems: "center" }}>
        <div className="seg" role="tablist">
          {(["calendar", "list", "mine"] as View[]).map((v) => (
            <button key={v} className={view === v ? "seg-on" : ""} onClick={() => setView(v)}>
              {t(`leaves.view.${v}`)}
            </button>
          ))}
        </div>
        <button className="btn btn-sm" onClick={() => setEditing("new")}>+ {t("leaves.new")}</button>
      </div>

      {view === "calendar" && <CalendarView bump={bump} onOpen={setDetail} />}
      {view === "list" && <ListView bump={bump} types={types} onOpen={setDetail} />}
      {view === "mine" && <MineView bump={bump} onOpen={setDetail} onNew={() => setEditing("new")} />}

      {editing && (
        <LeaveForm
          leave={editing === "new" ? null : editing}
          types={types}
          people={canFileForOthers ? people : []}
          requireApproval={!!config?.require_approval}
          selfId={user?.id}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reload(); }}
        />
      )}
      {detail && (
        <LeaveDetail
          leave={detail}
          onClose={() => setDetail(null)}
          onEdit={(lv) => { setDetail(null); setEditing(lv); }}
          onChanged={() => { setDetail(null); reload(); }}
        />
      )}
    </div>
  );
}

/* ---------- Calendar (month) ---------- */
/**
 * Month calendar of team absences. Renders a fixed 6-week (42-cell) grid starting
 * on the Monday before the 1st, and paints each person's approved/pending leave as
 * a coloured chip on the days it covers.
 *
 * Business logic:
 * - Fetches leaves and "overlaps" for the visible grid range; overlaps (days where
 *   several people are off) drive an amber warning banner and per-cell highlight.
 * - Only approved + pending leaves are shown; a ½ marker denotes a half-day at the
 *   start/end, and a dot marks still-pending requests.
 * - Re-fetches on month change or when `bump` changes (post-mutation refresh).
 *
 * @param onOpen invoked with a Leave when its chip is clicked (opens detail).
 */
function CalendarView({ bump, onOpen }: { bump: number; onOpen: (l: Leave) => void }) {
  const { t, lang } = useI18n();
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
  const [leaves, setLeaves] = useState<Leave[] | null>(null);
  const [overlaps, setOverlaps] = useState<LeaveOverlapDay[]>([]);

  // 6 weeks x 7 days = a stable 42-cell grid aligned to Monday.
  const gridStart = mondayBefore(startOfMonth(cursor));
  const days = useMemo(() => Array.from({ length: 42 }, (_, i) => addDays(gridStart, i)), [gridStart.getTime()]);
  const gridEnd = days[41];

  useEffect(() => {
    const qs = `from=${iso(gridStart)}&to=${iso(gridEnd)}`;
    api.get<Leave[]>(`/api/leaves?${qs}`).then(setLeaves).catch(() => setLeaves([]));
    api.get<LeaveOverlapDay[]>(`/api/leaves/overlaps?${qs}`).then(setOverlaps).catch(() => setOverlaps([]));
  }, [gridStart.getTime(), bump]);

  const monthLabel = cursor.toLocaleDateString(lang === "en" ? "en-GB" : "fr-FR", { month: "long", year: "numeric" });
  const overlapByDay = useMemo(() => {
    const m = new Set(overlaps.map((o) => o.day));
    return m;
  }, [overlaps]);

  if (!leaves) return <Spinner />;
  const today = new Date();
  const active = leaves.filter((l) => l.status === "approved" || l.status === "pending");

  return (
    <div className="card stack" style={{ gap: 12 }}>
      <div className="between" style={{ alignItems: "center" }}>
        <div className="inline" style={{ gap: 6 }}>
          <button className="btn-secondary btn-sm" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>‹</button>
          <button className="btn-secondary btn-sm" onClick={() => setCursor(startOfMonth(new Date()))}>{t("leaves.today")}</button>
          <button className="btn-secondary btn-sm" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>›</button>
        </div>
        <strong style={{ textTransform: "capitalize" }}>{monthLabel}</strong>
        <span className="small muted">{active.length} {t("leaves.absences")}</span>
      </div>

      {overlaps.length > 0 && (
        <div className="banner banner-amber small">
          ⚠ {t("leaves.overlap_warn", { n: overlaps.length })}
        </div>
      )}

      <div className="cal-grid">
        {WEEKDAY_KEYS.map((k) => <div key={k} className="cal-head">{t(`reporting.day.${k}`)}</div>)}
        {days.map((day) => {
          // A cell shows the leaves whose [start,end] range contains this day.
          const inMonth = day.getMonth() === cursor.getMonth();
          const dayLeaves = active.filter((l) => parseISO(l.start_date) <= day && day <= parseISO(l.end_date));
          const isToday = sameDay(day, today);
          const over = overlapByDay.has(iso(day));
          return (
            <div key={iso(day)} className={`cal-cell${inMonth ? "" : " cal-out"}${isToday ? " cal-today" : ""}${over ? " cal-over" : ""}`}>
              <div className="cal-day">{day.getDate()}</div>
              <div className="cal-chips">
                {dayLeaves.slice(0, 4).map((l) => {
                  const half = (sameDay(day, parseISO(l.start_date)) && l.start_half) ||
                               (sameDay(day, parseISO(l.end_date)) && l.end_half);
                  return (
                    <button key={l.id} className="cal-chip" style={{ background: l.type_color }}
                      title={`${l.user_name} · ${leaveLabel(l, lang)}${l.status === "pending" ? " (" + t("leaves.status.pending") + ")" : ""}`}
                      onClick={() => onOpen(l)}>
                      <span className="cal-chip-name">{l.user_name}</span>
                      {half && <span className="cal-chip-half">½</span>}
                      {l.status === "pending" && <span className="cal-chip-pending">•</span>}
                    </button>
                  );
                })}
                {dayLeaves.length > 4 && <span className="small muted">+{dayLeaves.length - 4}</span>}
              </div>
            </div>
          );
        })}
      </div>
      <Legend />
    </div>
  );
}

/** Colour legend mapping each leave type to its dot colour, shown under the grid. */
function Legend() {
  const { lang } = useI18n();
  const [types, setTypes] = useState<LeaveType[]>([]);
  useEffect(() => { api.get<LeaveType[]>("/api/leaves/types").then(setTypes).catch(() => {}); }, []);
  return (
    <div className="inline" style={{ gap: 14, flexWrap: "wrap" }}>
      {types.map((tp) => (
        <span key={tp.id} className="inline small" style={{ gap: 6 }}>
          <span className="dot" style={{ background: tp.color }} />{leaveTypeLabel(tp.label, lang)}
        </span>
      ))}
    </div>
  );
}

/* ---------- List (filterable + export) ---------- */
/**
 * Tabular, filterable view of leaves with CSV export.
 *
 * Business logic:
 * - Date range + status are sent to the API (server-side filter); type and free-text
 *   name search are applied client-side over the returned rows.
 * - Defaults to the current calendar year. Clicking a row opens its detail.
 * - The CSV link points at the export endpoint scoped to the same date range.
 *
 * @param types  leave types offered in the type dropdown.
 * @param onOpen invoked with the clicked Leave (opens detail).
 */
function ListView({ bump, types, onOpen }: { bump: number; types: LeaveType[]; onOpen: (l: Leave) => void }) {
  const { t, lang } = useI18n();
  const year = new Date().getFullYear();
  const [from, setFrom] = useState(`${year}-01-01`);
  const [to, setTo] = useState(`${year}-12-31`);
  const [status, setStatus] = useState("");
  const [typeId, setTypeId] = useState("");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Leave[] | null>(null);

  useEffect(() => {
    const p = new URLSearchParams({ from, to });
    if (status) p.set("status", status);
    api.get<Leave[]>(`/api/leaves?${p.toString()}`).then(setRows).catch(() => setRows([]));
  }, [from, to, status, bump]);

  // Client-side narrowing on top of the server range/status filter.
  const filtered = (rows ?? []).filter((r) =>
    (!typeId || r.type_id === Number(typeId)) &&
    (!q || r.user_name.toLowerCase().includes(q.toLowerCase())));

  const csvHref = `/api/leaves/export.csv?from=${from}&to=${to}`;

  return (
    <div className="card stack" style={{ gap: 12 }}>
      <div className="row" style={{ gap: 10, alignItems: "flex-end" }}>
        <div style={{ width: 150 }}><label className="field-label">{t("leaves.from")}</label>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
        <div style={{ width: 150 }}><label className="field-label">{t("leaves.to")}</label>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></div>
        <div style={{ width: 160 }}><label className="field-label">{t("leaves.type")}</label>
          <select value={typeId} onChange={(e) => setTypeId(e.target.value)}>
            <option value="">{t("leaves.all")}</option>
            {types.map((tp) => <option key={tp.id} value={tp.id}>{leaveTypeLabel(tp.label, lang)}</option>)}
          </select></div>
        <div style={{ width: 160 }}><label className="field-label">{t("leaves.status_label")}</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("leaves.all")}</option>
            {(["pending", "approved", "rejected"] as LeaveStatus[]).map((s) =>
              <option key={s} value={s}>{t(`leaves.status.${s}`)}</option>)}
          </select></div>
        <div className="col"><label className="field-label">{t("leaves.search")}</label>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("leaves.search")} /></div>
        <a className="btn-secondary btn-sm" href={csvHref}>{t("leaves.export_csv")}</a>
      </div>

      {!rows ? <Spinner /> : filtered.length === 0 ? (
        <div className="small muted" style={{ padding: 8 }}>{t("leaves.none")}</div>
      ) : (
        <table>
          <thead><tr>
            <th>{t("leaves.person")}</th><th>{t("leaves.type")}</th><th>{t("leaves.period")}</th>
            <th>{t("leaves.days")}</th><th>{t("leaves.status_label")}</th>
          </tr></thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => onOpen(r)}>
                <td><strong>{r.user_name}</strong></td>
                <td><span className="inline" style={{ gap: 6 }}><span className="dot" style={{ background: r.type_color }} />{leaveLabel(r, lang)}</span></td>
                <td>{fmtShort(r.start_date)} → {fmtShort(r.end_date)}</td>
                <td>{r.days}</td>
                <td><span className={`badge ${STATUS_CLASS[r.status]}`}>{t(`leaves.status.${r.status}`)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---------- My absences + pending approvals for leaders ---------- */
/**
 * Personal view: the current user's own absences, plus - for leaders - a queue of
 * pending requests they are entitled to decide.
 *
 * Business logic:
 * - `mine` comes from `?mine=true`.
 * - The approvals queue fetches all pending leaves then keeps only those with
 *   `can_decide` true (backend-computed), so a non-leader simply sees an empty
 *   queue and no approvals card.
 *
 * @param onNew opens the create form; @param onOpen opens a leave's detail.
 */
function MineView({ bump, onOpen, onNew }: { bump: number; onOpen: (l: Leave) => void; onNew: () => void }) {
  const { t, lang } = useI18n();
  const [mine, setMine] = useState<Leave[] | null>(null);
  const [pending, setPending] = useState<Leave[]>([]);

  useEffect(() => {
    api.get<Leave[]>("/api/leaves?mine=true").then(setMine).catch(() => setMine([]));
    // Pending requests the current user can decide (leaders) - across their scope.
    api.get<Leave[]>("/api/leaves?status=pending").then((rows) =>
      setPending(rows.filter((r) => r.can_decide))).catch(() => setPending([]));
  }, [bump]);

  if (!mine) return <Spinner />;
  return (
    <div className="stack" style={{ gap: 16 }}>
      {pending.length > 0 && (
        <div className="card stack" style={{ gap: 8 }}>
          <h2 style={{ margin: 0 }}>{t("leaves.to_approve")} <span className="badge badge-orange">{pending.length}</span></h2>
          {pending.map((r) => (
            <div key={r.id} className="between item-row" style={{ cursor: "pointer" }} onClick={() => onOpen(r)}>
              <span className="inline" style={{ gap: 8 }}>
                <span className="dot" style={{ background: r.type_color }} />
                <strong>{r.user_name}</strong> <span className="small muted">{leaveLabel(r, lang)} · {fmtShort(r.start_date)} → {fmtShort(r.end_date)} · {r.days} {t("leaves.days_short")}</span>
              </span>
              <span className="small" style={{ color: "var(--accent)" }}>{t("leaves.review")} →</span>
            </div>
          ))}
        </div>
      )}

      <div className="card stack" style={{ gap: 10 }}>
        <div className="between"><h2 style={{ margin: 0 }}>{t("leaves.view.mine")}</h2>
          <button className="btn btn-sm" onClick={onNew}>+ {t("leaves.new")}</button></div>
        {mine.length === 0 ? <div className="small muted">{t("leaves.none_mine")}</div> : (
          <table>
            <thead><tr><th>{t("leaves.type")}</th><th>{t("leaves.period")}</th><th>{t("leaves.days")}</th><th>{t("leaves.status_label")}</th></tr></thead>
            <tbody>
              {mine.map((r) => (
                <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => onOpen(r)}>
                  <td><span className="inline" style={{ gap: 6 }}><span className="dot" style={{ background: r.type_color }} />{leaveLabel(r, lang)}</span></td>
                  <td>{fmtShort(r.start_date)} → {fmtShort(r.end_date)}</td>
                  <td>{r.days}</td>
                  <td><span className={`badge ${STATUS_CLASS[r.status]}`}>{t(`leaves.status.${r.status}`)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ---------- Create / edit form ---------- */
/**
 * Modal to create a new leave or edit an existing one.
 *
 * Business logic:
 * - Edit (`leave` provided) -> PUT; create -> POST. When filing for someone else
 *   (leaders only, `people.length > 1` and a target other than self) the target
 *   `user_id` is included in the create body.
 * - The chosen type may `requires_detail`; when so, a detail field appears and is
 *   mandatory (Save stays disabled until filled).
 * - Half-day flags apply to the start/end days. Picking a start after the current
 *   end auto-advances the end date.
 * - When approval is required and the user files for themselves, a hint warns the
 *   request will need approval.
 *
 * @param requireApproval config flag; @param selfId the current user's id.
 */
function LeaveForm({ leave, types, people, requireApproval, selfId, onClose, onSaved }: {
  leave: Leave | null; types: LeaveType[]; people: { user_id: number; name: string }[];
  requireApproval: boolean; selfId?: number; onClose: () => void; onSaved: () => void;
}) {
  const { t, lang } = useI18n();
  const today = iso(new Date());
  const [typeId, setTypeId] = useState<number>(leave?.type_id ?? types[0]?.id ?? 0);
  const [userId, setUserId] = useState<number>(leave?.user_id ?? selfId ?? 0);
  const [start, setStart] = useState(leave?.start_date ?? today);
  const [end, setEnd] = useState(leave?.end_date ?? today);
  const [startHalf, setStartHalf] = useState(!!leave?.start_half);
  const [endHalf, setEndHalf] = useState(!!leave?.end_half);
  const [comment, setComment] = useState(leave?.comment ?? "");
  const [detail, setDetail] = useState(leave?.detail ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Whether the currently selected type forces a free-text detail (e.g. "other").
  const needsDetail = !!types.find((tp) => tp.id === typeId)?.requires_detail;

  async function save() {
    setBusy(true); setErr(null);
    const body: any = { type_id: typeId, start_date: start, end_date: end, start_half: startHalf, end_half: endHalf,
                        detail: needsDetail ? detail.trim() : null, comment: comment || null };
    try {
      if (leave) {
        await api.put(`/api/leaves/${leave.id}`, body);
      } else {
        // Only attach a target user when a leader is filing for someone else.
        if (people.length > 1 && userId && userId !== selfId) body.user_id = userId;
        await api.post("/api/leaves", body);
      }
      onSaved();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Erreur"); } finally { setBusy(false); }
  }

  // Filing on behalf of another person skips the "will need approval" self-hint.
  const filingForOther = !leave && people.length > 1 && userId !== selfId;
  return (
    <Modal title={leave ? t("leaves.edit") : t("leaves.new")} onClose={onClose} width={480}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
        <button className="btn" disabled={busy || !typeId || (needsDetail && !detail.trim())} onClick={save}>{busy ? "…" : t("action.save")}</button>
      </>}>
      <div className="stack" style={{ gap: 12 }}>
        {!leave && people.length > 1 && (
          <div><label className="field-label">{t("leaves.person")}</label>
            <select value={userId} onChange={(e) => setUserId(Number(e.target.value))}>
              {people.map((p) => <option key={p.user_id} value={p.user_id}>{p.name}</option>)}
            </select></div>
        )}
        <div><label className="field-label">{t("leaves.type")}</label>
          <select value={typeId} onChange={(e) => setTypeId(Number(e.target.value))}>
            {types.map((tp) => <option key={tp.id} value={tp.id}>{leaveTypeLabel(tp.label, lang)}</option>)}
          </select></div>
        {needsDetail && (
          <div><label className="field-label">{t("leaves.detail")}</label>
            <input value={detail} onChange={(e) => setDetail(e.target.value)} placeholder={t("leaves.detail_ph")} autoFocus /></div>
        )}
        <div className="row" style={{ gap: 10 }}>
          <div className="col"><label className="field-label">{t("leaves.from")}</label>
            <input type="date" value={start} onChange={(e) => { setStart(e.target.value); if (e.target.value > end) setEnd(e.target.value); }} /></div>
          <div className="col"><label className="field-label">{t("leaves.to")}</label>
            <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} /></div>
        </div>
        <div>
          <label className="field-label">{t("leaves.half_days")}</label>
          <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
            <label className={`check-chip${startHalf ? " on" : ""}`}>
              <input type="checkbox" checked={startHalf} onChange={(e) => setStartHalf(e.target.checked)} />{t("leaves.start_half")}</label>
            <label className={`check-chip${endHalf ? " on" : ""}`}>
              <input type="checkbox" checked={endHalf} onChange={(e) => setEndHalf(e.target.checked)} />{t("leaves.end_half")}</label>
          </div>
        </div>
        <div><label className="field-label">{t("leaves.comment")} <span className="muted small">({t("leaves.comment_private")})</span></label>
          <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} /></div>
        {!leave && !filingForOther && requireApproval && (
          <div className="banner small">{t("leaves.will_need_approval")}</div>
        )}
        {err && <div className="banner banner-red small">{err}</div>}
      </div>
    </Modal>
  );
}

/* ---------- Detail + decision ---------- */
/**
 * Read-only detail of a leave, plus contextual actions gated by backend flags:
 * - `can_edit`  -> Edit / Delete buttons in the footer.
 * - `can_decide` -> an approve/reject panel with an optional decision comment
 *   (shown to leaders reviewing a pending request).
 *
 * @param onEdit    switch to the edit form for this leave.
 * @param onChanged called after a successful decision/delete so the parent reloads.
 */
function LeaveDetail({ leave, onClose, onEdit, onChanged }: {
  leave: Leave; onClose: () => void; onEdit: (l: Leave) => void; onChanged: () => void;
}) {
  const { t, lang } = useI18n();
  const [decisionComment, setDecisionComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Approve or reject the request, carrying an optional decision comment.
  async function decide(action: "approve" | "reject") {
    setBusy(true); setErr(null);
    try { await api.post(`/api/leaves/${leave.id}/decision`, { action, comment: decisionComment || null }); onChanged(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Erreur"); } finally { setBusy(false); }
  }
  // Delete the leave after an explicit confirmation.
  async function remove() {
    if (!confirm(t("leaves.delete_confirm"))) return;
    setBusy(true); setErr(null);
    try { await api.del(`/api/leaves/${leave.id}`); onChanged(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Erreur"); } finally { setBusy(false); }
  }

  return (
    <Modal title={leave.user_name} onClose={onClose} width={460}
      footer={<>
        {leave.can_edit && <button className="btn-danger btn-sm" disabled={busy} onClick={remove}>{t("action.delete")}</button>}
        {leave.can_edit && <button className="btn-secondary btn-sm" disabled={busy} onClick={() => onEdit(leave)}>{t("action.edit")}</button>}
        <button className="btn-secondary btn-sm" onClick={onClose}>{t("action.close")}</button>
      </>}>
      <div className="stack" style={{ gap: 10 }}>
        <div className="inline" style={{ gap: 8 }}>
          <span className="dot" style={{ background: leave.type_color }} />
          <strong>{leaveLabel(leave, lang)}</strong>
          <span className={`badge ${STATUS_CLASS[leave.status]}`}>{t(`leaves.status.${leave.status}`)}</span>
        </div>
        <div className="small">{fmtShort(leave.start_date)} → {fmtShort(leave.end_date)} · <strong>{leave.days} {t("leaves.days_short")}</strong>
          {(leave.start_half || leave.end_half) && <span className="muted"> · {t("leaves.has_half")}</span>}</div>
        {leave.comment && <div><div className="field-label">{t("leaves.comment")}</div><div className="small">{leave.comment}</div></div>}
        {leave.decided_by_name && (
          <div className="small muted">{t("leaves.decided_by", { name: leave.decided_by_name })}
            {leave.decision_comment ? ` - ${leave.decision_comment}` : ""}</div>
        )}

        {leave.can_decide && (
          <div className="stack" style={{ gap: 8, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <label className="field-label">{t("leaves.decision_comment")}</label>
            <textarea rows={2} value={decisionComment} onChange={(e) => setDecisionComment(e.target.value)} />
            <div className="inline" style={{ gap: 8 }}>
              <button className="btn btn-sm" disabled={busy} onClick={() => decide("approve")}>{t("leaves.approve")}</button>
              <button className="btn-danger btn-sm" disabled={busy} onClick={() => decide("reject")}>{t("leaves.reject")}</button>
            </div>
          </div>
        )}
        {err && <div className="banner banner-red small">{err}</div>}
      </div>
    </Modal>
  );
}
