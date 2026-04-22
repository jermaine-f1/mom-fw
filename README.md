# CIO Momentum Dashboard

A momentum investing dashboard for building diversified, quality momentum-based
portfolios. A Python job fetches live ETF/equity data from Yahoo Finance and
writes a JSON snapshot (`public/data.json`) that a Vite + React app renders in
the browser.

## Architecture

- **`mom_gen.py`** — Python data pipeline. Loads `mapping.csv`, pulls prices
  from Yahoo Finance, computes momentum metrics + pairwise correlations, and
  writes `public/data.json`. Scheduled daily by `.github/workflows/daily-mom-gen.yml`.
- **`src/`** — Vite + React + TypeScript dashboard (Tailwind CSS). Fetches
  `/data.json` at runtime. The Screener tab is ported; Portfolio, Analyzer,
  CIO Signals, Strategy, and Settings tabs are stubs pending further migration
  from the legacy HTML.
- **`api/portfolios.js`** — Vercel serverless function backed by Vercel Blob.
  Unchanged.

## Overview

This tool implements a **Quality Momentum** strategy that goes beyond simple price returns. It ranks instruments using a composite score that balances:

- **Sortino Ratio** (40%) — Risk-adjusted returns focusing on downside volatility
- **Weeks Down** (25%) — Trend weakening detection over 12-week window
- **Z-Score Penalty** (20%) — Bubble/extension detection relative to 200-day MA
- **Slope** (15%) — Trend strength and consistency via linear regression

## Features

- **Live Data** — Fetches real-time prices from Yahoo Finance for 160+ instruments
- **Quality Scoring** — Multi-factor ranking beyond raw momentum
- **Correlation Filtering** — Builds diversified portfolios with low pairwise correlation
- **Configurable Rules** — Adjust weights, thresholds, and filters in the dashboard
- **Responsive UI** — Dark-themed dashboard that works on desktop and mobile
- **CSV Input** — Customize your instrument universe via `mapping.csv`
- **Automated Updates** — GitHub Actions workflow generates the dashboard daily after market close
- **Pure Return Mode** — Alternative ranking mode based purely on 6-month returns

## Installation

```bash
pip install -r requirements.txt
```

**Requirements:**
- Python 3.10+
- Internet connection for Yahoo Finance API

**Dependencies:**
- `yfinance` >= 0.2.0
- `pandas` >= 2.0.0
- `numpy` >= 1.24.0
- `scipy` >= 1.10.0

## Usage

### 1. Generate the data snapshot

Edit `mapping.csv` to customize your instrument universe (optional), then:

```bash
python mom_gen.py
```

This writes `public/data.json`.

### 2. Run the dashboard

```bash
npm install
npm run dev
```

Open the URL Vite prints (default http://localhost:5173).

### 3. Production build

```bash
npm run build    # outputs to dist/
npm run preview  # serves dist/ locally
```

Vercel handles this automatically on deploy (`vercel.json` points
`buildCommand` at `npm run build`).

## Instrument Universe (mapping.csv)

The script reads from `mapping.csv` in the same folder. Required columns:

| Column | Description | Example |
|--------|-------------|---------|
| `Name` | Full instrument name | SPDR S&P 500 |
| `Symbol` | Yahoo Finance ticker (with exchange suffix if needed) | SPY, EWJ, 2828.HK |
| `Region` | Geographic region | US, Japan, Emerging Markets |
| `Category` | Instrument type | ETF, Equity, Cash |
| `Subcategory` | Fine-grained classification | US Broad Market, Semiconductor |
| `High Vol` | High volatility flag | TRUE / FALSE |

### Example CSV

```csv
Name,Symbol,Region,Category,Subcategory,High Vol
SPDR S&P 500,SPY,US,ETF,US Broad Market,FALSE
Invesco QQQ,QQQ,US,ETF,US Tech,FALSE
iShares MSCI India ETF,INDA,Emerging Markets,ETF,ETF,TRUE
SPDR Gold Shares,GLD,Commodities,ETF,Commodities,FALSE
```

### Default Universe

The default `mapping.csv` covers 160+ instruments across:

| Category | Examples |
|----------|----------|
| US Equity | SPY, QQQ, IWM, DIA |
| Sectors | XLK, XLF, XLV, XLE, XLI |
| Semiconductors | SMH, SOXX |
| International | EFA, EEM, INDA, FXI, EWJ |
| Commodities | GLD, SLV, GDX, URA, DBC |
| Fixed Income | TLT, IEF, LQD, HYG |
| Cash | SHY |

## Strategy Rules

### BUY Signals
1. Quality Score >= 55
2. Price above MA-30 AND MA-60
3. Z-Score < 4 (not in bubble territory)
4. Low correlation to existing holdings

### SELL Signals
1. Z-Score > 4 (extreme extension)
2. Price breaks below MA-30 or MA-60
3. Weeks Down >= 8 of 12
4. Quality Score drops below 40

### Portfolio Construction
- Target 6-10 positions (configurable 4-12)
- Equal weight (no position > 15%)
- Max pairwise correlation: 0.70
- Min 3 countries, min 3 sectors
- Max 40% single country exposure

## Dashboard Tabs

| Tab | Description |
|-----|-------------|
| **Screener** | Full ranked universe with filtering, search, sorting, and top ideas highlighting |
| **Portfolio** | Constructed portfolio with correlation filtering, diversification stats, and excluded candidates |
| **Strategy** | Core principles, quality score formula, and methodology documentation |
| **Settings** | Configurable weights, thresholds, position sizing, and risk parameters |

## Metrics Explained

| Metric | Description |
|--------|-------------|
| **6M Return** | Price change over trailing 126 days |
| **Sortino** | Annualized return / downside deviation (risk-free rate: 4.5%) |
| **Weeks Down** | Negative weeks in last 12-week period |
| **Z-Score** | Current price deviation from 200-day MA (normalized) |
| **Slope** | Linear regression slope of 6-month price trend (normalized to mean) |
| **MA Status** | Whether price is above 30-day, 60-day, and 200-day moving averages |
| **Max Drawdown** | Peak-to-trough decline percentage |

## Configuration

### Instrument Universe
Edit `mapping.csv` to add/remove instruments. Each row needs:
- `Name` — Full instrument name
- `Symbol` — Valid Yahoo Finance symbol (with exchange suffix if needed, e.g. `.TO`, `.HK`)
- `Region` — Geographic region (used for diversification constraints)
- `Category` — ETF, Equity, or Cash
- `Subcategory` — Sector/theme classification (used for diversification)
- `High Vol` — TRUE/FALSE volatility flag

### Script Settings
Edit `mom_gen.py` to customize:

```python
RISK_FREE_RATE = 0.045    # For Sortino calculation (currently ~4.5%)
```

## Automation

GitHub Actions workflows automate dashboard generation:

- **Daily generation** — Runs weekdays at 4:05 PM ET (after US market close), executes `mom_gen.py`, and auto-commits the updated `index.html`
- **UI sync** — On changes to `index.html`, syncs the dashboard to the `mom-fw-ui` repository for hosting

## Output

The generated `index.html` file is self-contained with:
- Embedded Tailwind CSS via CDN
- All instrument data and correlations in JavaScript
- No external dependencies for viewing (works offline after generation)

## License

MIT

## Disclaimer

This tool is for educational and research purposes only. It does not constitute financial advice. Always do your own due diligence before making investment decisions.
