import type { RankedEtf } from "../types";
import { getCioRegionData, zScoreColor, type CioRegionKey } from "../lib/cio";

interface Props {
  regionKey: CioRegionKey;
  ranked: RankedEtf[];
}

export function CioRegionPanel({ regionKey, ranked }: Props) {
  const data = getCioRegionData(regionKey, ranked);
  const { etfs, maIntact, fullStack, maBroken, avgWksDown, breadthPct, total, label } =
    data;

  const breadthColor =
    breadthPct >= 70 ? "emerald" : breadthPct >= 40 ? "yellow" : "red";

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <HeadlineCard tone="emerald" value={`${maIntact}`} denom={total} label="MA Intact (3/3)" />
        <HeadlineCard tone="indigo" value={`${fullStack}`} denom={total} label="Full Stack (≥2/3)" />
        <HeadlineCard tone="red" value={`${maBroken}`} denom={total} label="MA Broken (0/3)" />
        <div className="bg-slate-800 rounded-lg p-3 text-center">
          <div
            className={
              "text-2xl font-bold " +
              (breadthColor === "emerald"
                ? "text-emerald-400"
                : breadthColor === "yellow"
                  ? "text-yellow-400"
                  : "text-red-400")
            }
          >
            {avgWksDown.toFixed(1)}
          </div>
          <div className="text-xs text-slate-400">Avg Wks Down</div>
        </div>
      </div>

      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
        <h4 className="text-sm font-bold text-slate-400 mb-2">
          Z-Score Heatmap — {label}
        </h4>
        <ZScoreStrip etfs={etfs} />
      </div>

      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
        <h4 className="text-sm font-bold text-slate-400 mb-3">ETFs by MA Tier</h4>
        <EtfCardsByTier etfs={etfs} />
      </div>

      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4">
        <h4 className="text-sm font-bold text-slate-400 mb-2">
          📖 Signal Reading — {label}
        </h4>
        <SignalReading data={data} />
      </div>
    </div>
  );
}

function HeadlineCard({
  tone,
  value,
  denom,
  label,
}: {
  tone: "emerald" | "indigo" | "red";
  value: string;
  denom: number;
  label: string;
}) {
  const toneClasses = {
    emerald: "bg-emerald-900/20 border-emerald-700/40 text-emerald-400",
    indigo: "bg-indigo-900/20 border-indigo-700/40 text-indigo-400",
    red: "bg-red-900/20 border-red-700/40 text-red-400",
  }[tone];
  return (
    <div className={`border rounded-lg p-3 text-center ${toneClasses}`}>
      <div className="text-2xl font-bold">
        {value}
        <span className="text-sm text-slate-500">/{denom}</span>
      </div>
      <div className="text-xs text-slate-400">{label}</div>
    </div>
  );
}

export function ZScoreStrip({ etfs }: { etfs: RankedEtf[] }) {
  if (etfs.length === 0) {
    return <div className="text-sm text-slate-500">No ETFs</div>;
  }
  const sorted = [...etfs].sort((a, b) => a.zScore - b.zScore);
  const widthPct = (100 / sorted.length).toFixed(2);
  return (
    <>
      <div style={{ display: "flex", borderRadius: 6, overflow: "hidden" }}>
        {sorted.map((e) => (
          <div
            key={e.ticker}
            title={`${e.ticker}: z=${e.zScore.toFixed(1)}`}
            style={{
              width: `${widthPct}%`,
              background: zScoreColor(e.zScore),
              height: 18,
              display: "inline-block",
              cursor: "pointer",
            }}
            className="hover:opacity-80 transition-opacity"
          />
        ))}
      </div>
      <div className="flex justify-between text-xs text-slate-500 mt-1">
        <span>← Oversold</span>
        <span>Normal</span>
        <span>Extended →</span>
      </div>
    </>
  );
}

function EtfCardsByTier({ etfs }: { etfs: RankedEtf[] }) {
  const tiers: {
    label: string;
    status: 3 | 2 | 1 | 0;
    color: "emerald" | "yellow" | "orange" | "red";
  }[] = [
    { label: "MA 3/3 — Full alignment", status: 3, color: "emerald" },
    { label: "MA 2/3 — Partial alignment", status: 2, color: "yellow" },
    { label: "MA 1/3 — Weak", status: 1, color: "orange" },
    { label: "MA 0/3 — No support", status: 0, color: "red" },
  ];
  const colorClass = {
    emerald: "text-emerald-400",
    yellow: "text-yellow-400",
    orange: "text-orange-400",
    red: "text-red-400",
  };
  return (
    <>
      {tiers.map((tier) => {
        const tierETFs = etfs
          .filter((e) => e.maStatus === tier.status)
          .sort((a, b) => a.weeksDown - b.weeksDown);
        if (tierETFs.length === 0) return null;
        return (
          <div key={tier.status} className="mb-4">
            <div className={"text-sm font-bold mb-2 " + colorClass[tier.color]}>
              {tier.label}{" "}
              <span className="text-slate-500 font-normal">
                ({tierETFs.length})
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {tierETFs.map((e) => {
                const retColor =
                  e.return6m >= 0 ? "text-emerald-400" : "text-red-400";
                const zColor =
                  e.zScore > 3
                    ? "text-red-400"
                    : e.zScore > 2
                      ? "text-orange-400"
                      : "text-slate-300";
                return (
                  <div
                    key={e.ticker}
                    className="bg-slate-800 rounded-lg p-2.5 min-w-[130px]"
                  >
                    <div className="font-bold text-sm">{e.ticker}</div>
                    <div className="text-xs text-slate-500 truncate">
                      {e.name || e.sector}
                    </div>
                    <div className="grid grid-cols-2 gap-x-2 mt-1.5 text-xs">
                      <span className="text-slate-500">Ret</span>
                      <span className={retColor + " text-right"}>
                        {e.return6m >= 0 ? "+" : ""}
                        {e.return6m.toFixed(1)}%
                      </span>
                      <span className="text-slate-500">Z</span>
                      <span className={zColor + " text-right"}>
                        {e.zScore.toFixed(1)}
                      </span>
                      <span className="text-slate-500">Wks↓</span>
                      <span
                        className={
                          "text-right " +
                          (e.weeksDown >= 6 ? "text-red-400" : "")
                        }
                      >
                        {e.weeksDown}/12
                      </span>
                      <span className="text-slate-500">Score</span>
                      <span className="text-indigo-400 text-right">
                        {e.score.toFixed(0)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </>
  );
}

function SignalReading({
  data,
}: {
  data: {
    maIntact: number;
    maBroken: number;
    total: number;
    avgWksDown: number;
    breadthPct: number;
    label: string;
  };
}) {
  const { maIntact, maBroken, total, avgWksDown, breadthPct, label } = data;
  const lines: React.ReactNode[] = [];

  if (breadthPct >= 70) {
    lines.push(
      <>
        <span className="text-emerald-400 font-bold">Strong uptrend.</span>{" "}
        {maIntact} of {total} {label} ETFs hold all three MAs — broad
        participation confirms the rally.
      </>,
    );
  } else if (breadthPct >= 40) {
    lines.push(
      <>
        <span className="text-yellow-400 font-bold">Mixed signals.</span>{" "}
        {maIntact} of {total} {label} ETFs hold all MAs — momentum is selective,
        not broad.
      </>,
    );
  } else {
    lines.push(
      <>
        <span className="text-red-400 font-bold">Weak breadth.</span> Only{" "}
        {maIntact} of {total} {label} ETFs hold all MAs — the trend is narrow or
        breaking down.
      </>,
    );
  }

  if (avgWksDown >= 6) {
    lines.push(
      <>
        Average weeks-down at {avgWksDown.toFixed(1)}/12 signals persistent
        selling pressure.
      </>,
    );
  } else if (avgWksDown >= 3) {
    lines.push(
      <>
        Average weeks-down at {avgWksDown.toFixed(1)}/12 — mild deterioration,
        watch for acceleration.
      </>,
    );
  } else {
    lines.push(
      <>
        Average weeks-down at {avgWksDown.toFixed(1)}/12 — buyers remain in
        control.
      </>,
    );
  }

  if (maBroken > total * 0.3) {
    lines.push(
      <>
        <span className="text-red-400">{maBroken} ETFs below all MAs</span> —
        material downside risk in this region.
      </>,
    );
  }

  return (
    <div className="text-sm text-slate-300 leading-relaxed">
      {lines.map((l, i) => (
        <p key={i} className="mb-1">
          {l}
        </p>
      ))}
    </div>
  );
}
