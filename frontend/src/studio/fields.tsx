// Studio des exports: one control per parameter kind, built from the catalogue.
// A parameter is labelled by its name (studio.p.*) and its options by their value
// (studio.o.*), so a new parameter of an existing kind needs no new screen.
import { ReactNode } from "react";
import { useI18n } from "../i18n";
import { Asset, ParamSpec } from "./model";

export function ParamField({ name, spec, value, onChange, disabled, assets, assetKind, inherited, onReset }: {
  name: string; spec: ParamSpec; value: any; onChange: (v: any) => void; disabled?: boolean;
  assets?: Asset[]; assetKind?: "image" | "pptx"; inherited?: boolean; onReset?: () => void;
}) {
  const { t } = useI18n();
  const label = t(`studio.p.${name}`);
  const reset = onReset && !inherited ? (
    <button type="button" className="btn-ghost btn-xs studio-reset" onClick={onReset} title={t("studio.reset_hint")}>
      {t("studio.reset")}
    </button>
  ) : null;
  const row = (control: ReactNode, inline = false) => (
    <div className={`studio-field${inline ? " inline-field" : ""}${inherited === false ? " overridden" : ""}`}>
      {!inline && <label className="field-label between"><span>{label}</span>{reset}</label>}
      {control}
      {inline && reset}
    </div>
  );
  switch (spec.kind) {
    case "bool":
      return row(
        <label className="inline small" style={{ gap: 6 }}>
          <input type="checkbox" checked={!!value} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
          {label}
        </label>, true);
    case "int":
      return row(
        <input type="number" value={value ?? ""} min={spec.min} max={spec.max} disabled={disabled}
               onChange={(e) => onChange(e.target.value === "" ? spec.default : Number(e.target.value))} />);
    case "enum":
      return row(
        <select value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          {(spec.options || []).map((o) => <option key={o} value={o}>{t(`studio.o.${o}`)}</option>)}
        </select>);
    case "multi": {
      const cur: string[] = Array.isArray(value) ? value : [];
      const move = (o: string, d: number) => {
        const i = cur.indexOf(o);
        const j = i + d;
        if (i < 0 || j < 0 || j >= cur.length) return;
        const n = [...cur]; [n[i], n[j]] = [n[j], n[i]]; onChange(n);
      };
      const ordered = [...cur, ...(spec.options || []).filter((o) => !cur.includes(o))];
      return row(
        <div className="studio-multi">
          {ordered.map((o) => (
            <div key={o} className="studio-multi-row">
              <label className="inline small" style={{ gap: 6, flex: 1 }}>
                <input type="checkbox" checked={cur.includes(o)} disabled={disabled}
                       onChange={(e) => onChange(e.target.checked ? [...cur, o] : cur.filter((x) => x !== o))} />
                {t(`studio.o.${o}`)}
              </label>
              {cur.includes(o) && !disabled && (
                <span className="inline" style={{ gap: 2 }}>
                  <button type="button" className="btn-ghost btn-xs" aria-label={t("studio.up")} onClick={() => move(o, -1)}>↑</button>
                  <button type="button" className="btn-ghost btn-xs" aria-label={t("studio.down")} onClick={() => move(o, 1)}>↓</button>
                </span>
              )}
            </div>
          ))}
        </div>);
    }
    case "text":
      return row(<input type="text" value={value ?? ""} maxLength={spec.max} disabled={disabled}
                        onChange={(e) => onChange(e.target.value)} />);
    case "longtext":
      return row(<textarea rows={5} value={value ?? ""} maxLength={spec.max} disabled={disabled}
                           onChange={(e) => onChange(e.target.value)} />);
    case "color":
      return row(
        <span className="inline" style={{ gap: 8 }}>
          <input type="color" value={value || "#1E2761"} disabled={disabled} onChange={(e) => onChange(e.target.value.toUpperCase())}
                 style={{ width: 44, padding: 2 }} />
          <span className="small muted">{value || t("studio.color_default")}</span>
          {value && !disabled && <button type="button" className="btn-ghost btn-xs" onClick={() => onChange("")}>{t("studio.clear")}</button>}
        </span>);
    case "asset": {
      const list = (assets || []).filter((a) => !assetKind || a.kind === assetKind);
      return row(
        <select value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
          <option value="">{t("studio.no_file")}</option>
          {list.map((a) => <option key={a.id} value={a.id}>{a.filename}</option>)}
        </select>);
    }
    default:
      return null;
  }
}

/** Which kind of file an asset parameter takes. */
export const assetKindOf = (sectionType: string, param: string): "image" | "pptx" =>
  sectionType === "imported" && param === "asset" ? "pptx" : "image";
