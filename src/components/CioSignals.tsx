import { useState } from "react";
import type { RankedEtf } from "../types";
import type { CioRegionKey } from "../lib/cio";
import { CioOverview } from "./CioOverview";
import { CioRegionPanel } from "./CioRegionPanel";
import { CioConstraints } from "./CioConstraints";

interface Props {
  ranked: RankedEtf[];
}

const SUB_TABS: { id: CioRegionKey; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "commodities", label: "Commodities" },
  { id: "em", label: "Emerging Mkts" },
  { id: "dm", label: "Developed Mkts" },
  { id: "us", label: "US" },
  { id: "taa", label: "TAA" },
];

export function CioSignals({ ranked }: Props) {
  const [active, setActive] = useState<CioRegionKey>("overview");

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        {SUB_TABS.map((t) => {
          const isActive = t.id === active;
          return (
            <button
              key={t.id}
              onClick={() => setActive(t.id)}
              className={
                "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors " +
                (isActive
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-800 text-slate-300 hover:bg-slate-700")
              }
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {active === "overview" ? (
        <CioOverview ranked={ranked} />
      ) : (
        <CioRegionPanel regionKey={active} ranked={ranked} />
      )}

      <CioConstraints />
    </div>
  );
}
