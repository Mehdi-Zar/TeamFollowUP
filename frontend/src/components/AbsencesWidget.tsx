// AbsencesWidget: dashboard card listing the people on leave during the current
// week. Reads the leaves module + the persona's "leaves" capability to decide
// whether to render at all, then fetches this Monday→Sunday window from the API.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useModule } from "../config";
import { useAuth } from "../auth";
import { Leave } from "../types";
import { leaveLabel } from "../leaves";

// Local date helpers kept minimal to avoid pulling a date library into the bundle.
/** Zero-pad a number to two digits (e.g. 3 → "03"). */
const pad = (n: number) => String(n).padStart(2, "0");
/** Format a Date as a local `YYYY-MM-DD` string (avoids UTC shift of toISOString). */
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
/** Return a new Date offset by `n` days (does not mutate the input). */
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
/** Turn an ISO `YYYY-MM-DD` into a compact `DD/MM` label for the badge tooltip. */
const fmtShort = (s: string) => { const [, m, d] = s.split("-"); return `${d}/${m}`; };

/** Dashboard card: "who is away this week". Hidden when the leaves module is off
 *  or the persona lacks the capability. Visible to everyone otherwise. */
export default function AbsencesWidget() {
  const { t, lang } = useI18n();
  const on = useModule()("leaves");
  const { can } = useAuth();
  const [rows, setRows] = useState<Leave[] | null>(null);

  // Current ISO week: Monday..Sunday. getDay() is 0=Sun, so (day+6)%7 gives the
  // number of days to step back to reach this week's Monday.
  const today = new Date();
  const monday = addDays(today, -((today.getDay() + 6) % 7));
  const sunday = addDays(monday, 6);

  useEffect(() => {
    if (!on) return;
    api.get<Leave[]>(`/api/leaves?from=${iso(monday)}&to=${iso(sunday)}`)
      .then((r) => setRows(r.filter((x) => x.status === "approved" || x.status === "pending")))
      .catch(() => setRows([]));
  }, [on]);

  if (!on || !can("leaves") || !rows) return null;

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between">
        <h2 style={{ margin: 0 }}>{t("leaves.widget_title")}</h2>
        <Link to="/conges" className="small" style={{ color: "var(--accent)" }}>{t("leaves.view.calendar")} →</Link>
      </div>
      {rows.length === 0 ? (
        <div className="small muted">{t("leaves.widget_none")}</div>
      ) : (
        <div className="inline" style={{ flexWrap: "wrap", gap: 8 }}>
          {rows.map((r) => (
            <Link key={r.id} to="/conges" className="badge"
              style={{ background: r.type_color, color: "#fff", textDecoration: "none" }}
              title={`${leaveLabel(r, lang)}, ${fmtShort(r.start_date)} → ${fmtShort(r.end_date)}`}>
              {r.user_name}
              {r.status === "pending" ? " •" : ""}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
