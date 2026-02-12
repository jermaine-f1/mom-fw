"""
CIO Momentum Dashboard - Real Data Generator
============================================
Run this locally to fetch live Yahoo Finance data and generate the dashboard.

Usage:
    pip install yfinance pandas numpy scipy
    python generate_cio_dashboard.py

Input:  mapping.csv (in same folder as this script)
        Columns: Name, Symbol, Region, Category, Subcategory, High Vol
        
Output: index.html
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
import json
import os
import warnings
warnings.filterwarnings('ignore')

# ============== CONFIGURATION ==============
RISK_FREE_RATE = 0.045  # Current ~4.5%


def clean_symbol(symbol):
    """Clean symbol for Yahoo Finance compatibility"""
    if pd.isna(symbol):
        return None
    
    symbol = str(symbol).strip()
    
    # Map of exchange suffixes to Yahoo Finance format
    # Most US exchanges (.O, .K) just need the suffix removed
    # Some international need different handling
    suffix_map = {
        '.O': '',      # NASDAQ
        '.K': '',      # NYSE Arca
        '.TO': '.TO',  # Toronto (keep)
        '.HK': '.HK',  # Hong Kong (keep)
        '.MI': '.MI',  # Milan (keep)
        '.WA': '.WA',  # Warsaw (keep)
        '.NS': '.NS',  # NSE India (keep)
        '.BO': '.BO',  # BSE India (keep)
        '.HM': '',     # Vietnam - may not work
        '.HNO': '',    # Vietnam - may not work
    }
    
    for suffix, replacement in suffix_map.items():
        if symbol.endswith(suffix):
            base = symbol[:-len(suffix)]
            return base + replacement
    
    return symbol


def load_etf_universe(csv_path):
    """Load ETF universe from CSV file (mapping.csv format)"""
    print(f"📂 Loading universe from: {csv_path}")
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"❌ File not found: {csv_path}")
    
    # Read CSV, handle BOM if present
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    # Validate required columns
    required_cols = ['Symbol', 'Region', 'Subcategory']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}. Found: {list(df.columns)}")
    
    # Clean symbols and remove duplicates
    df['CleanSymbol'] = df['Symbol'].apply(clean_symbol)
    df = df.dropna(subset=['CleanSymbol'])
    df = df.drop_duplicates(subset=['CleanSymbol'], keep='first')
    
    # Build lists and maps
    tickers = df['CleanSymbol'].tolist()
    
    # Use Subcategory as sector (more specific), Region as country
    sector_map = dict(zip(df['CleanSymbol'], df['Subcategory']))
    country_map = dict(zip(df['CleanSymbol'], df['Region']))
    
    # Also build name map for display
    name_map = {}
    if 'Name' in df.columns:
        name_map = dict(zip(df['CleanSymbol'], df['Name']))
    
    # Build high vol map
    highvol_map = {}
    if 'High Vol' in df.columns:
        highvol_map = dict(zip(df['CleanSymbol'], df['High Vol'].astype(str).str.upper() == 'TRUE'))
    
    # Build category map (ETF vs Equities)
    category_map = {}
    if 'Category' in df.columns:
        category_map = dict(zip(df['CleanSymbol'], df['Category']))
    
    print(f"✓ Loaded {len(tickers)} unique symbols")
    
    # Count ETFs vs non-ETFs
    etf_count = sum(1 for t in tickers if category_map.get(t, '').upper() == 'ETF')
    print(f"  → {etf_count} ETFs, {len(tickers) - etf_count} Equities/Other")
    
    return tickers, sector_map, country_map, name_map, highvol_map, category_map


def fetch_data(tickers):
    """Download historical data from Yahoo Finance"""
    print(f"📊 Fetching data for {len(tickers)} ETFs...")
    start_date = (datetime.now() - timedelta(days=3*365)).strftime('%Y-%m-%d')
    
    try:
        data = yf.download(tickers, start=start_date, progress=True)['Close']
        print(f"✓ Downloaded data from {start_date} to today")
        return data
    except Exception as e:
        print(f"❌ Error downloading data: {e}")
        return None


def calculate_metrics(prices, ticker, sector_map, country_map, name_map=None, category_map=None):
    """Calculate all momentum metrics for a single ETF"""
    try:
        prices = prices.dropna()
        if len(prices) < 252:  # Need at least 1 year
            return None
        
        current_price = prices.iloc[-1]
        daily_returns = prices.pct_change().dropna()
        weekly_prices = prices.resample('W').last().dropna()
        weekly_returns = weekly_prices.pct_change().dropna()
        
        # === 1. 6-MONTH RETURN ===
        six_month_idx = min(126, len(prices) - 1)
        six_month_price = prices.iloc[-six_month_idx]
        return_6m = ((current_price / six_month_price) - 1) * 100
        
        # === 2. SORTINO RATIO ===
        negative_returns = daily_returns[daily_returns < 0]
        downside_std = negative_returns.std() * np.sqrt(252)
        ann_return = daily_returns.mean() * 252
        sortino = (ann_return - RISK_FREE_RATE) / downside_std if downside_std > 0 else 0
        
        # === 3. WEEKS DOWN (last 12 weeks) ===
        recent_weekly = weekly_returns.iloc[-12:] if len(weekly_returns) >= 12 else weekly_returns
        weeks_down = int((recent_weekly < 0).sum())
        
        # === 4. Z-SCORE ===
        ma_200 = prices.rolling(window=200).mean()
        if len(ma_200.dropna()) < 100:
            z_score = 0
        else:
            prices_recent = prices.iloc[-756:] if len(prices) >= 756 else prices
            ma_200_recent = ma_200.iloc[-756:] if len(ma_200) >= 756 else ma_200
            ma_200_recent = ma_200_recent.dropna()
            prices_aligned = prices_recent.iloc[-len(ma_200_recent):]
            
            spread = prices_aligned - ma_200_recent.values
            spread_mean = spread.mean()
            spread_std = spread.std()
            current_spread = current_price - ma_200.iloc[-1]
            z_score = (current_spread - spread_mean) / spread_std if spread_std > 0 else 0
        
        # === 5. SLOPE (Trend Strength) ===
        prices_6m = prices.iloc[-126:] if len(prices) >= 126 else prices
        x = np.arange(len(prices_6m))
        slope, _, r_value, _, _ = stats.linregress(x, prices_6m.values)
        slope_normalized = (slope / prices_6m.mean()) * 100  # % per day
        
        # === 6. MOVING AVERAGES ===
        ma_30 = prices.rolling(window=30).mean().iloc[-1]
        ma_60 = prices.rolling(window=60).mean().iloc[-1]
        ma_200_current = ma_200.iloc[-1] if len(ma_200.dropna()) > 0 else current_price
        
        above_ma30 = current_price > ma_30
        above_ma60 = current_price > ma_60
        above_ma200 = current_price > ma_200_current
        
        # === MAX DRAWDOWN ===
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative / running_max) - 1
        max_dd = drawdown.min() * 100
        
        # Get name from map or use ticker
        name = name_map.get(ticker, ticker) if name_map else ticker
        
        # Determine if ETF
        category = category_map.get(ticker, '') if category_map else ''
        is_etf = category.upper() == 'ETF' or category.upper() == 'CASH'
        
        return {
            'ticker': ticker,
            'name': name,
            'sector': sector_map.get(ticker, 'Other'),
            'country': country_map.get(ticker, 'Other'),
            'category': category,
            'isETF': is_etf,
            'price': round(current_price, 2),
            'return6m': round(return_6m, 2),
            'sortino': round(sortino, 2),
            'weeksDown': weeks_down,
            'zScore': round(z_score, 2),
            'slope': round(slope_normalized, 3),
            'aboveMA30': bool(above_ma30),
            'aboveMA60': bool(above_ma60),
            'aboveMA200': bool(above_ma200),
            'maxDD': round(max_dd, 1),
        }
        
    except Exception as e:
        print(f"  ⚠️ Error processing {ticker}: {e}")
        return None


def calculate_correlations(prices, tickers):
    """Calculate pairwise correlations"""
    print("📈 Calculating correlations...")
    returns = prices[tickers].pct_change().dropna()
    corr_matrix = returns.corr()
    
    correlations = {}
    for i, t1 in enumerate(tickers):
        for t2 in tickers[i+1:]:
            try:
                corr = corr_matrix.loc[t1, t2]
                if not np.isnan(corr):
                    correlations[f"{t1}-{t2}"] = round(corr, 2)
            except:
                pass
    
    return correlations


def generate_html(etf_data, correlations, generation_date):
    """Generate the complete HTML dashboard"""
    
    # Convert to JSON for embedding
    etf_json = json.dumps(etf_data, indent=2)
    corr_json = json.dumps(correlations, indent=2)
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>📊 Momentum Portfolio Framework | CIO Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; }}
    .mono {{ font-family: 'SF Mono', 'Fira Code', monospace; }}
  </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 text-slate-100 p-4 md:p-6">
  <div class="max-w-7xl mx-auto">
    
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl md:text-3xl font-bold">📊 Momentum Portfolio Framework</h1>
      <p class="text-slate-400 text-sm">CIO Dashboard | Diversified Quality Momentum</p>
      <p class="text-emerald-400 text-xs mono mt-1">Live Data Generated: {generation_date}</p>
    </div>

    <!-- Tabs -->
    <div class="flex gap-2 mb-6 flex-wrap" id="tabs">
      <button onclick="showTab('strategy')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-indigo-600 text-white" data-tab="strategy">🎯 Strategy</button>
      <button onclick="showTab('signals')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-tab="signals">📡 Signals</button>
      <button onclick="showTab('portfolio')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-tab="portfolio">💼 Portfolio</button>
      <button onclick="showTab('rules')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-tab="rules">📋 Rules</button>
    </div>

    <!-- ===================== STRATEGY TAB ===================== -->
    <div id="tab-strategy" class="tab-content">
      <div class="space-y-6">
        
        <!-- Core Principles -->
        <div class="bg-indigo-900/20 border border-indigo-700/50 rounded-xl p-6">
          <h2 class="text-xl font-bold text-indigo-400 mb-4">🎯 Core Strategy Principles</h2>
          
          <div class="grid md:grid-cols-2 gap-6">
            
            <div class="bg-slate-800/50 rounded-lg p-4">
              <div class="text-lg font-bold text-emerald-400 mb-2">1. Momentum + Diversification</div>
              <ul class="text-sm text-slate-300 space-y-2">
                <li>• Buy ETFs with <strong>quality momentum</strong> (not just raw return)</li>
                <li>• Select holdings that are <strong>LOW correlation</strong> to each other</li>
                <li>• Spread across <strong>countries, sectors, asset classes</strong></li>
                <li>• Goal: Capture momentum while diversifying risk</li>
              </ul>
            </div>

            <div class="bg-slate-800/50 rounded-lg p-4">
              <div class="text-lg font-bold text-amber-400 mb-2">2. Many Small Bets</div>
              <ul class="text-sm text-slate-300 space-y-2">
                <li>• <strong>Equal weight</strong> or near-equal across positions</li>
                <li>• No single position &gt; <strong>15%</strong></li>
                <li>• Target <strong>6-10 positions</strong> for diversification</li>
                <li>• If one fails, portfolio survives</li>
              </ul>
            </div>

            <div class="bg-slate-800/50 rounded-lg p-4">
              <div class="text-lg font-bold text-red-400 mb-2">3. Cut Losers, Ride Winners</div>
              <ul class="text-sm text-slate-300 space-y-2">
                <li>• <strong>SELL when:</strong></li>
                <li class="ml-4">- Price breaks below MA30 or MA60</li>
                <li class="ml-4">- Weeks down rises (trend weakening)</li>
                <li class="ml-4">- Quality score deteriorates</li>
                <li>• <strong>HOLD winners until:</strong> Z-score &gt; 4 (extreme)</li>
              </ul>
            </div>

            <div class="bg-slate-800/50 rounded-lg p-4">
              <div class="text-lg font-bold text-cyan-400 mb-2">4. Quality Over Raw Return</div>
              <ul class="text-sm text-slate-300 space-y-2">
                <li>• Same 18% return - <strong>take the smoother trend</strong></li>
                <li>• Prioritize: High Sortino, few down weeks, steady slope</li>
                <li>• Avoid: Choppy, extended, parabolic moves</li>
                <li>• <strong>Sustainable &gt; Spectacular</strong></li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Quality Score Formula -->
        <div class="bg-slate-900/50 border border-slate-800 rounded-xl p-6">
          <h3 class="text-lg font-bold mb-4">📐 Quality Momentum Score</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div class="bg-slate-800 rounded-lg p-3 text-center">
              <div class="text-2xl font-bold text-indigo-400">40%</div>
              <div class="text-xs text-slate-400">Sortino Ratio</div>
              <div class="text-xs text-slate-500">Risk-adjusted return</div>
            </div>
            <div class="bg-slate-800 rounded-lg p-3 text-center">
              <div class="text-2xl font-bold text-indigo-400">25%</div>
              <div class="text-xs text-slate-400">Weeks Down (12wk)</div>
              <div class="text-xs text-slate-500">Trend weakening</div>
            </div>
            <div class="bg-slate-800 rounded-lg p-3 text-center">
              <div class="text-2xl font-bold text-indigo-400">20%</div>
              <div class="text-xs text-slate-400">Z-Score Penalty</div>
              <div class="text-xs text-slate-500">Bubble detection</div>
            </div>
            <div class="bg-slate-800 rounded-lg p-3 text-center">
              <div class="text-2xl font-bold text-indigo-400">15%</div>
              <div class="text-xs text-slate-400">Slope</div>
              <div class="text-xs text-slate-500">Trend strength</div>
            </div>
          </div>
          <div class="text-xs text-slate-500 bg-slate-800 p-2 rounded mono">
            + Hard filter: Z &gt; 4 = SELL | Parabolic combo = 30% penalty | Weeks down &amp; slope caps
          </div>
        </div>
      </div>
    </div>

    <!-- ===================== SIGNALS TAB ===================== -->
    <div id="tab-signals" class="tab-content hidden">
      <div class="space-y-6">
        
        <!-- Filter Controls -->
        <div class="bg-slate-900/50 rounded-xl border border-slate-800 p-4">
          <div class="flex flex-wrap items-center gap-4 mb-4">
            <span class="text-sm text-slate-400 font-medium">Filters:</span>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" id="etf-only-toggle" class="w-5 h-5 rounded" checked onchange="applyFilters()">
              <span class="text-sm">ETFs Only</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" id="buy-only-toggle" class="w-5 h-5 rounded" onchange="applyFilters()">
              <span class="text-sm">BUY Signals Only</span>
            </label>
            <div class="ml-auto text-sm text-slate-500">
              Showing: <span id="filter-count" class="text-indigo-400 font-bold">0</span> / <span id="total-count">0</span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-4">
            <span class="text-sm text-slate-400 font-medium">Search:</span>
            <input type="text" id="search-input" placeholder="Symbol, sector, region..." 
                   class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm w-64 focus:outline-none focus:border-indigo-500"
                   oninput="applyFilters()">
            <span class="text-sm text-slate-400 font-medium ml-4">Region:</span>
            <select id="region-filter" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-indigo-500" onchange="applyFilters()">
              <option value="">All Regions</option>
            </select>
            <span class="text-sm text-slate-400 font-medium ml-4">Sector:</span>
            <select id="sector-filter" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-indigo-500" onchange="applyFilters()">
              <option value="">All Sectors</option>
            </select>
            <button onclick="clearFilters()" class="ml-auto px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm transition-colors">
              ✕ Clear Filters
            </button>
          </div>
        </div>
        
        <!-- Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4" id="signal-summary">
          <!-- Filled by JS -->
        </div>

        <!-- Signals Table -->
        <div class="bg-slate-900/50 rounded-xl border border-slate-800 overflow-hidden">
          <div class="p-4 border-b border-slate-800 flex justify-between items-center">
            <h3 class="font-bold">All Instruments Ranked by Quality Score</h3>
            <span class="text-xs text-slate-500">Click column headers to sort</span>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="bg-slate-800 text-slate-400 text-xs uppercase">
                  <th class="px-3 py-2 text-left">#</th>
                  <th class="px-3 py-2 text-left cursor-pointer hover:text-white select-none" onclick="sortTable('ticker')">
                    Symbol <span id="sort-ticker" class="text-indigo-400"></span>
                  </th>
                  <th class="px-3 py-2 text-left cursor-pointer hover:text-white select-none" onclick="sortTable('isETF')">
                    Type <span id="sort-isETF" class="text-indigo-400"></span>
                  </th>
                  <th class="px-3 py-2 text-left cursor-pointer hover:text-white select-none" onclick="sortTable('country')">
                    Region <span id="sort-country" class="text-indigo-400"></span>
                  </th>
                  <th class="px-3 py-2 text-center cursor-pointer hover:text-white select-none" onclick="sortTable('signal')">
                    Signal <span id="sort-signal" class="text-indigo-400"></span>
                  </th>
                  <th class="px-3 py-2 text-right cursor-pointer hover:text-white select-none" onclick="sortTable('score')">
                    Score <span id="sort-score" class="text-indigo-400"></span>
                  </th>
                  <th class="px-3 py-2 text-right cursor-pointer hover:text-white select-none" onclick="sortTable('return6m')">
                    6M Ret <span id="sort-return6m" class="text-indigo-400"></span>
                  </th>
                  <th class="px-3 py-2 text-right cursor-pointer hover:text-white select-none" onclick="sortTable('sortino')">
                    Sortino <span id="sort-sortino" class="text-indigo-400"></span>
                  </th>
                  <th class="px-3 py-2 text-right cursor-pointer hover:text-white select-none" onclick="sortTable('weeksDown')">
                    Wks↓ <span id="sort-weeksDown" class="text-indigo-400"></span>
                  </th>
                  <th class="px-3 py-2 text-right cursor-pointer hover:text-white select-none" onclick="sortTable('zScore')">
                    Z <span id="sort-zScore" class="text-indigo-400"></span>
                  </th>
                  <th class="px-3 py-2 text-center cursor-pointer hover:text-white select-none" onclick="sortTable('maQuality')">
                    MA <span id="sort-maQuality" class="text-indigo-400"></span>
                  </th>
                </tr>
              </thead>
              <tbody id="signals-table">
                <!-- Filled by JS -->
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- ===================== PORTFOLIO TAB ===================== -->
    <div id="tab-portfolio" class="tab-content hidden">
      <div class="space-y-6">
        
        <!-- Portfolio Controls -->
        <div class="bg-slate-900/50 rounded-xl border border-slate-800 p-4">
          <h3 class="font-bold mb-4">⚙️ Portfolio Construction Parameters</h3>
          <div class="grid md:grid-cols-3 gap-4">
            <div>
              <label class="text-sm text-slate-400">Max Positions</label>
              <input type="range" min="4" max="12" value="8" id="maxPositions" class="w-full mt-1" onchange="updatePortfolio()">
              <div class="text-right text-sm mono text-indigo-400" id="maxPositionsVal">8</div>
            </div>
            <div>
              <label class="text-sm text-slate-400">Max Weight per Position</label>
              <input type="range" min="10" max="25" value="15" id="maxWeight" class="w-full mt-1" onchange="updatePortfolio()">
              <div class="text-right text-sm mono text-indigo-400" id="maxWeightVal">15%</div>
            </div>
            <div>
              <label class="text-sm text-slate-400">Max Pairwise Correlation</label>
              <input type="range" min="40" max="90" value="70" id="maxCorr" class="w-full mt-1" onchange="updatePortfolio()">
              <div class="text-right text-sm mono text-indigo-400" id="maxCorrVal">0.70</div>
            </div>
          </div>
        </div>

        <!-- Portfolio Stats -->
        <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4" id="portfolio-stats">
          <!-- Filled by JS -->
        </div>

        <!-- Recommended Portfolio -->
        <div class="bg-emerald-900/20 border border-emerald-700/50 rounded-xl p-4">
          <h3 class="font-bold text-emerald-400 mb-4">💼 Recommended Portfolio</h3>
          <div class="grid md:grid-cols-2 lg:grid-cols-4 gap-3" id="portfolio-holdings">
            <!-- Filled by JS -->
          </div>
        </div>

        <!-- Excluded -->
        <div class="bg-slate-900/50 rounded-xl border border-slate-800 p-4">
          <h3 class="font-bold text-slate-400 mb-2">🚫 Excluded (High Correlation)</h3>
          <p class="text-sm text-slate-500">These BUY signals were excluded to maintain diversification:</p>
          <div class="flex flex-wrap gap-2 mt-2" id="excluded-list">
            <!-- Filled by JS -->
          </div>
        </div>
      </div>
    </div>

    <!-- ===================== RULES TAB ===================== -->
    <div id="tab-rules" class="tab-content hidden">
      <div class="space-y-6">

        <!-- ========== SETTINGS SECTION ========== -->
        <div class="bg-amber-900/20 border border-amber-700/50 rounded-xl p-5">
          <h3 class="text-lg font-bold text-amber-400 mb-4">⚙️ Quality Momentum Settings</h3>
          
          <!-- Mode Toggle -->
          <div class="mb-6">
            <label class="text-sm text-slate-400 mb-2 block">Momentum Mode</label>
            <div class="flex gap-3">
              <button onclick="setMode('pure')" id="btn-pure" class="flex-1 p-3 rounded-lg border-2 border-slate-700 bg-slate-800 hover:border-orange-500 transition-all">
                <div class="font-bold text-orange-400">📈 Pure Return</div>
                <div class="text-xs text-slate-400">Simple 6M price momentum</div>
              </button>
              <button onclick="setMode('quality')" id="btn-quality" class="flex-1 p-3 rounded-lg border-2 border-emerald-500 bg-emerald-900/20 transition-all">
                <div class="font-bold text-emerald-400">🎯 Quality Momentum</div>
                <div class="text-xs text-slate-400">Risk-adjusted composite</div>
              </button>
            </div>
          </div>

          <!-- Quality Weights -->
          <div id="quality-settings">
            <div class="mb-4">
              <div class="flex justify-between items-center mb-2">
                <label class="text-sm text-slate-400">Component Weights</label>
                <span id="total-weight" class="text-sm mono px-2 py-1 rounded bg-emerald-900/50 text-emerald-400">Total: 100%</span>
              </div>
              <div class="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="bg-slate-800 rounded-lg p-3">
                  <label class="text-xs text-slate-400 block mb-1">Sortino Ratio</label>
                  <input type="range" min="0" max="100" value="40" id="w-sortino" class="w-full" oninput="updateWeights()">
                  <div class="flex justify-between text-xs mt-1">
                    <span class="text-slate-500">Risk-adjusted return</span>
                    <span class="mono text-indigo-400 font-bold" id="w-sortino-val">40%</span>
                  </div>
                </div>
                <div class="bg-slate-800 rounded-lg p-3">
                  <label class="text-xs text-slate-400 block mb-1">Weeks Down (12wk)</label>
                  <input type="range" min="0" max="100" value="25" id="w-weeksdown" class="w-full" oninput="updateWeights()">
                  <div class="flex justify-between text-xs mt-1">
                    <span class="text-slate-500">Trend weakening</span>
                    <span class="mono text-indigo-400 font-bold" id="w-weeksdown-val">25%</span>
                  </div>
                </div>
                <div class="bg-slate-800 rounded-lg p-3">
                  <label class="text-xs text-slate-400 block mb-1">Z-Score Penalty</label>
                  <input type="range" min="0" max="100" value="20" id="w-zscore" class="w-full" oninput="updateWeights()">
                  <div class="flex justify-between text-xs mt-1">
                    <span class="text-slate-500">Bubble detection</span>
                    <span class="mono text-indigo-400 font-bold" id="w-zscore-val">20%</span>
                  </div>
                </div>
                <div class="bg-slate-800 rounded-lg p-3">
                  <label class="text-xs text-slate-400 block mb-1">Slope</label>
                  <input type="range" min="0" max="100" value="15" id="w-slope" class="w-full" oninput="updateWeights()">
                  <div class="flex justify-between text-xs mt-1">
                    <span class="text-slate-500">Trend strength</span>
                    <span class="mono text-indigo-400 font-bold" id="w-slope-val">15%</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Thresholds -->
            <div class="mb-4">
              <label class="text-sm text-slate-400 mb-2 block">Thresholds</label>
              <div class="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="bg-slate-800 rounded-lg p-3">
                  <label class="text-xs text-slate-400 block mb-1">Z-Score Hard Limit (SELL)</label>
                  <input type="range" min="2" max="5" step="0.5" value="4" id="t-zscore" class="w-full" oninput="updateThresholds()">
                  <div class="flex justify-between text-xs mt-1">
                    <span class="text-slate-500">Above = bubble</span>
                    <span class="mono text-red-400 font-bold" id="t-zscore-val">4.0</span>
                  </div>
                </div>
                <div class="bg-slate-800 rounded-lg p-3">
                  <label class="text-xs text-slate-400 block mb-1">Z-Score Steep Penalty Start</label>
                  <input type="range" min="2" max="4" step="0.5" value="3" id="t-zscore-steep" class="w-full" oninput="updateThresholds()">
                  <div class="flex justify-between text-xs mt-1">
                    <span class="text-slate-500">Exponential above</span>
                    <span class="mono text-orange-400 font-bold" id="t-zscore-steep-val">3.0</span>
                  </div>
                </div>
                <div class="bg-slate-800 rounded-lg p-3">
                  <label class="text-xs text-slate-400 block mb-1">Max Weeks Down (SELL)</label>
                  <input type="range" min="4" max="12" value="8" id="t-weeksdown" class="w-full" oninput="updateThresholds()">
                  <div class="flex justify-between text-xs mt-1">
                    <span class="text-slate-500">Above = weakening</span>
                    <span class="mono text-red-400 font-bold" id="t-weeksdown-val">8</span>
                  </div>
                </div>
                <div class="bg-slate-800 rounded-lg p-3">
                  <label class="text-xs text-slate-400 block mb-1">Min Score for BUY</label>
                  <input type="range" min="40" max="70" value="55" id="t-minscore" class="w-full" oninput="updateThresholds()">
                  <div class="flex justify-between text-xs mt-1">
                    <span class="text-slate-500">Quality threshold</span>
                    <span class="mono text-emerald-400 font-bold" id="t-minscore-val">55</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- MA Filters -->
            <div>
              <label class="text-sm text-slate-400 mb-2 block">MA Quality Filters (Required for BUY)</label>
              <div class="flex flex-wrap gap-4">
                <label class="flex items-center gap-2 bg-slate-800 rounded-lg p-3 cursor-pointer hover:bg-slate-700">
                  <input type="checkbox" id="ma-30" checked class="w-5 h-5 rounded" onchange="updateFilters()">
                  <div>
                    <div class="font-medium text-sm">Above MA-30</div>
                    <div class="text-xs text-slate-400">Short-term trend</div>
                  </div>
                </label>
                <label class="flex items-center gap-2 bg-slate-800 rounded-lg p-3 cursor-pointer hover:bg-slate-700">
                  <input type="checkbox" id="ma-60" checked class="w-5 h-5 rounded" onchange="updateFilters()">
                  <div>
                    <div class="font-medium text-sm">Above MA-60</div>
                    <div class="text-xs text-slate-400">Medium-term trend</div>
                  </div>
                </label>
                <label class="flex items-center gap-2 bg-slate-800 rounded-lg p-3 cursor-pointer hover:bg-slate-700">
                  <input type="checkbox" id="ma-200" class="w-5 h-5 rounded" onchange="updateFilters()">
                  <div>
                    <div class="font-medium text-sm">Above MA-200</div>
                    <div class="text-xs text-slate-400">Long-term trend</div>
                  </div>
                </label>
              </div>
            </div>
          </div>

          <!-- Apply Button -->
          <div class="mt-4 flex gap-3">
            <button onclick="applySettings()" class="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-bold transition-colors">
              ✓ Apply & Recalculate
            </button>
            <button onclick="resetSettings()" class="px-6 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg font-medium transition-colors">
              ↺ Reset Defaults
            </button>
          </div>
        </div>

        <!-- Active Configuration Summary -->
        <div class="bg-slate-900/50 border border-slate-800 rounded-xl p-4">
          <h4 class="font-bold text-sm text-slate-400 mb-2">📐 Active Configuration</h4>
          <div class="mono text-xs bg-slate-800 p-3 rounded" id="config-summary">
            Mode: Quality Momentum | Weights: Sortino 40%, WeeksDown 25%, Z-Score 20%, Slope 15%
          </div>
        </div>

        <div class="grid md:grid-cols-2 gap-6">
          
          <!-- Entry Rules -->
          <div class="bg-emerald-900/20 border border-emerald-700/50 rounded-xl p-5">
            <h3 class="text-lg font-bold text-emerald-400 mb-4">✅ BUY Rules (Entry)</h3>
            <div class="space-y-3 text-sm">
              <div class="flex items-start gap-2">
                <span class="text-emerald-400">1.</span>
                <div>
                  <div class="font-medium">Quality Score ≥ 55</div>
                  <div class="text-slate-400">Composite of Sortino, weeks down, Z-score, slope</div>
                </div>
              </div>
              <div class="flex items-start gap-2">
                <span class="text-emerald-400">2.</span>
                <div>
                  <div class="font-medium">Above MA30 AND MA60</div>
                  <div class="text-slate-400">Short and medium term trends intact</div>
                </div>
              </div>
              <div class="flex items-start gap-2">
                <span class="text-emerald-400">3.</span>
                <div>
                  <div class="font-medium">Z-Score &lt; 4</div>
                  <div class="text-slate-400">Not in extreme/bubble territory</div>
                </div>
              </div>
              <div class="flex items-start gap-2">
                <span class="text-emerald-400">4.</span>
                <div>
                  <div class="font-medium">Low correlation to existing holdings</div>
                  <div class="text-slate-400">Max pairwise correlation threshold</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Exit Rules -->
          <div class="bg-red-900/20 border border-red-700/50 rounded-xl p-5">
            <h3 class="text-lg font-bold text-red-400 mb-4">🚫 SELL Rules (Exit)</h3>
            <div class="space-y-3 text-sm">
              <div class="flex items-start gap-2">
                <span class="text-red-400">1.</span>
                <div>
                  <div class="font-medium">Z-Score &gt; 4 (Extreme)</div>
                  <div class="text-slate-400">Take profits - bubble territory</div>
                </div>
              </div>
              <div class="flex items-start gap-2">
                <span class="text-red-400">2.</span>
                <div>
                  <div class="font-medium">Price breaks below MA30 or MA60</div>
                  <div class="text-slate-400">Trend is broken - cut the loss</div>
                </div>
              </div>
              <div class="flex items-start gap-2">
                <span class="text-red-400">3.</span>
                <div>
                  <div class="font-medium">Weeks Down ≥ 8 (of 12)</div>
                  <div class="text-slate-400">Trend weakening significantly</div>
                </div>
              </div>
              <div class="flex items-start gap-2">
                <span class="text-red-400">4.</span>
                <div>
                  <div class="font-medium">Quality Score drops below 40</div>
                  <div class="text-slate-400">Fundamental deterioration</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Position Sizing -->
          <div class="bg-amber-900/20 border border-amber-700/50 rounded-xl p-5">
            <h3 class="text-lg font-bold text-amber-400 mb-4">⚖️ Position Sizing</h3>
            <div class="space-y-3 text-sm">
              <div class="flex justify-between">
                <span class="text-slate-400">Target positions:</span>
                <span class="font-bold">6-10</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Max single position:</span>
                <span class="font-bold">15%</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Weighting method:</span>
                <span class="font-bold">Equal weight</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Rebalance frequency:</span>
                <span class="font-bold">Monthly</span>
              </div>
            </div>
          </div>

          <!-- Risk Management -->
          <div class="bg-cyan-900/20 border border-cyan-700/50 rounded-xl p-5">
            <h3 class="text-lg font-bold text-cyan-400 mb-4">🛡️ Risk Management</h3>
            <div class="space-y-3 text-sm">
              <div class="flex justify-between">
                <span class="text-slate-400">Max pairwise correlation:</span>
                <span class="font-bold">0.70</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Min countries:</span>
                <span class="font-bold">3+</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Min sectors:</span>
                <span class="font-bold">3+</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Max single country:</span>
                <span class="font-bold">40%</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Decision Tree -->
        <div class="bg-slate-900/50 rounded-xl border border-slate-800 p-5">
          <h3 class="text-lg font-bold mb-4">🌳 Decision Tree</h3>
          <div class="mono text-sm bg-slate-800 p-4 rounded overflow-x-auto">
            <pre class="text-slate-300">FOR each ETF in universe:
│
├─ IF Z-Score > 4 → SELL (extreme)
│
├─ ELSE IF below MA30 OR below MA60 → SELL (trend broken)
│
├─ ELSE IF weeks_down >= 8 → SELL (weakening)
│
├─ ELSE IF Z > 2.5 AND weeks_down < 3 AND slope > 0.4 → REDUCE (parabolic)
│
├─ ELSE IF quality_score >= 55 AND above_MA30 AND above_MA60:
│   │
│   ├─ IF correlation with portfolio < max_corr → BUY
│   │
│   └─ ELSE → SKIP (too correlated)
│
└─ ELSE → HOLD/AVOID</pre>
          </div>
        </div>
      </div>
    </div>

  </div>

  <script>
    // ========== LIVE DATA (Generated by Python) ==========
    const etfUniverse = {etf_json};
    const CORRELATIONS = {corr_json};

    // ========== SETTINGS STATE ==========
    let settings = {{
      mode: 'quality',
      weights: {{ sortino: 40, weeksDown: 25, zScore: 20, slope: 15 }},
      thresholds: {{ zScoreHard: 4.0, zScoreSteep: 3.0, weeksDown: 8, minScore: 55 }},
      maFilters: {{ ma30: true, ma60: true, ma200: false }}
    }};

    function getCorrelation(t1, t2) {{
      if (t1 === t2) return 1.0;
      return CORRELATIONS[`${{t1}}-${{t2}}`] || CORRELATIONS[`${{t2}}-${{t1}}`] || 0.5;
    }}

    // Calculate Quality Score
    function calculateScore(etf) {{
      const normalize = (val, min, max, inv = false) => {{
        const n = Math.max(0, Math.min(100, ((val - min) / (max - min)) * 100));
        return inv ? 100 - n : n;
      }};

      if (settings.mode === 'pure') {{
        const pureScore = normalize(etf.return6m, -20, 40);
        const maQuality = (etf.aboveMA30 ? 1 : 0) + (etf.aboveMA60 ? 1 : 0) + (etf.aboveMA200 ? 1 : 0);
        
        let maPass = true;
        if (settings.maFilters.ma30 && !etf.aboveMA30) maPass = false;
        if (settings.maFilters.ma60 && !etf.aboveMA60) maPass = false;
        if (settings.maFilters.ma200 && !etf.aboveMA200) maPass = false;

        let signal = 'HOLD';
        if (etf.zScore > settings.thresholds.zScoreHard) signal = 'SELL';
        else if (!maPass) signal = 'SELL';
        else if (etf.weeksDown >= settings.thresholds.weeksDown) signal = 'SELL';
        else if (pureScore >= settings.thresholds.minScore && maPass) signal = 'BUY';

        return {{ ...etf, score: pureScore, maQuality, maPass, signal, isParabolic: false }};
      }}

      const {{ weights, thresholds }} = settings;
      const totalWeight = weights.sortino + weights.weeksDown + weights.zScore + weights.slope;

      const sortinoScore = normalize(etf.sortino, -1, 2.5);
      const weeksDownScore = Math.min(85, normalize(etf.weeksDown, 0, 12, true));
      
      let excessiveScore;
      if (etf.zScore > thresholds.zScoreHard) excessiveScore = 0;
      else if (etf.zScore > thresholds.zScoreSteep) excessiveScore = 100 - Math.pow(etf.zScore - thresholds.zScoreSteep, 2) * 100;
      else if (etf.zScore > 2) excessiveScore = 100 - (etf.zScore - 2) * 20;
      else excessiveScore = 100;
      excessiveScore = Math.max(0, excessiveScore);

      const slopeScore = etf.slope > 0.45 ? Math.min(70, normalize(etf.slope, -0.2, 0.5)) : normalize(etf.slope, -0.2, 0.5);

      let total = (
        (sortinoScore * weights.sortino / totalWeight) +
        (weeksDownScore * weights.weeksDown / totalWeight) +
        (excessiveScore * weights.zScore / totalWeight) +
        (slopeScore * weights.slope / totalWeight)
      );

      const isParabolic = etf.zScore > 2.5 && etf.weeksDown < 3 && etf.slope > 0.4;
      if (isParabolic) total *= 0.7;

      const maQuality = (etf.aboveMA30 ? 1 : 0) + (etf.aboveMA60 ? 1 : 0) + (etf.aboveMA200 ? 1 : 0);
      
      let maPass = true;
      if (settings.maFilters.ma30 && !etf.aboveMA30) maPass = false;
      if (settings.maFilters.ma60 && !etf.aboveMA60) maPass = false;
      if (settings.maFilters.ma200 && !etf.aboveMA200) maPass = false;

      let signal = 'HOLD';
      if (etf.zScore > thresholds.zScoreHard) signal = 'SELL';
      else if (!maPass) signal = 'SELL';
      else if (etf.weeksDown >= thresholds.weeksDown) signal = 'SELL';
      else if (isParabolic) signal = 'REDUCE';
      else if (total >= thresholds.minScore && maPass) signal = 'BUY';

      return {{ ...etf, score: total, maQuality, maPass, signal, isParabolic }};
    }}

    let rankedETFs = etfUniverse.map(calculateScore).sort((a, b) => b.score - a.score);
    let filteredETFs = rankedETFs;
    let currentSort = {{ column: 'score', direction: 'desc' }};

    // Initialize filter dropdowns
    function initFilterDropdowns() {{
      const regions = [...new Set(etfUniverse.map(e => e.country))].sort();
      const sectors = [...new Set(etfUniverse.map(e => e.sector))].sort();
      
      const regionSelect = document.getElementById('region-filter');
      regions.forEach(r => {{
        const opt = document.createElement('option');
        opt.value = r;
        opt.textContent = r;
        regionSelect.appendChild(opt);
      }});
      
      const sectorSelect = document.getElementById('sector-filter');
      sectors.forEach(s => {{
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        sectorSelect.appendChild(opt);
      }});
    }}

    // Clear all filters
    function clearFilters() {{
      document.getElementById('etf-only-toggle').checked = true;
      document.getElementById('buy-only-toggle').checked = false;
      document.getElementById('search-input').value = '';
      document.getElementById('region-filter').value = '';
      document.getElementById('sector-filter').value = '';
      applyFilters();
    }}

    // Filter functions
    function applyFilters() {{
      const etfOnly = document.getElementById('etf-only-toggle').checked;
      const buyOnly = document.getElementById('buy-only-toggle').checked;
      const searchTerm = document.getElementById('search-input').value.toLowerCase();
      const regionFilter = document.getElementById('region-filter').value;
      const sectorFilter = document.getElementById('sector-filter').value;
      
      filteredETFs = rankedETFs.filter(e => {{
        if (etfOnly && !e.isETF) return false;
        if (buyOnly && e.signal !== 'BUY') return false;
        if (regionFilter && e.country !== regionFilter) return false;
        if (sectorFilter && e.sector !== sectorFilter) return false;
        if (searchTerm) {{
          const searchFields = [e.ticker, e.name, e.sector, e.country].join(' ').toLowerCase();
          if (!searchFields.includes(searchTerm)) return false;
        }}
        return true;
      }});
      
      // Apply current sort
      sortFilteredETFs();
      renderSignals();
      updatePortfolio();
    }}

    // Sort functions
    function sortTable(column) {{
      // Toggle direction if same column, otherwise default to desc for numbers, asc for strings
      if (currentSort.column === column) {{
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
      }} else {{
        currentSort.column = column;
        // Default sort direction based on column type
        const numericColumns = ['score', 'return6m', 'sortino', 'weeksDown', 'zScore', 'maQuality'];
        currentSort.direction = numericColumns.includes(column) ? 'desc' : 'asc';
      }}
      
      sortFilteredETFs();
      renderSignals();
    }}

    function sortFilteredETFs() {{
      const {{ column, direction }} = currentSort;
      const signalOrder = {{ 'BUY': 0, 'REDUCE': 1, 'HOLD': 2, 'SELL': 3 }};
      
      filteredETFs.sort((a, b) => {{
        let valA = a[column];
        let valB = b[column];
        
        // Special handling for signal column
        if (column === 'signal') {{
          valA = signalOrder[valA] ?? 4;
          valB = signalOrder[valB] ?? 4;
        }}
        
        // Handle booleans
        if (typeof valA === 'boolean') {{
          valA = valA ? 1 : 0;
          valB = valB ? 1 : 0;
        }}
        
        // Handle strings
        if (typeof valA === 'string') {{
          valA = valA.toLowerCase();
          valB = valB.toLowerCase();
        }}
        
        let result = 0;
        if (valA < valB) result = -1;
        if (valA > valB) result = 1;
        
        return direction === 'asc' ? result : -result;
      }});
      
      // Update sort indicators
      document.querySelectorAll('[id^="sort-"]').forEach(el => el.textContent = '');
      const indicator = document.getElementById(`sort-${{column}}`);
      if (indicator) {{
        indicator.textContent = direction === 'asc' ? '↑' : '↓';
      }}
    }}

    // Tab switching
    function showTab(tabId) {{
      document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
      document.getElementById('tab-' + tabId).classList.remove('hidden');
      
      document.querySelectorAll('.tab-btn').forEach(btn => {{
        btn.classList.remove('bg-indigo-600', 'bg-emerald-600', 'bg-amber-600', 'text-white');
        btn.classList.add('bg-slate-800', 'text-slate-300');
      }});
      
      const activeBtn = document.querySelector(`[data-tab="${{tabId}}"]`);
      const colors = {{ strategy: 'indigo', signals: 'emerald', portfolio: 'amber', rules: 'slate' }};
      activeBtn.classList.remove('bg-slate-800', 'text-slate-300');
      activeBtn.classList.add(`bg-${{colors[tabId]}}-600`, 'text-white');
    }}

    // Render signals
    function renderSignals() {{
      const buyCount = filteredETFs.filter(e => e.signal === 'BUY').length;
      const sellCount = filteredETFs.filter(e => e.signal === 'SELL').length;
      const holdCount = filteredETFs.filter(e => e.signal === 'HOLD' || e.signal === 'REDUCE').length;

      // Update filter counts
      document.getElementById('filter-count').textContent = filteredETFs.length;
      document.getElementById('total-count').textContent = rankedETFs.length;

      document.getElementById('signal-summary').innerHTML = `
        <div class="bg-emerald-900/30 border border-emerald-700/50 rounded-lg p-4 text-center">
          <div class="text-3xl font-bold text-emerald-400">${{buyCount}}</div>
          <div class="text-sm text-slate-400">BUY Signals</div>
        </div>
        <div class="bg-red-900/30 border border-red-700/50 rounded-lg p-4 text-center">
          <div class="text-3xl font-bold text-red-400">${{sellCount}}</div>
          <div class="text-sm text-slate-400">SELL Signals</div>
        </div>
        <div class="bg-slate-800 rounded-lg p-4 text-center">
          <div class="text-3xl font-bold text-slate-400">${{holdCount}}</div>
          <div class="text-sm text-slate-400">HOLD/REDUCE</div>
        </div>
        <div class="bg-slate-800 rounded-lg p-4 text-center">
          <div class="text-3xl font-bold text-indigo-400">${{filteredETFs.length}}</div>
          <div class="text-sm text-slate-400">Showing</div>
        </div>
      `;

      const tbody = document.getElementById('signals-table');
      tbody.innerHTML = filteredETFs.map((etf, i) => {{
        const signalColors = {{
          BUY: 'bg-emerald-900/50 text-emerald-400 border-emerald-500/50',
          SELL: 'bg-red-900/50 text-red-400 border-red-500/50',
          HOLD: 'bg-slate-700 text-slate-400 border-slate-600',
          REDUCE: 'bg-orange-900/50 text-orange-400 border-orange-500/50'
        }};
        const rowBg = etf.signal === 'BUY' ? 'bg-emerald-900/10' : etf.signal === 'SELL' ? 'bg-red-900/10' : '';
        const typeLabel = etf.isETF ? 'ETF' : 'Stock';
        const typeColor = etf.isETF ? 'text-cyan-400' : 'text-amber-400';
        
        return `
          <tr class="border-t border-slate-800 ${{rowBg}}">
            <td class="px-3 py-2 text-slate-500">${{i + 1}}</td>
            <td class="px-3 py-2">
              <div class="font-bold">${{etf.ticker}}</div>
              <div class="text-xs text-slate-500">${{etf.sector}}</div>
            </td>
            <td class="px-3 py-2 text-xs ${{typeColor}}">${{typeLabel}}</td>
            <td class="px-3 py-2 text-xs text-slate-400">${{etf.country}}</td>
            <td class="px-3 py-2 text-center">
              <span class="px-2 py-1 rounded text-xs font-bold border ${{signalColors[etf.signal]}}">${{etf.signal}}</span>
            </td>
            <td class="px-3 py-2 text-right mono font-bold text-indigo-400">${{etf.score.toFixed(1)}}</td>
            <td class="px-3 py-2 text-right mono ${{etf.return6m >= 0 ? 'text-emerald-400' : 'text-red-400'}}">
              ${{etf.return6m >= 0 ? '+' : ''}}${{etf.return6m.toFixed(1)}}%
            </td>
            <td class="px-3 py-2 text-right mono">${{etf.sortino.toFixed(2)}}</td>
            <td class="px-3 py-2 text-right mono ${{etf.weeksDown >= 8 ? 'text-red-400' : ''}}">${{etf.weeksDown}}/12</td>
            <td class="px-3 py-2 text-right mono ${{etf.zScore > 4 ? 'text-red-400 font-bold' : etf.zScore > 3 ? 'text-orange-400' : ''}}">${{etf.zScore.toFixed(1)}}</td>
            <td class="px-3 py-2 text-center ${{etf.maQuality === 3 ? 'text-emerald-400' : etf.maQuality >= 2 ? 'text-yellow-400' : 'text-red-400'}}">${{etf.maQuality}}/3</td>
          </tr>
        `;
      }}).join('');
    }}

    // Update portfolio
    function updatePortfolio() {{
      const maxPos = parseInt(document.getElementById('maxPositions').value);
      const maxWt = parseInt(document.getElementById('maxWeight').value);
      const maxCorr = parseInt(document.getElementById('maxCorr').value) / 100;

      document.getElementById('maxPositionsVal').textContent = maxPos;
      document.getElementById('maxWeightVal').textContent = maxWt + '%';
      document.getElementById('maxCorrVal').textContent = maxCorr.toFixed(2);

      const buySignals = filteredETFs.filter(e => e.signal === 'BUY');
      const portfolio = [];

      for (const etf of buySignals) {{
        if (portfolio.length >= maxPos) break;
        let tooCorrelated = false;
        for (const h of portfolio) {{
          if (getCorrelation(etf.ticker, h.ticker) > maxCorr) {{
            tooCorrelated = true;
            break;
          }}
        }}
        if (!tooCorrelated) portfolio.push(etf);
      }}

      if (portfolio.length === 0) {{
        document.getElementById('portfolio-stats').innerHTML = '<div class="col-span-full text-center text-slate-500">No positions match criteria</div>';
        document.getElementById('portfolio-holdings').innerHTML = '';
        document.getElementById('excluded-list').innerHTML = '';
        return;
      }}

      const weight = (100 / portfolio.length).toFixed(1);
      const avgRet = portfolio.reduce((s, e) => s + e.return6m, 0) / portfolio.length;
      const avgScore = portfolio.reduce((s, e) => s + e.score, 0) / portfolio.length;
      let totalCorr = 0, corrCount = 0;
      for (let i = 0; i < portfolio.length; i++) {{
        for (let j = i + 1; j < portfolio.length; j++) {{
          totalCorr += getCorrelation(portfolio[i].ticker, portfolio[j].ticker);
          corrCount++;
        }}
      }}
      const avgCorr = corrCount > 0 ? totalCorr / corrCount : 0;
      const countries = new Set(portfolio.map(e => e.country)).size;
      const sectors = new Set(portfolio.map(e => e.sector)).size;

      document.getElementById('portfolio-stats').innerHTML = `
        <div class="bg-slate-800 rounded-lg p-3 text-center">
          <div class="text-xl font-bold text-indigo-400">${{portfolio.length}}</div>
          <div class="text-xs text-slate-400">Positions</div>
        </div>
        <div class="bg-slate-800 rounded-lg p-3 text-center">
          <div class="text-xl font-bold text-emerald-400">${{avgRet >= 0 ? '+' : ''}}${{avgRet.toFixed(1)}}%</div>
          <div class="text-xs text-slate-400">Avg Return</div>
        </div>
        <div class="bg-slate-800 rounded-lg p-3 text-center">
          <div class="text-xl font-bold text-indigo-400">${{avgScore.toFixed(1)}}</div>
          <div class="text-xs text-slate-400">Avg Score</div>
        </div>
        <div class="bg-slate-800 rounded-lg p-3 text-center">
          <div class="text-xl font-bold text-amber-400">${{avgCorr.toFixed(2)}}</div>
          <div class="text-xs text-slate-400">Avg Corr</div>
        </div>
        <div class="bg-slate-800 rounded-lg p-3 text-center">
          <div class="text-xl font-bold text-cyan-400">${{countries}}</div>
          <div class="text-xs text-slate-400">Countries</div>
        </div>
        <div class="bg-slate-800 rounded-lg p-3 text-center">
          <div class="text-xl font-bold text-purple-400">${{sectors}}</div>
          <div class="text-xs text-slate-400">Sectors</div>
        </div>
      `;

      document.getElementById('portfolio-holdings').innerHTML = portfolio.map(etf => `
        <div class="bg-slate-800 rounded-lg p-3">
          <div class="flex justify-between items-start mb-2">
            <div>
              <div class="font-bold">${{etf.ticker}}</div>
              <div class="text-xs text-slate-400">${{etf.country}} • ${{etf.sector}}</div>
            </div>
            <div class="text-lg font-bold text-amber-400">${{weight}}%</div>
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div><span class="text-slate-500">Return:</span> <span class="${{etf.return6m >= 0 ? 'text-emerald-400' : 'text-red-400'}}">${{etf.return6m >= 0 ? '+' : ''}}${{etf.return6m}}%</span></div>
            <div><span class="text-slate-500">Score:</span> <span class="text-indigo-400">${{etf.score.toFixed(1)}}</span></div>
          </div>
        </div>
      `).join('');

      const excluded = buySignals.filter(e => !portfolio.find(p => p.ticker === e.ticker));
      document.getElementById('excluded-list').innerHTML = excluded.map(e => 
        `<span class="px-2 py-1 bg-slate-800 rounded text-sm">${{e.ticker}} <span class="text-slate-500">(${{e.country}})</span></span>`
      ).join('');
    }}

    // Settings functions
    function setMode(mode) {{
      settings.mode = mode;
      document.getElementById('btn-pure').className = mode === 'pure' 
        ? 'flex-1 p-3 rounded-lg border-2 border-orange-500 bg-orange-900/20 transition-all'
        : 'flex-1 p-3 rounded-lg border-2 border-slate-700 bg-slate-800 hover:border-orange-500 transition-all';
      document.getElementById('btn-quality').className = mode === 'quality'
        ? 'flex-1 p-3 rounded-lg border-2 border-emerald-500 bg-emerald-900/20 transition-all'
        : 'flex-1 p-3 rounded-lg border-2 border-slate-700 bg-slate-800 hover:border-emerald-500 transition-all';
      document.getElementById('quality-settings').style.display = mode === 'quality' ? 'block' : 'none';
      updateConfigSummary();
    }}

    function updateWeights() {{
      settings.weights.sortino = parseInt(document.getElementById('w-sortino').value);
      settings.weights.weeksDown = parseInt(document.getElementById('w-weeksdown').value);
      settings.weights.zScore = parseInt(document.getElementById('w-zscore').value);
      settings.weights.slope = parseInt(document.getElementById('w-slope').value);

      document.getElementById('w-sortino-val').textContent = settings.weights.sortino + '%';
      document.getElementById('w-weeksdown-val').textContent = settings.weights.weeksDown + '%';
      document.getElementById('w-zscore-val').textContent = settings.weights.zScore + '%';
      document.getElementById('w-slope-val').textContent = settings.weights.slope + '%';

      const total = settings.weights.sortino + settings.weights.weeksDown + settings.weights.zScore + settings.weights.slope;
      const totalEl = document.getElementById('total-weight');
      totalEl.textContent = 'Total: ' + total + '%';
      totalEl.className = total === 100 
        ? 'text-sm mono px-2 py-1 rounded bg-emerald-900/50 text-emerald-400'
        : 'text-sm mono px-2 py-1 rounded bg-red-900/50 text-red-400';
      
      updateConfigSummary();
    }}

    function updateThresholds() {{
      settings.thresholds.zScoreHard = parseFloat(document.getElementById('t-zscore').value);
      settings.thresholds.zScoreSteep = parseFloat(document.getElementById('t-zscore-steep').value);
      settings.thresholds.weeksDown = parseInt(document.getElementById('t-weeksdown').value);
      settings.thresholds.minScore = parseInt(document.getElementById('t-minscore').value);

      document.getElementById('t-zscore-val').textContent = settings.thresholds.zScoreHard.toFixed(1);
      document.getElementById('t-zscore-steep-val').textContent = settings.thresholds.zScoreSteep.toFixed(1);
      document.getElementById('t-weeksdown-val').textContent = settings.thresholds.weeksDown;
      document.getElementById('t-minscore-val').textContent = settings.thresholds.minScore;
      
      updateConfigSummary();
    }}

    function updateFilters() {{
      settings.maFilters.ma30 = document.getElementById('ma-30').checked;
      settings.maFilters.ma60 = document.getElementById('ma-60').checked;
      settings.maFilters.ma200 = document.getElementById('ma-200').checked;
      updateConfigSummary();
    }}

    function updateConfigSummary() {{
      const {{ mode, weights, thresholds, maFilters }} = settings;
      const modeText = mode === 'pure' ? 'Pure Return' : 'Quality Momentum';
      const weightsText = mode === 'pure' ? 'N/A' : 
        `Sortino ${{weights.sortino}}%, WeeksDown ${{weights.weeksDown}}%, Z-Score ${{weights.zScore}}%, Slope ${{weights.slope}}%`;
      const maText = `${{maFilters.ma30 ? '30✓' : '30✗'}} ${{maFilters.ma60 ? '60✓' : '60✗'}} ${{maFilters.ma200 ? '200✓' : '200✗'}}`;
      
      document.getElementById('config-summary').textContent = 
        `Mode: ${{modeText}} | Weights: ${{weightsText}} | Z-Limit: ${{thresholds.zScoreHard}} | MA: ${{maText}}`;
    }}

    function applySettings() {{
      rankedETFs = etfUniverse.map(calculateScore).sort((a, b) => b.score - a.score);
      applyFilters();  // This will update filteredETFs and call renderSignals + updatePortfolio
    }}

    function resetSettings() {{
      settings = {{
        mode: 'quality',
        weights: {{ sortino: 40, weeksDown: 25, zScore: 20, slope: 15 }},
        thresholds: {{ zScoreHard: 4.0, zScoreSteep: 3.0, weeksDown: 8, minScore: 55 }},
        maFilters: {{ ma30: true, ma60: true, ma200: false }}
      }};

      document.getElementById('w-sortino').value = 40;
      document.getElementById('w-weeksdown').value = 25;
      document.getElementById('w-zscore').value = 20;
      document.getElementById('w-slope').value = 15;
      document.getElementById('t-zscore').value = 4;
      document.getElementById('t-zscore-steep').value = 3;
      document.getElementById('t-weeksdown').value = 8;
      document.getElementById('t-minscore').value = 55;
      document.getElementById('ma-30').checked = true;
      document.getElementById('ma-60').checked = true;
      document.getElementById('ma-200').checked = false;

      updateWeights();
      updateThresholds();
      updateFilters();
      setMode('quality');
      applySettings();
    }}

    // Initialize
    initFilterDropdowns();
    applyFilters();  // This sets filteredETFs and renders
    updateConfigSummary();
  </script>
</body>
</html>'''
    
    return html


def main():
    print("=" * 60)
    print("📊 CIO Momentum Dashboard Generator")
    print("=" * 60)
    
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "mapping.csv")
    
    # Load universe from CSV
    tickers, sector_map, country_map, name_map, highvol_map, category_map = load_etf_universe(csv_path)
    
    # Fetch data
    prices = fetch_data(tickers)
    if prices is None:
        return
    
    # Calculate metrics for each ticker
    print("\n📈 Calculating metrics...")
    etf_data = []
    for ticker in tickers:
        if ticker in prices.columns:
            metrics = calculate_metrics(prices[ticker], ticker, sector_map, country_map, name_map, category_map)
            if metrics:
                etf_data.append(metrics)
                etf_label = "ETF" if metrics['isETF'] else "EQ"
                print(f"  ✓ {ticker} [{etf_label}]: {metrics['return6m']:+.1f}% | Sortino: {metrics['sortino']:.2f} | Z: {metrics['zScore']:.2f}")
    
    print(f"\n✓ Processed {len(etf_data)} symbols")
    
    # Calculate correlations
    valid_tickers = [e['ticker'] for e in etf_data]
    correlations = calculate_correlations(prices, valid_tickers)
    print(f"✓ Calculated {len(correlations)} pairwise correlations")
    
    # Generate HTML
    generation_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = generate_html(etf_data, correlations, generation_date)
    
    # Save to same directory as script
    output_file = os.path.join(script_dir, "index.html")
    with open(output_file, 'w') as f:
        f.write(html)

    print(f"\n✅ Dashboard saved to: {output_file}")

    # Sync to sibling mom-fw-ui repo if it exists
    ui_repo_dir = os.path.join(os.path.dirname(script_dir), "mom-fw-ui")
    ui_index = os.path.join(ui_repo_dir, "index.html")
    if os.path.isdir(ui_repo_dir):
        with open(ui_index, 'w') as f:
            f.write(html)
        print(f"✅ Synced to: {ui_index}")
    else:
        print(f"⚠️  mom-fw-ui not found at {ui_repo_dir} — skipping UI sync")

    print("   Open in browser to view")
    print("=" * 60)


if __name__ == "__main__":
    main()