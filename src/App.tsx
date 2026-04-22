import { useMemo, useState } from "react";
import { useData } from "./data/useData";
import { rankUniverse } from "./lib/score";
import { DEFAULT_SETTINGS } from "./types";
import { Screener } from "./components/Screener";
import { Settings } from "./components/Settings";
import { ComingSoon } from "./components/ComingSoon";

type TabId =
  | "signals"
  | "portfolio"
  | "analyzer"
  | "cio"
  | "strategy"
  | "rules";

const TABS: { id: TabId; label: string }[] = [
  { id: "signals", label: "📡 Screener" },
  { id: "portfolio", label: "💼 Portfolio" },
  { id: "analyzer", label: "📊 Portfolio Analyzer" },
  { id: "cio", label: "🏛️ CIO Signals" },
  { id: "strategy", label: "🎯 Strategy" },
  { id: "rules", label: "⚙️ Settings" },
];

export default function App() {
  const data = useData();
  const [active, setActive] = useState<TabId>("signals");
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);

  const ranked = useMemo(() => {
    if (data.status !== "ready") return [];
    return rankUniverse(data.payload.etfUniverse, settings);
  }, [data, settings]);

  return (
    <div className="p-4 md:p-6">
      <div className="max-w-7xl mx-auto">
        <header className="mb-6">
          <h1 className="text-2xl md:text-3xl font-bold">
            📊 Momentum Portfolio Framework
          </h1>
          <p className="text-slate-400 text-sm">
            CIO Dashboard | Diversified Quality Momentum Screener
          </p>
          {data.status === "ready" && (
            <p className="text-emerald-400 text-xs mono mt-1">
              Live Data Generated: {data.payload.generatedAt}
            </p>
          )}
        </header>

        <nav className="flex gap-2 flex-wrap mb-6">
          {TABS.map((t) => {
            const isActive = t.id === active;
            return (
              <button
                key={t.id}
                onClick={() => setActive(t.id)}
                className={
                  "px-4 py-2 rounded-lg font-medium transition-colors " +
                  (isActive
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700")
                }
              >
                {t.label}
              </button>
            );
          })}
        </nav>

        {data.status === "loading" && (
          <div className="text-slate-400 text-sm">Loading data…</div>
        )}
        {data.status === "error" && (
          <div className="bg-red-900/30 border border-red-600/50 rounded-xl p-4 text-red-300">
            <div className="font-bold mb-1">Failed to load data.json</div>
            <div className="text-sm text-red-200">{data.message}</div>
            <div className="text-xs text-red-200/70 mt-2">
              Generate it with <code className="mono">python mom_gen.py</code>.
            </div>
          </div>
        )}

        {data.status === "ready" && (
          <>
            {active === "signals" && (
              <Screener ranked={ranked} settings={settings} />
            )}
            {active === "portfolio" && (
              <ComingSoon
                title="Portfolio"
                note="Portfolio builder (max positions, max weight, max correlation) — pending port from legacy HTML."
              />
            )}
            {active === "analyzer" && (
              <ComingSoon
                title="Portfolio Analyzer"
                note="CSV upload, region breakdown, buy/sell candidates — pending port."
              />
            )}
            {active === "cio" && (
              <ComingSoon
                title="CIO Signals"
                note="Overview, Commodities, EM, DM, US, TAA sub-tabs — pending port."
              />
            )}
            {active === "strategy" && (
              <ComingSoon
                title="Strategy"
                note="Core strategy principles & methodology — pending port."
              />
            )}
            {active === "rules" && (
              <Settings settings={settings} onApply={setSettings} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
