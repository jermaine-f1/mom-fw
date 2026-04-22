import type { RankedEtf } from "../types";
import { getCioRegionData, type CioRegionKey } from "../lib/cio";
import { ZScoreStrip } from "./CioRegionPanel";

interface Props {
  ranked: RankedEtf[];
}

type Verdict = {
  label: string;
  color: "emerald" | "green" | "yellow" | "red";
  icon: string;
  playbook: string[];
};

function verdictFor(breadthPct: number): Verdict {
  if (breadthPct >= 70) {
    return {
      label: "FULL INVESTED",
      color: "emerald",
      icon: "🟢",
      playbook: [
        "Breadth is strong — stay fully invested in top-ranked momentum names.",
        "Use position limits (max 15%) and correlation filters to manage concentration.",
        "Cash allocation: 0-5%. Opportunity cost of sitting out is high.",
      ],
    };
  }
  if (breadthPct >= 50) {
    return {
      label: "LEAN INVESTED",
      color: "green",
      icon: "🟡",
      playbook: [
        "Breadth is adequate but not commanding — lean invested with selectivity.",
        "Favor regions showing MA 3/3 breadth above 60%. Trim lagging regions.",
        "Cash allocation: 10-20%. Keep dry powder for breakdown or re-acceleration.",
      ],
    };
  }
  if (breadthPct >= 30) {
    return {
      label: "REDUCE EXPOSURE",
      color: "yellow",
      icon: "🟠",
      playbook: [
        "Breadth is deteriorating — reduce gross exposure and tighten stops.",
        "Only hold ETFs with MA 3/3 status. Exit broken names promptly.",
        "Cash allocation: 25-40%. Protect capital; the market is not rewarding broad bets.",
      ],
    };
  }
  return {
    label: "RAISE CASH",
    color: "red",
    icon: "🔴",
    playbook: [
      "Breadth is broken — raise significant cash immediately.",
      "Sell all positions below MA 2/3. Only keep strongest momentum survivors.",
      "Cash allocation: 50%+. Capital preservation is the priority until breadth recovers above 40%.",
    ],
  };
}

const VERDICT_STYLES = {
  emerald: {
    banner: "bg-emerald-900/20 border-emerald-600/50",
    text: "text-emerald-400",
    accent: "text-emerald-400",
    playbookBanner: "bg-emerald-900/15 border-emerald-700/40",
    signalBadge: "bg-emerald-900/40 text-emerald-400",
    bar: "bg-emerald-500",
  },
  green: {
    banner: "bg-green-900/20 border-green-600/50",
    text: "text-green-400",
    accent: "text-green-400",
    playbookBanner: "bg-green-900/15 border-green-700/40",
    signalBadge: "bg-green-900/40 text-green-400",
    bar: "bg-green-500",
  },
  yellow: {
    banner: "bg-yellow-900/20 border-yellow-600/50",
    text: "text-yellow-400",
    accent: "text-yellow-400",
    playbookBanner: "bg-yellow-900/15 border-yellow-700/40",
    signalBadge: "bg-yellow-900/40 text-yellow-400",
    bar: "bg-yellow-500",
  },
  red: {
    banner: "bg-red-900/20 border-red-600/50",
    text: "text-red-400",
    accent: "text-red-400",
    playbookBanner: "bg-red-900/15 border-red-700/40",
    signalBadge: "bg-red-900/40 text-red-400",
    bar: "bg-red-500",
  },
} as const;

export function CioOverview({ ranked }: Props) {
  const allData = getCioRegionData("overview", ranked);
  const regionKeys: CioRegionKey[] = ["us", "dm", "em", "commodities", "taa"];
  const regionDataList = regionKeys.map((k) => ({
    key: k,
    ...getCioRegionData(k, ranked),
  }));

  const verdict = verdictFor(allData.breadthPct);
  const v = VERDICT_STYLES[verdict.color];

  const t = allData.total || 1;
  const ma3 = allData.etfs.filter((e) => e.maStatus === 3).length;
  const ma2 = allData.etfs.filter((e) => e.maStatus === 2).length;
  const ma1 = allData.etfs.filter((e) => e.maStatus === 1).length;
  const ma0 = allData.etfs.filter((e) => e.maStatus === 0).length;

  return (
    <div>
      <div className={`border-2 rounded-xl p-5 mb-4 text-center ${v.banner}`}>
        <div className="text-4xl mb-2">{verdict.icon}</div>
        <div className={`text-2xl font-bold ${v.text}`}>{verdict.label}</div>
        <div className="text-sm text-slate-400 mt-1">
          MA Breadth Score:{" "}
          <span className={`mono font-bold ${v.accent}`}>
            {allData.breadthPct.toFixed(0)}%
          </span>{" "}
          of ETFs hold all 3 MAs
        </div>
      </div>

      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
        <h4 className="text-sm font-bold text-slate-400 mb-3">
          MA Status Distribution
        </h4>
        <div className="space-y-2">
          <DistRow label="3/3" labelColor="text-emerald-400" barColor="bg-emerald-500" count={ma3} total={t} />
          <DistRow label="2/3" labelColor="text-yellow-400" barColor="bg-yellow-500" count={ma2} total={t} />
          <DistRow label="1/3" labelColor="text-orange-400" barColor="bg-orange-500" count={ma1} total={t} />
          <DistRow label="0/3" labelColor="text-red-400" barColor="bg-red-500" count={ma0} total={t} />
        </div>
      </div>

      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
        <h4 className="text-sm font-bold text-slate-400 mb-3">
          Regional Conviction
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-xs">
                <th className="px-3 py-2 text-left">Region</th>
                <th className="px-3 py-2 text-center">ETFs</th>
                <th className="px-3 py-2 text-center">MA 3/3</th>
                <th className="px-3 py-2 text-center">MA 0/3</th>
                <th className="px-3 py-2 text-center">Avg Wks↓</th>
                <th className="px-3 py-2 text-center">Signal</th>
              </tr>
            </thead>
            <tbody>
              {regionDataList.map((r) => {
                const signal =
                  r.breadthPct >= 70
                    ? { label: "Strong", cls: "bg-emerald-900/40 text-emerald-400" }
                    : r.breadthPct >= 40
                      ? { label: "Mixed", cls: "bg-yellow-900/40 text-yellow-400" }
                      : { label: "Weak", cls: "bg-red-900/40 text-red-400" };
                return (
                  <tr key={r.key} className="border-t border-slate-800">
                    <td className="px-3 py-2 font-medium">{r.label}</td>
                    <td className="px-3 py-2 text-center mono">{r.total}</td>
                    <td className="px-3 py-2 text-center mono text-emerald-400">
                      {r.maIntact}
                    </td>
                    <td className="px-3 py-2 text-center mono text-red-400">
                      {r.maBroken}
                    </td>
                    <td className="px-3 py-2 text-center mono">
                      {r.avgWksDown.toFixed(1)}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span
                        className={
                          "px-2 py-0.5 rounded text-xs font-bold " + signal.cls
                        }
                      >
                        {signal.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
        <h4 className="text-sm font-bold text-slate-400 mb-2">
          Z-Score Heatmap — All Regions
        </h4>
        <ZScoreStrip etfs={allData.etfs} />
      </div>

      <div className={`border rounded-xl p-5 ${v.playbookBanner}`}>
        <h4 className={`text-sm font-bold mb-3 ${v.text}`}>
          💰 Cash vs Exposure Playbook
        </h4>
        <ul className="space-y-2 text-sm text-slate-300">
          {verdict.playbook.map((l, i) => (
            <li key={i} className="flex gap-2">
              <span className={`mt-0.5 ${v.accent}`}>▸</span> {l}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function DistRow({
  label,
  labelColor,
  barColor,
  count,
  total,
}: {
  label: string;
  labelColor: string;
  barColor: string;
  count: number;
  total: number;
}) {
  const pct = (count / total) * 100;
  return (
    <div className="flex items-center gap-3">
      <span className={`text-xs w-16 ${labelColor}`}>{label}</span>
      <div className="flex-1 bg-slate-800 rounded-full h-5 overflow-hidden">
        <div
          className={`${barColor} h-full rounded-full transition-all`}
          style={{ width: `${pct.toFixed(1)}%` }}
        />
      </div>
      <span className="mono text-xs text-slate-400 w-16 text-right">
        {count} ({pct.toFixed(0)}%)
      </span>
    </div>
  );
}
