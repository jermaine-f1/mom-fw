import { useEffect, useState } from "react";
import type { ScoreSettings } from "../types";
import { DEFAULT_SETTINGS } from "../types";

interface Props {
  settings: ScoreSettings;
  onApply: (next: ScoreSettings) => void;
}

export function Settings({ settings, onApply }: Props) {
  const [draft, setDraft] = useState<ScoreSettings>(settings);

  // Stay in sync if the parent resets (e.g. external reset from another tab).
  useEffect(() => {
    setDraft(settings);
  }, [settings]);

  const totalWeights =
    draft.weights.sortino +
    draft.weights.weeksDown +
    draft.weights.zScore +
    draft.weights.slope;
  const totalIs100 = totalWeights === 100;

  const setWeight = (k: keyof ScoreSettings["weights"], v: number) =>
    setDraft((d) => ({ ...d, weights: { ...d.weights, [k]: v } }));

  const setMode = (mode: ScoreSettings["mode"]) =>
    setDraft((d) => ({ ...d, mode }));

  const apply = () => onApply(draft);

  const reset = () => {
    setDraft(DEFAULT_SETTINGS);
    onApply(DEFAULT_SETTINGS);
  };

  const configSummary = (() => {
    const modeText =
      draft.mode === "pure" ? "Pure Return" : "Quality Momentum";
    const weightsText =
      draft.mode === "pure"
        ? "N/A"
        : `Sortino ${draft.weights.sortino}%, WeeksDown ${draft.weights.weeksDown}%, Z-Score ${draft.weights.zScore}%, Slope ${draft.weights.slope}%`;
    return `Mode: ${modeText} | Weights: ${weightsText} | Top Ideas: ${draft.topCount} | Z-Steep: ${draft.zScoreSteep.toFixed(1)}`;
  })();

  const dirty =
    draft.mode !== settings.mode ||
    draft.topCount !== settings.topCount ||
    draft.zScoreSteep !== settings.zScoreSteep ||
    draft.weights.sortino !== settings.weights.sortino ||
    draft.weights.weeksDown !== settings.weights.weeksDown ||
    draft.weights.zScore !== settings.weights.zScore ||
    draft.weights.slope !== settings.weights.slope;

  return (
    <div className="space-y-6">
      <div className="bg-amber-900/20 border border-amber-700/50 rounded-xl p-5">
        <h3 className="text-lg font-bold text-amber-400 mb-4">
          ⚙️ Quality Momentum Settings
        </h3>

        <div className="mb-6">
          <label className="text-sm text-slate-400 mb-2 block">
            Scoring Mode
          </label>
          <div className="flex gap-3">
            <button
              onClick={() => setMode("pure")}
              className={
                "flex-1 p-3 rounded-lg border-2 transition-all " +
                (draft.mode === "pure"
                  ? "border-orange-500 bg-orange-900/20"
                  : "border-slate-700 bg-slate-800 hover:border-orange-500")
              }
            >
              <div className="font-bold text-orange-400">📈 Pure Return</div>
              <div className="text-xs text-slate-400">
                Simple 6M price momentum
              </div>
            </button>
            <button
              onClick={() => setMode("quality")}
              className={
                "flex-1 p-3 rounded-lg border-2 transition-all " +
                (draft.mode === "quality"
                  ? "border-emerald-500 bg-emerald-900/20"
                  : "border-slate-700 bg-slate-800 hover:border-emerald-500")
              }
            >
              <div className="font-bold text-emerald-400">
                🎯 Quality Momentum
              </div>
              <div className="text-xs text-slate-400">
                Risk-adjusted composite
              </div>
            </button>
          </div>
        </div>

        {draft.mode === "quality" && (
          <>
            <div className="mb-4">
              <div className="flex justify-between items-center mb-2">
                <label className="text-sm text-slate-400">
                  Component Weights
                </label>
                <span
                  className={
                    "text-sm mono px-2 py-1 rounded " +
                    (totalIs100
                      ? "bg-emerald-900/50 text-emerald-400"
                      : "bg-red-900/50 text-red-400")
                  }
                >
                  Total: {totalWeights}%
                </span>
              </div>
              <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                <WeightSlider
                  label="Sortino Ratio"
                  hint="Risk-adjusted return"
                  value={draft.weights.sortino}
                  onChange={(v) => setWeight("sortino", v)}
                />
                <WeightSlider
                  label="Weeks Down (12wk)"
                  hint="Trend weakening"
                  value={draft.weights.weeksDown}
                  onChange={(v) => setWeight("weeksDown", v)}
                />
                <WeightSlider
                  label="Z-Score Penalty"
                  hint="Extension detection"
                  value={draft.weights.zScore}
                  onChange={(v) => setWeight("zScore", v)}
                />
                <WeightSlider
                  label="Slope"
                  hint="Trend strength"
                  value={draft.weights.slope}
                  onChange={(v) => setWeight("slope", v)}
                />
              </div>
            </div>

            <div className="mb-4">
              <label className="text-sm text-slate-400 mb-2 block">
                Ranking
              </label>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-slate-800 rounded-lg p-3">
                  <label className="text-xs text-slate-400 block mb-1">
                    ⭐ Top Ideas Count
                  </label>
                  <input
                    type="range"
                    min={10}
                    max={30}
                    value={draft.topCount}
                    className="w-full"
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        topCount: parseInt(e.target.value, 10),
                      }))
                    }
                  />
                  <div className="flex justify-between text-xs mt-1">
                    <span className="text-slate-500">
                      Highlighted in screener
                    </span>
                    <span className="mono text-indigo-400 font-bold">
                      {draft.topCount}
                    </span>
                  </div>
                </div>
                <div className="bg-slate-800 rounded-lg p-3">
                  <label className="text-xs text-slate-400 block mb-1">
                    Z-Score Steep Penalty Start
                  </label>
                  <input
                    type="range"
                    min={2}
                    max={4}
                    step={0.5}
                    value={draft.zScoreSteep}
                    className="w-full"
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        zScoreSteep: parseFloat(e.target.value),
                      }))
                    }
                  />
                  <div className="flex justify-between text-xs mt-1">
                    <span className="text-slate-500">Exponential above</span>
                    <span className="mono text-orange-400 font-bold">
                      {draft.zScoreSteep.toFixed(1)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}

        <div className="mt-4 flex gap-3">
          <button
            onClick={apply}
            disabled={!dirty}
            className={
              "px-6 py-2 rounded-lg font-bold transition-colors " +
              (dirty
                ? "bg-emerald-600 hover:bg-emerald-500"
                : "bg-slate-700 text-slate-500 cursor-not-allowed")
            }
            title={
              dirty
                ? "Apply settings and recalculate screener"
                : "No unsaved changes"
            }
          >
            ✓ Apply &amp; Recalculate
          </button>
          <button
            onClick={reset}
            className="px-6 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg font-medium transition-colors"
          >
            ↺ Reset Defaults
          </button>
        </div>
      </div>

      <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4">
        <h4 className="font-bold text-sm text-slate-400 mb-2">
          📐 Active Configuration
        </h4>
        <div className="mono text-xs bg-slate-800 p-3 rounded">
          {configSummary}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-amber-900/20 border border-amber-700/50 rounded-xl p-5">
          <h3 className="text-lg font-bold text-amber-400 mb-4">
            ⚖️ Position Sizing
          </h3>
          <div className="space-y-3 text-sm">
            <InfoRow label="Target positions:" value="6-10" />
            <InfoRow label="Max single position:" value="15%" />
            <InfoRow label="Weighting method:" value="Equal weight" />
            <InfoRow label="Rebalance frequency:" value="Monthly" />
          </div>
        </div>

        <div className="bg-cyan-900/20 border border-cyan-700/50 rounded-xl p-5">
          <h3 className="text-lg font-bold text-cyan-400 mb-4">
            🛡️ Risk Management
          </h3>
          <div className="space-y-3 text-sm">
            <InfoRow label="Max pairwise correlation:" value="0.70" />
            <InfoRow label="Min countries:" value="3+" />
            <InfoRow label="Min sectors:" value="3+" />
            <InfoRow label="Max single country:" value="40%" />
          </div>
        </div>
      </div>

      <div className="bg-slate-900/80 border border-slate-700 rounded-xl p-5">
        <h3 className="text-lg font-bold text-slate-200 mb-4">
          🔒 Asset Class Constraints — CIO Limits
        </h3>
        <p className="text-xs text-slate-500 mb-2">
          The CIO constraint editor lives on the CIO Signals tab. This section
          previously duplicated it inline; the port keeps a single source of
          truth.
        </p>
      </div>
    </div>
  );
}

interface WeightSliderProps {
  label: string;
  hint: string;
  value: number;
  onChange: (n: number) => void;
}

function WeightSlider({ label, hint, value, onChange }: WeightSliderProps) {
  return (
    <div className="bg-slate-800 rounded-lg p-3">
      <label className="text-xs text-slate-400 block mb-1">{label}</label>
      <input
        type="range"
        min={0}
        max={100}
        value={value}
        className="w-full"
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
      />
      <div className="flex justify-between text-xs mt-1">
        <span className="text-slate-500">{hint}</span>
        <span className="mono text-indigo-400 font-bold">{value}%</span>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-400">{label}</span>
      <span className="font-bold">{value}</span>
    </div>
  );
}
