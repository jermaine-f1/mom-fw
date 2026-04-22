export interface EtfRow {
  ticker: string;
  name: string;
  sector: string;
  country: string;
  regions: string[];
  category: string;
  isETF: boolean;
  price: number | null;
  return6m: number;
  sortino: number;
  weeksDown: number;
  zScore: number;
  slope: number;
  aboveMA30: boolean;
  aboveMA60: boolean;
  aboveMA200: boolean;
  maxDD: number;
}

export interface RankedEtf extends EtfRow {
  score: number;
  maStatus: number;
}

export type Correlations = Record<string, number>;

export interface DataPayload {
  schemaVersion: number;
  generatedAt: string;
  etfUniverse: EtfRow[];
  correlations: Correlations;
}

export type ScoreMode = "quality" | "pure";

export interface ScoreSettings {
  mode: ScoreMode;
  weights: {
    sortino: number;
    weeksDown: number;
    zScore: number;
    slope: number;
  };
  topCount: number;
  zScoreSteep: number;
}

export const DEFAULT_SETTINGS: ScoreSettings = {
  mode: "quality",
  weights: { sortino: 40, weeksDown: 25, zScore: 20, slope: 15 },
  topCount: 20,
  zScoreSteep: 3.0,
};
