// Le role d'un membre: un de la liste reglee dans l'administration, ou un autre
// ecrit librement. Une liste plutot qu'un champ libre, pour que « Tech Lead »,
// « tech lead » et « TL » ne fassent pas trois roles.
import { useEffect, useState } from "react";
import { useConfig } from "../config";
import { useI18n } from "../i18n";
import PickOrType from "./PickOrType";

/** Total time on the squad in full-time equivalents, "2,5" or "2.5". */
export function fte(members: { allocation_pct?: number }[], lang: string): string {
  const n = members.reduce((s, m) => s + (m.allocation_pct ?? 100), 0) / 100;
  return n.toLocaleString(lang === "en" ? "en-GB" : "fr-FR", { maximumFractionDigits: 1 });
}

/**
 * The role list plus "Other (type it)". `onCommit` receives the role when it is
 * picked, or the typed one when the field is left; the caller saves it.
 */
export default function RolePicker({ value, onCommit, ariaLabel }: {
  value: string | null | undefined; onCommit: (role: string | null) => void; ariaLabel?: string;
}) {
  const { t } = useI18n();
  const roles = useConfig().member_roles ?? [];
  // A role that is not (or no longer) in the list shows as typed, never lost.
  const inList = (v: string) => roles.includes(v);
  const [picked, setPicked] = useState<string | null>(value && inList(value) ? value : null);
  const [text, setText] = useState(value && !inList(value) ? value : "");
  useEffect(() => {
    setPicked(value && inList(value) ? value : null);
    setText(value && !inList(value) ? value : "");
  }, [value, roles.join("|")]);
  return (
    <div onBlur={(e) => {
      // Leaving the typed field commits it; moving to the dropdown does not.
      if (e.target.tagName === "INPUT" && (text.trim() || null) !== (value ?? null) && !picked) onCommit(text.trim() || null);
    }}>
      <PickOrType ariaLabel={ariaLabel} placeholder={t("team.role_none")} maxLength={255}
                  groups={[{ options: roles.map((r) => ({ value: r, label: r })) }]}
                  picked={picked} text={text}
                  onPick={(v) => { setPicked(v); if (v !== null) { setText(""); onCommit(v); } }}
                  onClear={() => { setText(""); if (value) onCommit(null); }}
                  onText={setText} />
    </div>
  );
}
