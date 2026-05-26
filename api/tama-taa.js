import fs from 'node:fs';
import path from 'node:path';

// Extract the `const etfUniverse = [ ... ];` array literal from index.html
// by brace/bracket counting so we tolerate nested objects without a JS parser.
function extractEtfUniverse(html) {
  const marker = 'const etfUniverse = ';
  const start = html.indexOf(marker);
  if (start === -1) throw new Error('etfUniverse marker not found in index.html');
  let i = start + marker.length;
  while (i < html.length && html[i] !== '[' && html[i] !== '{') i++;
  if (i >= html.length) throw new Error('etfUniverse opening bracket not found');
  const open = html[i];
  const close = open === '[' ? ']' : '}';
  let depth = 0;
  const begin = i;
  for (; i < html.length; i++) {
    const c = html[i];
    if (c === open) depth++;
    else if (c === close) {
      depth--;
      if (depth === 0) {
        const json = html.slice(begin, i + 1);
        return JSON.parse(json);
      }
    }
  }
  throw new Error('etfUniverse closing bracket not found');
}

function extractGenerationDate(html) {
  const m = html.match(/Live Data Generated:\s*([^<]+)</);
  return m ? m[1].trim() : null;
}

// Mirror of mom_gen.py's embedded JS calculateScore.
function calculateScore(etf, settings) {
  const normalize = (val, min, max, inv = false) => {
    const n = Math.max(0, Math.min(100, ((val - min) / (max - min)) * 100));
    return inv ? 100 - n : n;
  };
  const maStatus =
    (etf.aboveMA30 ? 1 : 0) + (etf.aboveMA60 ? 1 : 0) + (etf.aboveMA200 ? 1 : 0);

  if (settings.mode === 'pure') {
    const score = normalize(etf.return6m, -20, 40);
    return { ...etf, score, maStatus };
  }

  const { weights } = settings;
  const totalWeight = weights.sortino + weights.weeksDown + weights.zScore + weights.slope;

  const sortinoScore = normalize(etf.sortino, -1, 2.5);
  const weeksDownScore = Math.min(85, normalize(etf.weeksDown, 0, 12, true));

  let excessiveScore;
  if (etf.zScore > settings.zScoreSteep)
    excessiveScore = 100 - Math.pow(etf.zScore - settings.zScoreSteep, 2) * 100;
  else if (etf.zScore > 2) excessiveScore = 100 - (etf.zScore - 2) * 20;
  else excessiveScore = 100;
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

  const isParabolic = etf.zScore > 2.5 && etf.weeksDown < 3 && etf.slope > 0.4;
  if (isParabolic) total *= 0.7;

  return { ...etf, score: total, maStatus };
}

// Mirror of mom_gen.py's embedded JS applyTAMA: z-score of score * (0.5 + 0.5 * MA/3)
// over the FULL screener universe, not just the TAA subset — matches the UI.
function applyTAMA(etfs) {
  const raws = etfs.map((e) => e.score * (0.5 + 0.5 * (e.maStatus / 3)));
  const mean = raws.reduce((a, b) => a + b, 0) / raws.length;
  const variance = raws.reduce((s, v) => s + (v - mean) ** 2, 0) / raws.length;
  const std = Math.sqrt(variance);
  etfs.forEach((e, i) => {
    e.tamaRaw = raws[i];
    e.tama = std > 0 ? (raws[i] - mean) / std : 0;
  });
  return etfs;
}

function parseSettings(query) {
  const num = (v, fallback) => {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : fallback;
  };
  return {
    mode: query.mode === 'pure' ? 'pure' : 'quality',
    weights: {
      sortino: num(query.w_sortino, 40),
      weeksDown: num(query.w_weeksDown, 25),
      zScore: num(query.w_zScore, 20),
      slope: num(query.w_slope, 15),
    },
    zScoreSteep: num(query.zScoreSteep, 3.0),
  };
}

let cached = null; // { mtimeMs, html }

function readIndexHtml() {
  const indexPath = path.join(process.cwd(), 'index.html');
  const stat = fs.statSync(indexPath);
  if (!cached || cached.mtimeMs !== stat.mtimeMs) {
    cached = { mtimeMs: stat.mtimeMs, html: fs.readFileSync(indexPath, 'utf8') };
  }
  return cached.html;
}

export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const html = readIndexHtml();
    const universe = extractEtfUniverse(html);
    const generatedAt = extractGenerationDate(html);
    const settings = parseSettings(req.query || {});

    const scored = applyTAMA(universe.map((e) => calculateScore(e, settings)));
    const taa = scored
      .filter((e) => Array.isArray(e.regions) && e.regions.includes('TAA ETFs'))
      .map((e) => ({
        symbol: e.ticker,
        name: e.name,
        country: e.country,
        regions: e.regions,
        sector: e.sector,
        tama: Number(e.tama.toFixed(4)),
        score: Number(e.score.toFixed(4)),
        maStatus: e.maStatus,
        return6m: e.return6m,
        sortino: e.sortino,
        zScore: e.zScore,
      }))
      .sort((a, b) => b.tama - a.tama);

    res.setHeader('Cache-Control', 'public, max-age=60, s-maxage=60');
    return res.status(200).json({
      generatedAt,
      settings,
      count: taa.length,
      items: taa,
    });
  } catch (err) {
    console.error('tama-taa error:', err);
    return res.status(500).json({ error: err.message });
  }
}
