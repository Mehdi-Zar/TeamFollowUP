// InitiativesCard: read-only table of the initiatives a tribe leader assigned to a
// squad. Rendered identically on the squad page and the reporting (saisie) screen
// so both stay in sync; always shown, with an explicit empty state.
import { Link } from "react-router-dom";
import { Initiative } from "../types";
import { useI18n } from "../i18n";
import { Collapsible } from "./ui";

/** Read-only Initiatives card (assigned to the squad by the tribe leader). Always
 *  shown - even when empty - so the exact same rendering appears at the top of the
 *  squad page and of the reporting (saisie), keeping the two views coherent. */
export function InitiativesCard({ initiatives, editTo, editLabel }: {
  initiatives: Initiative[]; editTo?: string; editLabel?: string;
}) {
  const { t, formatDate } = useI18n();
  return (
    <Collapsible title={t("nav.initiatives")} defaultOpen
                 subtitle={t("init.collapsed_hint", { n: initiatives.length })}
                 right={editTo ? <Link to={editTo} className="small">{editLabel}</Link> : undefined}>
      {initiatives.length === 0 ? (
        <div className="small muted">{t("init.empty_here")}</div>
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
                <td>{i.deadline ? formatDate(i.deadline) : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Collapsible>
  );
}
