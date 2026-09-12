// Administration > Personnalisation.
//
// L'apparence de l'application se regle ici, et nulle part ailleurs: couleurs,
// logos, typographie, densite, plus le nom et le sous-titre qui vivaient deja
// dans les reglages generaux. Chacun reste stocke chez lui (un nom d'application
// n'est pas une couleur), l'ecran se contente de les rassembler la ou on les
// cherche.
//
// L'apercu est applique en direct sur la page reelle, pas dans une vignette: une
// palette se juge sur les vraies cartes, les vrais badges et le vrai contraste.
// Quitter sans enregistrer remet ce que le serveur avait publie.
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api";
import { useI18n } from "../../i18n";
import { useReloadConfig } from "../../config";
import { ErrorBanner, Spinner } from "../../components/ui";

type Branding = Record<string, any>;

// Le libelle de chaque couleur et la variable CSS qu'elle pilote. Le serveur est
// l'autorite sur la liste (app/branding.py), celle-ci n'est que son affichage.
const COLORS: { key: string; label: string }[] = [
  { key: "navy", label: "brand.color_navy" },
  { key: "navy_deep", label: "brand.color_navy_deep" },
  { key: "accent", label: "brand.color_accent" },
  { key: "ice_blue", label: "brand.color_ice" },
  { key: "ice_soft", label: "brand.color_ice_soft" },
  { key: "green", label: "brand.color_green" },
  { key: "orange", label: "brand.color_orange" },
  { key: "red", label: "brand.color_red" },
  { key: "text", label: "brand.color_text" },
  { key: "grey", label: "brand.color_grey" },
  { key: "line", label: "brand.color_line" },
  { key: "bg", label: "brand.color_bg" },
];

const IMAGES: { key: string; label: string; hint: string }[] = [
  { key: "logo", label: "brand.logo", hint: "brand.logo_hint" },
  { key: "favicon", label: "brand.favicon", hint: "brand.favicon_hint" },
  { key: "login_background", label: "brand.login_bg", hint: "brand.login_bg_hint" },
  { key: "document_logo", label: "brand.doc_logo", hint: "brand.doc_logo_hint" },
];

// Des palettes pretes a l'emploi. Pas un theme de plus a maintenir: juste les
// memes champs, pre-remplis, parce que choisir douze couleurs qui vont ensemble
// est un metier et que la plupart des gens veulent surtout autre chose que le
// bleu par defaut.
const PRESETS: Record<string, Partial<Branding>> = {
  default: {},
  slate: { navy: "#0F172A", navy_deep: "#020617", accent: "#2563EB", ice_blue: "#CBD5E1",
           ice_soft: "#F1F5F9", bg: "#F8FAFC", line: "#E2E8F0" },
  forest: { navy: "#14532D", navy_deep: "#0B3A1F", accent: "#15803D", ice_blue: "#BBF7D0",
            ice_soft: "#DCFCE7", bg: "#F6FBF7", line: "#DCE7DE" },
  plum: { navy: "#3B0764", navy_deep: "#2A0247", accent: "#7E22CE", ice_blue: "#E9D5FF",
          ice_soft: "#F5EBFF", bg: "#FAF7FD", line: "#E7DDF0" },
  graphite: { navy: "#1F2937", navy_deep: "#111827", accent: "#4B5563", ice_blue: "#D1D5DB",
              ice_soft: "#F3F4F6", bg: "#F9FAFB", line: "#E5E7EB" },
};

/** Administration > Personnalisation. Admin uniquement. */
export function BrandingAdmin() {
  const { t } = useI18n();
  const reloadConfig = useReloadConfig();
  const [cfg, setCfg] = useState<Branding | null>(null);
  const [general, setGeneral] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const initial = useRef<Branding | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<Branding>("/api/admin/branding"),
      api.get<any>("/api/admin/settings"),
    ]).then(([b, g]) => {
      initial.current = b;
      setCfg(b);
      setGeneral(g);
    }).catch((e) => setErr(e instanceof ApiError ? e.message : "Erreur"));
    // Quitter l'ecran sans enregistrer doit rendre l'apparence publiee.
    return () => { reloadConfig(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Apercu en direct: les memes variables que celles que le serveur publiera.
  useEffect(() => {
    if (!cfg) return;
    const root = document.documentElement;
    const css: Record<string, string> = {
      "--navy": cfg.navy, "--navy-deep": cfg.navy_deep, "--accent": cfg.accent,
      "--ice-blue": cfg.ice_blue, "--ice-soft": cfg.ice_soft, "--green": cfg.green,
      "--orange": cfg.orange, "--red": cfg.red, "--text": cfg.text, "--grey": cfg.grey,
      "--line": cfg.line, "--bg": cfg.bg,
      "--radius": `${cfg.radius}px`, "--font-scale": String((cfg.font_scale ?? 100) / 100),
    };
    for (const [k, v] of Object.entries(css)) if (v) root.style.setProperty(k, v);
    root.dataset.density = cfg.density ?? "comfortable";
  }, [cfg]);

  if (err && !cfg) return <ErrorBanner message={err} />;
  if (!cfg || !general) return <Spinner />;

  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });

  const onImage = (key: string, file?: File) => {
    if (!file) return;
    if (file.size > 300 * 1024) { window.alert(t("brand.image_too_big")); return; }
    const reader = new FileReader();
    reader.onload = () => set(key, String(reader.result || ""));
    reader.readAsDataURL(file);
  };

  async function save() {
    setErr(null);
    try {
      const out = await api.put<Branding>("/api/admin/branding", cfg);
      await api.put("/api/admin/settings",
                    { app_name: general.app_name, app_subtitle: general.app_subtitle });
      initial.current = out;
      setCfg(out);
      reloadConfig();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Erreur");
    }
  }

  async function reset() {
    if (!window.confirm(t("brand.reset_confirm"))) return;
    const out = await api.put<Branding>("/api/admin/branding", { reset: true });
    initial.current = out;
    setCfg(out);
    reloadConfig();
  }

  return (
    <div className="stack" style={{ gap: 16 }}>
      {err && <ErrorBanner message={err} />}

      <div className="card stack" style={{ gap: 12 }}>
        <div className="between" style={{ alignItems: "center" }}>
          <div>
            <h2 style={{ margin: 0 }}>{t("brand.title")}</h2>
            <div className="small muted">{t("brand.hint")}</div>
          </div>
          <div className="inline" style={{ gap: 8 }}>
            {saved && <span className="small" style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
            <button className="btn-ghost btn-sm" onClick={reset}>{t("brand.reset")}</button>
            <button className="btn-sm" onClick={save}>{t("action.save")}</button>
          </div>
        </div>
        <div className="small muted">{t("brand.preview_note")}</div>
      </div>

      {/* ---- Identite ---- */}
      <div className="card stack" style={{ gap: 12 }}>
        <h3 style={{ margin: 0 }}>{t("brand.identity")}</h3>
        <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label htmlFor="brand-name">{t("set.app_name")}</label>
            <input id="brand-name" value={general.app_name ?? ""}
                   onChange={(e) => setGeneral({ ...general, app_name: e.target.value })} />
          </div>
          <div style={{ flex: 2, minWidth: 220 }}>
            <label htmlFor="brand-sub">{t("set.app_subtitle")}</label>
            <input id="brand-sub" value={general.app_subtitle ?? ""}
                   onChange={(e) => setGeneral({ ...general, app_subtitle: e.target.value })} />
          </div>
        </div>
        <div className="row" style={{ gap: 16, flexWrap: "wrap" }}>
          {IMAGES.map((img) => (
            <div key={img.key} style={{ flex: 1, minWidth: 220 }}>
              <label>{t(img.label)}</label>
              <div className="small muted" style={{ marginBottom: 4 }}>{t(img.hint)}</div>
              <div className="inline" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                {cfg[img.key] ? (
                  <img src={cfg[img.key]} alt="" style={{ height: 28, maxWidth: 120, objectFit: "contain",
                                                          background: "var(--ice-soft)", borderRadius: 6 }} />
                ) : <span className="small muted">{t("brand.none")}</span>}
                <label className="btn-secondary btn-sm" style={{ cursor: "pointer" }}>
                  {t("brand.choose_file")}
                  <input type="file" accept="image/*" style={{ display: "none" }}
                         onChange={(e) => { onImage(img.key, e.target.files?.[0]); e.target.value = ""; }} />
                </label>
                {cfg[img.key] && (
                  <button className="btn-ghost btn-sm" onClick={() => set(img.key, "")}>
                    {t("action.delete")}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ---- Couleurs ---- */}
      <div className="card stack" style={{ gap: 12 }}>
        <div className="between" style={{ alignItems: "center" }}>
          <div>
            <h3 style={{ margin: 0 }}>{t("brand.colors")}</h3>
            <div className="small muted">{t("brand.colors_hint")}</div>
          </div>
          <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
            {Object.keys(PRESETS).map((name) => (
              <button key={name} className="btn-secondary btn-sm"
                      onClick={() => setCfg({ ...cfg, ...PRESETS[name] })}>
                {t(`brand.preset_${name}`)}
              </button>
            ))}
          </div>
        </div>
        <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
          {COLORS.map((c) => (
            <div key={c.key} style={{ width: 150 }}>
              <label htmlFor={`color-${c.key}`}>{t(c.label)}</label>
              <div className="inline" style={{ gap: 6 }}>
                <input id={`color-${c.key}`} type="color" style={{ width: 42, padding: 2 }}
                       value={cfg[c.key]} onChange={(e) => set(c.key, e.target.value)} />
                <input aria-label={t(c.label)} style={{ width: 90 }} value={cfg[c.key]}
                       onChange={(e) => set(c.key, e.target.value)} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ---- Typographie et mise en page ---- */}
      <div className="card stack" style={{ gap: 12 }}>
        <h3 style={{ margin: 0 }}>{t("brand.layout")}</h3>
        <div className="row" style={{ gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ width: 200 }}>
            <label htmlFor="brand-font">{t("brand.font")}</label>
            <select id="brand-font" value={cfg.font} onChange={(e) => set("font", e.target.value)}>
              {["system", "grotesque", "serif", "mono"].map((f) => (
                <option key={f} value={f}>{t(`brand.font_${f}`)}</option>
              ))}
            </select>
          </div>
          <div style={{ width: 180 }}>
            <label htmlFor="brand-scale">{t("brand.font_scale", { n: String(cfg.font_scale) })}</label>
            <input id="brand-scale" type="range" min={85} max={125} step={5} value={cfg.font_scale}
                   onChange={(e) => set("font_scale", Number(e.target.value))} />
          </div>
          <div style={{ width: 180 }}>
            <label htmlFor="brand-radius">{t("brand.radius", { n: String(cfg.radius) })}</label>
            <input id="brand-radius" type="range" min={0} max={24} step={1} value={cfg.radius}
                   onChange={(e) => set("radius", Number(e.target.value))} />
          </div>
          <div style={{ width: 190 }}>
            <label htmlFor="brand-density">{t("brand.density")}</label>
            <select id="brand-density" value={cfg.density} onChange={(e) => set("density", e.target.value)}>
              <option value="comfortable">{t("brand.density_comfortable")}</option>
              <option value="compact">{t("brand.density_compact")}</option>
            </select>
          </div>
          <label className="switch">
            <input type="checkbox" checked={!!cfg.shadows} onChange={(e) => set("shadows", e.target.checked)} />
            <span className="track"><span className="knob" /></span>
            <span className="small">{t("brand.shadows")}</span>
          </label>
        </div>

        {/* Un echantillon des composants reels, pour juger sur pieces. */}
        <div className="card" style={{ background: "var(--bg)" }}>
          <div className="inline" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <button className="btn-sm">{t("brand.sample_primary")}</button>
            <button className="btn-secondary btn-sm">{t("brand.sample_secondary")}</button>
            <span className="badge badge-green">{t("brand.sample_ok")}</span>
            <span className="badge badge-orange">{t("brand.sample_warn")}</span>
            <span className="badge badge-red">{t("brand.sample_late")}</span>
            <span className="badge badge-navy">{t("brand.sample_tag")}</span>
          </div>
          <div className="small muted" style={{ marginTop: 8 }}>{t("brand.sample_text")}</div>
        </div>
      </div>

      {/* ---- Emails et documents ---- */}
      <div className="card stack" style={{ gap: 10 }}>
        <h3 style={{ margin: 0 }}>{t("brand.documents")}</h3>
        <div>
          <label htmlFor="brand-footer">{t("brand.email_footer")}</label>
          <div className="small muted" style={{ marginBottom: 4 }}>{t("brand.email_footer_hint")}</div>
          <input id="brand-footer" value={cfg.email_footer ?? ""} placeholder={t("brand.email_footer_ph")}
                 onChange={(e) => set("email_footer", e.target.value)} />
        </div>
        <div className="small muted">{t("brand.pptx_note")}</div>
      </div>
    </div>
  );
}
