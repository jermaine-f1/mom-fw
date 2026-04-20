"""
CIO Momentum Dashboard - Real Data Generator
============================================
Run this locally to fetch live Yahoo Finance data and generate the dashboard.

Usage:
    pip install yfinance pandas numpy scipy
    python mom_gen.py

Input:  mapping.csv (in same folder as this script)
        Columns: Name, Symbol, Region, Category, Subcategory, High Vol
        
Output: index.html
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
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
    
    suffix_map = {
        '.O': '',      # NASDAQ
        '.K': '',      # NYSE Arca
        '.TO': '.TO',  # Toronto (keep)
        '.HK': '.HK',  # Hong Kong (keep)
        '.MI': '.MI',  # Milan (keep)
        '.WA': '.WA',  # Warsaw (keep)
        '.NS': '.NS',  # NSE India (keep)
        '.BO': '.BO',  # BSE India (keep)
        '.HM': '',     # Vietnam
        '.HNO': '',    # Vietnam
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
    
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    required_cols = ['Symbol', 'Region', 'Subcategory']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}. Found: {list(df.columns)}")
    
    df['CleanSymbol'] = df['Symbol'].apply(clean_symbol)
    df = df.dropna(subset=['CleanSymbol'])

    # Collect all unique regions per ticker before deduplication
    regions_map = {}
    for _, row in df.iterrows():
        sym = row['CleanSymbol']
        region = row['Region']
        if sym not in regions_map:
            regions_map[sym] = []
        if region not in regions_map[sym]:
            regions_map[sym].append(region)

    df = df.drop_duplicates(subset=['CleanSymbol'], keep='first')

    tickers = df['CleanSymbol'].tolist()
    sector_map = dict(zip(df['CleanSymbol'], df['Subcategory']))
    country_map = dict(zip(df['CleanSymbol'], df['Region']))
    
    name_map = {}
    if 'Name' in df.columns:
        name_map = dict(zip(df['CleanSymbol'], df['Name']))
    
    highvol_map = {}
    if 'High Vol' in df.columns:
        highvol_map = dict(zip(df['CleanSymbol'], df['High Vol'].astype(str).str.upper() == 'TRUE'))
    
    category_map = {}
    if 'Category' in df.columns:
        category_map = dict(zip(df['CleanSymbol'], df['Category']))
    
    print(f"✓ Loaded {len(tickers)} unique symbols")
    etf_count = sum(1 for t in tickers if category_map.get(t, '').upper() == 'ETF')
    print(f"  → {etf_count} ETFs, {len(tickers) - etf_count} Equities/Other")
    
    return tickers, sector_map, country_map, name_map, highvol_map, category_map, regions_map


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


def calculate_metrics(prices, ticker, sector_map, country_map, name_map=None, category_map=None, regions_map=None):
    """Calculate all momentum metrics for a single ETF"""
    try:
        prices = prices.dropna()
        if len(prices) < 252:
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
        slope_normalized = (slope / prices_6m.mean()) * 100
        
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
        
        name = name_map.get(ticker, ticker) if name_map else ticker
        category = category_map.get(ticker, '') if category_map else ''
        is_etf = category.upper() == 'ETF' or category.upper() == 'CASH'
        
        return {
            'ticker': ticker,
            'name': name,
            'sector': sector_map.get(ticker, 'Other'),
            'country': country_map.get(ticker, 'Other'),
            'regions': (regions_map or {}).get(ticker, [country_map.get(ticker, 'Other')]),
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
    .top-idea-row {{ background: linear-gradient(90deg, rgba(99,102,241,0.08) 0%, transparent 100%); }}
  </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 text-slate-100 p-4 md:p-6">
  <div class="max-w-7xl mx-auto">
    
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl md:text-3xl font-bold">📊 Momentum Portfolio Framework</h1>
      <p class="text-slate-400 text-sm">CIO Dashboard | Diversified Quality Momentum Screener</p>
      <p class="text-emerald-400 text-xs mono mt-1">Live Data Generated: {generation_date}</p>
    </div>

    <!-- Tabs -->
    <div class="flex gap-2 mb-6 flex-wrap" id="tabs">
      <button onclick="showTab('signals')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-indigo-600 text-white" data-tab="signals">📡 Screener</button>
      <button onclick="showTab('portfolio')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-tab="portfolio">💼 Portfolio</button>
      <button onclick="showTab('analyzer')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-tab="analyzer">📊 Portfolio Analyzer</button>
      <button onclick="showTab('cio')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-tab="cio">🏛️ CIO Signals</button>
      <button onclick="showTab('strategy')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-tab="strategy">🎯 Strategy</button>
      <button onclick="showTab('rules')" class="tab-btn px-4 py-2 rounded-lg font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-tab="rules">⚙️ Settings</button>
    </div>

    <!-- ===================== SCREENER TAB (was Signals) ===================== -->
    <div id="tab-signals" class="tab-content">
      <div class="space-y-6">
        
        <!-- Filter Controls -->
        <div class="bg-slate-900/50 rounded-xl border border-slate-800 p-4">
          <div class="flex flex-wrap items-center gap-4 mb-4">
            <span class="text-sm text-slate-400 font-medium">View:</span>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" id="etf-only-toggle" class="w-5 h-5 rounded" checked onchange="applyFilters()">
              <span class="text-sm">ETFs Only</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" id="top-ideas-toggle" class="w-5 h-5 rounded" onchange="applyFilters()">
              <span class="text-sm">⭐ Top Ideas Only</span>
            </label>
            <div class="ml-auto text-sm text-slate-500">
              Showing: <span id="filter-count" class="text-indigo-400 font-bold">0</span> / <span id="total-count">0</span>
            </div>
          </div>

          <!-- Search & Dropdowns -->
          <div class="flex flex-wrap items-center gap-4 mb-4">
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
              ✕ Clear All
            </button>
          </div>

          <!-- Toggleable Narrowing Filters — all OFF by default -->
          <div class="border-t border-slate-700 pt-4">
            <span class="text-sm text-slate-400 font-medium mb-3 block">Narrowing Filters (all off by default):</span>
            <div class="flex flex-wrap items-center gap-5">
              <label class="flex items-center gap-2 cursor-pointer bg-slate-800/50 rounded-lg px-3 py-2 hover:bg-slate-700/50 transition-colors">
                <input type="checkbox" id="filter-ma30" class="w-4 h-4 rounded" onchange="applyFilters()">
                <span class="text-sm">Above MA-30</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer bg-slate-800/50 rounded-lg px-3 py-2 hover:bg-slate-700/50 transition-colors">
                <input type="checkbox" id="filter-ma60" class="w-4 h-4 rounded" onchange="applyFilters()">
                <span class="text-sm">Above MA-60</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer bg-slate-800/50 rounded-lg px-3 py-2 hover:bg-slate-700/50 transition-colors">
                <input type="checkbox" id="filter-ma200" class="w-4 h-4 rounded" onchange="applyFilters()">
                <span class="text-sm">Above MA-200</span>
              </label>
              <div class="flex items-center gap-2 bg-slate-800/50 rounded-lg px-3 py-2">
                <span class="text-sm text-slate-300">Z-Score ≤</span>
                <input type="number" id="filter-zscore-cap" value="" placeholder="—" step="0.5" min="0" max="10"
                       class="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm w-16 mono text-center focus:outline-none focus:border-indigo-500"
                       oninput="applyFilters()">
              </div>
              <div class="flex items-center gap-2 bg-slate-800/50 rounded-lg px-3 py-2">
                <span class="text-sm text-slate-300">Min Score ≥</span>
                <input type="number" id="filter-min-score" value="" placeholder="—" step="5" min="0" max="100"
                       class="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm w-16 mono text-center focus:outline-none focus:border-indigo-500"
                       oninput="applyFilters()">
              </div>
            </div>
          </div>
        </div>
        
        <!-- Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4" id="signal-summary">
        </div>

        <!-- Ranked Table -->
        <div class="bg-slate-900/50 rounded-xl border border-slate-800 overflow-hidden">
          <div class="p-4 border-b border-slate-800 flex justify-between items-center">
            <h3 class="font-bold">All Instruments — Ranked by Quality Score</h3>
            <div class="flex items-center gap-3">
              <span class="text-xs text-slate-500">⭐ = Top 20 Ideas</span>
              <span class="text-xs text-slate-500">Click headers to sort</span>
            </div>
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
                  <th class="px-3 py-2 text-right cursor-pointer hover:text-white select-none" onclick="sortTable('price')">
                    Price <span id="sort-price" class="text-indigo-400"></span>
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
                  <th class="px-3 py-2 text-center cursor-pointer hover:text-white select-none" onclick="sortTable('maStatus')">
                    MA <span id="sort-maStatus" class="text-indigo-400"></span>
                  </th>
                </tr>
              </thead>
              <tbody id="signals-table">
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- ===================== CIO SIGNALS TAB ===================== -->
    <div id="tab-cio" class="tab-content hidden">
      <div class="space-y-4">

        <!-- Sub-tabs -->
        <div class="flex gap-2 flex-wrap" id="cio-subtabs">
          <button onclick="showCioSubTab('overview')" class="cio-subtab-btn px-3 py-1.5 rounded-lg text-sm font-medium bg-indigo-600 text-white" data-cio-tab="overview">Overview</button>
          <button onclick="showCioSubTab('commodities')" class="cio-subtab-btn px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-cio-tab="commodities">Commodities</button>
          <button onclick="showCioSubTab('em')" class="cio-subtab-btn px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-cio-tab="em">Emerging Mkts</button>
          <button onclick="showCioSubTab('dm')" class="cio-subtab-btn px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-cio-tab="dm">Developed Mkts</button>
          <button onclick="showCioSubTab('us')" class="cio-subtab-btn px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-cio-tab="us">US</button>
          <button onclick="showCioSubTab('taa')" class="cio-subtab-btn px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-800 text-slate-300 hover:bg-slate-700" data-cio-tab="taa">TAA</button>
        </div>

        <!-- Sub-tab content containers -->
        <div id="cio-subtab-overview" class="cio-subtab-content"></div>
        <div id="cio-subtab-commodities" class="cio-subtab-content hidden"></div>
        <div id="cio-subtab-em" class="cio-subtab-content hidden"></div>
        <div id="cio-subtab-dm" class="cio-subtab-content hidden"></div>
        <div id="cio-subtab-us" class="cio-subtab-content hidden"></div>
        <div id="cio-subtab-taa" class="cio-subtab-content hidden"></div>

      </div>
    </div>

    <!-- ===================== STRATEGY TAB ===================== -->
    <div id="tab-strategy" class="tab-content hidden">
      <div class="space-y-6">
        
        <div class="bg-indigo-900/20 border border-indigo-700/50 rounded-xl p-6">
          <h2 class="text-xl font-bold text-indigo-400 mb-4">🎯 Core Strategy Principles</h2>
          
          <div class="grid md:grid-cols-2 gap-6">
            
            <div class="bg-slate-800/50 rounded-lg p-4">
              <div class="text-lg font-bold text-emerald-400 mb-2">1. Momentum + Diversification</div>
              <ul class="text-sm text-slate-300 space-y-2">
                <li>• Screen for ETFs with <strong>quality momentum</strong> (not just raw return)</li>
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
              <div class="text-lg font-bold text-cyan-400 mb-2">3. Quality Over Raw Return</div>
              <ul class="text-sm text-slate-300 space-y-2">
                <li>• Same 18% return — <strong>take the smoother trend</strong></li>
                <li>• Prioritize: High Sortino, few down weeks, steady slope</li>
                <li>• Avoid: Choppy, extended, parabolic moves</li>
                <li>• <strong>Sustainable &gt; Spectacular</strong></li>
              </ul>
            </div>

            <div class="bg-slate-800/50 rounded-lg p-4">
              <div class="text-lg font-bold text-purple-400 mb-2">4. Flexible Screening</div>
              <ul class="text-sm text-slate-300 space-y-2">
                <li>• Ranked universe — <strong>no rigid buy/sell labels</strong></li>
                <li>• Use filters to narrow: MA position, Z-Score, min score</li>
                <li>• Top-ranked ideas surface naturally</li>
                <li>• <strong>Judgment + data, not autopilot</strong></li>
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
              <div class="text-xs text-slate-500">Extension detection</div>
            </div>
            <div class="bg-slate-800 rounded-lg p-3 text-center">
              <div class="text-2xl font-bold text-indigo-400">15%</div>
              <div class="text-xs text-slate-400">Slope</div>
              <div class="text-xs text-slate-500">Trend strength</div>
            </div>
          </div>
          <div class="text-xs text-slate-500 bg-slate-800 p-2 rounded mono">
            Score 0-100 | Parabolic combo (Z &gt; 2.5 + low weeks down + high slope) applies 30% penalty | All ETFs ranked, top 20 highlighted
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
          <div class="mt-3 text-xs text-slate-500">
            Portfolio is built from the <strong>top-ranked</strong> ETFs in the screener (after any active filters), selecting greedily by score while enforcing the correlation constraint.
          </div>
        </div>

        <!-- Portfolio Stats -->
        <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4" id="portfolio-stats">
        </div>

        <!-- Recommended Portfolio -->
        <div class="bg-emerald-900/20 border border-emerald-700/50 rounded-xl p-4">
          <h3 class="font-bold text-emerald-400 mb-4">💼 Constructed Portfolio</h3>
          <div class="grid md:grid-cols-2 lg:grid-cols-4 gap-3" id="portfolio-holdings">
          </div>
        </div>

        <!-- Excluded -->
        <div class="bg-slate-900/50 rounded-xl border border-slate-800 p-4">
          <h3 class="font-bold text-slate-400 mb-2">🚫 Excluded (High Correlation)</h3>
          <p class="text-sm text-slate-500">These top-ranked ETFs were excluded to maintain diversification:</p>
          <div class="flex flex-wrap gap-2 mt-2" id="excluded-list">
          </div>
        </div>
      </div>
    </div>

    <!-- ===================== PORTFOLIO ANALYZER TAB ===================== -->
    <div id="tab-analyzer" class="tab-content hidden">
      <div class="space-y-6">

        <!-- CSV Upload Zone -->
        <div id="analyzer-dropzone" class="border-2 border-dashed border-slate-600 rounded-xl p-10 text-center hover:border-indigo-500 transition-colors cursor-pointer"
             onclick="document.getElementById('analyzer-file-input').click()"
             ondragover="event.preventDefault(); this.classList.add('border-indigo-500','bg-indigo-500/5');"
             ondragleave="this.classList.remove('border-indigo-500','bg-indigo-500/5');"
             ondrop="event.preventDefault(); this.classList.remove('border-indigo-500','bg-indigo-500/5'); handleAnalyzerFile(event.dataTransfer.files[0]);">
          <div class="text-4xl mb-3">📂</div>
          <div class="text-slate-300 font-medium mb-1">Drop portfolio CSV · required column: Symbol</div>
          <div class="text-slate-500 text-sm mb-1">Optional: Shares/Amount/Quantity · Cost Basis/Avg Price · Market Value · Weight · Type (BUY/SELL) · delimiter: comma or tab</div>
          <div class="text-slate-500 text-xs mb-4">Accepts <span class="mono text-slate-400">$1,234.56</span> / <span class="mono text-slate-400">1.97%</span> / suffixed tickers like <span class="mono text-slate-400">SHY.O</span>. SELL rows excluded. Last uploaded portfolio is persisted and shown to all users.</div>
          <button class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition-colors" onclick="event.stopPropagation(); document.getElementById('analyzer-file-input').click();">Choose File</button>
          <input type="file" id="analyzer-file-input" accept=".csv" class="hidden" onchange="handleAnalyzerFile(this.files[0]);" />
        </div>

        <!-- Last-loaded badge -->
        <div id="analyzer-persist-badge" class="hidden text-xs text-slate-500 text-right -mt-4"></div>

        <!-- Processing state -->
        <div id="analyzer-loading" class="hidden border-2 border-indigo-500/30 rounded-xl p-10 text-center bg-indigo-500/5">
          <div class="inline-block mb-4">
            <svg class="animate-spin h-10 w-10 text-indigo-400 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
          </div>
          <div class="text-indigo-300 font-medium text-lg mb-1" id="analyzer-loading-title">Processing portfolio…</div>
          <div class="text-slate-400 text-sm" id="analyzer-loading-detail">Parsing CSV</div>
        </div>

        <!-- Error banner (hidden by default) -->
        <div id="analyzer-error" class="hidden bg-red-900/30 border border-red-600/50 rounded-xl p-4 text-red-300">
          <div class="font-bold mb-1">⛔ Portfolio analyzer error</div>
          <div id="analyzer-error-msg" class="text-sm text-red-200"></div>
        </div>

        <!-- Parsing notes banner — unrecognized symbols, skipped rows (hidden by default) -->
        <div id="analyzer-unrecognized" class="hidden bg-amber-900/30 border border-amber-600/50 rounded-xl p-4 text-amber-300">
          <span class="font-bold">⚠ Parsing notes:</span>
          <span id="analyzer-unrecognized-list"></span>
        </div>

        <!-- Analyzer results (hidden by default) -->
        <div id="analyzer-results" class="hidden space-y-6">

          <!-- Summary stats -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4" id="analyzer-summary"></div>

          <!-- Risk Strip -->
          <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3" id="analyzer-risk-strip"></div>

          <!-- Score Distribution Panel -->
          <div class="bg-slate-900/50 rounded-xl border border-slate-800 p-5 space-y-4">
            <h3 class="font-bold text-slate-200 text-sm uppercase tracking-wide">Score Distribution</h3>

            <!-- Bar 1 — MA Distribution (primary) -->
            <div>
              <div class="text-xs text-slate-400 mb-1">MA Signal Distribution</div>
              <div class="flex w-full h-8 rounded-lg overflow-hidden" id="analyzer-ma-bar"></div>
              <div class="flex gap-4 mt-1.5 text-xs text-slate-400" id="analyzer-ma-legend"></div>
            </div>

            <!-- Bar 2 — Score Bands (secondary) -->
            <div>
              <div class="text-xs text-slate-400 mb-1">Score Bands</div>
              <div class="flex w-full h-5 rounded-lg overflow-hidden" id="analyzer-score-bar"></div>
              <div class="flex gap-4 mt-1.5 text-xs text-slate-400" id="analyzer-score-legend"></div>
            </div>

            <!-- Region Breakdown Table -->
            <div class="overflow-x-auto mt-2">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-slate-700 text-slate-400 text-xs uppercase">
                    <th class="text-left p-2 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('region','name')">Region <span id="az-sort-region-name"></span></th>
                    <th class="text-right p-2 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('region','count')">Positions <span id="az-sort-region-count"></span></th>
                    <th class="text-right p-2 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('region','wt')">Wt% <span id="az-sort-region-wt"></span></th>
                    <th class="text-right p-2 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('region','ma3')">MA=3 <span id="az-sort-region-ma3"></span></th>
                    <th class="text-right p-2 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('region','ma2')">MA=2 <span id="az-sort-region-ma2"></span></th>
                    <th class="text-right p-2 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('region','ma1')">MA=1 <span id="az-sort-region-ma1"></span></th>
                    <th class="text-right p-2 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('region','ma0')">MA=0 <span id="az-sort-region-ma0"></span></th>
                    <th class="text-right p-2 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('region','avg')">Avg Score <span id="az-sort-region-avg"></span></th>
                  </tr>
                </thead>
                <tbody id="analyzer-region-table"></tbody>
              </table>
            </div>
          </div>

          <!-- Holdings table -->
          <div class="bg-slate-900/50 rounded-xl border border-slate-800 overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-slate-700 text-slate-400 text-xs uppercase">
                    <th class="text-left p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','symbol')">Symbol <span id="az-sort-holdings-symbol"></span></th>
                    <th class="text-center p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','maStatus')">MA Signal <span id="az-sort-holdings-maStatus"></span></th>
                    <th class="text-center p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','ma30')">MA30 <span id="az-sort-holdings-ma30"></span></th>
                    <th class="text-center p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','ma60')">MA60 <span id="az-sort-holdings-ma60"></span></th>
                    <th class="text-center p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','ma200')">MA200 <span id="az-sort-holdings-ma200"></span></th>
                    <th class="text-right p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','score')">Score <span id="az-sort-holdings-score"></span></th>
                    <th class="text-right p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','price')">Price <span id="az-sort-holdings-price"></span></th>
                    <th class="text-right p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','mktValue')">Mkt Val <span id="az-sort-holdings-mktValue"></span></th>
                    <th class="text-right p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','weight')">Wt% <span id="az-sort-holdings-weight"></span></th>
                    <th class="text-left p-3 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('holdings','region')">Region <span id="az-sort-holdings-region"></span></th>
                  </tr>
                </thead>
                <tbody id="analyzer-table"></tbody>
              </table>
            </div>
            <div class="px-4 py-2.5 border-t border-slate-800 text-xs text-slate-500">
              Red = MA=0 (exit) · Amber = MA=1 (watch) · Click column headers to sort
            </div>
          </div>

          <!-- Sell/Reduce + Buy Candidates (side by side) -->
          <div class="grid md:grid-cols-2 gap-4">

            <!-- Sell / Reduce panel -->
            <div class="bg-slate-900/50 rounded-xl border border-slate-800 overflow-hidden">
              <div class="px-4 py-3 border-b border-slate-800 flex items-center gap-2">
                <span class="text-red-400 font-bold text-sm uppercase tracking-wide">Sell / Reduce</span>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead>
                    <tr class="border-b border-slate-700 text-slate-400 text-xs uppercase">
                      <th class="text-left p-2.5 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('sell','symbol')">Symbol <span id="az-sort-sell-symbol"></span></th>
                      <th class="text-center p-2.5 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('sell','ma')">MA <span id="az-sort-sell-ma"></span></th>
                      <th class="text-right p-2.5 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('sell','score')">Score <span id="az-sort-sell-score"></span></th>
                      <th class="text-left p-2.5 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('sell','reason')">Reason <span id="az-sort-sell-reason"></span></th>
                      <th class="text-center p-2.5 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('sell','action')">Action <span id="az-sort-sell-action"></span></th>
                    </tr>
                  </thead>
                  <tbody id="analyzer-sell-table"></tbody>
                </table>
              </div>
              <div id="analyzer-sell-empty" class="hidden px-4 py-6 text-center text-slate-500 text-sm">No sell or reduce signals</div>
            </div>

            <!-- Buy Candidates panel -->
            <div class="bg-slate-900/50 rounded-xl border border-slate-800 overflow-hidden">
              <div class="px-4 py-3 border-b border-slate-800 flex items-center gap-2">
                <span class="text-emerald-400 font-bold text-sm uppercase tracking-wide">Buy Candidates</span>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead>
                    <tr class="border-b border-slate-700 text-slate-400 text-xs uppercase">
                      <th class="text-left p-2.5 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('buy','symbol')">Symbol <span id="az-sort-buy-symbol"></span></th>
                      <th class="text-center p-2.5 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('buy','ma')">MA <span id="az-sort-buy-ma"></span></th>
                      <th class="text-right p-2.5 cursor-pointer hover:text-white select-none" onclick="sortAnalyzerColumn('buy','score')">Score <span id="az-sort-buy-score"></span></th>
                      <th class="text-left p-2.5">Why Buy</th>
                    </tr>
                  </thead>
                  <tbody id="analyzer-buy-table"></tbody>
                </table>
              </div>
              <div id="analyzer-buy-empty" class="hidden px-4 py-6 text-center text-slate-500 text-sm">No buy candidates found</div>
            </div>

          </div>
        </div>

      </div>
    </div>

    <!-- ===================== SETTINGS TAB (was Rules) ===================== -->
    <div id="tab-rules" class="tab-content hidden">
      <div class="space-y-6">

        <!-- Settings Section -->
        <div class="bg-amber-900/20 border border-amber-700/50 rounded-xl p-5">
          <h3 class="text-lg font-bold text-amber-400 mb-4">⚙️ Quality Momentum Settings</h3>
          
          <!-- Mode Toggle -->
          <div class="mb-6">
            <label class="text-sm text-slate-400 mb-2 block">Scoring Mode</label>
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
                    <span class="text-slate-500">Extension detection</span>
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

            <!-- Top Ideas Count -->
            <div class="mb-4">
              <label class="text-sm text-slate-400 mb-2 block">Ranking</label>
              <div class="grid md:grid-cols-2 gap-4">
                <div class="bg-slate-800 rounded-lg p-3">
                  <label class="text-xs text-slate-400 block mb-1">⭐ Top Ideas Count</label>
                  <input type="range" min="10" max="30" value="20" id="t-topcount" class="w-full" oninput="updateThresholds()">
                  <div class="flex justify-between text-xs mt-1">
                    <span class="text-slate-500">Highlighted in screener</span>
                    <span class="mono text-indigo-400 font-bold" id="t-topcount-val">20</span>
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
            Mode: Quality Momentum | Weights: Sortino 40%, WeeksDown 25%, Z-Score 20%, Slope 15% | Top Ideas: 20
          </div>
        </div>

        <div class="grid md:grid-cols-2 gap-6">
          
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

        <!-- CIO Asset Class Constraints -->
        <div class="bg-slate-900/80 border border-slate-700 rounded-xl p-5">
          <h3 class="text-lg font-bold text-slate-200 mb-4">🔒 Asset Class Constraints — CIO Limits</h3>
          <p class="text-xs text-slate-400 mb-4">Four asset classes: EM, DM, Commodities, Cash. Total must equal 100%.</p>

          <!-- Stacked allocation bar -->
          <div id="cio-alloc-bar" class="mb-4"></div>

          <!-- Constraint rows -->
          <div id="cio-constraint-rows" class="space-y-3"></div>

          <!-- Summary footer -->
          <div id="cio-constraint-footer" class="mt-4 text-center text-sm font-bold mono py-2 rounded-lg"></div>

          <!-- Buttons -->
          <div class="mt-4 flex gap-3">
            <button onclick="saveCioConstraints()" class="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-bold transition-colors">
              ✓ Save Constraints
            </button>
            <button onclick="resetCioConstraints()" class="px-6 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg font-medium transition-colors">
              ↺ Reset Defaults
            </button>
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
      topCount: 20,
      zScoreSteep: 3.0
    }};

    function getCorrelation(t1, t2) {{
      if (t1 === t2) return 1.0;
      return CORRELATIONS[`${{t1}}-${{t2}}`] || CORRELATIONS[`${{t2}}-${{t1}}`] || 0.5;
    }}

    // Calculate Quality Score — pure ranking, no signals
    function calculateScore(etf) {{
      const normalize = (val, min, max, inv = false) => {{
        const n = Math.max(0, Math.min(100, ((val - min) / (max - min)) * 100));
        return inv ? 100 - n : n;
      }};

      if (settings.mode === 'pure') {{
        const score = normalize(etf.return6m, -20, 40);
        const maStatus = (etf.aboveMA30 ? 1 : 0) + (etf.aboveMA60 ? 1 : 0) + (etf.aboveMA200 ? 1 : 0);
        return {{ ...etf, score, maStatus }};
      }}

      const {{ weights }} = settings;
      const totalWeight = weights.sortino + weights.weeksDown + weights.zScore + weights.slope;

      const sortinoScore = normalize(etf.sortino, -1, 2.5);
      const weeksDownScore = Math.min(85, normalize(etf.weeksDown, 0, 12, true));
      
      let excessiveScore;
      if (etf.zScore > settings.zScoreSteep) excessiveScore = 100 - Math.pow(etf.zScore - settings.zScoreSteep, 2) * 100;
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

      // Parabolic penalty (still useful as a score modifier)
      const isParabolic = etf.zScore > 2.5 && etf.weeksDown < 3 && etf.slope > 0.4;
      if (isParabolic) total *= 0.7;

      const maStatus = (etf.aboveMA30 ? 1 : 0) + (etf.aboveMA60 ? 1 : 0) + (etf.aboveMA200 ? 1 : 0);

      return {{ ...etf, score: total, maStatus }};
    }}

    let rankedETFs = etfUniverse.map(calculateScore).sort((a, b) => b.score - a.score);
    let filteredETFs = rankedETFs;
    let currentSort = {{ column: 'score', direction: 'desc' }};

    // Analyzer sort state & data stores
    const analyzerSort = {{
      holdings: {{ column: 'maStatus', direction: 'desc' }},
      region: {{ column: 'wt', direction: 'desc' }},
      sell: {{ column: 'ma', direction: 'asc' }},
      buy: {{ column: 'score', direction: 'desc' }},
    }};
    let analyzerHoldings = [];
    let analyzerTotalValue = 0;
    let analyzerSellRows = [];
    let analyzerBuyCandidates = [];
    let analyzerRegionData = [];

    // Initialize filter dropdowns
    function initFilterDropdowns() {{
      const regions = [...new Set(etfUniverse.flatMap(e => e.regions))].sort();
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

    function clearFilters() {{
      document.getElementById('etf-only-toggle').checked = true;
      document.getElementById('top-ideas-toggle').checked = false;
      document.getElementById('search-input').value = '';
      document.getElementById('region-filter').value = '';
      document.getElementById('sector-filter').value = '';
      document.getElementById('filter-ma30').checked = false;
      document.getElementById('filter-ma60').checked = false;
      document.getElementById('filter-ma200').checked = false;
      document.getElementById('filter-zscore-cap').value = '';
      document.getElementById('filter-min-score').value = '';
      applyFilters();
    }}

    function applyFilters() {{
      const etfOnly = document.getElementById('etf-only-toggle').checked;
      const topOnly = document.getElementById('top-ideas-toggle').checked;
      const searchTerm = document.getElementById('search-input').value.toLowerCase();
      const regionFilter = document.getElementById('region-filter').value;
      const sectorFilter = document.getElementById('sector-filter').value;
      
      // Narrowing filters
      const reqMA30 = document.getElementById('filter-ma30').checked;
      const reqMA60 = document.getElementById('filter-ma60').checked;
      const reqMA200 = document.getElementById('filter-ma200').checked;
      const zScoreCapStr = document.getElementById('filter-zscore-cap').value;
      const minScoreStr = document.getElementById('filter-min-score').value;
      const zScoreCap = zScoreCapStr !== '' ? parseFloat(zScoreCapStr) : null;
      const minScore = minScoreStr !== '' ? parseFloat(minScoreStr) : null;
      
      // Determine top ideas based on full ranked list (before filtering)
      const topIdeasSet = new Set(rankedETFs.slice(0, settings.topCount).map(e => e.ticker));
      
      filteredETFs = rankedETFs.filter(e => {{
        if (etfOnly && !e.isETF) return false;
        if (topOnly && !topIdeasSet.has(e.ticker)) return false;
        if (regionFilter && !e.regions.includes(regionFilter)) return false;
        if (sectorFilter && e.sector !== sectorFilter) return false;
        if (reqMA30 && !e.aboveMA30) return false;
        if (reqMA60 && !e.aboveMA60) return false;
        if (reqMA200 && !e.aboveMA200) return false;
        if (zScoreCap !== null && e.zScore > zScoreCap) return false;
        if (minScore !== null && e.score < minScore) return false;
        if (searchTerm) {{
          const searchFields = [e.ticker, e.name, e.sector, e.country, ...e.regions].join(' ').toLowerCase();
          if (!searchFields.includes(searchTerm)) return false;
        }}
        return true;
      }});
      
      sortFilteredETFs();
      renderSignals();
      updatePortfolio();
    }}

    // Sort
    function sortTable(column) {{
      if (currentSort.column === column) {{
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
      }} else {{
        currentSort.column = column;
        const numericColumns = ['price', 'score', 'return6m', 'sortino', 'weeksDown', 'zScore', 'maStatus'];
        currentSort.direction = numericColumns.includes(column) ? 'desc' : 'asc';
      }}
      
      sortFilteredETFs();
      renderSignals();
    }}

    function sortFilteredETFs() {{
      const {{ column, direction }} = currentSort;
      
      filteredETFs.sort((a, b) => {{
        let valA = a[column];
        let valB = b[column];
        
        if (typeof valA === 'boolean') {{ valA = valA ? 1 : 0; valB = valB ? 1 : 0; }}
        if (typeof valA === 'string') {{ valA = valA.toLowerCase(); valB = valB.toLowerCase(); }}
        
        let result = 0;
        if (valA < valB) result = -1;
        if (valA > valB) result = 1;
        
        return direction === 'asc' ? result : -result;
      }});
      
      document.querySelectorAll('[id^="sort-"]').forEach(el => el.textContent = '');
      const indicator = document.getElementById(`sort-${{column}}`);
      if (indicator) indicator.textContent = direction === 'asc' ? '↑' : '↓';
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
      activeBtn.classList.remove('bg-slate-800', 'text-slate-300');
      activeBtn.classList.add('bg-indigo-600', 'text-white');

      // Re-render CIO tab when opened (picks up score/settings changes)
      if (tabId === 'cio') {{
        const activeCioTab = document.querySelector('.cio-subtab-btn.bg-indigo-600');
        const activeKey = activeCioTab ? activeCioTab.dataset.cioTab : 'overview';
        renderCioSubTab(activeKey);
      }}

      // Auto-load last persisted portfolio when opening analyzer tab
      if (tabId === 'analyzer') {{
        loadPersistedAnalyzer();
      }}
    }}

    // Render screener
    function renderSignals() {{
      const topIdeasSet = new Set(rankedETFs.slice(0, settings.topCount).map(e => e.ticker));
      const topInView = filteredETFs.filter(e => topIdeasSet.has(e.ticker)).length;
      const avgScore = filteredETFs.length > 0 ? (filteredETFs.reduce((s, e) => s + e.score, 0) / filteredETFs.length).toFixed(1) : '—';
      const aboveAllMA = filteredETFs.filter(e => e.maStatus === 3).length;

      document.getElementById('filter-count').textContent = filteredETFs.length;
      document.getElementById('total-count').textContent = rankedETFs.length;

      document.getElementById('signal-summary').innerHTML = `
        <div class="bg-indigo-900/30 border border-indigo-700/50 rounded-lg p-4 text-center">
          <div class="text-3xl font-bold text-indigo-400">${{filteredETFs.length}}</div>
          <div class="text-sm text-slate-400">Showing</div>
        </div>
        <div class="bg-amber-900/30 border border-amber-700/50 rounded-lg p-4 text-center">
          <div class="text-3xl font-bold text-amber-400">⭐ ${{topInView}}</div>
          <div class="text-sm text-slate-400">Top Ideas</div>
        </div>
        <div class="bg-slate-800 rounded-lg p-4 text-center">
          <div class="text-3xl font-bold text-emerald-400">${{avgScore}}</div>
          <div class="text-sm text-slate-400">Avg Score</div>
        </div>
        <div class="bg-slate-800 rounded-lg p-4 text-center">
          <div class="text-3xl font-bold text-cyan-400">${{aboveAllMA}}</div>
          <div class="text-sm text-slate-400">All MAs ✓</div>
        </div>
      `;

      const tbody = document.getElementById('signals-table');
      tbody.innerHTML = filteredETFs.map((etf, i) => {{
        const isTop = topIdeasSet.has(etf.ticker);
        const rowClass = isTop ? 'top-idea-row' : '';
        const typeLabel = etf.isETF ? 'ETF' : 'Stock';
        const typeColor = etf.isETF ? 'text-cyan-400' : 'text-amber-400';
        const rankBadge = isTop ? '⭐' : '';
        
        // Score color based on value
        let scoreColor = 'text-slate-400';
        if (etf.score >= 65) scoreColor = 'text-emerald-400';
        else if (etf.score >= 50) scoreColor = 'text-indigo-400';
        else if (etf.score >= 35) scoreColor = 'text-amber-400';
        else scoreColor = 'text-red-400';
        
        return `
          <tr class="border-t border-slate-800 ${{rowClass}}">
            <td class="px-3 py-2 text-slate-500">${{rankBadge}} ${{i + 1}}</td>
            <td class="px-3 py-2">
              <div class="font-bold">${{etf.ticker}}</div>
              <div class="text-xs text-slate-500">${{etf.sector}}</div>
            </td>
            <td class="px-3 py-2 text-xs ${{typeColor}}">${{typeLabel}}</td>
            <td class="px-3 py-2 text-xs text-slate-400">${{etf.country}}</td>
            <td class="px-3 py-2 text-right mono" style="color:#fbbf24">${{etf.price != null ? '$' + etf.price.toFixed(2) : '—'}}</td>
            <td class="px-3 py-2 text-right mono font-bold ${{scoreColor}}">${{etf.score.toFixed(1)}}</td>
            <td class="px-3 py-2 text-right mono ${{etf.return6m >= 0 ? 'text-emerald-400' : 'text-red-400'}}">
              ${{etf.return6m >= 0 ? '+' : ''}}${{etf.return6m.toFixed(1)}}%
            </td>
            <td class="px-3 py-2 text-right mono">${{etf.sortino.toFixed(2)}}</td>
            <td class="px-3 py-2 text-right mono ${{etf.weeksDown >= 8 ? 'text-red-400' : ''}}">${{etf.weeksDown}}/12</td>
            <td class="px-3 py-2 text-right mono ${{etf.zScore > 4 ? 'text-red-400 font-bold' : etf.zScore > 3 ? 'text-orange-400' : ''}}">${{etf.zScore.toFixed(1)}}</td>
            <td class="px-3 py-2 text-center ${{etf.maStatus === 3 ? 'text-emerald-400' : etf.maStatus >= 2 ? 'text-yellow-400' : 'text-red-400'}}">${{etf.maStatus}}/3</td>
          </tr>
        `;
      }}).join('');
    }}

    // Portfolio construction — uses top ranked from filtered list
    function updatePortfolio() {{
      const maxPos = parseInt(document.getElementById('maxPositions').value);
      const maxWt = parseInt(document.getElementById('maxWeight').value);
      const maxCorr = parseInt(document.getElementById('maxCorr').value) / 100;

      document.getElementById('maxPositionsVal').textContent = maxPos;
      document.getElementById('maxWeightVal').textContent = maxWt + '%';
      document.getElementById('maxCorrVal').textContent = maxCorr.toFixed(2);

      // Build portfolio from the filtered + sorted list (ETFs only for portfolio)
      const candidates = filteredETFs.filter(e => e.isETF).sort((a, b) => b.score - a.score);
      const portfolio = [];
      const excluded = [];

      for (const etf of candidates) {{
        if (portfolio.length >= maxPos) break;
        let tooCorrelated = false;
        for (const h of portfolio) {{
          if (getCorrelation(etf.ticker, h.ticker) > maxCorr) {{
            tooCorrelated = true;
            break;
          }}
        }}
        if (tooCorrelated) {{
          excluded.push(etf);
        }} else {{
          portfolio.push(etf);
        }}
      }}

      if (portfolio.length === 0) {{
        document.getElementById('portfolio-stats').innerHTML = '<div class="col-span-full text-center text-slate-500">No positions match criteria. Try adjusting filters.</div>';
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

      document.getElementById('excluded-list').innerHTML = excluded.length > 0 
        ? excluded.map(e => 
            `<span class="px-2 py-1 bg-slate-800 rounded text-sm">${{e.ticker}} <span class="text-slate-500">(Score: ${{e.score.toFixed(1)}})</span></span>`
          ).join('')
        : '<span class="text-sm text-slate-600">None excluded</span>';
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
      settings.topCount = parseInt(document.getElementById('t-topcount').value);
      settings.zScoreSteep = parseFloat(document.getElementById('t-zscore-steep').value);

      document.getElementById('t-topcount-val').textContent = settings.topCount;
      document.getElementById('t-zscore-steep-val').textContent = settings.zScoreSteep.toFixed(1);
      
      updateConfigSummary();
    }}

    function updateConfigSummary() {{
      const {{ mode, weights, topCount, zScoreSteep }} = settings;
      const modeText = mode === 'pure' ? 'Pure Return' : 'Quality Momentum';
      const weightsText = mode === 'pure' ? 'N/A' : 
        `Sortino ${{weights.sortino}}%, WeeksDown ${{weights.weeksDown}}%, Z-Score ${{weights.zScore}}%, Slope ${{weights.slope}}%`;
      
      document.getElementById('config-summary').textContent = 
        `Mode: ${{modeText}} | Weights: ${{weightsText}} | Top Ideas: ${{topCount}} | Z-Steep: ${{zScoreSteep}}`;
    }}

    function applySettings() {{
      rankedETFs = etfUniverse.map(calculateScore).sort((a, b) => b.score - a.score);
      applyFilters();
    }}

    function resetSettings() {{
      settings = {{
        mode: 'quality',
        weights: {{ sortino: 40, weeksDown: 25, zScore: 20, slope: 15 }},
        topCount: 20,
        zScoreSteep: 3.0
      }};

      document.getElementById('w-sortino').value = 40;
      document.getElementById('w-weeksdown').value = 25;
      document.getElementById('w-zscore').value = 20;
      document.getElementById('w-slope').value = 15;
      document.getElementById('t-topcount').value = 20;
      document.getElementById('t-zscore-steep').value = 3;

      updateWeights();
      updateThresholds();
      setMode('quality');
      applySettings();
    }}

    // ========== CIO ASSET CLASS CONSTRAINTS ==========

    const CIO_CONSTRAINT_DEFAULTS = [
      {{ id: 'em',          name: 'EM',          color: '#10b981', current: 31.4, min: 0,  max: 30 }},
      {{ id: 'dm',          name: 'DM',          color: '#818cf8', current: 18.1, min: 0,  max: 30 }},
      {{ id: 'commodities', name: 'Commodities', color: '#f59e0b', current: 25.3, min: 0,  max: 35 }},
      {{ id: 'cash',        name: 'Cash',        color: '#22d3ee', current: 25.2, min: 5,  max: 40 }},
    ];

    let cioConstraints = JSON.parse(JSON.stringify(CIO_CONSTRAINT_DEFAULTS));

    function renderCioConstraints() {{
      const total = cioConstraints.reduce((s, c) => s + c.current, 0);

      // Stacked allocation bar
      const barSegments = cioConstraints.map(c => {{
        const pct = (c.current / total * 100);
        return `<div style="width:${{pct}}%;background:${{c.color}}" class="h-6 relative group">
          <span class="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-white drop-shadow">${{c.current >= 8 ? c.name + ' ' + c.current.toFixed(1) + '%' : ''}}</span>
        </div>`;
      }}).join('');
      const legend = cioConstraints.map(c =>
        `<span class="flex items-center gap-1.5 text-xs text-slate-300"><span class="w-3 h-3 rounded-sm inline-block" style="background:${{c.color}}"></span>${{c.name}} ${{c.current.toFixed(1)}}%</span>`
      ).join('');
      document.getElementById('cio-alloc-bar').innerHTML =
        `<div class="flex rounded-lg overflow-hidden border border-slate-700">${{barSegments}}</div>
         <div class="flex gap-4 mt-2 justify-center">${{legend}}</div>`;

      // Constraint rows
      const rowsHtml = cioConstraints.map((c, i) => {{
        const overMax = c.current > c.max;
        const underMin = c.min > 0 && c.current < c.min;
        const ok = !overMax && !underMin;

        let statusBadge, bgClass, borderClass;
        if (overMax) {{
          const diff = (c.current - c.max).toFixed(1);
          statusBadge = `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-red-900/60 text-red-300">↑ ${{diff}}% over max</span>`;
          bgClass = 'background:#1a0505';
          borderClass = 'border-color:#7f1d1d';
        }} else if (underMin) {{
          const diff = (c.min - c.current).toFixed(1);
          statusBadge = `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-900/60 text-amber-300">↓ ${{diff}}% below min</span>`;
          bgClass = 'background:#1c1200';
          borderClass = 'border-color:#78350f';
        }} else {{
          statusBadge = `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-900/60 text-emerald-300">✓ Within range</span>`;
          bgClass = 'background:#0f172a';
          borderClass = 'border-color:#1e293b';
        }}

        const fillColor = overMax ? '#dc2626' : underMin ? '#d97706' : c.color;
        const fillWidth = Math.min(c.current, 100);

        return `<div class="rounded-lg border p-3" style="${{bgClass}};${{borderClass}}">
          <div class="flex items-center gap-3 mb-2 flex-wrap">
            <span class="font-bold text-sm text-white flex items-center gap-2">
              <span class="w-3 h-3 rounded-sm inline-block" style="background:${{c.color}}"></span>${{c.name}}
            </span>
            <span class="mono text-sm" style="color:${{c.color}}">Current ${{c.current.toFixed(1)}}%</span>
            <span class="flex items-center gap-2 text-xs">
              <label class="text-slate-400">Min%</label>
              <input type="number" min="0" max="100" value="${{c.min}}" data-idx="${{i}}" data-field="min"
                class="cio-input w-16 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs mono text-white text-center">
            </span>
            <span class="flex items-center gap-2 text-xs">
              <label class="text-slate-400">Max%</label>
              <input type="number" min="0" max="100" value="${{c.max}}" data-idx="${{i}}" data-field="max"
                class="cio-input w-16 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs mono text-white text-center">
            </span>
            ${{statusBadge}}
          </div>
          <div class="relative h-5 bg-slate-800 rounded-full overflow-visible">
            <div class="absolute top-0 left-0 h-full rounded-full" style="width:${{fillWidth}}%;background:${{fillColor}};"></div>
            ${{c.min > 0 ? `<div class="absolute top-0 h-full w-0.5" style="left:${{c.min}}%;background:#d97706;z-index:2" title="Min ${{c.min}}%"></div>` : ''}}
            <div class="absolute top-0 h-full w-0.5" style="left:${{Math.min(c.max, 100)}}%;background:#dc2626;z-index:2" title="Max ${{c.max}}%"></div>
          </div>
          <div class="flex justify-between text-[10px] text-slate-500 mt-1 px-0.5">
            <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
          </div>
        </div>`;
      }}).join('');
      document.getElementById('cio-constraint-rows').innerHTML = rowsHtml;

      // Footer
      const totalRounded = parseFloat(total.toFixed(1));
      const balanced = Math.abs(totalRounded - 100) < 0.01;
      document.getElementById('cio-constraint-footer').innerHTML = balanced
        ? `<span class="text-emerald-400">Total: ${{totalRounded}}% ✓ Balanced</span>`
        : `<span class="text-red-400">Total: ${{totalRounded}}% ≠ 100%</span>`;
      document.getElementById('cio-constraint-footer').className =
        `mt-4 text-center text-sm font-bold mono py-2 rounded-lg ${{balanced ? 'bg-emerald-900/30 border border-emerald-700/50' : 'bg-red-900/30 border border-red-700/50'}}`;

      // Re-bind input listeners
      document.querySelectorAll('.cio-input').forEach(inp => {{
        inp.addEventListener('input', function() {{
          const idx = parseInt(this.dataset.idx);
          const field = this.dataset.field;
          const val = parseFloat(this.value);
          if (!isNaN(val) && val >= 0 && val <= 100) {{
            cioConstraints[idx][field] = val;
            renderCioConstraints();
          }}
        }});
      }});
    }}

    function saveCioConstraints() {{
      try {{
        localStorage.setItem('cioConstraints', JSON.stringify(cioConstraints));
      }} catch(e) {{}}
      renderCioConstraints();
    }}

    function resetCioConstraints() {{
      cioConstraints = JSON.parse(JSON.stringify(CIO_CONSTRAINT_DEFAULTS));
      try {{
        localStorage.removeItem('cioConstraints');
      }} catch(e) {{}}
      renderCioConstraints();
    }}

    // Load saved constraints on startup
    try {{
      const saved = localStorage.getItem('cioConstraints');
      if (saved) cioConstraints = JSON.parse(saved);
    }} catch(e) {{}}

    // ========== CIO SIGNALS DASHBOARD ==========

    const CIO_REGIONS = {{
      overview: {{ label: 'All Regions', filter: () => true }},
      commodities: {{ label: 'Commodities', filter: e => e.regions.includes('Commodities') }},
      em: {{ label: 'Emerging Markets', filter: e => e.regions.includes('Emerging Markets') || e.regions.includes('India') }},
      dm: {{ label: 'Developed Markets', filter: e => e.regions.includes('Developed Markets') }},
      us: {{ label: 'US', filter: e => e.regions.includes('US') }},
      taa: {{ label: 'TAA', filter: e => e.regions.includes('TAA ETFs') }}
    }};

    function showCioSubTab(tabId) {{
      document.querySelectorAll('.cio-subtab-content').forEach(el => el.classList.add('hidden'));
      document.getElementById('cio-subtab-' + tabId).classList.remove('hidden');
      document.querySelectorAll('.cio-subtab-btn').forEach(btn => {{
        btn.classList.remove('bg-indigo-600', 'text-white');
        btn.classList.add('bg-slate-800', 'text-slate-300');
      }});
      const activeBtn = document.querySelector(`[data-cio-tab="${{tabId}}"]`);
      activeBtn.classList.remove('bg-slate-800', 'text-slate-300');
      activeBtn.classList.add('bg-indigo-600', 'text-white');
      renderCioSubTab(tabId);
    }}

    function getCioRegionData(regionKey) {{
      const cfg = CIO_REGIONS[regionKey];
      const etfs = rankedETFs.filter(e => e.isETF && cfg.filter(e));
      const maIntact = etfs.filter(e => e.maStatus === 3).length;
      const fullStack = etfs.filter(e => e.maStatus >= 2).length;
      const maBroken = etfs.filter(e => e.maStatus === 0).length;
      const avgWksDown = etfs.length > 0 ? (etfs.reduce((s, e) => s + e.weeksDown, 0) / etfs.length) : 0;
      const breadthPct = etfs.length > 0 ? (maIntact / etfs.length * 100) : 0;
      return {{ etfs, maIntact, fullStack, maBroken, avgWksDown, breadthPct, total: etfs.length, label: cfg.label }};
    }}

    function zScoreColor(z) {{
      if (z <= 0.5) return '#6366f1';   // indigo — deeply oversold
      if (z <= 1.0) return '#22c55e';   // green — normal
      if (z <= 2.0) return '#eab308';   // yellow — warm
      if (z <= 3.0) return '#f97316';   // orange — extended
      return '#ef4444';                  // red — extreme
    }}

    function zScoreZoneLabel(z) {{
      if (z <= 0.5) return 'Oversold';
      if (z <= 1.0) return 'Normal';
      if (z <= 2.0) return 'Warm';
      if (z <= 3.0) return 'Extended';
      return 'Extreme';
    }}

    function renderColorStrip(etfs) {{
      if (etfs.length === 0) return '<div class="text-sm text-slate-500">No ETFs</div>';
      const sorted = [...etfs].sort((a, b) => a.zScore - b.zScore);
      const segments = sorted.map(e => {{
        const color = zScoreColor(e.zScore);
        const widthPct = (100 / sorted.length).toFixed(2);
        return `<div title="${{e.ticker}}: z=${{e.zScore.toFixed(1)}}" style="width:${{widthPct}}%;background:${{color}};height:18px;display:inline-block;cursor:pointer;" class="hover:opacity-80 transition-opacity"></div>`;
      }}).join('');
      return `<div style="display:flex;border-radius:6px;overflow:hidden;">${{segments}}</div>
        <div class="flex justify-between text-xs text-slate-500 mt-1">
          <span>← Oversold</span><span>Normal</span><span>Extended →</span>
        </div>`;
    }}

    function renderEtfCardsByTier(etfs) {{
      const tiers = [
        {{ label: 'MA 3/3 — Full alignment', status: 3, color: 'emerald' }},
        {{ label: 'MA 2/3 — Partial alignment', status: 2, color: 'yellow' }},
        {{ label: 'MA 1/3 — Weak', status: 1, color: 'orange' }},
        {{ label: 'MA 0/3 — No support', status: 0, color: 'red' }}
      ];
      return tiers.map(tier => {{
        const tierETFs = etfs.filter(e => e.maStatus === tier.status).sort((a, b) => a.weeksDown - b.weeksDown);
        if (tierETFs.length === 0) return '';
        const cards = tierETFs.map(e => {{
          const retColor = e.return6m >= 0 ? 'text-emerald-400' : 'text-red-400';
          const zColor = e.zScore > 3 ? 'text-red-400' : e.zScore > 2 ? 'text-orange-400' : 'text-slate-300';
          return `<div class="bg-slate-800 rounded-lg p-2.5 min-w-[130px]">
            <div class="font-bold text-sm">${{e.ticker}}</div>
            <div class="text-xs text-slate-500 truncate">${{e.name || e.sector}}</div>
            <div class="grid grid-cols-2 gap-x-2 mt-1.5 text-xs">
              <span class="text-slate-500">Ret</span><span class="${{retColor}} text-right">${{e.return6m >= 0 ? '+' : ''}}${{e.return6m.toFixed(1)}}%</span>
              <span class="text-slate-500">Z</span><span class="${{zColor}} text-right">${{e.zScore.toFixed(1)}}</span>
              <span class="text-slate-500">Wks↓</span><span class="text-right ${{e.weeksDown >= 6 ? 'text-red-400' : ''}}">${{e.weeksDown}}/12</span>
              <span class="text-slate-500">Score</span><span class="text-indigo-400 text-right">${{e.score.toFixed(0)}}</span>
            </div>
          </div>`;
        }}).join('');
        return `<div class="mb-4">
          <div class="text-sm font-bold text-${{tier.color}}-400 mb-2">${{tier.label}} <span class="text-slate-500 font-normal">(${{tierETFs.length}})</span></div>
          <div class="flex flex-wrap gap-2">${{cards}}</div>
        </div>`;
      }}).join('');
    }}

    function generateSignalReading(data) {{
      const {{ maIntact, maBroken, total, avgWksDown, breadthPct, label }} = data;
      const lines = [];

      if (breadthPct >= 70) {{
        lines.push(`<span class="text-emerald-400 font-bold">Strong uptrend.</span> ${{maIntact}} of ${{total}} ${{label}} ETFs hold all three MAs — broad participation confirms the rally.`);
      }} else if (breadthPct >= 40) {{
        lines.push(`<span class="text-yellow-400 font-bold">Mixed signals.</span> ${{maIntact}} of ${{total}} ${{label}} ETFs hold all MAs — momentum is selective, not broad.`);
      }} else {{
        lines.push(`<span class="text-red-400 font-bold">Weak breadth.</span> Only ${{maIntact}} of ${{total}} ${{label}} ETFs hold all MAs — the trend is narrow or breaking down.`);
      }}

      if (avgWksDown >= 6) {{
        lines.push(`Average weeks-down at ${{avgWksDown.toFixed(1)}}/12 signals persistent selling pressure.`);
      }} else if (avgWksDown >= 3) {{
        lines.push(`Average weeks-down at ${{avgWksDown.toFixed(1)}}/12 — mild deterioration, watch for acceleration.`);
      }} else {{
        lines.push(`Average weeks-down at ${{avgWksDown.toFixed(1)}}/12 — buyers remain in control.`);
      }}

      if (maBroken > total * 0.3) {{
        lines.push(`<span class="text-red-400">${{maBroken}} ETFs below all MAs</span> — material downside risk in this region.`);
      }}

      return lines.map(l => `<p class="mb-1">${{l}}</p>`).join('');
    }}

    function renderCioRegionPanel(regionKey) {{
      const data = getCioRegionData(regionKey);
      const {{ etfs, maIntact, fullStack, maBroken, avgWksDown, breadthPct, total, label }} = data;

      const breadthColor = breadthPct >= 70 ? 'emerald' : breadthPct >= 40 ? 'yellow' : 'red';

      return `
        <!-- Headline Metrics -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div class="bg-emerald-900/20 border border-emerald-700/40 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-emerald-400">${{maIntact}}<span class="text-sm text-slate-500">/${{total}}</span></div>
            <div class="text-xs text-slate-400">MA Intact (3/3)</div>
          </div>
          <div class="bg-indigo-900/20 border border-indigo-700/40 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-indigo-400">${{fullStack}}<span class="text-sm text-slate-500">/${{total}}</span></div>
            <div class="text-xs text-slate-400">Full Stack (≥2/3)</div>
          </div>
          <div class="bg-red-900/20 border border-red-700/40 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-red-400">${{maBroken}}<span class="text-sm text-slate-500">/${{total}}</span></div>
            <div class="text-xs text-slate-400">MA Broken (0/3)</div>
          </div>
          <div class="bg-slate-800 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-${{breadthColor}}-400">${{avgWksDown.toFixed(1)}}</div>
            <div class="text-xs text-slate-400">Avg Wks Down</div>
          </div>
        </div>

        <!-- Z-Score Color Strip -->
        <div class="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
          <h4 class="text-sm font-bold text-slate-400 mb-2">Z-Score Heatmap — ${{label}}</h4>
          ${{renderColorStrip(etfs)}}
        </div>

        <!-- ETF Cards by MA Tier -->
        <div class="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
          <h4 class="text-sm font-bold text-slate-400 mb-3">ETFs by MA Tier</h4>
          ${{renderEtfCardsByTier(etfs)}}
        </div>

        <!-- Signal Readings -->
        <div class="bg-slate-900/50 border border-slate-800 rounded-xl p-4">
          <h4 class="text-sm font-bold text-slate-400 mb-2">📖 Signal Reading — ${{label}}</h4>
          <div class="text-sm text-slate-300 leading-relaxed">${{generateSignalReading(data)}}</div>
        </div>
      `;
    }}

    function renderCioOverview() {{
      // Aggregate breadth across all regions
      const allData = getCioRegionData('overview');
      const regionKeys = ['us', 'dm', 'em', 'commodities', 'taa'];
      const regionDataList = regionKeys.map(k => ({{ key: k, ...getCioRegionData(k) }}));

      // MA Breadth Score verdict
      const breadthPct = allData.breadthPct;
      let verdict, verdictColor, verdictIcon;
      if (breadthPct >= 70) {{
        verdict = 'FULL INVESTED'; verdictColor = 'emerald'; verdictIcon = '🟢';
      }} else if (breadthPct >= 50) {{
        verdict = 'LEAN INVESTED'; verdictColor = 'green'; verdictIcon = '🟡';
      }} else if (breadthPct >= 30) {{
        verdict = 'REDUCE EXPOSURE'; verdictColor = 'yellow'; verdictIcon = '🟠';
      }} else {{
        verdict = 'RAISE CASH'; verdictColor = 'red'; verdictIcon = '🔴';
      }}

      // Distribution bar data
      const ma3 = allData.etfs.filter(e => e.maStatus === 3).length;
      const ma2 = allData.etfs.filter(e => e.maStatus === 2).length;
      const ma1 = allData.etfs.filter(e => e.maStatus === 1).length;
      const ma0 = allData.etfs.filter(e => e.maStatus === 0).length;
      const t = allData.total || 1;

      // Regional conviction panel
      const convictionRows = regionDataList.map(r => {{
        const bPct = r.breadthPct;
        let signal, sColor;
        if (bPct >= 70) {{ signal = 'Strong'; sColor = 'emerald'; }}
        else if (bPct >= 40) {{ signal = 'Mixed'; sColor = 'yellow'; }}
        else {{ signal = 'Weak'; sColor = 'red'; }}
        return `<tr class="border-t border-slate-800">
          <td class="px-3 py-2 font-medium">${{r.label}}</td>
          <td class="px-3 py-2 text-center mono">${{r.total}}</td>
          <td class="px-3 py-2 text-center mono text-emerald-400">${{r.maIntact}}</td>
          <td class="px-3 py-2 text-center mono text-red-400">${{r.maBroken}}</td>
          <td class="px-3 py-2 text-center mono">${{r.avgWksDown.toFixed(1)}}</td>
          <td class="px-3 py-2 text-center"><span class="px-2 py-0.5 rounded text-xs font-bold bg-${{sColor}}-900/40 text-${{sColor}}-400">${{signal}}</span></td>
        </tr>`;
      }}).join('');

      // Cash vs Exposure playbook
      let playbookLines = [];
      if (breadthPct >= 70) {{
        playbookLines = [
          'Breadth is strong — stay fully invested in top-ranked momentum names.',
          'Use position limits (max 15%) and correlation filters to manage concentration.',
          'Cash allocation: 0-5%. Opportunity cost of sitting out is high.'
        ];
      }} else if (breadthPct >= 50) {{
        playbookLines = [
          'Breadth is adequate but not commanding — lean invested with selectivity.',
          'Favor regions showing MA 3/3 breadth above 60%. Trim lagging regions.',
          'Cash allocation: 10-20%. Keep dry powder for breakdown or re-acceleration.'
        ];
      }} else if (breadthPct >= 30) {{
        playbookLines = [
          'Breadth is deteriorating — reduce gross exposure and tighten stops.',
          'Only hold ETFs with MA 3/3 status. Exit broken names promptly.',
          'Cash allocation: 25-40%. Protect capital; the market is not rewarding broad bets.'
        ];
      }} else {{
        playbookLines = [
          'Breadth is broken — raise significant cash immediately.',
          'Sell all positions below MA 2/3. Only keep strongest momentum survivors.',
          'Cash allocation: 50%+. Capital preservation is the priority until breadth recovers above 40%.'
        ];
      }}

      return `
        <!-- Verdict Banner -->
        <div class="bg-${{verdictColor}}-900/20 border-2 border-${{verdictColor}}-600/50 rounded-xl p-5 mb-4 text-center">
          <div class="text-4xl mb-2">${{verdictIcon}}</div>
          <div class="text-2xl font-bold text-${{verdictColor}}-400">${{verdict}}</div>
          <div class="text-sm text-slate-400 mt-1">MA Breadth Score: <span class="mono font-bold text-${{verdictColor}}-400">${{breadthPct.toFixed(0)}}%</span> of ETFs hold all 3 MAs</div>
        </div>

        <!-- Distribution Bars -->
        <div class="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
          <h4 class="text-sm font-bold text-slate-400 mb-3">MA Status Distribution</h4>
          <div class="space-y-2">
            <div class="flex items-center gap-3">
              <span class="text-xs text-emerald-400 w-16">3/3</span>
              <div class="flex-1 bg-slate-800 rounded-full h-5 overflow-hidden">
                <div class="bg-emerald-500 h-full rounded-full transition-all" style="width:${{(ma3/t*100).toFixed(1)}}%"></div>
              </div>
              <span class="mono text-xs text-slate-400 w-16 text-right">${{ma3}} (${{(ma3/t*100).toFixed(0)}}%)</span>
            </div>
            <div class="flex items-center gap-3">
              <span class="text-xs text-yellow-400 w-16">2/3</span>
              <div class="flex-1 bg-slate-800 rounded-full h-5 overflow-hidden">
                <div class="bg-yellow-500 h-full rounded-full transition-all" style="width:${{(ma2/t*100).toFixed(1)}}%"></div>
              </div>
              <span class="mono text-xs text-slate-400 w-16 text-right">${{ma2}} (${{(ma2/t*100).toFixed(0)}}%)</span>
            </div>
            <div class="flex items-center gap-3">
              <span class="text-xs text-orange-400 w-16">1/3</span>
              <div class="flex-1 bg-slate-800 rounded-full h-5 overflow-hidden">
                <div class="bg-orange-500 h-full rounded-full transition-all" style="width:${{(ma1/t*100).toFixed(1)}}%"></div>
              </div>
              <span class="mono text-xs text-slate-400 w-16 text-right">${{ma1}} (${{(ma1/t*100).toFixed(0)}}%)</span>
            </div>
            <div class="flex items-center gap-3">
              <span class="text-xs text-red-400 w-16">0/3</span>
              <div class="flex-1 bg-slate-800 rounded-full h-5 overflow-hidden">
                <div class="bg-red-500 h-full rounded-full transition-all" style="width:${{(ma0/t*100).toFixed(1)}}%"></div>
              </div>
              <span class="mono text-xs text-slate-400 w-16 text-right">${{ma0}} (${{(ma0/t*100).toFixed(0)}}%)</span>
            </div>
          </div>
        </div>

        <!-- Regional Conviction Panel -->
        <div class="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
          <h4 class="text-sm font-bold text-slate-400 mb-3">Regional Conviction</h4>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-slate-500 text-xs">
                  <th class="px-3 py-2 text-left">Region</th>
                  <th class="px-3 py-2 text-center">ETFs</th>
                  <th class="px-3 py-2 text-center">MA 3/3</th>
                  <th class="px-3 py-2 text-center">MA 0/3</th>
                  <th class="px-3 py-2 text-center">Avg Wks↓</th>
                  <th class="px-3 py-2 text-center">Signal</th>
                </tr>
              </thead>
              <tbody>${{convictionRows}}</tbody>
            </table>
          </div>
        </div>

        <!-- Z-Score Heatmap (all) -->
        <div class="bg-slate-900/50 border border-slate-800 rounded-xl p-4 mb-4">
          <h4 class="text-sm font-bold text-slate-400 mb-2">Z-Score Heatmap — All Regions</h4>
          ${{renderColorStrip(allData.etfs)}}
        </div>

        <!-- Cash vs Exposure Playbook -->
        <div class="bg-${{verdictColor}}-900/15 border border-${{verdictColor}}-700/40 rounded-xl p-5">
          <h4 class="text-sm font-bold text-${{verdictColor}}-400 mb-3">💰 Cash vs Exposure Playbook</h4>
          <ul class="space-y-2 text-sm text-slate-300">
            ${{playbookLines.map(l => `<li class="flex gap-2"><span class="text-${{verdictColor}}-400 mt-0.5">▸</span> ${{l}}</li>`).join('')}}
          </ul>
        </div>
      `;
    }}

    function renderCioSubTab(tabId) {{
      const container = document.getElementById('cio-subtab-' + tabId);
      if (tabId === 'overview') {{
        container.innerHTML = renderCioOverview();
      }} else {{
        container.innerHTML = renderCioRegionPanel(tabId);
      }}
    }}

    // ========== PORTFOLIO ANALYZER ==========

    // Map a ticker to its native trading currency. Yahoo Finance returns
    // prices in the security's local currency (e.g. 3110.HK is quoted in
    // HKD), so we need to know the source currency to convert to USD.
    function getInstrumentCurrency(ticker) {{
      const t = (ticker || '').toUpperCase();
      if (t.endsWith('.HK')) return 'HKD';
      return 'USD';
    }}

    // Live FX rates: multiply a native-currency amount by rates[ccy] to get USD.
    const analyzerFxRates = {{ USD: 1 }};
    let analyzerFxLoaded = false;
    let analyzerFxPromise = null;
    let analyzerFxWarning = null;

    function loadAnalyzerFxRates() {{
      if (analyzerFxLoaded) return Promise.resolve(analyzerFxRates);
      if (analyzerFxPromise) return analyzerFxPromise;
      // Primary: open.er-api.com (free, no key). Fall back to Frankfurter.
      const sources = [
        {{
          url: 'https://open.er-api.com/v6/latest/HKD',
          extract: data => data && data.rates && data.rates.USD,
        }},
        {{
          url: 'https://api.frankfurter.app/latest?from=HKD&to=USD',
          extract: data => data && data.rates && data.rates.USD,
        }},
      ];
      const tryNext = (i) => {{
        if (i >= sources.length) {{
          throw new Error('All FX providers failed');
        }}
        return fetch(sources[i].url)
          .then(r => {{
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
          }})
          .then(data => {{
            const rate = sources[i].extract(data);
            if (typeof rate !== 'number' || !(rate > 0)) {{
              throw new Error('missing USD rate');
            }}
            return rate;
          }})
          .catch(err => {{
            console.warn('[PortfolioAnalyzer] FX source failed (' + sources[i].url + '):', err);
            return tryNext(i + 1);
          }});
      }};
      analyzerFxPromise = tryNext(0)
        .then(rate => {{
          analyzerFxRates.HKD = rate;
          analyzerFxLoaded = true;
          analyzerFxWarning = null;
          return analyzerFxRates;
        }})
        .catch(err => {{
          analyzerFxPromise = null;
          analyzerFxWarning = 'Could not fetch live FX rates — non-USD prices (e.g. .HK tickers in HKD) are shown in native currency.';
          throw err;
        }});
      return analyzerFxPromise;
    }}

    function toUsd(value, currency) {{
      if (!value) return 0;
      if (currency === 'USD') return value;
      const rate = analyzerFxRates[currency];
      return typeof rate === 'number' ? value * rate : value;
    }}

    function showAnalyzerLoading(show, detail) {{
      document.getElementById('analyzer-dropzone').classList.toggle('hidden', show);
      document.getElementById('analyzer-loading').classList.toggle('hidden', !show);
      if (detail) document.getElementById('analyzer-loading-detail').textContent = detail;
    }}

    function showAnalyzerError(message) {{
      showAnalyzerLoading(false);
      const banner = document.getElementById('analyzer-error');
      const msgEl = document.getElementById('analyzer-error-msg');
      if (banner && msgEl) {{
        msgEl.textContent = message;
        banner.classList.remove('hidden');
      }}
      console.error('[PortfolioAnalyzer]', message);
    }}

    function clearAnalyzerError() {{
      const banner = document.getElementById('analyzer-error');
      if (banner) banner.classList.add('hidden');
    }}

    function handleAnalyzerFile(file) {{
      if (!file) {{
        showAnalyzerError('No file selected.');
        return;
      }}
      clearAnalyzerError();
      showAnalyzerLoading(true, 'Reading ' + file.name);
      const reader = new FileReader();
      reader.onerror = function() {{
        const err = reader.error;
        showAnalyzerError('Failed to read file "' + file.name + '": ' + (err && err.message ? err.message : 'unknown I/O error'));
      }};
      reader.onload = function(e) {{
        // Defer to let the loading UI paint
        requestAnimationFrame(() => {{
          setTimeout(() => {{
            document.getElementById('analyzer-loading-detail').textContent = 'Fetching live FX rates…';
            loadAnalyzerFxRates()
              .catch(err => {{
                console.warn('[PortfolioAnalyzer] FX rate load failed, HKD prices will not be converted', err);
              }})
              .then(() => {{
                try {{
                  parseAnalyzerCSV(e.target.result);
                }} catch (err) {{
                  showAnalyzerError(err && err.message ? err.message : String(err));
                  return;
                }}
                persistAnalyzerPortfolio(e.target.result);
                analyzerAutoLoaded = true;
                const badge = document.getElementById('analyzer-persist-badge');
                if (badge) {{
                  const now = new Date();
                  badge.textContent = 'Last uploaded: ' + now.toLocaleDateString(undefined, {{ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }});
                  badge.classList.remove('hidden');
                }}
              }});
          }}, 50);
        }});
      }};
      reader.readAsText(file);
    }}

    function persistAnalyzerPortfolio(csvText) {{
      fetch('/api/portfolios', {{
        method: 'PUT',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ name: '__last_analyzer__', csvText, holdings: [] }}),
      }})
        .then(async r => {{
          if (!r.ok) {{
            let detail = '';
            try {{ detail = (await r.json()).error || ''; }} catch (_) {{ detail = await r.text().catch(() => ''); }}
            throw new Error('Persist failed (HTTP ' + r.status + ')' + (detail ? ': ' + detail : ''));
          }}
        }})
        .catch(err => {{
          showAnalyzerError('Could not save portfolio to server: ' + (err && err.message ? err.message : String(err)) + '. Your analysis is still shown below.');
        }});
    }}

    let analyzerAutoLoaded = false;
    function loadPersistedAnalyzer() {{
      if (analyzerAutoLoaded) return;
      // Skip if results are already displayed
      if (!document.getElementById('analyzer-results').classList.contains('hidden')) return;
      analyzerAutoLoaded = true;
      clearAnalyzerError();
      showAnalyzerLoading(true, 'Loading last portfolio…');
      Promise.all([
        fetch('/api/portfolios?name=__last_analyzer__').then(async r => {{
          if (r.status === 404) return null; // no saved portfolio — expected on first visit
          if (!r.ok) {{
            let detail = '';
            try {{ detail = (await r.json()).error || ''; }} catch (_) {{ detail = await r.text().catch(() => ''); }}
            throw new Error('Load failed (HTTP ' + r.status + ')' + (detail ? ': ' + detail : ''));
          }}
          return r.json();
        }}),
        loadAnalyzerFxRates().catch(err => {{
          console.warn('[PortfolioAnalyzer] FX rate load failed, HKD prices will not be converted', err);
        }}),
      ])
        .then(([data]) => {{
          if (data === null) {{
            // No saved portfolio — quietly return to dropzone
            showAnalyzerLoading(false);
            analyzerAutoLoaded = false;
            return;
          }}
          if (!data.csvText) {{
            showAnalyzerLoading(false);
            analyzerAutoLoaded = false;
            showAnalyzerError('Saved portfolio is missing csvText. Please re-upload your CSV.');
            return;
          }}
          try {{
            parseAnalyzerCSV(data.csvText);
          }} catch (err) {{
            showAnalyzerError('Saved portfolio failed to parse: ' + (err && err.message ? err.message : String(err)));
            return;
          }}
          const ts = data.savedAt ? new Date(data.savedAt) : null;
          if (ts) {{
            const badge = document.getElementById('analyzer-persist-badge');
            if (badge) {{
              badge.textContent = 'Last uploaded: ' + ts.toLocaleDateString(undefined, {{ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }});
              badge.classList.remove('hidden');
            }}
          }}
        }})
        .catch(err => {{
          analyzerAutoLoaded = false;
          showAnalyzerError('Could not load saved portfolio: ' + (err && err.message ? err.message : String(err)));
        }});
    }}

    function detectDelimiter(line) {{
      return line.split('\\t').length > line.split(',').length ? '\\t' : ',';
    }}

    function splitLine(line, delim) {{
      const cols = [];
      let cur = '', inQ = false;
      for (let i = 0; i < line.length; i++) {{
        const ch = line[i];
        if (ch === '"') {{ inQ = !inQ; }}
        else if (ch === delim && !inQ) {{ cols.push(cur.trim()); cur = ''; }}
        else {{ cur += ch; }}
      }}
      cols.push(cur.trim());
      return cols;
    }}

    function cleanNum(val) {{
      if (!val) return 0;
      return parseFloat(val.replace(/[^0-9.\\-]/g, '')) || 0;
    }}

    function parseAnalyzerCSV(text) {{
      if (typeof text !== 'string' || text.trim() === '') {{
        throw new Error('CSV is empty. Expected header row with a "Symbol" column plus at least one data row.');
      }}
      const lines = text.trim().split(/\\r?\\n/);
      if (lines.length < 2) {{
        throw new Error('CSV has ' + lines.length + ' row(s); expected a header row plus at least one data row.');
      }}

      const delim = detectDelimiter(lines[0]);
      const header = splitLine(lines[0], delim).map(h => h.trim().toLowerCase().replace(/[^a-z0-9]/g, ''));
      const symIdx = header.findIndex(h => h === 'symbol' || h === 'ticker' || h === 'sym');
      const sharesIdx = header.findIndex(h => h === 'shares' || h === 'quantity' || h === 'qty' || h === 'units' || h === 'position' || h === 'amount');
      const costIdx = header.findIndex(h => h === 'avgprice' || h === 'avgcost' || h.includes('cost') || h.includes('basis'));
      const mktValIdx = header.findIndex(h => h === 'marketvalue' || h === 'mktval' || h === 'mktvalue' || (h.includes('market') && h.includes('val')));
      const weightIdx = header.findIndex(h => h === 'weight' || h === 'wt' || h === 'allocation' || h.includes('alloc'));
      const typeIdx = header.findIndex(h => h === 'type' || h === 'side' || h === 'action' || h === 'buysell');

      if (symIdx === -1) {{
        throw new Error('CSV must contain a "Symbol" column (accepted headers: Symbol, Ticker, Sym). Found headers: ' + splitLine(lines[0], delim).join(', '));
      }}

      // Build a ticker map keyed by both the full universe ticker ("3110.HK",
      // "BAMI.MI") and its bare form ("3110", "BAMI"), so CSV inputs match
      // regardless of whether the exchange suffix is present.
      const tickerMap = {{}};
      etfUniverse.forEach(inst => {{
        const full = inst.ticker.toUpperCase();
        tickerMap[full] = inst;
        const bare = full.split('.')[0];
        if (bare && bare !== full && !tickerMap[bare]) {{
          tickerMap[bare] = inst;
        }}
      }});

      const holdings = [];
      const unrecognized = [];
      const filteredSellRows = [];
      let skippedBlankRows = 0;

      for (let i = 1; i < lines.length; i++) {{
        const cols = splitLine(lines[i], delim);
        if (!cols[symIdx]) {{ skippedBlankRows++; continue; }}
        const rawSym = cols[symIdx].toUpperCase().replace(/[^A-Z0-9.]/g, '');
        if (!rawSym) {{ skippedBlankRows++; continue; }}

        // Filter broker-export Type column: include BUY/LONG, skip SELL/SHORT/EXIT
        if (typeIdx !== -1) {{
          const type = (cols[typeIdx] || '').trim().toUpperCase();
          if (type && /^(SELL|SHORT|EXIT|CLOSE|SLD)/.test(type)) {{
            filteredSellRows.push(rawSym + ' (' + type + ')');
            continue;
          }}
        }}

        const shares = sharesIdx !== -1 ? cleanNum(cols[sharesIdx]) : 0;
        const costBasis = costIdx !== -1 ? cleanNum(cols[costIdx]) : 0;
        const csvMktVal = mktValIdx !== -1 ? cleanNum(cols[mktValIdx]) : null;
        const csvWeight = weightIdx !== -1 ? cleanNum(cols[weightIdx]) : null;

        // Match against universe. Try the symbol as-entered first so
        // "3110.HK" matches the universe entry "3110.HK" directly; fall back
        // to the bare form so "SHY.O" matches universe entry "SHY" and "3110"
        // matches "3110.HK" via the aliased key.
        let instrument = tickerMap[rawSym];
        if (!instrument && rawSym.includes('.')) {{
          const bare = rawSym.split('.')[0];
          if (bare) instrument = tickerMap[bare];
        }}
        if (!instrument) {{
          unrecognized.push(rawSym);
          continue;
        }}
        const sym = instrument.ticker.toUpperCase();
        // Normalize everything to USD. Yahoo Finance quotes 3110.HK in HKD, and
        // broker CSV exports typically report cost basis / market value in the
        // security's native currency — convert both using the live FX rate so
        // all downstream math and display is in USD.
        const currency = getInstrumentCurrency(instrument.ticker);
        const usdInstrument = currency === 'USD'
          ? instrument
          : Object.assign({{}}, instrument, {{ price: toUsd(instrument.price, currency) }});
        holdings.push({{
          symbol: sym,
          shares,
          costBasis: toUsd(costBasis, currency),
          csvMktVal: csvMktVal !== null ? toUsd(csvMktVal, currency) : null,
          csvWeight,
          instrument: usdInstrument,
          currency,
        }});
      }}

      if (holdings.length === 0) {{
        const parts = [];
        parts.push('No recognized holdings found in CSV.');
        if (unrecognized.length > 0) parts.push('Unrecognized symbols (' + unrecognized.length + '): ' + unrecognized.join(', ') + '. These tickers are not in the ETF universe.');
        if (filteredSellRows.length > 0) parts.push('Skipped ' + filteredSellRows.length + ' non-BUY row(s): ' + filteredSellRows.join(', ') + '.');
        if (skippedBlankRows > 0) parts.push(skippedBlankRows + ' row(s) had an empty Symbol column and were skipped.');
        throw new Error(parts.join(' '));
      }}

      document.getElementById('analyzer-loading-detail').textContent = 'Scoring ' + holdings.length + ' holdings…';
      try {{
        renderAnalyzer(holdings, unrecognized, filteredSellRows);
      }} catch (err) {{
        throw new Error('Failed to render analyzer after parsing ' + holdings.length + ' holdings: ' + (err && err.message ? err.message : String(err)));
      }}
    }}

    function renderAnalyzer(holdings, unrecognized, filteredSellRows) {{
      filteredSellRows = filteredSellRows || [];
      const banner = document.getElementById('analyzer-unrecognized');
      const notes = [];
      if (analyzerFxWarning) {{
        notes.push(analyzerFxWarning);
      }}
      if (unrecognized.length > 0) {{
        notes.push('Unrecognized symbols: ' + unrecognized.join(', '));
      }}
      if (filteredSellRows.length > 0) {{
        notes.push('Skipped ' + filteredSellRows.length + ' non-BUY row(s): ' + filteredSellRows.join(', '));
      }}
      if (notes.length > 0) {{
        banner.classList.remove('hidden');
        document.getElementById('analyzer-unrecognized-list').textContent = ' ' + notes.join(' · ');
      }} else {{
        banner.classList.add('hidden');
      }}

      holdings.forEach(h => {{
        const scored = calculateScore(h.instrument);
        h.instrument = scored;
        h.score = scored.score;
        const computedMktVal = h.shares * h.instrument.price;
        h.mktValue = computedMktVal > 0 ? computedMktVal : (h.csvMktVal || 0);
        if (h.mktValue > 0 && h.shares === 0 && h.instrument.price > 0) {{
          h.shares = h.mktValue / h.instrument.price;
        }}
        h.pnl = h.shares * (h.instrument.price - h.costBasis);
        h.pnlPct = h.costBasis > 0 ? ((h.instrument.price - h.costBasis) / h.costBasis * 100) : 0;
      }});

      const totalValue = holdings.reduce((s, h) => s + h.mktValue, 0);
      const totalCost = holdings.reduce((s, h) => s + h.shares * h.costBasis, 0);
      const totalPnL = holdings.reduce((s, h) => s + h.pnl, 0);
      const totalPnLPct = totalCost > 0 ? (totalPnL / totalCost * 100) : 0;
      const avgScore = holdings.length > 0 ? holdings.reduce((s, h) => s + h.score, 0) / holdings.length : 0;

      document.getElementById('analyzer-summary').innerHTML = [
        {{ label: 'Holdings', value: holdings.length, color: 'indigo' }},
        {{ label: 'Market Value', value: '$' + totalValue.toLocaleString(undefined, {{minimumFractionDigits:0, maximumFractionDigits:0}}), color: 'cyan' }},
        {{ label: 'Total P&L', value: (totalPnL >= 0 ? '+' : '') + '$' + totalPnL.toLocaleString(undefined, {{minimumFractionDigits:0, maximumFractionDigits:0}}) + ' (' + totalPnLPct.toFixed(1) + '%)', color: totalPnL >= 0 ? 'emerald' : 'red' }},
        {{ label: 'Avg Score', value: avgScore.toFixed(1), color: avgScore >= 60 ? 'emerald' : avgScore >= 40 ? 'amber' : 'red' }},
      ].map(c => `<div class="bg-slate-900/50 rounded-xl border border-slate-800 p-4">
        <div class="text-xs text-slate-400 uppercase mb-1">${{c.label}}</div>
        <div class="text-xl font-bold text-${{c.color}}-400 mono">${{c.value}}</div>
      </div>`).join('');

      // Risk Strip
      const wtdScore = totalValue > 0
        ? holdings.reduce((s, h) => s + h.score * h.mktValue, 0) / totalValue
        : 0;
      const ma3Count = holdings.filter(h => h.instrument.aboveMA30 && h.instrument.aboveMA60 && h.instrument.aboveMA200).length;
      const ma0Count = holdings.filter(h => !h.instrument.aboveMA30 && !h.instrument.aboveMA60 && !h.instrument.aboveMA200).length;
      const sellCount = ma0Count;
      const heldTickers = new Set(holdings.map(h => h.symbol));
      const buyCount = rankedETFs.filter(e => e.isETF && !heldTickers.has(e.ticker) && e.score >= 60 && e.aboveMA30 && e.aboveMA60 && e.aboveMA200).length;
      const MAX_CLASS_PCT = 30;
      const countryWtsRisk = {{}};
      const sectorWtsRisk = {{}};
      holdings.forEach(h => {{
        const c = h.instrument.country || 'Unknown';
        const s = h.instrument.sector || 'Unknown';
        countryWtsRisk[c] = (countryWtsRisk[c] || 0) + h.mktValue;
        sectorWtsRisk[s] = (sectorWtsRisk[s] || 0) + h.mktValue;
      }});
      let violations = 0;
      if (totalValue > 0) {{
        Object.values(countryWtsRisk).forEach(v => {{ if (v / totalValue * 100 > MAX_CLASS_PCT) violations++; }});
        Object.values(sectorWtsRisk).forEach(v => {{ if (v / totalValue * 100 > MAX_CLASS_PCT) violations++; }});
      }}

      document.getElementById('analyzer-risk-strip').innerHTML = [
        {{ label: 'Wtd Score', value: wtdScore.toFixed(1), color: wtdScore >= 60 ? 'emerald' : wtdScore >= 40 ? 'amber' : 'red' }},
        {{ label: 'MA\u20053 Holdings', value: ma3Count, color: 'emerald' }},
        {{ label: 'MA\u20050 Holdings', value: ma0Count, color: 'red' }},
        {{ label: 'Sell Signals', value: sellCount, color: 'red' }},
        {{ label: 'Buy Candidates', value: buyCount, color: 'emerald' }},
        {{ label: 'Violations', value: violations, color: 'red' }},
      ].map(c => `<div class="bg-slate-900/50 rounded-xl border border-slate-800 p-4 text-center">
        <div class="text-xs text-slate-400 uppercase mb-1">${{c.label}}</div>
        <div class="text-2xl font-bold text-${{c.color}}-400 mono">${{c.value}}</div>
      </div>`).join('');

      // Score Distribution Panel
      renderAnalyzerDistribution(holdings, totalValue);

      // Holdings table — compute maStatus, store globally, render
      holdings.forEach(h => {{
        h.maStatus = (h.instrument.aboveMA30 ? 1 : 0) + (h.instrument.aboveMA60 ? 1 : 0) + (h.instrument.aboveMA200 ? 1 : 0);
        h.weight = totalValue > 0 ? (h.mktValue / totalValue * 100) : 0;
      }});
      holdings.sort((a, b) => b.maStatus - a.maStatus || b.score - a.score);
      analyzerHoldings = holdings;
      analyzerTotalValue = totalValue;
      analyzerSort.holdings = {{ column: 'maStatus', direction: 'desc' }};
      renderAnalyzerHoldingsTable();

      // Sell/Reduce + Buy Candidates
      renderAnalyzerActions(holdings, totalValue);

      showAnalyzerLoading(false);
      document.getElementById('analyzer-results').classList.remove('hidden');
    }}

    // ---- Analyzer table rendering functions ----
    const maDot = (above) => above
      ? '<span class="inline-block w-3 h-3 rounded-full bg-emerald-500"></span>'
      : '<span class="inline-block w-3 h-3 rounded-full border border-slate-600"></span>';

    const maPillColors = {{
      3: 'bg-emerald-900 text-emerald-300',
      2: 'bg-emerald-800/60 text-emerald-400',
      1: 'bg-amber-900/60 text-amber-300',
      0: 'bg-red-900/60 text-red-300',
    }};

    function renderAnalyzerHoldingsTable() {{
      const holdings = analyzerHoldings;
      const totalValue = analyzerTotalValue;
      document.getElementById('analyzer-table').innerHTML = holdings.map(h => {{
        const weight = totalValue > 0 ? (h.mktValue / totalValue * 100) : 0;
        const scoreColor = h.score >= 60 ? 'text-emerald-400' : h.score >= 40 ? 'text-amber-400' : 'text-red-400';
        const borderClass = h.maStatus === 0 ? 'border-l-2 border-l-red-500' : h.maStatus === 1 ? 'border-l-2 border-l-amber-500' : '';
        return `<tr class="border-b border-slate-800 hover:bg-slate-800/50 ${{borderClass}}">
          <td class="p-3 font-medium text-white mono">${{h.symbol}}</td>
          <td class="p-3 text-center"><span class="px-2 py-0.5 rounded-full text-xs font-bold mono ${{maPillColors[h.maStatus]}}">${{h.maStatus}}/3</span></td>
          <td class="p-3 text-center">${{maDot(h.instrument.aboveMA30)}}</td>
          <td class="p-3 text-center">${{maDot(h.instrument.aboveMA60)}}</td>
          <td class="p-3 text-center">${{maDot(h.instrument.aboveMA200)}}</td>
          <td class="p-3 text-right mono ${{scoreColor}}">${{h.score.toFixed(0)}}</td>
          <td class="p-3 text-right mono text-slate-300">${{h.instrument.price.toFixed(2)}}</td>
          <td class="p-3 text-right mono text-slate-300">${{h.mktValue.toLocaleString(undefined, {{minimumFractionDigits:0, maximumFractionDigits:0}})}}</td>
          <td class="p-3 text-right mono text-slate-300">${{weight.toFixed(1)}}%</td>
          <td class="p-3 text-slate-400 text-xs">${{h.instrument.country || '\u2014'}}</td>
        </tr>`;
      }}).join('');
      updateAnalyzerSortIndicators('holdings');
    }}

    function renderAnalyzerSellTable() {{
      const sellTable = document.getElementById('analyzer-sell-table');
      const sellEmpty = document.getElementById('analyzer-sell-empty');
      if (analyzerSellRows.length === 0) {{
        sellTable.innerHTML = '';
        sellEmpty.classList.remove('hidden');
      }} else {{
        sellEmpty.classList.add('hidden');
        const maPill = (ma) => {{
          const colors = {{ 0: 'bg-red-900/60 text-red-300', 1: 'bg-amber-900/60 text-amber-300', 2: 'bg-emerald-800/60 text-emerald-400', 3: 'bg-emerald-900 text-emerald-300' }};
          return `<span class="px-2 py-0.5 rounded-full text-xs font-bold mono ${{colors[ma]}}">${{ma}}/3</span>`;
        }};
        sellTable.innerHTML = analyzerSellRows.map(r => {{
          const scoreColor = r.score >= 60 ? 'text-emerald-400' : r.score >= 40 ? 'text-amber-400' : 'text-red-400';
          const actionBadge = r.action === 'Exit'
            ? '<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-red-900/60 text-red-300">Exit</span>'
            : '<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-900/60 text-amber-300">Reduce</span>';
          return `<tr class="border-b border-slate-800">
            <td class="p-2.5 font-medium text-white mono">${{r.symbol}}</td>
            <td class="p-2.5 text-center">${{maPill(r.ma)}}</td>
            <td class="p-2.5 text-right mono ${{scoreColor}}">${{r.score.toFixed(0)}}</td>
            <td class="p-2.5 text-xs text-slate-400">${{r.reason}}</td>
            <td class="p-2.5 text-center">${{actionBadge}}</td>
          </tr>`;
        }}).join('');
      }}
      updateAnalyzerSortIndicators('sell');
    }}

    function renderAnalyzerBuyTable() {{
      const buyTable = document.getElementById('analyzer-buy-table');
      const buyEmpty = document.getElementById('analyzer-buy-empty');
      if (analyzerBuyCandidates.length === 0) {{
        buyTable.innerHTML = '';
        buyEmpty.classList.remove('hidden');
      }} else {{
        buyEmpty.classList.add('hidden');
        const totalValue = analyzerTotalValue;
        const countryWts = {{}};
        analyzerHoldings.forEach(h => {{
          const c = h.instrument.country || 'Unknown';
          countryWts[c] = (countryWts[c] || 0) + h.mktValue;
        }});
        buyTable.innerHTML = analyzerBuyCandidates.map(e => {{
          const ma = (e.aboveMA30 ? 1 : 0) + (e.aboveMA60 ? 1 : 0) + (e.aboveMA200 ? 1 : 0);
          const bPillColors = {{ 3: 'bg-emerald-900 text-emerald-300', 2: 'bg-emerald-800/60 text-emerald-400' }};
          const scoreColor = e.score >= 60 ? 'text-emerald-400' : 'text-amber-400';
          const c = e.country || 'Unknown';
          const currentPct = totalValue > 0 ? ((countryWts[c] || 0) / totalValue * 100) : 0;
          const maxPct = getAssetClassMaxPct(c);
          const headroom = (maxPct - currentPct).toFixed(0);
          const whyParts = [];
          whyParts.push(`Score ${{e.score.toFixed(0)}}`);
          whyParts.push(`MA=${{ma}}/3`);
          whyParts.push(`${{c}} has ${{headroom}}% headroom`);
          if (e.return6m > 10) whyParts.push(`+${{e.return6m.toFixed(0)}}% 6M`);
          return `<tr class="border-b border-slate-800">
            <td class="p-2.5 font-medium text-white mono">${{e.ticker}}</td>
            <td class="p-2.5 text-center"><span class="px-2 py-0.5 rounded-full text-xs font-bold mono ${{bPillColors[ma]}}">${{ma}}/3</span></td>
            <td class="p-2.5 text-right mono ${{scoreColor}}">${{e.score.toFixed(0)}}</td>
            <td class="p-2.5 text-xs text-slate-400">${{whyParts.join(' \u00b7 ')}}</td>
          </tr>`;
        }}).join('');
      }}
      updateAnalyzerSortIndicators('buy');
    }}

    function renderAnalyzerRegionTableRows() {{
      document.getElementById('analyzer-region-table').innerHTML = analyzerRegionData.map(([name, r]) => {{
        const totalValue = analyzerTotalValue;
        const wt = totalValue > 0 ? (r.value / totalValue * 100) : 0;
        const avg = r.scores.reduce((s, v) => s + v, 0) / r.scores.length;
        const avgColor = avg >= 60 ? 'text-emerald-400' : avg >= 40 ? 'text-amber-400' : 'text-red-400';
        return `<tr class="border-b border-slate-800">
          <td class="p-2 text-white font-medium">${{name}}</td>
          <td class="p-2 text-right mono text-slate-300">${{r.count}}</td>
          <td class="p-2 text-right mono text-slate-300">${{wt.toFixed(1)}}%</td>
          <td class="p-2 text-right mono text-emerald-400">${{r.ma[3]}}</td>
          <td class="p-2 text-right mono text-emerald-400">${{r.ma[2]}}</td>
          <td class="p-2 text-right mono text-amber-400">${{r.ma[1]}}</td>
          <td class="p-2 text-right mono text-red-400">${{r.ma[0]}}</td>
          <td class="p-2 text-right mono ${{avgColor}}">${{avg.toFixed(0)}}</td>
        </tr>`;
      }}).join('');
      updateAnalyzerSortIndicators('region');
    }}

    // ---- Analyzer sort logic ----
    function getAnalyzerSortValue(tableKey, item, column) {{
      if (tableKey === 'holdings') {{
        switch(column) {{
          case 'symbol': return item.symbol.toLowerCase();
          case 'maStatus': return item.maStatus;
          case 'ma30': return item.instrument.aboveMA30 ? 1 : 0;
          case 'ma60': return item.instrument.aboveMA60 ? 1 : 0;
          case 'ma200': return item.instrument.aboveMA200 ? 1 : 0;
          case 'score': return item.score;
          case 'price': return item.instrument.price;
          case 'mktValue': return item.mktValue;
          case 'weight': return item.weight;
          case 'region': return (item.instrument.country || '').toLowerCase();
        }}
      }} else if (tableKey === 'region') {{
        const [name, r] = item;
        switch(column) {{
          case 'name': return name.toLowerCase();
          case 'count': return r.count;
          case 'wt': return r.value;
          case 'ma3': return r.ma[3];
          case 'ma2': return r.ma[2];
          case 'ma1': return r.ma[1];
          case 'ma0': return r.ma[0];
          case 'avg': return r.scores.reduce((s, v) => s + v, 0) / r.scores.length;
        }}
      }} else if (tableKey === 'sell') {{
        switch(column) {{
          case 'symbol': return item.symbol.toLowerCase();
          case 'ma': return item.ma;
          case 'score': return item.score;
          case 'reason': return item.reason.toLowerCase();
          case 'action': return item.action.toLowerCase();
        }}
      }} else if (tableKey === 'buy') {{
        switch(column) {{
          case 'symbol': return item.ticker.toLowerCase();
          case 'ma': return (item.aboveMA30 ? 1 : 0) + (item.aboveMA60 ? 1 : 0) + (item.aboveMA200 ? 1 : 0);
          case 'score': return item.score;
        }}
      }}
      return 0;
    }}

    function sortAnalyzerColumn(tableKey, column) {{
      const state = analyzerSort[tableKey];
      if (state.column === column) {{
        state.direction = state.direction === 'asc' ? 'desc' : 'asc';
      }} else {{
        state.column = column;
        const stringCols = ['symbol', 'region', 'name', 'reason', 'action'];
        state.direction = stringCols.includes(column) ? 'asc' : 'desc';
      }}

      const dir = state.direction === 'asc' ? 1 : -1;
      const getData = (tableKey) => {{
        switch(tableKey) {{
          case 'holdings': return analyzerHoldings;
          case 'region': return analyzerRegionData;
          case 'sell': return analyzerSellRows;
          case 'buy': return analyzerBuyCandidates;
        }}
      }};
      const data = getData(tableKey);
      data.sort((a, b) => {{
        const va = getAnalyzerSortValue(tableKey, a, column);
        const vb = getAnalyzerSortValue(tableKey, b, column);
        if (va < vb) return -1 * dir;
        if (va > vb) return 1 * dir;
        return 0;
      }});

      switch(tableKey) {{
        case 'holdings': renderAnalyzerHoldingsTable(); break;
        case 'region': renderAnalyzerRegionTableRows(); break;
        case 'sell': renderAnalyzerSellTable(); break;
        case 'buy': renderAnalyzerBuyTable(); break;
      }}
    }}

    function updateAnalyzerSortIndicators(tableKey) {{
      document.querySelectorAll(`[id^="az-sort-${{tableKey}}-"]`).forEach(el => el.textContent = '');
      const state = analyzerSort[tableKey];
      if (state.column) {{
        const el = document.getElementById(`az-sort-${{tableKey}}-${{state.column}}`);
        if (el) el.textContent = state.direction === 'asc' ? '\u2191' : '\u2193';
      }}
    }}

    // CIO Max% per asset class (country/region). Anything not listed defaults to 25%.
    const CIO_MAX_PCT = {{
      'US': 40, 'Commodities': 20, 'India': 15,
      'Emerging Markets': 20, 'Developed Markets': 30,
      'Japan': 15, 'China': 15, 'Brazil': 10, 'Taiwan': 10,
    }};
    const CIO_DEFAULT_MAX_PCT = 25;

    function getAssetClassMaxPct(country) {{
      return CIO_MAX_PCT[country] || CIO_DEFAULT_MAX_PCT;
    }}

    function renderAnalyzerActions(holdings, totalValue) {{
      const countryWts = {{}};
      holdings.forEach(h => {{
        const c = h.instrument.country || 'Unknown';
        countryWts[c] = (countryWts[c] || 0) + h.mktValue;
      }});

      // --- Sell / Reduce ---
      const sellRows = [];
      holdings.forEach(h => {{
        const ma = h.maStatus;
        const countryPct = totalValue > 0 ? (countryWts[h.instrument.country || 'Unknown'] / totalValue * 100) : 0;
        const maxPct = getAssetClassMaxPct(h.instrument.country || 'Unknown');
        const reasons = [];
        let action = null;

        if (ma === 0) {{
          reasons.push('MA=0/3 \u2014 all MAs broken');
          action = 'Exit';
        }} else if (ma === 1 && h.score < 50) {{
          reasons.push('MA=1/3 + Score < 50');
          action = 'Exit';
        }} else if (ma === 1 && h.score >= 50) {{
          reasons.push('MA=1/3 + Score \u2265 50');
          action = 'Reduce';
        }}

        if (countryPct > maxPct) {{
          reasons.push(`${{h.instrument.country}} at ${{countryPct.toFixed(0)}}% > ${{maxPct}}% max`);
          if (!action) action = 'Reduce';
        }}

        if (action) {{
          sellRows.push({{ symbol: h.symbol, ma, score: h.score, reason: reasons.join('; '), action }});
        }}
      }});

      analyzerSellRows = sellRows;
      analyzerSort.sell = {{ column: 'ma', direction: 'asc' }};
      renderAnalyzerSellTable();

      // --- Buy Candidates ---
      const heldTickers = new Set(holdings.map(h => h.symbol));
      const buyCandidates = rankedETFs.filter(e => {{
        if (!e.isETF || heldTickers.has(e.ticker)) return false;
        const ma = (e.aboveMA30 ? 1 : 0) + (e.aboveMA60 ? 1 : 0) + (e.aboveMA200 ? 1 : 0);
        if (ma < 2 || e.score < 65) return false;
        const c = e.country || 'Unknown';
        const currentPct = totalValue > 0 ? ((countryWts[c] || 0) / totalValue * 100) : 0;
        const maxPct = getAssetClassMaxPct(c);
        return currentPct < maxPct;
      }});

      analyzerBuyCandidates = buyCandidates.slice(0, 15);
      analyzerSort.buy = {{ column: 'score', direction: 'desc' }};
      renderAnalyzerBuyTable();
    }}

    function renderAnalyzerDistribution(holdings, totalValue) {{
      const maGroups = [0, 0, 0, 0];
      const maValues = [0, 0, 0, 0];
      holdings.forEach(h => {{
        const ma = (h.instrument.aboveMA30 ? 1 : 0) + (h.instrument.aboveMA60 ? 1 : 0) + (h.instrument.aboveMA200 ? 1 : 0);
        maGroups[ma]++;
        maValues[ma] += h.mktValue;
      }});

      const maColors = ['#7f1d1d', '#78350f', '#854d0e', '#065f46'];
      const maLabels = ['MA\u20050', 'MA\u20051', 'MA\u20052', 'MA\u20053'];

      const maOrder = [3, 2, 1, 0];
      let maBarHtml = '';
      let maLegendHtml = '';
      maOrder.forEach(i => {{
        const pct = totalValue > 0 ? (maValues[i] / totalValue * 100) : 0;
        if (pct > 0) {{
          maBarHtml += `<div style="width:${{pct}}%;background:${{maColors[i]}}" class="flex items-center justify-center text-xs font-bold text-white/90 mono">${{pct >= 8 ? pct.toFixed(0) + '%' : ''}}</div>`;
        }}
        if (maGroups[i] > 0) {{
          maLegendHtml += `<span class="flex items-center gap-1"><span class="inline-block w-2.5 h-2.5 rounded-sm" style="background:${{maColors[i]}}"></span>${{maLabels[i]}} ${{maGroups[i]}} (${{pct.toFixed(0)}}%)</span>`;
        }}
      }});
      document.getElementById('analyzer-ma-bar').innerHTML = maBarHtml;
      document.getElementById('analyzer-ma-legend').innerHTML = maLegendHtml;

      const scoreBands = [
        {{ label: '\u226570', min: 70, max: Infinity, color: '#065f46', value: 0 }},
        {{ label: '50\u201369', min: 50, max: 70, color: '#78350f', value: 0 }},
        {{ label: '<50', min: -Infinity, max: 50, color: '#7f1d1d', value: 0 }},
      ];
      holdings.forEach(h => {{
        for (const b of scoreBands) {{
          if (h.score >= b.min && h.score < b.max) {{ b.value += h.mktValue; break; }}
        }}
      }});
      let scoreBarHtml = '';
      let scoreLegendHtml = '';
      scoreBands.forEach(b => {{
        const pct = totalValue > 0 ? (b.value / totalValue * 100) : 0;
        if (pct > 0) {{
          scoreBarHtml += `<div style="width:${{pct}}%;background:${{b.color}}" class="flex items-center justify-center text-xs font-bold text-white/90 mono">${{pct >= 8 ? pct.toFixed(0) + '%' : ''}}</div>`;
        }}
        scoreLegendHtml += `<span class="flex items-center gap-1"><span class="inline-block w-2.5 h-2.5 rounded-sm" style="background:${{b.color}}"></span>${{b.label}}</span>`;
      }});
      document.getElementById('analyzer-score-bar').innerHTML = scoreBarHtml;
      document.getElementById('analyzer-score-legend').innerHTML = scoreLegendHtml;

      // Region breakdown table
      const regions = {{}};
      holdings.forEach(h => {{
        const c = h.instrument.country || 'Unknown';
        if (c === 'TAA ETFs') return;
        if (!regions[c]) regions[c] = {{ count: 0, value: 0, scores: [], ma: [0,0,0,0] }};
        const r = regions[c];
        r.count++;
        r.value += h.mktValue;
        r.scores.push(h.score);
        const ma = (h.instrument.aboveMA30 ? 1 : 0) + (h.instrument.aboveMA60 ? 1 : 0) + (h.instrument.aboveMA200 ? 1 : 0);
        r.ma[ma]++;
      }});
      analyzerRegionData = Object.entries(regions).sort((a, b) => b[1].value - a[1].value);
      analyzerSort.region = {{ column: 'wt', direction: 'desc' }};
      renderAnalyzerRegionTableRows();
    }}

    // Initialize
    initFilterDropdowns();
    applyFilters();
    updateConfigSummary();
    renderCioSubTab('overview');
    renderCioConstraints();
  </script>
</body>
</html>'''
    
    return html


def main():
    print("=" * 60)
    print("📊 CIO Momentum Dashboard Generator")
    print("=" * 60)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "mapping.csv")
    
    tickers, sector_map, country_map, name_map, highvol_map, category_map, regions_map = load_etf_universe(csv_path)
    
    prices = fetch_data(tickers)
    if prices is None:
        return
    
    print("\n📈 Calculating metrics...")
    etf_data = []
    for ticker in tickers:
        if ticker in prices.columns:
            metrics = calculate_metrics(prices[ticker], ticker, sector_map, country_map, name_map, category_map, regions_map)
            if metrics:
                etf_data.append(metrics)
                etf_label = "ETF" if metrics['isETF'] else "EQ"
                print(f"  ✓ {ticker} [{etf_label}]: {metrics['return6m']:+.1f}% | Sortino: {metrics['sortino']:.2f} | Z: {metrics['zScore']:.2f}")
    
    print(f"\n✓ Processed {len(etf_data)} symbols")
    
    valid_tickers = [e['ticker'] for e in etf_data]
    correlations = calculate_correlations(prices, valid_tickers)
    print(f"✓ Calculated {len(correlations)} pairwise correlations")
    
    generation_date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    html = generate_html(etf_data, correlations, generation_date)
    
    output_file = os.path.join(script_dir, "index.html")
    with open(output_file, 'w') as f:
        f.write(html)

    print(f"\n✅ Dashboard saved to: {output_file}")

    ui_repo_dir = os.path.join(os.path.dirname(script_dir), "mom-fw-ui")
    ui_index = os.path.join(ui_repo_dir, "index.html")
    if os.path.isdir(ui_repo_dir):
        with open(ui_index, 'w') as f:
            f.write(html)
        print(f"✅ Synced to: {ui_index}")
    elif not os.environ.get("CI"):
        print(f"⚠️  mom-fw-ui not found at {ui_repo_dir} — skipping UI sync")

    print("   Open in browser to view")
    print("=" * 60)


if __name__ == "__main__":
    main()
