import { useState } from "react";
import {
  CIO_CONSTRAINT_DEFAULTS,
  clearStoredConstraints,
  loadStoredConstraints,
  saveStoredConstraints,
  type CioConstraint,
} from "../lib/cio";

export function CioConstraints() {
  const [constraints, setConstraints] = useState<CioConstraint[]>(() =>
    loadStoredConstraints(),
  );

  const total = constraints.reduce((s, c) => s + c.current, 0);
  const totalRounded = parseFloat(total.toFixed(1));
  const balanced = Math.abs(totalRounded - 100) < 0.01;

  const updateField = (idx: number, field: "min" | "max", raw: string) => {
    const val = parseFloat(raw);
    if (!Number.isFinite(val) || val < 0 || val > 100) return;
    setConstraints((prev) =>
      prev.map((c, i) => (i === idx ? { ...c, [field]: val } : c)),
    );
  };

  const save = () => saveStoredConstraints(constraints);
  const reset = () => {
    clearStoredConstraints();
    setConstraints(CIO_CONSTRAINT_DEFAULTS.map((c) => ({ ...c })));
  };

  return (
    <div className="bg-slate-900/80 border border-slate-700 rounded-xl p-5">
      <h3 className="text-lg font-bold text-slate-200 mb-4">
        🔒 Asset Class Constraints — CIO Limits
      </h3>
      <p className="text-xs text-slate-400 mb-4">
        Four asset classes: EM, DM, Commodities, Cash. Total must equal 100%.
      </p>

      <div className="mb-4">
        <AllocBar constraints={constraints} total={total} />
      </div>

      <div className="space-y-3">
        {constraints.map((c, i) => (
          <ConstraintRow
            key={c.id}
            c={c}
            onMinChange={(v) => updateField(i, "min", v)}
            onMaxChange={(v) => updateField(i, "max", v)}
          />
        ))}
      </div>

      <div
        className={
          "mt-4 text-center text-sm font-bold mono py-2 rounded-lg " +
          (balanced
            ? "bg-emerald-900/30 border border-emerald-700/50"
            : "bg-red-900/30 border border-red-700/50")
        }
      >
        {balanced ? (
          <span className="text-emerald-400">
            Total: {totalRounded}% ✓ Balanced
          </span>
        ) : (
          <span className="text-red-400">Total: {totalRounded}% ≠ 100%</span>
        )}
      </div>

      <div className="mt-4 flex gap-3">
        <button
          onClick={save}
          className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-bold transition-colors"
        >
          ✓ Save Constraints
        </button>
        <button
          onClick={reset}
          className="px-6 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg font-medium transition-colors"
        >
          ↺ Reset Defaults
        </button>
      </div>
    </div>
  );
}

function AllocBar({
  constraints,
  total,
}: {
  constraints: CioConstraint[];
  total: number;
}) {
  return (
    <>
      <div className="flex rounded-lg overflow-hidden border border-slate-700">
        {constraints.map((c) => {
          const pct = (c.current / total) * 100;
          return (
            <div
              key={c.id}
              style={{ width: `${pct}%`, background: c.color }}
              className="h-6 relative group"
            >
              <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-white drop-shadow">
                {c.current >= 8
                  ? `${c.name} ${c.current.toFixed(1)}%`
                  : ""}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex gap-4 mt-2 justify-center">
        {constraints.map((c) => (
          <span
            key={c.id}
            className="flex items-center gap-1.5 text-xs text-slate-300"
          >
            <span
              className="w-3 h-3 rounded-sm inline-block"
              style={{ background: c.color }}
            />
            {c.name} {c.current.toFixed(1)}%
          </span>
        ))}
      </div>
    </>
  );
}

function ConstraintRow({
  c,
  onMinChange,
  onMaxChange,
}: {
  c: CioConstraint;
  onMinChange: (v: string) => void;
  onMaxChange: (v: string) => void;
}) {
  const overMax = c.current > c.max;
  const underMin = c.min > 0 && c.current < c.min;

  let statusNode: React.ReactNode;
  let containerStyle: React.CSSProperties;
  if (overMax) {
    statusNode = (
      <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-red-900/60 text-red-300">
        ↑ {(c.current - c.max).toFixed(1)}% over max
      </span>
    );
    containerStyle = { background: "#1a0505", borderColor: "#7f1d1d" };
  } else if (underMin) {
    statusNode = (
      <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-900/60 text-amber-300">
        ↓ {(c.min - c.current).toFixed(1)}% below min
      </span>
    );
    containerStyle = { background: "#1c1200", borderColor: "#78350f" };
  } else {
    statusNode = (
      <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-900/60 text-emerald-300">
        ✓ Within range
      </span>
    );
    containerStyle = { background: "#0f172a", borderColor: "#1e293b" };
  }

  const fillColor = overMax ? "#dc2626" : underMin ? "#d97706" : c.color;
  const fillWidth = Math.min(c.current, 100);

  return (
    <div className="rounded-lg border p-3" style={containerStyle}>
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <span className="font-bold text-sm text-white flex items-center gap-2">
          <span
            className="w-3 h-3 rounded-sm inline-block"
            style={{ background: c.color }}
          />
          {c.name}
        </span>
        <span className="mono text-sm" style={{ color: c.color }}>
          Current {c.current.toFixed(1)}%
        </span>
        <span className="flex items-center gap-2 text-xs">
          <label className="text-slate-400">Min%</label>
          <input
            type="number"
            min={0}
            max={100}
            value={c.min}
            onChange={(e) => onMinChange(e.target.value)}
            className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs mono text-white text-center"
          />
        </span>
        <span className="flex items-center gap-2 text-xs">
          <label className="text-slate-400">Max%</label>
          <input
            type="number"
            min={0}
            max={100}
            value={c.max}
            onChange={(e) => onMaxChange(e.target.value)}
            className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs mono text-white text-center"
          />
        </span>
        {statusNode}
      </div>
      <div className="relative h-5 bg-slate-800 rounded-full overflow-visible">
        <div
          className="absolute top-0 left-0 h-full rounded-full"
          style={{ width: `${fillWidth}%`, background: fillColor }}
        />
        {c.min > 0 && (
          <div
            className="absolute top-0 h-full w-0.5"
            style={{ left: `${c.min}%`, background: "#d97706", zIndex: 2 }}
            title={`Min ${c.min}%`}
          />
        )}
        <div
          className="absolute top-0 h-full w-0.5"
          style={{
            left: `${Math.min(c.max, 100)}%`,
            background: "#dc2626",
            zIndex: 2,
          }}
          title={`Max ${c.max}%`}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-500 mt-1 px-0.5">
        <span>0%</span>
        <span>25%</span>
        <span>50%</span>
        <span>75%</span>
        <span>100%</span>
      </div>
    </div>
  );
}
