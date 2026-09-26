// La barre de lecture d'une liste: rechercher, trier, choisir cartes ou liste.
//
// Le tableau de bord l'avait, la consolidation steerco et les initiatives non, et
// les trois montrent la meme chose: une collection d'objets qu'on parcourt. Trois
// ecrans qui se ressemblent doivent se piloter pareil, sinon chacun s'invente sa
// convention et l'utilisateur reapprend a chaque onglet.
//
// Le tri, son sens et la densite sont des preferences de lecture: elles vivent
// dans le navigateur de celui qui regarde, sous une cle par ecran, et ne
// traversent jamais le reseau.
import { ReactNode, useEffect, useState } from "react";
import { useI18n } from "../i18n";

/** Un critere de tri: sa cle, son libelle, et la comparaison dans son sens naturel. */
export type SortSpec<T> = { key: string; label: string; cmp: (a: T, b: T) => number };

export type ListView = {
  query: string;
  setQuery: (v: string) => void;
  sort: string;
  desc: boolean;
  pickSort: (k: string) => void;
  dense: boolean;
  setDense: (v: boolean) => void;
  /** Vrai des qu'une recherche, un tri ou une vue s'ecarte de la valeur d'origine. */
  touched: boolean;
  reset: () => void;
};

function readPref(key: string, fallback: string): string {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}

function writePref(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* stockage refuse: tant pis */ }
}

/**
 * L'etat de lecture d'une liste, retenu d'une visite a l'autre.
 *
 * `denseByDefault` existe parce que la bonne vue depend de ce qu'on regarde: des
 * squads se lisent en cartes, une table d'initiatives se lit en lignes.
 */
export function useListView(storageKey: string, defaultSort: string,
                            denseByDefault = false): ListView {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState(() => readPref(`${storageKey}.sort`, defaultSort));
  const [desc, setDesc] = useState(() => readPref(`${storageKey}.desc`, "") === "1");
  const [dense, setDense] = useState(
    () => readPref(`${storageKey}.dense`, denseByDefault ? "1" : "") === "1");

  useEffect(() => { writePref(`${storageKey}.sort`, sort); }, [storageKey, sort]);
  useEffect(() => { writePref(`${storageKey}.desc`, desc ? "1" : ""); }, [storageKey, desc]);
  useEffect(() => { writePref(`${storageKey}.dense`, dense ? "1" : ""); }, [storageKey, dense]);

  // Choisir un critere le pose dans son sens naturel; le rechoisir retourne le sens.
  const pickSort = (k: string) => {
    if (k === sort) { setDesc((v) => !v); return; }
    setSort(k);
    setDesc(false);
  };

  return {
    query, setQuery, sort, desc, pickSort, dense, setDense,
    touched: !!query || sort !== defaultSort || desc || dense !== denseByDefault,
    reset: () => { setQuery(""); setSort(defaultSort); setDesc(false); setDense(denseByDefault); },
  };
}

/** Filtre puis trie une collection selon l'etat de lecture. */
export function applyListView<T>(rows: T[], view: ListView, sorts: SortSpec<T>[],
                                 matches: (row: T, needle: string) => boolean): T[] {
  const needle = view.query.trim().toLowerCase();
  let out = needle ? rows.filter((r) => matches(r, needle)) : [...rows];
  const spec = sorts.find((s) => s.key === view.sort) ?? sorts[0];
  if (spec) {
    out = [...out].sort(spec.cmp);
    if (view.desc) out.reverse();
  }
  return out;
}

/** Le champ de recherche, a placer avec les filtres propres a chaque ecran. */
export function ListSearch({ view, id }: { view: ListView; id: string }) {
  const { t } = useI18n();
  return (
    <div style={{ width: 200 }}>
      <label htmlFor={id}>{t("list.search")}</label>
      <input id={id} value={view.query} placeholder={t("list.search")}
             onChange={(e) => view.setQuery(e.target.value)} />
    </div>
  );
}

/**
 * Les commandes d'affichage: le tri, la vue, et la remise a zero.
 *
 * A droite, a l'ecart des filtres: chercher et filtrer reduit ce qu'on voit,
 * trier et changer de vue ne fait que le reordonner. `left` recoit ce que
 * l'ecran veut poser en vis-a-vis, une legende par exemple.
 */
export function ListControls<T>({ view, sorts, left, right, views = true,
                                 extraTouched, onResetExtra }: {
  view: ListView;
  sorts: SortSpec<T>[];
  left?: ReactNode;
  /** Ce que l'ecran veut poser juste avant la remise a zero (un choix de squads). */
  right?: ReactNode;
  /** Faux quand cartes et liste n'ont pas de sens: une matrice est deja une vue. */
  views?: boolean;
  /** Filtres propres a l'ecran, pour que « reinitialiser » les emporte aussi. */
  extraTouched?: boolean;
  onResetExtra?: () => void;
}) {
  const { t } = useI18n();
  const touched = view.touched || !!extraTouched;
  return (
    <div className="between" style={{ gap: 16, flexWrap: "wrap", alignItems: "center" }}>
      <div>{left}</div>
      <div className="inline" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <span className="small muted">{t("list.sort")}</span>
        <span className="seg">
          {sorts.map((s) => (
            <button key={s.key} className={s.key === view.sort ? "seg-on" : ""} aria-pressed={s.key === view.sort}
                    onClick={() => view.pickSort(s.key)}
                    title={s.key === view.sort ? t("list.sort_flip") : undefined}>
              {s.label}{s.key === view.sort ? (view.desc ? " ↓" : " ↑") : ""}
            </button>
          ))}
        </span>
        {views && (
          <span className="seg">
            <button className={view.dense ? "" : "seg-on"} aria-pressed={!view.dense} onClick={() => view.setDense(false)}>
              {t("list.view_cards")}
            </button>
            <button className={view.dense ? "seg-on" : ""} aria-pressed={view.dense} onClick={() => view.setDense(true)}>
              {t("list.view_list")}
            </button>
          </span>
        )}
        {right}
        {touched && (
          <button className="btn-ghost btn-sm"
                  onClick={() => { view.reset(); onResetExtra?.(); }}>{t("list.reset")}</button>
        )}
      </div>
    </div>
  );
}
