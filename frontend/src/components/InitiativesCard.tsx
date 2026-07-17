import { Initiative } from "../types";
import { useI18n } from "../i18n";

/** Read-only Initiatives card (assigned to the squad by the tribe leader). Always
 *  shown - even when empty - so the exact same rendering appears at the top of the
 *  squad page and of the reporting (saisie), keeping the two views coherent. */
export function InitiativesCard({ initiatives }: { initiatives: Initiative[] }) {
  const { t } = useI18n();
  return (
    <div className="card">
      <h2>{t("nav.initiatives")}</h2>
      {initiatives.length === 0 ? (
        <div className="small muted">{t("init.empty")}</div>
      ) : (
        <table className="init-tbl">
          <thead><tr>
            <th>{t("init.h_initiative")}</th><th>{t("init.h_owner")}</th><th>{t("init.h_deadline")}</th>
          </tr></thead>
          <tbody>
            {initiatives.map((i) => (
              <tr key={i.id}>
                <td><strong>{i.title}</strong></td>
                <td>{i.owner || "-"}</td>
                <td>{i.deadline ? i.deadline.slice(0, 10) : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
