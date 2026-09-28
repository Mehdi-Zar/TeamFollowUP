// Choisir dans ce qui existe deja, ou ecrire librement quand ce n'est pas dans la liste.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";

export type PickGroup = { label?: string; options: { value: string; label: string }[] };

const OTHER = "__other__";

/**
 * One dropdown of what already exists (squads, tribes, people...), grouped, with a
 * last entry "Other (type it)" that opens a text field. Typing a name that exists
 * is not needed: the list shows it. The caller keeps two values, the picked one
 * (`picked`, an option value) and the typed one (`text`), and exactly one of them
 * is set at a time.
 *
 * Without `allowText`, it is a plain dropdown of existing items (the field only
 * accepts an existing one).
 */
export default function PickOrType({ id, groups, picked, text, onPick, onText, allowText = true,
                                    placeholder, textPlaceholder, maxLength, ariaLabel }: {
  id?: string;
  groups: PickGroup[];
  picked: string | null | undefined;
  text?: string | null;
  onPick: (value: string | null) => void;
  onText?: (text: string) => void;
  allowText?: boolean;
  placeholder?: string;
  textPlaceholder?: string;
  maxLength?: number;
  ariaLabel?: string;
}) {
  const { t } = useI18n();
  const known = new Set(groups.flatMap((g) => g.options.map((o) => o.value)));
  const hasText = !!(text ?? "").trim();
  // "Other" stays open while one types, even while the field is still empty.
  const [typing, setTyping] = useState<boolean>(allowText && !picked && hasText);
  useEffect(() => { if (picked) setTyping(false); else if (hasText) setTyping(true); }, [picked, hasText]);

  const value = picked && known.has(picked) ? picked : typing ? OTHER : "";
  return (
    <div className="stack" style={{ gap: 6 }}>
      <select id={id} aria-label={ariaLabel} value={value}
              onChange={(e) => {
                const v = e.target.value;
                if (v === OTHER) { setTyping(true); onPick(null); return; }
                setTyping(false);
                onPick(v || null);
                if (v && onText) onText("");
              }}>
        <option value="">{placeholder ?? t("pick.none")}</option>
        {groups.filter((g) => g.options.length > 0).map((g, i) => g.label ? (
          <optgroup key={i} label={g.label}>
            {g.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </optgroup>
        ) : g.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>))}
        {allowText && <option value={OTHER}>{t("pick.other")}</option>}
      </select>
      {allowText && typing && (
        <input autoFocus aria-label={ariaLabel ? `${ariaLabel} (${t("pick.other_short")})` : t("pick.other_short")}
               placeholder={textPlaceholder ?? t("pick.type_here")} maxLength={maxLength}
               value={text ?? ""} onChange={(e) => onText?.(e.target.value)} />
      )}
    </div>
  );
}
