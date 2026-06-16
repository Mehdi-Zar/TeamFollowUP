import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { TribeOrg } from "../types";
import { Spinner, ErrorBanner } from "../components/ui";

/** Admin overview of all tribes. Selecting a tribe opens the main Org chart
 *  page, pre-selected on that tribe (no separate embedded view). */
export default function TribesPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [tribes, setTribes] = useState<TribeOrg[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<TribeOrg[]>("/api/tribes/org-overview").then(setTribes).catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorBanner message={error} />;
  if (!tribes) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="muted small">{t("tribes.sub")}</div>
      <div className="squad-grid-2">
        {tribes.map((tr) => (
          <button
            key={tr.tribe_id}
            className="squad-card squad-card-lg s-green"
            onClick={() => navigate(`/organigramme?tribe=${tr.tribe_id}`)}
          >
            <div className="strong sc-name" style={{ color: "var(--navy)" }}>{tr.tribe_name}</div>
            <div className="muted small" style={{ marginTop: 6 }}>
              {tr.squads_count} {t("tribes.squads")} · {t("tribes.open_org")}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
