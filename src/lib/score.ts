import type { EtfRow, RankedEtf, ScoreSettings } from "../types";

const normalize = (val: number, min: number, max: number, inv = false) => {
  const n = Math.max(0, Math.min(100, ((val - min) / (max - min)) * 100));
  return inv ? 100 - n : n;
};

const maStatusOf = (etf: EtfRow) =>
  (etf.aboveMA30 ? 1 : 0) + (etf.aboveMA60 ? 1 : 0) + (etf.aboveMA200 ? 1 : 0);

export function calculateScore(etf: EtfRow, settings: ScoreSettings): RankedEtf {
  if (settings.mode === "pure") {
    const score = normalize(etf.return6m, -20, 40);
    return { ...etf, score, maStatus: maStatusOf(etf) };
  }

  const { weights } = settings;
  const totalWeight =
    weights.sortino + weights.weeksDown + weights.zScore + weights.slope;

  const sortinoScore = normalize(etf.sortino, -1, 2.5);
  const weeksDownScore = Math.min(85, normalize(etf.weeksDown, 0, 12, true));

  let excessiveScore: number;
  if (etf.zScore > settings.zScoreSteep) {
    excessiveScore = 100 - Math.pow(etf.zScore - settings.zScoreSteep, 2) * 100;
  } else if (etf.zScore > 2) {
    excessiveScore = 100 - (etf.zScore - 2) * 20;
  } else {
    excessiveScore = 100;
  }
  excessiveScore = Math.max(0, excessiveScore);

  const slopeScore =
    etf.slope > 0.45
      ? Math.min(70, normalize(etf.slope, -0.2, 0.5))
      : normalize(etf.slope, -0.2, 0.5);

  let total =
    (sortinoScore * weights.sortino) / totalWeight +
    (weeksDownScore * weights.weeksDown) / totalWeight +
    (excessiveScore * weights.zScore) / totalWeight +
    (slopeScore * weights.slope) / totalWeight;

  const isParabolic =
    etf.zScore > 2.5 && etf.weeksDown < 3 && etf.slope > 0.4;
  if (isParabolic) total *= 0.7;

  return { ...etf, score: total, maStatus: maStatusOf(etf) };
}

export function rankUniverse(
  universe: EtfRow[],
  settings: ScoreSettings,
): RankedEtf[] {
  return universe
    .map((e) => calculateScore(e, settings))
    .sort((a, b) => b.score - a.score);
}
