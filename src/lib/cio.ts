import type { RankedEtf } from "../types";

export type CioRegionKey =
  | "overview"
  | "commodities"
  | "em"
  | "dm"
  | "us"
  | "taa";

export interface CioRegionConfig {
  label: string;
  filter: (e: RankedEtf) => boolean;
}

export const CIO_REGIONS: Record<CioRegionKey, CioRegionConfig> = {
  overview: { label: "All Regions", filter: () => true },
  commodities: {
    label: "Commodities",
    filter: (e) => e.regions.includes("Commodities"),
  },
  em: {
    label: "Emerging Markets",
    filter: (e) =>
      e.regions.includes("Emerging Markets") || e.regions.includes("India"),
  },
  dm: {
    label: "Developed Markets",
    filter: (e) => e.regions.includes("Developed Markets"),
  },
  us: { label: "US", filter: (e) => e.regions.includes("US") },
  taa: { label: "TAA", filter: (e) => e.regions.includes("TAA ETFs") },
};

export interface CioRegionAggregate {
  etfs: RankedEtf[];
  label: string;
  total: number;
  maIntact: number; // 3/3
  fullStack: number; // ≥2/3
  maBroken: number; // 0/3
  avgWksDown: number;
  breadthPct: number;
}

export function getCioRegionData(
  regionKey: CioRegionKey,
  rankedETFs: RankedEtf[],
): CioRegionAggregate {
  const cfg = CIO_REGIONS[regionKey];
  const etfs = rankedETFs.filter((e) => e.isETF && cfg.filter(e));
  const maIntact = etfs.filter((e) => e.maStatus === 3).length;
  const fullStack = etfs.filter((e) => e.maStatus >= 2).length;
  const maBroken = etfs.filter((e) => e.maStatus === 0).length;
  const avgWksDown =
    etfs.length > 0 ? etfs.reduce((s, e) => s + e.weeksDown, 0) / etfs.length : 0;
  const breadthPct = etfs.length > 0 ? (maIntact / etfs.length) * 100 : 0;
  return {
    etfs,
    label: cfg.label,
    total: etfs.length,
    maIntact,
    fullStack,
    maBroken,
    avgWksDown,
    breadthPct,
  };
}

export function zScoreColor(z: number): string {
  if (z <= 0.5) return "#6366f1"; // indigo — deeply oversold
  if (z <= 1.0) return "#22c55e"; // green — normal
  if (z <= 2.0) return "#eab308"; // yellow — warm
  if (z <= 3.0) return "#f97316"; // orange — extended
  return "#ef4444"; // red — extreme
}

// ========== CIO Asset-Class Constraints ==========

export interface CioConstraint {
  id: string;
  name: string;
  color: string;
  current: number;
  min: number;
  max: number;
}

export const CIO_CONSTRAINT_DEFAULTS: CioConstraint[] = [
  { id: "em", name: "EM", color: "#10b981", current: 31.4, min: 0, max: 30 },
  { id: "dm", name: "DM", color: "#818cf8", current: 18.1, min: 0, max: 30 },
  {
    id: "commodities",
    name: "Commodities",
    color: "#f59e0b",
    current: 25.3,
    min: 0,
    max: 35,
  },
  {
    id: "cash",
    name: "Cash",
    color: "#22d3ee",
    current: 25.2,
    min: 5,
    max: 40,
  },
];

const CONSTRAINTS_STORAGE_KEY = "cioConstraints";

export function loadStoredConstraints(): CioConstraint[] {
  try {
    const saved = localStorage.getItem(CONSTRAINTS_STORAGE_KEY);
    if (!saved) return cloneDefaults();
    const parsed = JSON.parse(saved) as unknown;
    if (!Array.isArray(parsed)) return cloneDefaults();
    // Shape-check each entry to keep a corrupt localStorage from crashing render.
    const validated = parsed.filter(
      (c): c is CioConstraint =>
        !!c &&
        typeof c === "object" &&
        typeof (c as CioConstraint).id === "string" &&
        typeof (c as CioConstraint).current === "number" &&
        typeof (c as CioConstraint).min === "number" &&
        typeof (c as CioConstraint).max === "number",
    );
    if (validated.length !== CIO_CONSTRAINT_DEFAULTS.length) {
      return cloneDefaults();
    }
    return validated;
  } catch {
    return cloneDefaults();
  }
}

export function saveStoredConstraints(constraints: CioConstraint[]): void {
  try {
    localStorage.setItem(CONSTRAINTS_STORAGE_KEY, JSON.stringify(constraints));
  } catch {
    // localStorage may be disabled or full; degrade silently but log.
    console.warn("Failed to persist CIO constraints to localStorage");
  }
}

export function clearStoredConstraints(): void {
  try {
    localStorage.removeItem(CONSTRAINTS_STORAGE_KEY);
  } catch {
    // Ignore.
  }
}

function cloneDefaults(): CioConstraint[] {
  return CIO_CONSTRAINT_DEFAULTS.map((c) => ({ ...c }));
}
