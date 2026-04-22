import { useMemo, useState } from "react";
import type { RankedEtf, ScoreSettings } from "../types";

interface Props {
  ranked: RankedEtf[];
  settings: ScoreSettings;
}

type SortColumn =
  | "ticker"
  | "isETF"
  | "country"
  | "price"
  | "score"
  | "return6m"
  | "sortino"
  | "weeksDown"
  | "zScore"
  | "maStatus";

const NUMERIC_COLUMNS: SortColumn[] = [
  "price",
  "score",
  "return6m",
  "sortino",
  "weeksDown",
  "zScore",
  "maStatus",
];

interface Filters {
  etfOnly: boolean;
  topOnly: boolean;
  search: string;
  region: string;
  sector: string;
  reqMA30: boolean;
  reqMA60: boolean;
  reqMA200: boolean;
  zScoreCap: string;
  minScore: string;
}

const DEFAULT_FILTERS: Filters = {
  etfOnly: true,
  topOnly: false,
  search: "",
  region: "",
  sector: "",
  reqMA30: false,
  reqMA60: false,
  reqMA200: false,
  zScoreCap: "",
  minScore: "",
};

type SortState = { column: SortColumn; direction: "asc" | "desc" };

function compare(a: RankedEtf, b: RankedEtf, sort: SortState): number {
  let valA: unknown = a[sort.column];
  let valB: unknown = b[sort.column];
  if (typeof valA === "boolean") valA = valA ? 1 : 0;
  if (typeof valB === "boolean") valB = valB ? 1 : 0;
  if (typeof valA === "string" && typeof valB === "string") {
    valA = valA.toLowerCase();
    valB = valB.toLowerCase();
  }
  let result = 0;
  if ((valA as number | string) < (valB as number | string)) result = -1;
  if ((valA as number | string) > (valB as number | string)) result = 1;
  return sort.direction === "asc" ? result : -result;
}

function scoreColor(score: number): string {
  if (score >= 65) return "text-emerald-400";
  if (score >= 50) return "text-indigo-400";
  if (score >= 35) return "text-amber-400";
  return "text-red-400";
}

export function Screener({ ranked, settings }: Props) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [sort, setSort] = useState<SortState>({
    column: "score",
    direction: "desc",
  });

  const regions = useMemo(
    () => [...new Set(ranked.flatMap((e) => e.regions))].sort(),
    [ranked],
  );
  const sectors = useMemo(
    () => [...new Set(ranked.map((e) => e.sector))].sort(),
    [ranked],
  );

  const topIdeasSet = useMemo(
    () => new Set(ranked.slice(0, settings.topCount).map((e) => e.ticker)),
    [ranked, settings.topCount],
  );

  const parseNumericFilter = (raw: string): number | null => {
    if (raw === "") return null;
    const n = parseFloat(raw);
    // parseFloat("abc") === NaN. NaN comparisons are always false, so the
    // filter would silently no-op — return null explicitly so callers can
    // decide (here: treat as "no filter" AND flag to the user).
    return Number.isFinite(n) ? n : null;
  };

  const zCapInvalid =
    filters.zScoreCap !== "" && !Number.isFinite(parseFloat(filters.zScoreCap));
  const minScoreInvalid =
    filters.minScore !== "" && !Number.isFinite(parseFloat(filters.minScore));

  const filtered = useMemo(() => {
    const zCap = parseNumericFilter(filters.zScoreCap);
    const minS = parseNumericFilter(filters.minScore);
    const search = filters.search.toLowerCase();

    const list = ranked.filter((e) => {
      if (filters.etfOnly && !e.isETF) return false;
      if (filters.topOnly && !topIdeasSet.has(e.ticker)) return false;
      if (filters.region && !e.regions.includes(filters.region)) return false;
      if (filters.sector && e.sector !== filters.sector) return false;
      if (filters.reqMA30 && !e.aboveMA30) return false;
      if (filters.reqMA60 && !e.aboveMA60) return false;
      if (filters.reqMA200 && !e.aboveMA200) return false;
      if (zCap !== null && e.zScore > zCap) return false;
      if (minS !== null && e.score < minS) return false;
      if (search) {
        const haystack = [e.ticker, e.name, e.sector, e.country, ...e.regions]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });
    return list.sort((a, b) => compare(a, b, sort));
  }, [ranked, filters, sort, topIdeasSet]);

  const handleSort = (column: SortColumn) => {
    setSort((prev) => {
      if (prev.column === column) {
        return {
          column,
          direction: prev.direction === "asc" ? "desc" : "asc",
        };
      }
      return {
        column,
        direction: NUMERIC_COLUMNS.includes(column) ? "desc" : "asc",
      };
    });
  };

  const topInView = filtered.filter((e) => topIdeasSet.has(e.ticker)).length;
  const avgScore =
    filtered.length > 0
      ? (filtered.reduce((s, e) => s + e.score, 0) / filtered.length).toFixed(1)
      : "—";
  const aboveAllMA = filtered.filter((e) => e.maStatus === 3).length;

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters((f) => ({ ...f, [key]: value }));

  return (
    <div className="space-y-6">
      <div className="bg-slate-900/50 rounded-xl border border-slate-800 p-4">
        <div className="flex flex-wrap items-center gap-4 mb-4">
          <span className="text-sm text-slate-400 font-medium">View:</span>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              className="w-5 h-5 rounded"
              checked={filters.etfOnly}
              onChange={(e) => setFilter("etfOnly", e.target.checked)}
            />
            <span className="text-sm">ETFs Only</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              className="w-5 h-5 rounded"
              checked={filters.topOnly}
              onChange={(e) => setFilter("topOnly", e.target.checked)}
            />
            <span className="text-sm">⭐ Top Ideas Only</span>
          </label>
          <div className="ml-auto text-sm text-slate-500">
            Showing:{" "}
            <span className="text-indigo-400 font-bold">{filtered.length}</span>{" "}
            / {ranked.length}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 mb-4">
          <span className="text-sm text-slate-400 font-medium">Search:</span>
          <input
            type="text"
            placeholder="Symbol, sector, region..."
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm w-64 focus:outline-none focus:border-indigo-500"
            value={filters.search}
            onChange={(e) => setFilter("search", e.target.value)}
          />
          <span className="text-sm text-slate-400 font-medium ml-4">
            Region:
          </span>
          <select
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-indigo-500"
            value={filters.region}
            onChange={(e) => setFilter("region", e.target.value)}
          >
            <option value="">All Regions</option>
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <span className="text-sm text-slate-400 font-medium ml-4">
            Sector:
          </span>
          <select
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-indigo-500"
            value={filters.sector}
            onChange={(e) => setFilter("sector", e.target.value)}
          >
            <option value="">All Sectors</option>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button
            className="ml-auto px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm transition-colors"
            onClick={() => setFilters(DEFAULT_FILTERS)}
          >
            ✕ Clear All
          </button>
        </div>

        <div className="border-t border-slate-700 pt-4">
          <span className="text-sm text-slate-400 font-medium mb-3 block">
            Narrowing Filters (all off by default):
          </span>
          <div className="flex flex-wrap items-center gap-5">
            {(
              [
                ["reqMA30", "Above MA-30"],
                ["reqMA60", "Above MA-60"],
                ["reqMA200", "Above MA-200"],
              ] as const
            ).map(([key, label]) => (
              <label
                key={key}
                className="flex items-center gap-2 cursor-pointer bg-slate-800/50 rounded-lg px-3 py-2 hover:bg-slate-700/50 transition-colors"
              >
                <input
                  type="checkbox"
                  className="w-4 h-4 rounded"
                  checked={filters[key]}
                  onChange={(e) => setFilter(key, e.target.checked)}
                />
                <span className="text-sm">{label}</span>
              </label>
            ))}
            <div className="flex items-center gap-2 bg-slate-800/50 rounded-lg px-3 py-2">
              <span className="text-sm text-slate-300">Z-Score ≤</span>
              <input
                type="number"
                step="0.5"
                min="0"
                max="10"
                placeholder="—"
                className={
                  "bg-slate-700 border rounded px-2 py-1 text-sm w-16 mono text-center focus:outline-none " +
                  (zCapInvalid
                    ? "border-red-500 focus:border-red-500"
                    : "border-slate-600 focus:border-indigo-500")
                }
                value={filters.zScoreCap}
                onChange={(e) => setFilter("zScoreCap", e.target.value)}
                aria-invalid={zCapInvalid}
                title={zCapInvalid ? "Not a number — filter ignored" : undefined}
              />
            </div>
            <div className="flex items-center gap-2 bg-slate-800/50 rounded-lg px-3 py-2">
              <span className="text-sm text-slate-300">Min Score ≥</span>
              <input
                type="number"
                step="5"
                min="0"
                max="100"
                placeholder="—"
                className={
                  "bg-slate-700 border rounded px-2 py-1 text-sm w-16 mono text-center focus:outline-none " +
                  (minScoreInvalid
                    ? "border-red-500 focus:border-red-500"
                    : "border-slate-600 focus:border-indigo-500")
                }
                value={filters.minScore}
                onChange={(e) => setFilter("minScore", e.target.value)}
                aria-invalid={minScoreInvalid}
                title={minScoreInvalid ? "Not a number — filter ignored" : undefined}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-indigo-900/30 border border-indigo-700/50 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-indigo-400">
            {filtered.length}
          </div>
          <div className="text-sm text-slate-400">Showing</div>
        </div>
        <div className="bg-amber-900/30 border border-amber-700/50 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-amber-400">
            ⭐ {topInView}
          </div>
          <div className="text-sm text-slate-400">Top Ideas</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-emerald-400">{avgScore}</div>
          <div className="text-sm text-slate-400">Avg Score</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-cyan-400">{aboveAllMA}</div>
          <div className="text-sm text-slate-400">All MAs ✓</div>
        </div>
      </div>

      <div className="bg-slate-900/50 rounded-xl border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex justify-between items-center">
          <h3 className="font-bold">All Instruments — Ranked by Quality Score</h3>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">
              ⭐ = Top {settings.topCount} Ideas
            </span>
            <span className="text-xs text-slate-500">
              Click headers to sort
            </span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-800 text-slate-400 text-xs uppercase">
                <th className="px-3 py-2 text-left">#</th>
                <HeaderCell column="ticker" label="Symbol" sort={sort} onClick={handleSort} />
                <HeaderCell column="isETF" label="Type" sort={sort} onClick={handleSort} />
                <HeaderCell column="country" label="Region" sort={sort} onClick={handleSort} />
                <HeaderCell column="price" label="Price" align="right" sort={sort} onClick={handleSort} />
                <HeaderCell column="score" label="Score" align="right" sort={sort} onClick={handleSort} />
                <HeaderCell column="return6m" label="6M Ret" align="right" sort={sort} onClick={handleSort} />
                <HeaderCell column="sortino" label="Sortino" align="right" sort={sort} onClick={handleSort} />
                <HeaderCell column="weeksDown" label="Wks↓" align="right" sort={sort} onClick={handleSort} />
                <HeaderCell column="zScore" label="Z" align="right" sort={sort} onClick={handleSort} />
                <HeaderCell column="maStatus" label="MA" align="center" sort={sort} onClick={handleSort} />
              </tr>
            </thead>
            <tbody>
              {filtered.map((etf, i) => {
                const isTop = topIdeasSet.has(etf.ticker);
                return (
                  <tr
                    key={etf.ticker}
                    className={
                      "border-t border-slate-800 " +
                      (isTop ? "top-idea-row" : "")
                    }
                  >
                    <td className="px-3 py-2 text-slate-500">
                      {isTop ? "⭐ " : ""}
                      {i + 1}
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-bold">{etf.ticker}</div>
                      <div className="text-xs text-slate-500">{etf.sector}</div>
                    </td>
                    <td
                      className={
                        "px-3 py-2 text-xs " +
                        (etf.isETF ? "text-cyan-400" : "text-amber-400")
                      }
                    >
                      {etf.isETF ? "ETF" : "Stock"}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-400">
                      {etf.country}
                    </td>
                    <td
                      className="px-3 py-2 text-right mono"
                      style={{ color: "#fbbf24" }}
                    >
                      {etf.price != null ? `$${etf.price.toFixed(2)}` : "—"}
                    </td>
                    <td
                      className={
                        "px-3 py-2 text-right mono font-bold " +
                        scoreColor(etf.score)
                      }
                    >
                      {etf.score.toFixed(1)}
                    </td>
                    <td
                      className={
                        "px-3 py-2 text-right mono " +
                        (etf.return6m >= 0 ? "text-emerald-400" : "text-red-400")
                      }
                    >
                      {etf.return6m >= 0 ? "+" : ""}
                      {etf.return6m.toFixed(1)}%
                    </td>
                    <td className="px-3 py-2 text-right mono">
                      {etf.sortino.toFixed(2)}
                    </td>
                    <td
                      className={
                        "px-3 py-2 text-right mono " +
                        (etf.weeksDown >= 8 ? "text-red-400" : "")
                      }
                    >
                      {etf.weeksDown}/12
                    </td>
                    <td
                      className={
                        "px-3 py-2 text-right mono " +
                        (etf.zScore > 4
                          ? "text-red-400 font-bold"
                          : etf.zScore > 3
                            ? "text-orange-400"
                            : "")
                      }
                    >
                      {etf.zScore.toFixed(1)}
                    </td>
                    <td
                      className={
                        "px-3 py-2 text-center " +
                        (etf.maStatus === 3
                          ? "text-emerald-400"
                          : etf.maStatus >= 2
                            ? "text-yellow-400"
                            : "text-red-400")
                      }
                    >
                      {etf.maStatus}/3
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="p-6 text-center text-slate-500 text-sm">
              No instruments match the current filters.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface HeaderCellProps {
  column: SortColumn;
  label: string;
  align?: "left" | "right" | "center";
  sort: SortState;
  onClick: (c: SortColumn) => void;
}

function HeaderCell({ column, label, align = "left", sort, onClick }: HeaderCellProps) {
  const indicator =
    sort.column === column ? (sort.direction === "asc" ? "↑" : "↓") : "";
  const alignClass =
    align === "right"
      ? "text-right"
      : align === "center"
        ? "text-center"
        : "text-left";
  return (
    <th
      className={`px-3 py-2 ${alignClass} cursor-pointer hover:text-white select-none`}
      onClick={() => onClick(column)}
    >
      {label}{" "}
      <span className="text-indigo-400">{indicator}</span>
    </th>
  );
}
