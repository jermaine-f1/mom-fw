"""
CIO Momentum Dashboard - Data Generator
=======================================
Fetches live Yahoo Finance data, computes momentum metrics, and writes
a JSON snapshot consumed by the Vite + React dashboard.

Usage:
    pip install yfinance pandas numpy scipy
    python mom_gen.py

Input:  mapping.csv (in same folder as this script)
        Columns: Name, Symbol, Region, Category, Subcategory, High Vol

Output: public/data.json
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from scipy import stats
import json
import os
import sys
import warnings
warnings.filterwarnings('ignore')

# ============== CONFIGURATION ==============
RISK_FREE_RATE = 0.045  # Current ~4.5%

# JSON schema version emitted in data.json. Bump when the shape of
# etfUniverse/correlations changes in a way the frontend must react to.
DATA_SCHEMA_VERSION = 1


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

    df = df.sort_values(
        by='Region',
        key=lambda s: s.eq('TAA ETFs'),
        kind='stable',
    )
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


# Fail the whole run if more than this fraction of tickers produce no metrics.
# Catches yfinance rate-limits or upstream outages that would otherwise
# silently ship a thinned-out dataset.
MAX_DROP_RATE = 0.25


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
            except Exception as e:
                print(f"  ⚠️ Correlation {t1}-{t2} skipped: {e}")

    return correlations


def generate_data(etf_data, correlations, generation_date):
    """Build the JSON payload consumed by the frontend dashboard."""
    return {
        'schemaVersion': DATA_SCHEMA_VERSION,
        'generatedAt': generation_date,
        'etfUniverse': etf_data,
        'correlations': correlations,
    }


def main():
    print("=" * 60)
    print("📊 CIO Momentum Dashboard Generator")
    print("=" * 60)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "mapping.csv")

    tickers, sector_map, country_map, name_map, highvol_map, category_map, regions_map = load_etf_universe(csv_path)

    prices = fetch_data(tickers)
    if prices is None:
        print("❌ Aborting: price fetch failed. Not overwriting public/data.json.")
        sys.exit(1)

    print("\n📈 Calculating metrics...")
    etf_data = []
    dropped = []
    for ticker in tickers:
        if ticker not in prices.columns:
            dropped.append((ticker, "no price column"))
            continue
        metrics = calculate_metrics(prices[ticker], ticker, sector_map, country_map, name_map, category_map, regions_map)
        if metrics:
            etf_data.append(metrics)
            etf_label = "ETF" if metrics['isETF'] else "EQ"
            print(f"  ✓ {ticker} [{etf_label}]: {metrics['return6m']:+.1f}% | Sortino: {metrics['sortino']:.2f} | Z: {metrics['zScore']:.2f}")
        else:
            dropped.append((ticker, "calculate_metrics returned None"))

    print(f"\n✓ Processed {len(etf_data)} symbols, dropped {len(dropped)}")
    if dropped:
        print("   Dropped tickers:")
        for ticker, reason in dropped:
            print(f"     • {ticker}: {reason}")

    drop_rate = len(dropped) / len(tickers) if tickers else 0
    if drop_rate > MAX_DROP_RATE:
        print(
            f"❌ Aborting: drop rate {drop_rate:.0%} exceeds threshold {MAX_DROP_RATE:.0%}. "
            f"Refusing to overwrite public/data.json with a thinned-out dataset."
        )
        sys.exit(1)

    valid_tickers = [e['ticker'] for e in etf_data]
    correlations = calculate_correlations(prices, valid_tickers)
    print(f"✓ Calculated {len(correlations)} pairwise correlations")

    generation_date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    payload = generate_data(etf_data, correlations, generation_date)

    public_dir = os.path.join(script_dir, "public")
    os.makedirs(public_dir, exist_ok=True)
    output_file = os.path.join(public_dir, "data.json")
    with open(output_file, 'w') as f:
        json.dump(payload, f, indent=2)

    print(f"\n✅ Data snapshot saved to: {output_file}")
    print(f"   Run `npm run dev` (or `npm run build`) to view in the Vite app.")
    print("=" * 60)


if __name__ == "__main__":
    main()
