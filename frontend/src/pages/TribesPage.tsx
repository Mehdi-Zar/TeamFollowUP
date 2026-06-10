import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { OrgNode, TribeOrg } from "../types";
import { Spinner, ErrorBanner } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";

function ReadNode({ node }: { node: OrgNode }) {
  const { t } = useI18n();
  return (
    <div className="org-subtree">
      <div className="org-box org-node">
        <div className="strong small">{node.title}</div>
        {node.person_name && <div className="small muted">{node.person_name}</div>}
        {node.squad_id && (
          <Link className="small" to={`/squads/${node.squad_id}`}>
            {t("org.see_squad")}
          </Link>
        )}
      </div>
      {node.children.length > 0 && (
        <>
          <div className="org-connector" />
          <div className="org-children">
            {node.children.map((c) => (
              <ReadNode key={c.id} node={c} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function TribesPage() {
  const { t } = useI18n();
  const [tribes, setTribes] = useState<TribeOrg[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    api.get<TribeOrg[]>("/api/tribes/org-overview").then(setTribes).catch((e) => setError(e.message));
  }, []);

  const detailTitle =
    tribes && selected != null ? tribes.find((tr) => tr.tribe_id === selected)?.tribe_name : undefined;
  useSetPageChrome({ title: detailTitle }, [detailTitle]);

  if (error) return <ErrorBanner message={error} />;
  if (!tribes) return <Spinner />;

  const current = selected != null ? tribes.find((tr) => tr.tribe_id === selected) : null;

  if (current) {
    return (
      <div className="stack" style={{ gap: 18 }}>
        <div>
          <button className="btn-ghost btn-sm" onClick={() => setSelected(null)}>
            {t("tribes.back")}
          </button>
          <div className="muted small" style={{ marginTop: 8 }}>{current.squads_count} {t("tribes.squads")}</div>
        </div>
        {current.tree.length === 0 ? (
          <div className="card muted">{t("tribes.empty")}</div>
        ) : (
          <div className="card" style={{ overflowX: "auto" }}>
            <div className="row" style={{ justifyContent: "center", alignItems: "flex-start", gap: 24 }}>
              {current.tree.map((n) => (
                <ReadNode key={n.id} node={n} />
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="muted small">{t("tribes.sub")}</div>
      <div className="squad-grid-2">
        {tribes.map((tr) => (
          <button key={tr.tribe_id} className="squad-card squad-card-lg s-green" onClick={() => setSelected(tr.tribe_id)}>
            <div className="strong sc-name" style={{ color: "var(--navy)" }}>{tr.tribe_name}</div>
            <div className="muted small" style={{ marginTop: 6 }}>{tr.squads_count} {t("tribes.squads")}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
