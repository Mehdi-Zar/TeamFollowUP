// Every data table sorts and filters the same way: a search box above it, and a
// click on a column header to sort by that column (a second click reverses the
// order). The sort is remembered per table in the browser; the search is not.
//
// A table opts in with three lines: useTableView over its rows and columns, the
// TableSearch box, and SortTh in place of each <th>. The rows it renders are the
// hook's `rows`, already filtered and sorted.
import { ReactNode, useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";

/** A sortable, searchable column: what to compare, and what the search reads. */
export type Col<T> = {
  key: string;
  /** The value sorted on: a number sorts as a number, a string as text. */
  value: (row: T) => string | number | null | undefined;
  /** The text the search looks into (defaults to the sort value). */
  text?: (row: T) => string | null | undefined;
};

export type TableView<T> = {
  rows: T[];
  total: number;
  query: string;
  setQuery: (q: string) => void;
  sort: string | null;
  desc: boolean;
  toggle: (key: string) => void;
  reset: () => void;
  touched: boolean;
};

function read(k: string): string | null {
  try { return localStorage.getItem(k); } catch { return null; }
}
function write(k: string, v: string | null): void {
  try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* blocked */ }
}

export function useTableView<T>(storageKey: string, rows: T[], cols: Col<T>[],
                                defaultSort: string | null = null): TableView<T> {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<string | null>(() => read(`${storageKey}.sort`) ?? defaultSort);
  const [desc, setDesc] = useState(() => read(`${storageKey}.desc`) === "1");
  useEffect(() => { write(`${storageKey}.sort`, sort); }, [storageKey, sort]);
  useEffect(() => { write(`${storageKey}.desc`, desc ? "1" : null); }, [storageKey, desc]);

  const out = useMemo(() => {
    const needle = query.trim().toLowerCase();
    let r = needle
      ? rows.filter((row) => cols.some((c) => String((c.text ?? c.value)(row) ?? "").toLowerCase().includes(needle)))
      : [...rows];
    const col = cols.find((c) => c.key === sort);
    if (col) {
      r = [...r].sort((a, b) => {
        const x = col.value(a), y = col.value(b);
        if (x === y) return 0;
        if (x === null || x === undefined || x === "") return 1;     // blanks last, either way
        if (y === null || y === undefined || y === "") return -1;
        const c = typeof x === "number" && typeof y === "number"
          ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: "base" });
        return desc ? -c : c;
      });
    }
    return r;
  }, [rows, cols, query, sort, desc]);

  return {
    rows: out, total: rows.length, query, setQuery, sort, desc,
    toggle: (key) => {
      if (key === sort) setDesc((d) => !d);
      else { setSort(key); setDesc(false); }
    },
    reset: () => { setQuery(""); setSort(defaultSort); setDesc(false); },
    touched: !!query || sort !== defaultSort || desc,
  };
}

/** A column header that sorts its table. */
export function SortTh<T>({ view, col, children, style, className }: {
  view: TableView<T>; col: string; children: ReactNode; style?: React.CSSProperties; className?: string;
}) {
  const { t } = useI18n();
  const on = view.sort === col;
  return (
    <th style={style} className={`sort-th${on ? " on" : ""}${className ? ` ${className}` : ""}`}
        aria-sort={on ? (view.desc ? "descending" : "ascending") : "none"}>
      <button type="button" className="sort-th-btn" onClick={() => view.toggle(col)}
              title={on ? t("list.sort_flip") : t("table.sort_by")}>
        {children}<span className="sort-th-mark" aria-hidden>{on ? (view.desc ? "▼" : "▲") : "↕"}</span>
      </button>
    </th>
  );
}

/** The search box of a table, with how many rows it shows and a reset. */
export function TableSearch<T>({ view, id, right }: { view: TableView<T>; id: string; right?: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="table-tools">
      <input id={id} className="table-search" value={view.query} placeholder={t("list.search")}
             aria-label={t("list.search")} onChange={(e) => view.setQuery(e.target.value)} />
      {view.query.trim() && (
        <span className="small muted">{t("table.count", { n: view.rows.length, total: view.total })}</span>
      )}
      {right}
      {view.touched && <button type="button" className="btn-ghost btn-sm" onClick={view.reset}>{t("list.reset")}</button>}
    </div>
  );
}

/** The hook as a wrapper, for a table drawn by a helper or in a loop: it keeps its
 *  own sort and search, and hands the filtered, sorted rows to `children`. */
export function Sorted<T>({ storageKey, rows, cols, defaultSort = null, search = true, children }: {
  storageKey: string; rows: T[]; cols: Col<T>[]; defaultSort?: string | null; search?: boolean;
  children: (view: TableView<T>) => ReactNode;
}) {
  const view = useTableView(storageKey, rows, cols, defaultSort);
  return (
    <>
      {search && rows.length > 3 && <TableSearch view={view} id={`${storageKey}-search`} />}
      {children(view)}
      {view.query.trim() && view.rows.length === 0 && <NoMatch />}
    </>
  );
}

function NoMatch() {
  const { t } = useI18n();
  return <div className="small muted" style={{ padding: 8 }}>{t("list.no_match")}</div>;
}
